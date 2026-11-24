# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Check NVMe DMA into GPU memory mapped through iommufd PAL
=========================================================

Binds the NVMe controller at 'pci_addr' to vfio-pci and runs the PoC tools
that 'tasks/setup_pal.yaml' builds into 'tools':

* pal_probe exports a CUDA buffer as a dma-buf and maps it into an IOAS
  attached to the controller with IOMMU_IOAS_MAP_FILE.
* pal_nvme, a minimal NVMe driver on the controller's VFIO cdev, maps a CUDA
  buffer the same way. The controller then writes the buffer (C1) and reads
  it (C2), and pal_nvme compares the data through CUDA. Last, it sends the
  controller's DMA to an IOVA that is not mapped (D, D2). It runs once per
  transfer size in 'xfers'.
* xnvmeperf reads into GPU memory through xNVMe's upcie-cuda backend, which
  opens the controller itself and maps the CUDA heap with IOMMU_IOAS_MAP_FILE
  first. iommu_map_pa, which xNVMe falls back to, is unloaded meanwhile.

The check fails when the map fails, a compare does not match, D completes
without an error, xnvmeperf fails or completes no read, or, with Intel VT-d,
the kernel log gains no DMA remapping fault for the controller from D or
gains one from xnvmeperf. The controller goes back to the nvme driver
afterwards, pass or fail, and iommu_map_pa and the hugepage count are
restored. It WRITES three transfers from 'slba'.

Retargetable: True
------------------
"""

import errno
import logging as log
import re
from argparse import ArgumentParser

from iommu_overhead import parse_xnvmeperf, run_with_vfio_retry

# a full PCI address; sysfs has no path for one without its domain
PCI_ADDR = re.compile(r"^[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]$")

# In 2 MiB pages: 128 MiB, well above the 16 MiB host heap of xnvmeperf's queue
HUGEPAGES = 64

# The mode is named, as xNVMe otherwise falls back to type1 without saying so
XNVMEPERF = (
    "XNVME_UPCIE_VFIO_MODE=iommufd xnvmeperf run --be upcie-cuda"
    " --iopattern randread --qdepth 32 --iosize 4096 --runtime 5 --cpumask 0x1"
)


def add_args(parser: ArgumentParser):
    parser.add_argument("--pci_addr", type=str, required=True)
    parser.add_argument("--slba", type=int, default=0)
    parser.add_argument("--tools", type=str, required=True)
    parser.add_argument("--xfers", type=int, nargs="+", default=[65536, 4096])


def output(cijoe, cmd):
    """Run 'cmd' on the target and return its error and output"""

    err, state = cijoe.run(cmd)
    return err, state.output().strip()


def dmar_faults(cijoe, pci_addr):
    """The DMA remapping faults that VT-d has logged for the controller"""

    # Kernels name the device as bus:dev.fn, some with the domain in front
    bdf = pci_addr[5:].replace(".", "\\.")
    _, out = output(
        cijoe,
        f"dmesg | grep -cE 'DMAR: .*Request device \\[([0-9a-f]{{4}}:)?{bdf}\\]' || true",
    )
    return int(out) if out.isdigit() else 0


def bind(cijoe, sysfs, pci_addr, driver):
    """Bind the controller to 'driver', or to its default one when empty"""

    for cmd in [
        f"test ! -e {sysfs}/driver || echo {pci_addr} > {sysfs}/driver/unbind",
        f"echo '{driver}' > {sysfs}/driver_override",
        f"echo {pci_addr} > /sys/bus/pci/drivers_probe",
    ]:
        err, _ = output(cijoe, cmd)
        if err:
            return err
    return 0


def vfio_cdev(cijoe, sysfs):
    """The VFIO cdev of the controller, once udev has created it"""

    err, out = output(
        cijoe,
        f"for _ in $(seq 50); do n=$(ls {sysfs}/vfio-dev 2>/dev/null);"
        ' test -n "$n" && test -e /dev/vfio/devices/$n && break; sleep 0.1; done;'
        ' test -n "$n" && echo /dev/vfio/devices/$n',
    )
    return out if not err else None


def run_tools(cijoe, args, cdev):
    """Run pal_probe and pal_nvme on 'cdev' and return the failures"""

    failures = []

    err, out = output(cijoe, f"{args.tools}/pal_probe --vfio {cdev}")
    if err or "IOMMU_IOAS_MAP_FILE: OK" not in out:
        failures.append("pal_probe: IOMMU_IOAS_MAP_FILE did not map the dma-buf")

    for xfer in args.xfers:
        err, out = output(
            cijoe,
            f"{args.tools}/pal_nvme --vfio {cdev} --slba {args.slba} --xfer {xfer}",
        )
        if err:
            failures.append(f"pal_nvme --xfer {xfer}: exited with {err}")
        for line in ["C1 compare: MATCH", "C2 compare: MATCH"]:
            if line not in out:
                failures.append(f"pal_nvme --xfer {xfer}: no '{line}'")

    return failures


def xnvmeperf_reads(cijoe, pci_addr, vtd):
    """Run xnvmeperf on the controller and return the failures"""

    err, _ = output(cijoe, "test -e /dev/dmabuf_import")
    if err:
        return ["xnvmeperf: dmabuf_import is not loaded"]

    _, out = output(cijoe, "test ! -d /sys/module/iommu_map_pa || echo loaded")
    map_pa = out == "loaded"
    if map_pa and output(cijoe, "rmmod iommu_map_pa")[0]:
        return ["xnvmeperf: iommu_map_pa is in use and cannot be unloaded"]

    _, nr = output(cijoe, "cat /proc/sys/vm/nr_hugepages")
    _, free = output(cijoe, "awk '/^HugePages_Free:/ {print $2}' /proc/meminfo")
    try:
        if nr.isdigit() and free.isdigit() and int(free) < HUGEPAGES:
            more = int(nr) + HUGEPAGES - int(free)
            output(cijoe, f"echo {more} > /proc/sys/vm/nr_hugepages")

        faults = dmar_faults(cijoe, pci_addr)
        err, out = run_with_vfio_retry(
            cijoe, f"{XNVMEPERF} {pci_addr}", "vfio-pci", "xnvmeperf"
        )
        if err:
            return [f"xnvmeperf: exited with {err}"]
        try:
            result = parse_xnvmeperf(out)
        except ValueError:
            return ["xnvmeperf: printed no result"]

        failures = []
        if result["iops"] <= 0:
            failures.append("xnvmeperf: completed no read")
        if result["failed"] > 0:
            failures.append(f"xnvmeperf: {int(result['failed'])} reads failed")
        if vtd and dmar_faults(cijoe, pci_addr) > faults:
            failures.append("xnvmeperf: the controller's DMA left DMAR faults")
        return failures
    finally:
        if nr.isdigit():
            output(cijoe, f"echo {nr} > /proc/sys/vm/nr_hugepages")
        if map_pa:
            output(cijoe, "modprobe iommu_map_pa")


def main(args, cijoe):
    if not PCI_ADDR.match(args.pci_addr):
        log.error(f"pci_addr({args.pci_addr}) is not a full PCI address")
        return errno.EINVAL
    sysfs = f"/sys/bus/pci/devices/{args.pci_addr}"

    err, out = output(
        cijoe, f"test -x {args.tools}/pal_nvme && test -x {args.tools}/pal_probe"
    )
    if err:
        log.error(f"the PoC tools are not built in {args.tools}")
        return errno.ENOENT

    _, driver = output(
        cijoe, f"test ! -e {sysfs}/driver || basename $(readlink {sysfs}/driver)"
    )
    if driver not in ("", "nvme"):
        log.error(f"{args.pci_addr} is bound to {driver}; give it back to nvme first")
        return errno.EBUSY

    # vfio-pci takes a device only when it has the IOMMU group to itself
    err, out = output(cijoe, f"ls {sysfs}/iommu_group/devices | wc -l")
    if err or out != "1":
        log.error(f"{args.pci_addr} is not alone in its IOMMU group")
        return errno.EINVAL

    _, out = output(cijoe, "ls /sys/class/iommu | grep -c '^dmar' || true")
    vtd = out.isdigit() and int(out) > 0
    faults = dmar_faults(cijoe, args.pci_addr)

    err = bind(cijoe, sysfs, args.pci_addr, "vfio-pci")
    try:
        cdev = vfio_cdev(cijoe, sysfs) if not err else None
        if not cdev:
            log.error(f"{args.pci_addr} has no VFIO cdev after binding vfio-pci")
            return errno.ENODEV

        failures = run_tools(cijoe, args, cdev)
        if vtd and dmar_faults(cijoe, args.pci_addr) <= faults:
            failures.append("the DMA to the unmapped IOVA left no DMAR fault")
        elif not vtd:
            log.info("not Intel VT-d: the DMA remapping faults are not checked")

        failures += xnvmeperf_reads(cijoe, args.pci_addr, vtd)
    finally:
        bind(cijoe, sysfs, args.pci_addr, "")

    for failure in failures:
        log.error(failure)
    if failures:
        return errno.EIO

    log.info(
        f"PASS: {args.pci_addr} moved data to and from GPU memory through PAL,"
        " with the PoC tools and with xnvmeperf"
    )
    return 0
