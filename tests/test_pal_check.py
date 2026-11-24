#!/usr/bin/env python3
# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause
"""
pal_check against a stand-in host.

main() passes when the PoC tools map, compare and fault as they should. It
fails when pal_probe does not map the dma-buf, a compare does not match,
pal_nvme exits with an error or, with VT-d, the DMA to the unmapped IOVA
leaves no fault, and when xnvmeperf fails. It runs the tools and xnvmeperf
only with the controller on vfio-pci, and gives the controller back to the
nvme driver whatever they did.

The xnvmeperf part passes reads that all complete, and fails a run that exits
with an error, prints no result, fails a read or leaves a DMAR fault. It runs
xnvmeperf only with iommu_map_pa unloaded and dmabuf_import loaded, and puts
iommu_map_pa and the hugepage count back whatever the run did.

    python3 tests/test_pal_check.py
"""

import errno
import logging
import sys
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import pal_check  # noqa: E402

PCI_ADDR = "0000:4e:00.0"
SYSFS = f"/sys/bus/pci/devices/{PCI_ADDR}"
TOOLS = "/root/aisio/pal/upcie/experimental/iommufd_gpu_poc/build"
CDEV = "/dev/vfio/devices/vfio0"
XFERS = [65536, 4096]


def result(failed=0, iops="812345.12"):
    return (
        " Device                  CPUs          IOPS      MiB/s   Failed\n"
        f" {PCI_ADDR}               0  {iops:>12} {'3173.22':>10} {failed:>8}\n"
        "--------------------------------------------------------------------\n"
        f" {'Total:':<29} {iops:>12} {'3173.22':>10} {failed:>8}\n"
    )


class State:
    def __init__(self, text):
        self.text = text

    def output(self):
        return self.text


class Errors(logging.Handler):
    """The errors that pal_check logs"""

    def __init__(self):
        super().__init__(logging.ERROR)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


class Host:
    """The state pal_check reads and changes, and what the tools print"""

    def __init__(
        self,
        out=None,
        err=0,
        map_pa=True,
        rmmod_err=0,
        dmabuf_import=True,
        nr=0,
        free=0,
        new_faults=0,
        dmar=True,
        probe="OK iova=0x200000 length=0x40000000",
        c1="MATCH",
        c2="MATCH",
        nvme_err=0,
        d_faults=2,
    ):
        self.out = result() if out is None else out
        self.err, self.map_pa, self.rmmod_err = err, map_pa, rmmod_err
        self.dmabuf_import, self.nr, self.free = dmabuf_import, nr, free
        self.new_faults, self.faults = new_faults, 3
        self.ran, self.map_pa_at_run = False, None
        self.dmar, self.probe, self.c1, self.c2 = dmar, probe, c1, c2
        self.nvme_err, self.d_faults = nvme_err, d_faults
        self.driver, self.override = "nvme", ""
        self.probed, self.xfers, self.driver_at_run = False, [], None

    def run(self, command):
        if command == "test -e /dev/dmabuf_import":
            return (0 if self.dmabuf_import else 1), State("")
        if command.startswith("test ! -d /sys/module/iommu_map_pa"):
            return 0, State("loaded\n" if self.map_pa else "")
        if command == "rmmod iommu_map_pa":
            if not self.rmmod_err:
                self.map_pa = False
            return self.rmmod_err, State("")
        if command == "modprobe iommu_map_pa":
            self.map_pa = True
            return 0, State("")
        if command == "cat /proc/sys/vm/nr_hugepages":
            return 0, State(f"{self.nr}\n")
        if command.startswith("awk '/^HugePages_Free:/"):
            return 0, State(f"{self.free}\n")
        if command.startswith("echo ") and command.endswith(
            "/proc/sys/vm/nr_hugepages"
        ):
            n = int(command.split()[1])
            self.free += n - self.nr
            self.nr = n
            return 0, State("")
        if command.startswith("dmesg"):
            return 0, State(f"{self.faults}\n")
        if command.startswith("XNVME_UPCIE_VFIO_MODE=iommufd xnvmeperf run"):
            assert command.endswith(f" {PCI_ADDR}")
            assert " --be upcie-cuda " in command, "xnvmeperf is not on GPU memory"
            assert " --iopattern randread " in command, "xnvmeperf does not only read"
            self.ran, self.map_pa_at_run = True, self.map_pa
            self.driver_at_run = self.driver
            self.free_at_run = self.free
            self.faults += self.new_faults
            return self.err, State(self.out)
        if command == f"test -x {TOOLS}/pal_nvme && test -x {TOOLS}/pal_probe":
            return 0, State("")
        if command.startswith(f"test ! -e {SYSFS}/driver || basename "):
            return 0, State(f"{self.driver}\n")
        if command == f"ls {SYSFS}/iommu_group/devices | wc -l":
            return 0, State("1\n")
        if command.startswith("ls /sys/class/iommu | grep -c '^dmar'"):
            return 0, State("1\n" if self.dmar else "0\n")
        if command.endswith(f" > {SYSFS}/driver/unbind"):
            self.driver = ""
            return 0, State("")
        if command.startswith("echo '") and command.endswith(
            f"' > {SYSFS}/driver_override"
        ):
            self.override = command.split("'")[1]
            return 0, State("")
        if command == f"echo {PCI_ADDR} > /sys/bus/pci/drivers_probe":
            # As the kernel does, probe a device only when no driver has it
            if not self.driver:
                self.driver = self.override or "nvme"
            return 0, State("")
        if command.startswith(f"for _ in $(seq 50); do n=$(ls {SYSFS}/vfio-dev "):
            if self.driver != "vfio-pci":
                return 1, State("")
            return 0, State(f"{CDEV}\n")
        if command == f"{TOOLS}/pal_probe --vfio {CDEV}":
            assert self.driver == "vfio-pci", "pal_probe ran without vfio-pci"
            self.probed = True
            return 0, State(f"IOMMU_IOAS_MAP_FILE: {self.probe}\n")
        if command.startswith(f"{TOOLS}/pal_nvme --vfio {CDEV} --slba 0 --xfer "):
            assert self.driver == "vfio-pci", "pal_nvme ran without vfio-pci"
            xfer = int(command.split()[-1])
            self.xfers.append(xfer)
            self.faults += self.d_faults
            return self.nvme_err, State(
                f"C1 compare: {self.c1} ({xfer} bytes)\n"
                f"C2 compare: {self.c2} ({xfer} bytes)\n"
            )
        raise AssertionError(f"unexpected command: {command}")


def check(name, host, vtd, want):
    loaded, nr = host.map_pa, host.nr
    failures = pal_check.xnvmeperf_reads(host, PCI_ADDR, vtd)
    assert failures == want, f"{name}: {failures} != {want}"
    if host.ran:
        assert host.map_pa_at_run is False, f"{name}: ran with iommu_map_pa loaded"
        assert host.free_at_run >= pal_check.HUGEPAGES, f"{name}: too few hugepages"
    assert host.map_pa == loaded, f"{name}: iommu_map_pa not put back"
    assert host.nr == nr, f"{name}: nr_hugepages not put back"
    print(f"ok: {name}")


def check_main(name, host, want_err, want):
    errors = Errors()
    logging.getLogger().addHandler(errors)
    try:
        args = Namespace(pci_addr=PCI_ADDR, slba=0, tools=TOOLS, xfers=XFERS)
        err = pal_check.main(args, host)
    finally:
        logging.getLogger().removeHandler(errors)
    assert err == want_err, f"main, {name}: returned {err}, not {want_err}"
    assert errors.lines == want, f"main, {name}: {errors.lines} != {want}"
    assert host.probed and host.xfers == XFERS, f"main, {name}: tools did not run"
    on_vfio = host.driver_at_run == "vfio-pci"
    assert on_vfio, f"main, {name}: xnvmeperf did not run on vfio-pci"
    back = host.driver == "nvme" and host.override == ""
    assert back, f"main, {name}: controller not given back to nvme"
    print(f"ok: main, {name}")


def main():
    check_main("pass", Host(), 0, [])
    check_main("pass without VT-d", Host(dmar=False, d_faults=0), 0, [])
    check_main(
        "no map",
        Host(probe="FAILED errno=95 (Operation not supported)"),
        errno.EIO,
        ["pal_probe: IOMMU_IOAS_MAP_FILE did not map the dma-buf"],
    )
    check_main(
        "C1 mismatch",
        Host(c1="MISMATCH"),
        errno.EIO,
        [f"pal_nvme --xfer {x}: no 'C1 compare: MATCH'" for x in XFERS],
    )
    check_main(
        "C2 mismatch",
        Host(c2="MISMATCH"),
        errno.EIO,
        [f"pal_nvme --xfer {x}: no 'C2 compare: MATCH'" for x in XFERS],
    )
    check_main(
        "pal_nvme exit error",
        Host(nvme_err=1),
        errno.EIO,
        [f"pal_nvme --xfer {x}: exited with 1" for x in XFERS],
    )
    check_main(
        "no DMAR fault",
        Host(d_faults=0),
        errno.EIO,
        ["the DMA to the unmapped IOVA left no DMAR fault"],
    )
    check_main(
        "xnvmeperf failed reads",
        Host(out=result(failed=7)),
        errno.EIO,
        ["xnvmeperf: 7 reads failed"],
    )

    check("pass", Host(), True, [])
    check("pass with hugepages free", Host(nr=512, free=512), True, [])
    check("pass with no iommu_map_pa", Host(map_pa=False), True, [])
    check("not VT-d", Host(new_faults=2), False, [])
    check(
        "exit error",
        Host(err=234, out="FAILED: xnvme_dev_open()"),
        True,
        ["xnvmeperf: exited with 234"],
    )
    check("no result", Host(out="nothing"), True, ["xnvmeperf: printed no result"])
    check(
        "failed reads",
        Host(out=result(failed=7)),
        True,
        ["xnvmeperf: 7 reads failed"],
    )
    check(
        "no reads",
        Host(out=result(iops="0.00")),
        True,
        ["xnvmeperf: completed no read"],
    )
    check(
        "DMAR fault",
        Host(new_faults=1),
        True,
        ["xnvmeperf: the controller's DMA left DMAR faults"],
    )
    host = Host(dmabuf_import=False)
    check("no dmabuf_import", host, True, ["xnvmeperf: dmabuf_import is not loaded"])
    assert not host.ran
    host = Host(rmmod_err=1)
    check(
        "iommu_map_pa held",
        host,
        True,
        ["xnvmeperf: iommu_map_pa is in use and cannot be unloaded"],
    )
    assert not host.ran


if __name__ == "__main__":
    main()
