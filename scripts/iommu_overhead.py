# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Collect uPCIe IOMMU overhead benchmark results
==============================================

Runs xnvmeperf and fio for one driver in the current boot configuration.
Benchmark parameters come from the 'iommu_overhead' config section, and the
devices from a top-level '[[devices]]' list; see configs/iommu_overhead.toml.
"""

import errno
import json
import logging as log
import re
import shlex
import time
from argparse import ArgumentParser
from pathlib import Path

from iommu_common import IOMMU_SYSFS, check_vfio_kernel, iommu_units
from xnvmeperf import xnvmeperf_cmd

FIO_PERCENTILE_LIST = "99.9:99.99:99.999"
VFIO_DEVICE_OPEN_RETRIES = 5
VFIO_DEVICE_OPEN_RETRY_DELAY = 2
# EAGAIN out of the VFIO device open, in whichever spelling the runner uses:
# fio's xNVMe ioengine prints the errno as-is, xnvmeperf prints it negated.
VFIO_DEVICE_OPEN_EAGAIN = (
    re.compile(r"failed retrieving device handle, errno: -?11\b"),
    re.compile(r"xnvme_dev_open\([^)]*\): err\(-?11\)"),
)
TAIL_LATENCIES = {
    "p99_9": "99.900000",
    "p99_99": "99.990000",
    "p99_999": "99.999000",
}
RW_TO_OP = {
    "read": "read",
    "randread": "read",
    "write": "write",
    "randwrite": "write",
}


def add_args(parser: ArgumentParser):
    parser.add_argument(
        "--driver", choices=["uio_pci_generic", "vfio-pci"], required=True
    )
    parser.add_argument("--label", choices=["uio", "vfio"], required=True)
    parser.add_argument("--memory", choices=["host", "gpu"], default="host")
    parser.add_argument("--gpu_id", type=int, default=0)


def q(value):
    return shlex.quote(str(value))


def conf(cijoe, key, default=None):
    return cijoe.getconf(f"iommu_overhead.{key}", default)


def cpu_to_cpumask(cpu):
    return hex(1 << int(cpu))


def cpus_to_cpumask(cpus):
    mask = 0
    for cpu in cpus:
        mask |= 1 << int(cpu)
    return hex(mask)


def backend_for(memory):
    """The xNVMe backend that puts data buffers where `memory` says."""
    return "upcie-cuda" if memory == "gpu" else "upcie"


def gpu_memory(args):
    return args.memory == "gpu"


def gpu_bdf_from_smi(bus_id):
    """'00000000:01:00.0' from nvidia-smi as the sysfs name '0000:01:00.0'."""
    domain, rest = bus_id.strip().lower().split(":", 1)
    return f"{domain[-4:]}:{rest}"


def warn_gpu_cross_node(args, cijoe, pci_addrs):
    """
    Warn about a device on another NUMA node than the GPU it reads into.

    Only a warning, as for CPUs. nvidia-smi numbers GPUs in PCI bus order while
    CUDA, which reads gpu_id, puts the fastest first by default, so on a machine
    with mixed GPU models this may look at the wrong GPU.
    """
    if not gpu_memory(args):
        return

    err, state = cijoe.run(
        f"nvidia-smi --query-gpu=pci.bus_id --format=csv,noheader -i {q(args.gpu_id)}"
    )
    lines = state.output().strip().splitlines()
    if err or not lines:
        return
    try:
        gpu_bdf = gpu_bdf_from_smi(lines[-1])
    except ValueError:
        return

    bdfs = [gpu_bdf, *pci_addrs]
    cmd = "; ".join(f"cat /sys/bus/pci/devices/{q(bdf)}/numa_node" for bdf in bdfs)
    err, state = cijoe.run(cmd)
    lines = state.output().strip().splitlines()[-len(bdfs) :]
    if err or len(lines) != len(bdfs):
        return
    try:
        gpu_node, *dev_nodes = (int(line) for line in lines)
    except ValueError:
        return
    if gpu_node < 0:
        return

    for pci_addr, dev_node in zip(pci_addrs, dev_nodes):
        if dev_node >= 0 and dev_node != gpu_node:
            log.warning(
                f"{pci_addr} is on NUMA node {dev_node} but GPU {args.gpu_id} "
                f"({gpu_bdf}) is on node {gpu_node}"
            )


def xnvmeperf_env(args):
    """
    Environment prefix for an xnvmeperf or fio run.

    Reaching GPU memory while an IOMMU enforces needs the iommufd path: it is
    the one that reserves the IOVA window the GPU pages are mapped into. xNVMe
    picks it only when /dev/iommu opens and the device has a cdev node, and
    falls back to the legacy type1 container without saying so, which maps the
    window without reserving it. Asking for it by name turns that silent
    fallback into a failure. Host-memory runs ask for it too, so both kinds of
    memory are measured on the same IOMMU backend.
    """
    if args.driver == "vfio-pci":
        return "XNVME_UPCIE_VFIO_MODE=iommufd "
    return ""


def bdf_safe(pci_addr):
    return str(pci_addr).replace(":", "_").replace(".", "_")


def bdf_from_fio_filename(filename):
    return str(filename).replace("\\:", ":")


def configured_devices(cijoe):
    """
    Resolve '[[devices]]' into the (pci_addr, cpu) pairs a run pins.

    A device entry may name the CPU to pin to. Without one it falls back to its
    position in the list, which only lands on the right cores when the node the
    devices sit on owns CPU ids from 0 up.
    """
    devices = cijoe.getconf("devices", [])
    if not devices:
        return []

    resolved = []
    seen = set()
    for idx, device in enumerate(devices):
        pci_addr = device.get("pci_addr")
        if not pci_addr:
            raise ValueError(f"devices[{idx}] is missing pci_addr")
        if pci_addr in seen:
            raise ValueError(f"devices[{idx}] repeats {pci_addr}")
        seen.add(pci_addr)

        try:
            cpu = int(device.get("cpu", idx))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"devices[{idx}] has a non-integer cpu: {exc}") from exc
        if cpu < 0:
            raise ValueError(f"devices[{idx}] has a negative cpu: {cpu}")

        resolved.append({"pci_addr": pci_addr, "cpu": cpu})

    by_cpu = {}
    for device in resolved:
        owner = by_cpu.setdefault(device["cpu"], device["pci_addr"])
        if owner != device["pci_addr"]:
            raise ValueError(
                f"{device['pci_addr']} and {owner} are both pinned to CPU "
                f"{device['cpu']}"
            )

    return resolved


def parse_cpu_list(text):
    """Expand a sysfs CPU list such as '0-3,8,12-15' into a set of ids."""
    cpus = set()
    for part in text.strip().split(","):
        if not part:
            continue
        if "-" in part:
            low, high = part.split("-", 1)
            cpus.update(range(int(low), int(high) + 1))
        else:
            cpus.add(int(part))
    return cpus


def check_cpu_pinning(cijoe, devices):
    """Every CPU a device is pinned to has to be online on the target."""
    err, state = cijoe.run("cat /sys/devices/system/cpu/online")
    if err:
        log.error(f"Failed reading the target's online CPUs: {state.output().strip()}")
        return err

    try:
        online = parse_cpu_list(state.output().strip().splitlines()[-1])
    except (IndexError, ValueError):
        log.error(f"Failed parsing the online CPU list: {state.output()!r}")
        return errno.EINVAL

    wanted = {device["cpu"] for device in devices}
    missing = sorted(wanted - online)
    if missing:
        log.error(f"devices pinned to CPUs the target has offline: {missing}")
        return errno.EINVAL

    warn_cross_node_pinning(cijoe, devices)
    return 0


def warn_cross_node_pinning(cijoe, devices):
    """
    Warn about a device pinned to a CPU on another NUMA node.

    Only a warning: both boots pin the same way, so the IOMMU delta stays
    comparable, and a single-node machine reports no node for its devices.
    """
    for device in devices:
        pci_addr, cpu = device["pci_addr"], device["cpu"]
        cmd = (
            f"cat /sys/bus/pci/devices/{q(pci_addr)}/numa_node; "
            f"for n in /sys/devices/system/cpu/cpu{cpu}/node*; "
            'do echo "${n##*node}"; done'
        )
        err, state = cijoe.run(cmd)
        lines = state.output().strip().splitlines()
        if err or len(lines) < 2:
            continue
        try:
            dev_node, cpu_node = int(lines[-2]), int(lines[-1])
        except ValueError:
            continue
        if dev_node >= 0 and dev_node != cpu_node:
            log.warning(
                f"{pci_addr} is on NUMA node {dev_node} but pinned to CPU {cpu} "
                f"on node {cpu_node}"
            )


def expected_iommu_enabled(driver):
    return driver == "vfio-pci"


def check_iommu_state(args, cijoe):
    """
    Refuse a run whose boot does not match the driver it measures.

    Reads sysfs rather than dmesg, which loses its head once the ring buffer
    wraps.
    """
    expected = expected_iommu_enabled(args.driver)

    present = bool(iommu_units(cijoe))
    if present != expected:
        mode = "enabled" if expected else "disabled"
        seen = "is not empty" if present else "is empty or absent"
        log.error(
            f"{args.driver} requires IOMMU {mode}, but {IOMMU_SYSFS} {seen}; "
            f"refusing to overwrite results"
        )
        return errno.EINVAL

    return 0


def workload_cases(cijoe):
    """
    Expand 'iommu_overhead.workloads' into (rw, iosize, iodepth) cases.

    Raises ValueError rather than returning an empty list: with no cases the
    benchmark runs nothing and still reports success, and the config carrying
    them has to be passed on the command line.
    """
    workloads = conf(cijoe, "workloads", [])
    if not workloads:
        raise ValueError(
            "Missing iommu_overhead.workloads in config; pass a benchmark "
            "config such as configs/iommu_overhead.toml"
        )

    cases = []
    for idx, workload in enumerate(workloads):
        try:
            rw = workload["rw"]
            iosize = int(workload["iosize"])
            iodepths = [int(iodepth) for iodepth in workload["iodepths"]]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"iommu_overhead.workloads[{idx}] is malformed: {exc}"
            ) from exc

        if not iodepths:
            raise ValueError(f"iommu_overhead.workloads[{idx}] has no iodepths")

        cases.extend((rw, iosize, iodepth) for iodepth in iodepths)

    return cases


def results_path(args):
    path = Path(args.output) / "artifacts" / "iommu-overhead" / args.label
    path.mkdir(parents=True, exist_ok=True)
    return path


def output_tail(output, lines=10):
    """The last lines of a command's output, which is where tools report why."""
    return "\n".join(output.strip().splitlines()[-lines:])


def run_command(cijoe, cmd):
    err, state = cijoe.run(cmd)
    output = state.output()
    if err:
        log.error(f"Failed command (err {err}): {cmd}\n{output_tail(output)}")
    return err, output


def transient_vfio_device_open_failure(output):
    return any(marker.search(output) for marker in VFIO_DEVICE_OPEN_EAGAIN)


def run_with_vfio_retry(cijoe, cmd, driver, what):
    """
    Run `cmd`, retrying while the VFIO device open comes back with EAGAIN.

    The group the previous workload used can still be closing when the next one
    opens it, which fails a run with nothing actually wrong. Every runner opens
    the devices the same way, so all of them go through here.
    """
    attempts = VFIO_DEVICE_OPEN_RETRIES if driver == "vfio-pci" else 1

    for attempt in range(1, attempts + 1):
        err, output = run_command(cijoe, cmd)
        if not err or not transient_vfio_device_open_failure(output):
            return err, output

        if attempt == attempts:
            if attempts > 1:
                log.error(
                    f"VFIO device open still returned EAGAIN for {what} after "
                    f"{attempts} attempts"
                )
            return err, output

        log.warning(
            f"VFIO device open returned EAGAIN; retrying {what} ({attempt}/{attempts})"
        )
        time.sleep(VFIO_DEVICE_OPEN_RETRY_DELAY)


def bind_driver(cijoe, driver, pci_addrs, mountpoint, hugepages):
    if isinstance(pci_addrs, str):
        pci_addrs = [pci_addrs]

    if driver == "vfio-pci":
        err = check_vfio_kernel(cijoe)
        if err:
            return err

    commands = [
        "set -e",
        f"modprobe {q(driver)}",
        f"umount {q(mountpoint)} || true",
        f"sysctl -w vm.nr_hugepages={q(hugepages)}",
        "mkdir -p /dev/hugepages",
        "mountpoint -q /dev/hugepages || mount -t hugetlbfs nodev /dev/hugepages",
    ]
    if driver == "vfio-pci":
        # /dev/iommu only appears once the module is in, and not every setup
        # loads it. Tolerate a kernel built without it: the run then fails
        # where the mode is asked for, naming what is missing.
        commands.append("modprobe iommufd || true")
    commands.extend(
        f"devbind --device {q(pci_addr)} --bind {q(driver)}" for pci_addr in pci_addrs
    )
    return run_command(cijoe, "\n".join(commands))[0]


def reset_driver(cijoe, pci_addrs):
    if isinstance(pci_addrs, str):
        pci_addrs = [pci_addrs]

    cmd = "\n".join(
        f"devbind --device {q(pci_addr)} --bind nvme || true" for pci_addr in pci_addrs
    )
    err, _ = run_command(cijoe, cmd)
    return err


def build_xnvmeperf_cmd(args, cijoe, devices, rw, iosize, iodepth):
    """
    One xnvmeperf run over every device.

    xnvmeperf opens each device it is given in the same process and wants a CPU
    per device, so the mask covers the CPUs the devices are pinned to. Keeping
    every device in one process is what makes the GPU-memory runs possible at
    all: the CUDA heap is per-process, and the vfio path refuses the shared-
    memory mode that would let separate processes share a controller.
    """
    return xnvmeperf_env(args) + xnvmeperf_cmd(
        "xnvmeperf",
        {
            "cpumask": cpus_to_cpumask(device["cpu"] for device in devices),
            "qdepth": iodepth,
            "iosize": iosize,
            "runtime": int(conf(cijoe, "runtime", 10)),
            "iopattern": rw,
            "backend": backend_for(args.memory),
            "gpu_id": args.gpu_id if gpu_memory(args) else None,
            "devices": [device["pci_addr"] for device in devices],
        },
    )


def fio_cmd_multi(args, cijoe, devices, rw, iosize, iodepth):
    runtime = int(conf(cijoe, "runtime", 10))
    ramp_time = int(conf(cijoe, "fio_ramp_time", 5))
    size = conf(cijoe, "fio_size", "100%")
    parts = [
        "fio",
        "--ioengine=xnvme",
        f"--xnvme_be={backend_for(args.memory)}",
        "--thread=1",
        "--direct=1",
        f"--rw={q(rw)}",
        f"--size={q(size)}",
        f"--bs={q(iosize)}",
        f"--iodepth={q(iodepth)}",
        "--time_based=1",
        f"--runtime={q(runtime)}",
        f"--ramp_time={q(ramp_time)}",
        "--norandommap=1",
        "--output-format=json",
        f"--percentile_list={FIO_PERCENTILE_LIST}",
    ]

    for idx, device in enumerate(devices):
        fio_device = str(device["pci_addr"]).replace(":", r"\:")
        parts.extend(
            [
                f"--name=dev{idx}",
                f"--filename={q(fio_device)}",
                "--xnvme_dev_nsid=1",
                "--numjobs=1",
                f"--cpus_allowed={q(device['cpu'])}",
            ]
        )

    return xnvmeperf_env(args) + " ".join(parts)


def fio_cmd(args, cijoe, pci_addr, rw, iosize, iodepth):
    runtime = int(conf(cijoe, "runtime", 10))
    ramp_time = int(conf(cijoe, "fio_ramp_time", 5))
    size = conf(cijoe, "fio_size", "100%")
    fio_device = str(pci_addr).replace(":", r"\:")
    return xnvmeperf_env(args) + " ".join(
        [
            "fio",
            "--name=aisio-iommu-overhead",
            f"--filename={q(fio_device)}",
            "--ioengine=xnvme",
            f"--xnvme_be={backend_for(args.memory)}",
            "--xnvme_dev_nsid=1",
            "--thread=1",
            "--direct=1",
            f"--rw={q(rw)}",
            f"--size={q(size)}",
            f"--bs={q(iosize)}",
            f"--iodepth={q(iodepth)}",
            "--time_based=1",
            f"--runtime={q(runtime)}",
            f"--ramp_time={q(ramp_time)}",
            "--norandommap=1",
            "--group_reporting=1",
            "--output-format=json",
            f"--percentile_list={FIO_PERCENTILE_LIST}",
            "--numjobs=1",
            "--cpus_allowed=0",
        ]
    )


def parse_xnvmeperf(output):
    match = re.search(
        r"^\s*Total:?\s+(?:[0-9,]+\s+)?(?P<iops>[0-9.]+)\s+"
        r"(?P<mibs>[0-9.]+)\s+(?P<failed>[0-9.]+)",
        output,
        re.MULTILINE,
    )
    if not match:
        raise ValueError("failed parsing xnvmeperf output")
    return {key: float(value) for key, value in match.groupdict().items()}


def parse_fio(output, rw):
    data = json.loads(output)
    job = data["jobs"][0]
    if int(job.get("error", 0)):
        raise ValueError(f"fio job failed with error {job['error']}")

    if rw not in RW_TO_OP:
        raise ValueError(f"unsupported rw={rw!r}; mixed workloads are not supported")
    stats = job[RW_TO_OP[rw]]
    percentiles = stats["clat_ns"]["percentile"]

    return {
        "iops": float(stats["iops"]),
        "mibs": float(stats.get("bw_bytes", 0)) / (1024 * 1024),
        "lat_ns": float(stats["lat_ns"]["mean"]),
        "tail_lat_ns": {
            name: float(percentiles[key]) for name, key in TAIL_LATENCIES.items()
        },
    }


def parse_fio_multi(output, rw, devices):
    data = json.loads(output)
    jobs = data.get("jobs", [])
    if len(jobs) != len(devices):
        raise ValueError(
            f"fio returned {len(jobs)} jobs for {len(devices)} configured devices"
        )

    if rw not in RW_TO_OP:
        raise ValueError(f"unsupported rw={rw!r}; mixed workloads are not supported")

    devices_by_bdf = {device["pci_addr"]: device for device in devices}
    parsed = []
    seen = set()
    for job in jobs:
        if int(job.get("error", 0)):
            raise ValueError(f"fio job failed with error {job['error']}")

        opts = job.get("job options", job.get("job_options", {}))
        filename = opts.get("filename")
        if not filename:
            raise ValueError(f"fio job missing filename: jobname={job.get('jobname')}")

        bdf = bdf_from_fio_filename(filename)
        device = devices_by_bdf.get(bdf)
        if not device:
            raise ValueError(f"fio returned unexpected device filename: {filename}")
        if bdf in seen:
            raise ValueError(f"fio returned duplicate device filename: {filename}")
        seen.add(bdf)

        stats = job[RW_TO_OP[rw]]
        percentiles = stats["clat_ns"]["percentile"]
        parsed.append(
            (
                device,
                {
                    "iops": float(stats["iops"]),
                    "mibs": float(stats.get("bw_bytes", 0)) / (1024 * 1024),
                    "lat_ns": float(stats["lat_ns"]["mean"]),
                    "tail_lat_ns": {
                        name: float(percentiles[key])
                        for name, key in TAIL_LATENCIES.items()
                    },
                },
            )
        )

    return parsed


def result_file(
    path, label, memory, runner, rw, iosize, iodepth, rep, devcount=None, dev=None
):
    suffix = (
        f"label_{label}-mem_{memory}-runner_{runner}-rw_{rw}-"
        f"iosize_{iosize}-iodepth_{iodepth}"
    )
    if devcount is not None:
        suffix += f"-devcount_{devcount}"
    if dev is not None:
        suffix += f"-dev_{bdf_safe(dev)}"
    return path / f"{suffix}-rep_{rep}.json"


def write_result(path, result):
    with path.open("x") as jfd:
        json.dump(result, jfd, indent=2)


def base_result(
    args,
    cijoe,
    runner,
    rw,
    iosize,
    iodepth,
    rep,
    cpu=0,
    devcount=None,
    dev=None,
    cpumask=None,
):
    result = {
        "label": args.label,
        "driver": args.driver,
        "iommu": "on" if args.driver == "vfio-pci" else "off",
        "memory": args.memory,
        "backend": backend_for(args.memory),
        "runner": runner,
        "rw": rw,
        "iosize": iosize,
        "iodepth": iodepth,
        "repeat": rep,
        "runtime": int(conf(cijoe, "runtime", 10)),
        "cpu": int(cpu),
        # A run spanning devices spans their CPUs, so the mask is passed in
        # rather than derived from the one CPU a per-device row belongs to.
        "cpumask": cpumask or cpu_to_cpumask(cpu),
    }
    if runner == "fio":
        result["fio_numjobs"] = 1
        result["fio_cpus_allowed"] = str(cpu)
    if gpu_memory(args):
        result["gpu_id"] = int(args.gpu_id)
    if devcount is not None:
        result["devcount"] = int(devcount)
    if dev is not None:
        result["dev"] = dev
    return result


def print_progress(done, total, action):
    print(f"{done}/{total}: {action}\033[K", end="\r", flush=True)


def xnvmeperf_pass(args, cijoe, devices, cases, repeat, out_dir, progress):
    """
    Run xnvmeperf once per case, over every device at once.

    The row it writes is already summed over the devices, since that is what
    xnvmeperf's Total line reports, so it carries devcount but no dev. The fio
    pass below also covers GPU memory: it selects the upcie-cuda backend, which
    allocates data buffers from the CUDA heap.
    """
    devcount = len(devices)
    cpumask = cpus_to_cpumask(device["cpu"] for device in devices)
    workload_pause = int(conf(cijoe, "workload_pause", 5))

    for case_idx, (rw, iosize, iodepth) in enumerate(cases, start=1):
        for rep in range(1, repeat + 1):
            path = result_file(
                out_dir,
                args.label,
                args.memory,
                "xnvmeperf",
                rw,
                iosize,
                iodepth,
                rep,
                devcount=devcount,
            )
            if path.exists():
                progress["done"] += 1
                continue

            workload = (
                f"{args.label}/{args.memory} {rw} iosize={iosize} "
                f"iodepth={iodepth} devices={devcount} rep={rep}"
            )
            print_progress(
                progress["done"], progress["total"], f"running xnvmeperf {workload}"
            )
            err, output = run_with_vfio_retry(
                cijoe,
                build_xnvmeperf_cmd(args, cijoe, devices, rw, iosize, iodepth),
                args.driver,
                f"xnvmeperf {workload}",
            )
            if err:
                return err

            result = base_result(
                args,
                cijoe,
                "xnvmeperf",
                rw,
                iosize,
                iodepth,
                rep,
                devcount=devcount,
                cpumask=cpumask,
            )
            result.update(parse_xnvmeperf(output))
            if result["failed"]:
                # An enforcing IOMMU that rejects the buffer shows up here: the
                # run reports throughput while every command failed.
                log.error(f"xnvmeperf reported failed I/O: {result}")
                return errno.EIO
            write_result(path, result)
            progress["done"] += 1

        if workload_pause > 0 and case_idx < len(cases):
            time.sleep(workload_pause)

    return 0


def run_multi(args, cijoe, devices, cases):
    mountpoint = cijoe.getconf("filesystems.dset.mountpoint", "/mnt/datasets")

    err = check_iommu_state(args, cijoe)
    if err:
        return err
    err = check_cpu_pinning(cijoe, devices)
    if err:
        return err
    warn_gpu_cross_node(args, cijoe, [device["pci_addr"] for device in devices])

    repeat = int(conf(cijoe, "repeat", 3))
    hugepages = int(conf(cijoe, "hugepages", 1024))
    workload_pause = int(conf(cijoe, "workload_pause", 5))
    out_dir = results_path(args)
    devcount = len(devices)

    err = bind_driver(
        cijoe,
        args.driver,
        [device["pci_addr"] for device in devices],
        mountpoint,
        hugepages,
    )
    if err:
        reset_driver(cijoe, [device["pci_addr"] for device in devices])
        return err

    runners = 2
    progress = {"done": 0, "total": len(cases) * repeat * runners}

    try:
        err = xnvmeperf_pass(args, cijoe, devices, cases, repeat, out_dir, progress)
        if err:
            return err

        for case_idx, (rw, iosize, iodepth) in enumerate(cases, start=1):
            for rep in range(1, repeat + 1):
                workload = (
                    f"{args.label}/{args.memory} {rw} iosize={iosize} "
                    f"iodepth={iodepth} devices={devcount} rep={rep}"
                )
                paths = {
                    device["pci_addr"]: result_file(
                        out_dir,
                        args.label,
                        args.memory,
                        "fio",
                        rw,
                        iosize,
                        iodepth,
                        rep,
                        devcount=devcount,
                        dev=device["pci_addr"],
                    )
                    for device in devices
                }
                if all(path.exists() for path in paths.values()):
                    progress["done"] += 1
                    continue
                if any(path.exists() for path in paths.values()):
                    log.error(f"partial fio result set exists for {workload}")
                    return errno.EEXIST

                print_progress(
                    progress["done"], progress["total"], f"running fio {workload}"
                )
                err, output = run_with_vfio_retry(
                    cijoe,
                    fio_cmd_multi(args, cijoe, devices, rw, iosize, iodepth),
                    args.driver,
                    f"fio {workload}",
                )
                if err:
                    return err

                for device, parsed in parse_fio_multi(output, rw, devices):
                    result = base_result(
                        args,
                        cijoe,
                        "fio",
                        rw,
                        iosize,
                        iodepth,
                        rep,
                        cpu=device["cpu"],
                        devcount=devcount,
                        dev=device["pci_addr"],
                    )
                    result.update(parsed)
                    write_result(paths[device["pci_addr"]], result)
                progress["done"] += 1

            if workload_pause > 0 and case_idx < len(cases):
                time.sleep(workload_pause)

        print(f"{progress['done']}/{progress['total']}: complete")
    finally:
        reset_driver(cijoe, [device["pci_addr"] for device in devices])

    return 0


def main(args, cijoe):
    # fio's xNVMe engine has no option that reaches xnvme_opts.gpu_id, so fio
    # would measure GPU 0 while xnvmeperf measured the one asked for.
    if gpu_memory(args) and args.gpu_id != 0:
        log.error(f"gpu_id {args.gpu_id} is not supported: fio always uses GPU 0")
        return errno.EINVAL

    try:
        devices = configured_devices(cijoe)
        cases = workload_cases(cijoe)
    except ValueError as exc:
        log.error(str(exc))
        return errno.EINVAL

    if devices:
        return run_multi(args, cijoe, devices, cases)

    pci_addr = cijoe.getconf("filesystems.dset.pci_addr", None)
    mountpoint = cijoe.getconf("filesystems.dset.mountpoint", "/mnt/datasets")
    if not pci_addr:
        log.error("Missing filesystems.dset.pci_addr in config")
        return errno.EINVAL

    err = check_iommu_state(args, cijoe)
    if err:
        return err
    warn_gpu_cross_node(args, cijoe, [pci_addr])

    repeat = int(conf(cijoe, "repeat", 3))
    hugepages = int(conf(cijoe, "hugepages", 1024))
    workload_pause = int(conf(cijoe, "workload_pause", 5))
    out_dir = results_path(args)

    err = bind_driver(cijoe, args.driver, pci_addr, mountpoint, hugepages)
    if err:
        reset_driver(cijoe, pci_addr)
        return err

    runners = 2
    progress = {"done": 0, "total": len(cases) * repeat * runners}
    single = [{"pci_addr": pci_addr, "cpu": 0}]

    try:
        err = xnvmeperf_pass(args, cijoe, single, cases, repeat, out_dir, progress)
        if err:
            return err

        for case_idx, (rw, iosize, iodepth) in enumerate(cases, start=1):
            for rep in range(1, repeat + 1):
                workload = (
                    f"{args.label}/{args.memory} {rw} iosize={iosize} "
                    f"iodepth={iodepth} rep={rep}"
                )
                path = result_file(
                    out_dir, args.label, args.memory, "fio", rw, iosize, iodepth, rep
                )

                if path.exists():
                    progress["done"] += 1
                    continue

                print_progress(
                    progress["done"], progress["total"], f"running fio {workload}"
                )
                err, output = run_with_vfio_retry(
                    cijoe,
                    fio_cmd(args, cijoe, pci_addr, rw, iosize, iodepth),
                    args.driver,
                    f"fio {workload}",
                )
                if err:
                    return err
                result = base_result(args, cijoe, "fio", rw, iosize, iodepth, rep)
                result.update(parse_fio(output, rw))
                write_result(path, result)
                progress["done"] += 1

            if workload_pause > 0 and case_idx < len(cases):
                time.sleep(workload_pause)

        print(f"{progress['done']}/{progress['total']}: complete")
    finally:
        reset_driver(cijoe, pci_addr)

    return 0
