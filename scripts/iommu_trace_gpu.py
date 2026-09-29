# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Trace how the kernel maps a GPU dma-buf for an NVMe
===================================================

Runs the dma-buf probe once with ``--bdf`` while recording the ``iommu:map``
and ``iommu:unmap`` tracepoints, plus a kprobe on the IOMMU driver's
``map_pages`` domain op. The tracepoints give the size of each ``iommu_map``
call. The kprobe gives the page size and count the kernel split that call
into. The op is ``intel_iommu_map_pages`` or ``amd_iommu_map_pages`` up to
Linux 6.18, and a ``pt_iommu_*_map_pages`` of the generic page table after
that. All take the same arguments, so the script puts the kprobe on each of
them that the running kernel has.

The console shows the probe output, the map and unmap events of 2 MiB or more,
and findings on the probe's ``--bdf`` mapping. The findings first check the
kprobe records against the tracepoint and the probe output, and fail the task
when they disagree, since a kernel whose argument slots moved would otherwise
print plausible but wrong numbers. They then name the page size the mapping
ended up with and what capped it: how the IOVA and physical address line up,
the size of the call, or the pages the domain offers. The full trace is saved
to ``artifacts/iommu-trace-gpu/trace.txt``.

Before tracing, the script stops with a reason when the trace could not show
the mapping: no IOMMU on the target, the NVMe in an identity (passthrough)
domain, or the NVMe not bound to nvme. It traces in a tracefs instance of its
own and removes the instance and its kprobes afterward, so the global tracing
state and any trace someone else is taking are left alone. On a kernel with
none of the ``map_pages`` symbols, only the findings are missing.
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

# Events below 2 MiB are the CUDA context's own system-memory traffic, not the
# GPU window. They stay in trace.txt.
SUPERPAGE_BYTES = 2 << 20

# The map_pages domain op of each Intel and AMD page-table format. A kernel
# has the first two (up to 6.18) or the last three, never a wrapper and the
# op it calls, so a call is not recorded twice.
MAP_PAGES = {
    "intel": "intel_iommu_map_pages",
    "amd": "amd_iommu_map_pages",
    "vtdss": "pt_iommu_vtdss_map_pages",
    "x86_64": "pt_iommu_x86_64_map_pages",
    "amdv1": "pt_iommu_amdv1_map_pages",
}
# Names get a per-run suffix, so two runs on one target do not collide.
KPROBES = {
    f"aisio_imp_{fmt}": (
        f"{symbol} iova=$arg2:x64 paddr=$arg3:x64 pgsize=$arg4:u64 pgcount=$arg5:u64"
    )
    for fmt, symbol in MAP_PAGES.items()
}
# Every trace line starts with "<comm>-<pid> [cpu]". IOVA ranges are per
# domain, so records are matched to the probe's process, not only by IOVA.
TASK_PID = re.compile(r"^\s*.+?-(\d+)\s+\[")
IMP_LINE = re.compile(
    r"\baisio_imp_\w+:.*\biova=0x([0-9a-f]+) paddr=0x([0-9a-f]+) "
    r"pgsize=(\d+) pgcount=(\d+)"
)
MAP_LINE = re.compile(
    r": map: IOMMU: iova=0x([0-9a-f]+) - 0x[0-9a-f]+ paddr=0x([0-9a-f]+) size=(\d+)"
)
BDF_IOVA = re.compile(r"== PCI device.*?dma_addr 0x([0-9a-f]+) len (\d+)", re.S)
MISC_PADDR = re.compile(r"== misc device.*?dma_addr 0x([0-9a-f]+)", re.S)

# IOMMU pages are powers of two from 4 KiB. Which sizes a domain offers above
# that depends on the IOMMU and its page-table format, and is not traced.
SMALLEST_PAGE = 4 << 10


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
    """The largest power of two that addr is a multiple of (0 has no limit)."""
    return addr & -addr if addr else 1 << 64


def largest_fit(iova, nbytes):
    """The largest page whose aligned block fits in [iova, iova + nbytes)."""
    page = SMALLEST_PAGE
    while -(-iova // (2 * page)) * (2 * page) + 2 * page <= iova + nbytes:
        page *= 2
    return page


def records(trace, iova, nbytes):
    """Collect the probe's records for the mapping at [iova, iova + nbytes).

    Returns (map_event, calls). map_event is the (iova, paddr, size) of the
    iommu:map tracepoint at iova, or None. calls are the map_pages
    (iova, paddr, pgsize, pgcount) inside the range. Both come only from the
    process that made the first call at iova, because IOVA ranges repeat
    across domains.
    """
    lines = trace.splitlines()

    # IOVA ranges repeat across domains, so first pick the process that made
    # the call at this IOVA, then take every record from that process alone.
    pid = None
    for line in lines:
        task = TASK_PID.match(line)
        imp = IMP_LINE.search(line)
        if imp and task and int(imp.group(1), 16) == iova:
            pid = task.group(1)
            break

    map_event = None
    calls = []
    for line in lines:
        task = TASK_PID.match(line)
        if not task or task.group(1) != pid:
            continue
        tp = MAP_LINE.search(line)
        if tp and int(tp.group(1), 16) == iova and map_event is None:
            map_event = tuple(int(g, 16) for g in tp.groups()[:2]) + (int(tp.group(3)),)
        imp = IMP_LINE.search(line)
        if not imp:
            continue
        call = (int(imp.group(1), 16), int(imp.group(2), 16))
        call += (int(imp.group(3)), int(imp.group(4)))
        if iova <= call[0] < iova + nbytes:
            calls.append(call)

    return map_event, sorted(calls)


def check_records(iova, nbytes, misc_paddr, map_event, calls):
    """Cross-check the kprobe records against the other observers.

    Returns a list of (ok, line). Every observer saw the same mapping only if
    all are ok. A kernel whose argument slots moved fails here.
    """
    checks = []

    def check(ok, text):
        checks.append((ok, f"{'ok  ' if ok else 'FAIL'} {text}"))

    check(map_event is not None, f"iommu:map has a call at the probe's IOVA 0x{iova:x}")
    check(bool(calls), f"map_pages has calls at IOVA 0x{iova:x}")
    if map_event is None or not calls:
        return checks

    sizes = sorted({pgsize for _, _, pgsize, _ in calls})
    check(
        all(
            pgsize >= SMALLEST_PAGE
            and alignment(pgsize) == pgsize
            and alignment(call_iova | call_paddr) >= pgsize
            for call_iova, call_paddr, pgsize, _ in calls
        ),
        f"page sizes {[fmt_size(s) for s in sizes]} are powers of two of at least "
        f"{fmt_size(SMALLEST_PAGE)}, and each call's addresses are aligned to its "
        "page size",
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
    # needs a P-aligned block of P to fit inside the range. Less aligned start
    # addresses only add smaller pages up to the first such spot.
    paddr = calls[0][1]
    lines_up = alignment(abs(iova - paddr))
    fits = largest_fit(iova, nbytes)
    allowed = min(lines_up, fits)

    lines = [f"mapping: {fmt_size(nbytes)} as {split}"]
    if largest < allowed:
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
            reasons.append(f"no aligned {fmt_size(2 * allowed)} page fits in the range")
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
    if iova == misc_paddr:
        return False, [
            f"FAIL the --bdf import is not translated: it got the physical address "
            f"0x{iova:x}, so no iommu_map backs it"
        ]

    map_event, calls = records(trace, iova, nbytes)
    checks = check_records(iova, nbytes, misc_paddr, map_event, calls)
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
        err, _ = cijoe.run(
            f"echo 'p:kprobes/{name} {spec}' >> {TRACE_DIR}/kprobe_events"
        )
        if err:
            # Expected for the symbols of the other vendor or kernel version.
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
    if kprobes:
        findings_ok, lines = mapping_findings(trace, probe_out)
        print("== findings: --bdf mapping ==")
        print("\n".join(lines))
    else:
        log.warning(
            f"none of {sorted(MAP_PAGES.values())} resolves on this kernel; "
            "no findings on the mapping"
        )

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
