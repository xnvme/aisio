# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Trace how the kernel maps a GPU dma-buf for an NVMe
===================================================

Runs the dma-buf probe once with ``--bdf`` while recording the ``iommu:map``
and ``iommu:unmap`` tracepoints, plus kprobes on ``intel_iommu_map_pages`` and
``pfn_to_dma_pte``. The tracepoints give the size of each ``iommu_map`` call.
The kprobes give the page size and count the kernel split that call into, and
the page-table level the Intel driver wrote.

The console shows the probe output, the map and unmap events of 2 MiB or more,
and findings on the probe's ``--bdf`` mapping. The findings first check the
kprobe records against the tracepoint and the probe output, and fail the task
when they disagree, since a kernel whose argument slots moved would otherwise
print plausible but wrong numbers. They then name the page size the mapping
ended up with and what capped it: the IOVA alignment, the physical address
alignment, the size of the call, or the pages the domain offers. The full
trace is saved to ``artifacts/iommu-trace-gpu/trace.txt``.

Before tracing, the script stops with a reason when the trace could not show
the mapping: no IOMMU on the target, the NVMe in an identity (passthrough)
domain, or the NVMe not bound to nvme. It traces in a tracefs instance of its
own and removes the instance and its kprobes afterward, so the global tracing
state and any trace someone else is taking are left alone. The kprobe symbols
are Linux 6.8's. Where they do not resolve, only the findings are missing.
"""

import errno
import logging as log
import re
from argparse import ArgumentParser
from pathlib import Path

from dmabuf_import_probe import cleanup_probe, stage_probe

TRACE_DIR = "/sys/kernel/debug/tracing"
IOMMU_SYSFS = "/sys/class/iommu"
BDF_FORMAT = re.compile(r"^[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]$")
PROBE_TIMEOUT_S = 300
SIZE_LINE = re.compile(r"\bsize=(\d+)")

# Smallest Intel VT-d superpage. Anything below is the CUDA context's own
# system-memory traffic, not the GPU window. It stays in trace.txt.
SUPERPAGE_BYTES = 2 << 20

# Names get a per-run suffix, so two runs on one target do not collide.
KPROBES = {
    "aisio_imp": (
        "intel_iommu_map_pages "
        "iova=$arg2:x64 paddr=$arg3:x64 pgsize=$arg4:u64 pgcount=$arg5:u64"
    ),
    # The level (1=4K, 2=2M, 3=1G) is passed by pointer.
    "aisio_pte": "pfn_to_dma_pte iov_pfn=$arg2:x64 level=+0($arg3):s32",
}
# Every trace line starts with "<comm>-<pid> [cpu]". IOVA ranges are per
# domain, so pte lines are matched to the probe's process, not only by IOVA.
TASK_PID = re.compile(r"^\s*.+?-(\d+)\s+\[")
IMP_LINE = re.compile(
    r"\baisio_imp_\w+:.*\biova=0x([0-9a-f]+) paddr=0x([0-9a-f]+) "
    r"pgsize=(\d+) pgcount=(\d+)"
)
PTE_LINE = re.compile(r"\baisio_pte_\w+:.*\biov_pfn=0x([0-9a-f]+) level=(-?\d+)")
MAP_LINE = re.compile(
    r": map: IOMMU: iova=0x([0-9a-f]+) - 0x[0-9a-f]+ paddr=0x([0-9a-f]+) size=(\d+)"
)
BDF_IOVA = re.compile(r"== PCI device.*?dma_addr 0x([0-9a-f]+) len (\d+)", re.S)
MISC_PADDR = re.compile(r"== misc device.*?dma_addr 0x([0-9a-f]+)", re.S)

# VT-d page sizes and the page-table level each is written at.
PAGE_LEVEL = {4 << 10: 1, 2 << 20: 2, 1 << 30: 3}
LARGEST_PAGE = 1 << 30


def add_args(parser: ArgumentParser):
    parser.add_argument(
        "--bdf",
        type=str,
        required=True,
        help="NVMe PCI address to import on behalf of, e.g. 0000:4d:00.0",
    )
    parser.add_argument(
        "--size_mib",
        type=int,
        default=1024,
        help="CUDA buffer size in MiB to probe (default: 1024)",
    )
    parser.add_argument(
        "--gpu_id",
        type=int,
        default=0,
        help="CUDA device ordinal to allocate from (default: 0)",
    )


def artifacts_path(args):
    path = Path(args.output) / "artifacts" / "iommu-trace-gpu"
    path.mkdir(parents=True, exist_ok=True)
    return path


def superpage_lines(trace):
    """Keep only map/unmap lines whose size field is at least one superpage."""
    kept = []
    for line in trace.splitlines():
        if ": map:" not in line and ": unmap:" not in line:
            continue
        match = SIZE_LINE.search(line)
        if match and int(match.group(1)) >= SUPERPAGE_BYTES:
            kept.append(line)
    return "\n".join(kept)


def fmt_size(nbytes):
    for unit, shift in (("GiB", 30), ("MiB", 20), ("KiB", 10)):
        if nbytes >= 1 << shift and nbytes % (1 << shift) == 0:
            return f"{nbytes >> shift} {unit}"
    return f"{nbytes} B"


def alignment(addr):
    """The largest power of two that addr is a multiple of."""
    return addr & -addr if addr else LARGEST_PAGE


def records(trace, iova, nbytes):
    """Collect the probe's records for the mapping at [iova, iova + nbytes).

    Returns (map_event, calls, levels). map_event is the (iova, paddr, size)
    of the iommu:map tracepoint at iova, or None. calls are the
    intel_iommu_map_pages (iova, paddr, pgsize, pgcount) inside the range,
    and levels the pfn_to_dma_pte levels there, both taken only from the
    process that made the first call, because IOVA ranges repeat across
    domains.
    """
    map_event = None
    pid = None
    calls = []
    for line in trace.splitlines():
        task = TASK_PID.match(line)
        tp = MAP_LINE.search(line)
        if tp and int(tp.group(1), 16) == iova and map_event is None:
            map_event = tuple(int(g, 16) for g in tp.groups()[:2]) + (int(tp.group(3)),)
        imp = IMP_LINE.search(line)
        if not imp or not task:
            continue
        call = (int(imp.group(1), 16), int(imp.group(2), 16))
        call += (int(imp.group(3)), int(imp.group(4)))
        if call[0] == iova and pid is None:
            pid = task.group(1)
        if pid == task.group(1) and iova <= call[0] < iova + nbytes:
            calls.append(call)

    levels = set()
    lo, hi = iova >> 12, (iova + nbytes) >> 12
    for line in trace.splitlines():
        pte = PTE_LINE.search(line)
        task = TASK_PID.match(line)
        if not pte or not task or task.group(1) != pid:
            continue
        # Level 0 is a lookup of an existing entry (unmap, iova_to_phys),
        # not a choice of page size.
        if lo <= int(pte.group(1), 16) < hi and int(pte.group(2)) > 0:
            levels.add(int(pte.group(2)))

    return map_event, sorted(calls), levels


def check_records(iova, nbytes, misc_paddr, map_event, calls, levels):
    """Cross-check the kprobe records against the other observers.

    Returns a list of (ok, line). Every observer saw the same mapping only if
    all are ok. A kernel whose argument slots moved fails here.
    """
    checks = []

    def check(ok, text):
        checks.append((ok, f"{'ok  ' if ok else 'FAIL'} {text}"))

    check(map_event is not None, f"iommu:map has a call at the probe's IOVA 0x{iova:x}")
    check(bool(calls), f"intel_iommu_map_pages has calls at IOVA 0x{iova:x}")
    if map_event is None or not calls:
        return checks

    sizes = sorted({pgsize for _, _, pgsize, _ in calls})
    check(
        all(pgsize in PAGE_LEVEL for pgsize in sizes),
        f"page sizes {[fmt_size(s) for s in sizes]} are VT-d page sizes",
    )

    covered = sum(pgsize * count for _, _, pgsize, count in calls)
    check(
        covered == map_event[2] == nbytes,
        f"pages cover the call: {fmt_size(covered)} in pages, "
        f"{fmt_size(map_event[2])} in iommu:map, {fmt_size(nbytes)} from the probe",
    )

    contiguous = all(
        nxt[0] == cur[0] + cur[2] * cur[3] and nxt[1] - nxt[0] == cur[1] - cur[0]
        for cur, nxt in zip(calls, calls[1:])
    )
    check(contiguous, "the calls follow each other in IOVA and physical address")

    paddr = calls[0][1]
    same_paddr = paddr == map_event[1] and misc_paddr in (None, paddr)
    check(
        same_paddr,
        f"physical address 0x{paddr:x} matches iommu:map 0x{map_event[1]:x}"
        + (f" and the probe's misc import 0x{misc_paddr:x}" if misc_paddr else ""),
    )

    expected = {PAGE_LEVEL.get(pgsize, -1) for _, _, pgsize, _ in calls}
    check(
        expected == levels,
        f"page-table levels {sorted(levels)} match the page sizes "
        f"(expected {sorted(expected)})",
    )
    return checks


def verdict(iova, nbytes, calls):
    """Name the page size the mapping got and what capped it."""
    sizes = {}
    for _, _, pgsize, count in calls:
        sizes[pgsize] = sizes.get(pgsize, 0) + count
    split = " + ".join(f"{count} x {fmt_size(s)}" for s, count in sorted(sizes.items()))
    largest = max(sizes)

    # A page of size P needs IOVA and physical address both P-aligned at the
    # same spot, which happens only if they differ by a multiple of P, and it
    # needs a P-aligned block of P to fit inside the range.
    paddr = calls[0][1]
    lines_up = min(alignment(abs(iova - paddr)), LARGEST_PAGE)
    fits = max(
        (p for p in PAGE_LEVEL if -(-iova // p) * p + p <= iova + nbytes),
        default=min(PAGE_LEVEL),
    )
    allowed = max(
        (p for p in PAGE_LEVEL if p <= min(lines_up, fits)), default=min(PAGE_LEVEL)
    )

    lines = [f"mapping: {fmt_size(nbytes)} as {split}"]
    if largest == LARGEST_PAGE:
        lines.append(f"page size: {fmt_size(largest)}, the largest VT-d page")
    elif largest < allowed:
        lines.append(
            f"page size: {fmt_size(largest)}, although the addresses and the size "
            f"allowed {fmt_size(allowed)}: the IOMMU or this domain offers no larger "
            "page"
        )
    else:
        reasons = []
        if lines_up == allowed:
            reasons.append(
                f"IOVA 0x{iova:x} ({fmt_size(alignment(iova))}-aligned) and physical "
                f"0x{paddr:x} ({fmt_size(alignment(paddr))}-aligned) line up only on "
                f"{fmt_size(lines_up)} boundaries"
            )
        if fits == allowed:
            bigger = min(p for p in PAGE_LEVEL if p > allowed)
            reasons.append(f"no aligned {fmt_size(bigger)} page fits in the range")
        lines.append(
            f"page size: {fmt_size(largest)}, capped because " + ", and ".join(reasons)
        )
    lines.append(f"translations to cover the buffer: {sum(sizes.values())}")
    return lines


def mapping_findings(trace, probe_out):
    """Check the records and report findings on the probe's --bdf mapping.

    Returns (ok, lines). ok is False when the probe output has no --bdf
    segment or the records disagree, and the lines say why.
    """
    match = BDF_IOVA.search(probe_out)
    if not match:
        return False, ["FAIL no --bdf segment in the probe output"]
    iova, nbytes = int(match.group(1), 16), int(match.group(2))
    misc = MISC_PADDR.search(probe_out)
    misc_paddr = int(misc.group(1), 16) if misc else None

    map_event, calls, levels = records(trace, iova, nbytes)
    checks = check_records(iova, nbytes, misc_paddr, map_event, calls, levels)
    lines = [line for _, line in checks]
    if not all(ok for ok, _ in checks):
        return False, lines
    return True, lines + verdict(iova, nbytes, calls)


def check_target(cijoe, bdf):
    """Stop early on a target where the trace could not show the mapping.

    Returns 0, or an errno after logging why. Without an IOMMU, or with the
    NVMe in an identity (passthrough) domain, no iommu_map happens and an
    empty trace would read like "no mappings". An NVMe bound to vfio or uio
    makes the probe fail for a reason that is not about the IOMMU.
    """
    if not BDF_FORMAT.match(bdf):
        log.error(f"bdf '{bdf}' is not in the form 0000:4d:00.0 (lowercase hex)")
        return errno.EINVAL

    err, state = cijoe.run(f"ls -A {IOMMU_SYSFS}")
    if err or not state.output().strip():
        log.error(f"no IOMMU on the target ({IOMMU_SYSFS} is empty); nothing to trace")
        return errno.ENODEV

    dev = f"/sys/bus/pci/devices/{bdf}"
    err, state = cijoe.run(f"cat {dev}/iommu_group/type")
    group_type = state.output().strip()
    if err or not group_type:
        log.error(f"{bdf} is in no IOMMU group; check the address")
        return errno.ENODEV
    if group_type == "identity":
        log.error(
            f"{bdf} is in an identity (passthrough) domain; boot without iommu=pt"
        )
        return errno.EINVAL

    err, state = cijoe.run(f"readlink {dev}/driver")
    if err or not state.output().strip():
        log.error(f"{bdf} is bound to no driver; bind it to nvme before tracing")
        return errno.EBUSY
    driver = Path(state.output().strip()).name
    if driver != "nvme":
        log.error(f"{bdf} is bound to '{driver}', not nvme; rebind it before tracing")
        return errno.EBUSY

    return 0


def main(args, cijoe):
    err = check_target(cijoe, args.bdf)
    if err:
        return err

    # Best-effort for a target that never mounted tracefs. Creating the
    # instance below is what decides whether tracing is usable.
    cijoe.run(f"mountpoint -q {TRACE_DIR} || mount -t tracefs nodev {TRACE_DIR}")

    err, workdir, binary = stage_probe(cijoe)
    if err:
        return err

    # The work directory's mktemp suffix names this run's instance and kprobes.
    tag = workdir.rsplit(".", 1)[-1]
    instance = f"{TRACE_DIR}/instances/aisio-iommu-trace-{tag}"
    kprobes = []
    try:
        err, state = cijoe.run(f"mkdir {instance}")
        if err:
            log.error(f"cannot create tracefs instance {instance}: {state.output()}")
            return errno.EIO
        err = trace_probe(args, cijoe, binary, instance, tag, kprobes)
    finally:
        # The instance holds the only enable of these kprobes, so they can be
        # removed once it is gone.
        cijoe.run(f"rmdir {instance}")
        for name in kprobes:
            cijoe.run(f"echo '-:kprobes/{name}' >> {TRACE_DIR}/kprobe_events")
        cleanup_probe(cijoe, workdir)
    return err


def trace_probe(args, cijoe, binary, instance, tag, kprobes):
    """Trace one --bdf run of the probe. Registered kprobes go into kprobes."""
    for cmd in [
        f"echo 8192 > {instance}/buffer_size_kb",
        f"echo 'iommu:map' > {instance}/set_event",
        f"echo 'iommu:unmap' >> {instance}/set_event",
    ]:
        err, state = cijoe.run(cmd)
        if err:
            # An unusable instance still lets the probe run and returns an
            # empty trace, which reads exactly like "no mappings happened".
            log.error(f"trace setup failed ({cmd}): {state.output()}")
            return err

    for base, spec in KPROBES.items():
        name = f"{base}_{tag}"
        err, state = cijoe.run(
            f"echo 'p:kprobes/{name} {spec}' >> {TRACE_DIR}/kprobe_events"
        )
        if err:
            log.warning(f"kprobe {name} not registered: {state.output().strip()}")
            continue
        kprobes.append(name)
        cijoe.run(f"echo 'kprobes:{name}' >> {instance}/set_event")

    cijoe.run(f"echo 1 > {instance}/tracing_on")

    # The timeout keeps a stuck CUDA call or ioctl from holding the kprobes.
    run_cmd = (
        f"timeout {PROBE_TIMEOUT_S} {binary} --size_mib {args.size_mib} "
        f"--gpu_id {args.gpu_id} --bdf {args.bdf}"
    )
    probe_err, state = cijoe.run(run_cmd)
    probe_out = state.output()

    cijoe.run(f"echo 0 > {instance}/tracing_on")
    trace_err, state = cijoe.run(f"cat {instance}/trace")
    trace = state.output()

    path = artifacts_path(args)
    (path / "probe.out").write_text(probe_out)
    (path / "trace.txt").write_text(trace)

    print("== probe ==")
    print(probe_out)
    print("== trace (superpage-sized) ==")
    print(superpage_lines(trace))
    findings_ok = True
    if len(kprobes) == len(KPROBES):
        findings_ok, lines = mapping_findings(trace, probe_out)
        print("== findings: --bdf mapping ==")
        print("\n".join(lines))
    else:
        log.warning("kprobes missing on this kernel; no findings on the mapping")

    if probe_err == 124:
        log.error(f"Probe did not finish within {PROBE_TIMEOUT_S} s")
        return errno.ETIMEDOUT

    if probe_err:
        log.error(f"Probe failed with err({probe_err})")
        return probe_err

    if trace_err:
        log.error(f"failed reading trace: err({trace_err})")
        return trace_err

    if not findings_ok:
        log.error("the kprobe records disagree with the other observers")
        return errno.EBADMSG

    return 0
