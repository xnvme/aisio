# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Probe how a CUDA dma-buf is imported for an NVMe
================================================

The probe allocates one large CUDA device-memory buffer, exports it as a
dma-buf, imports it through uPCIe's /dev/dmabuf_import, and prints the
``(dma_addr, dma_len)`` tuples that ``DMABUF_IMPORT_GET_MAP`` returns. Those
tuples are not the IOMMU mapping unit. The NVIDIA exporter cuts the buffer
into chunks of the importing device's DMA max segment size and maps each
chunk with ``dma_map_resource()`` for that device. The misc device sets no
max segment size, so it gets the kernel's 64 KiB default and plain physical
addresses. An NVMe (``--bdf``) sets it to 4 GiB, so it gets one segment for
the whole buffer: the IOVA of a single ``iommu_map`` when the IOMMU is
enforcing, the raw BAR1 physical range when it is off. The IOMMU page size
behind that IOVA is shown by ``iommu_trace_gpu``.

It also prints the CUDA VMM allocation granularity for reference, and
DMABUF_IMPORT_DESCRIBE. Each import is checked: the segments must cover the
whole buffer, every entry must be device memory rather than memory migrated
to the host, and DESCRIBE must agree on the segment count. A failed check
fails the probe. It ends with findings on the imports: the pieces each one
came in, and whether the --bdf import is translated by the IOMMU (an IOVA)
or not (the physical address the misc import shows).

The build needs the DMABUF_IMPORT UAPI, installed by
``tasks/setup_upcie_modules.yaml``, and CUDA. The source is copied into a fresh
``/tmp/aisio-dmabuf-import-probe.*`` directory on the target, compiled with
nvcc or else with gcc against libcuda, and the directory is removed after the
run.

Example:

  cijoe --monitor \\
      -c configs/transport.toml \\
      tasks/probe_dmabuf_import.yaml

Pass ``--bdf 0000:4d:00.0`` to also import on behalf of an NVMe device, which
is the peer-to-peer path the addresses are actually programmed into. The
default (no bdf) performs the same misc-device enumeration the upcie-cuda
backend does; its actual 2 MiB IOMMU mapping is not exercised here.
"""

import errno
import logging as log
from argparse import ArgumentParser
from pathlib import Path

from cijoe.core.resources import get_resources

PROBE_RESOURCE = "dmabuf_import_probe"
PROBE_WORKDIR_PREFIX = "/tmp/aisio-dmabuf-import-probe."


def add_args(parser: ArgumentParser):
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
    parser.add_argument(
        "--bdf",
        type=str,
        default=None,
        help="NVMe PCI address to import on behalf of, e.g. 0000:4d:00.0",
    )


def artifacts_path(args):
    path = Path(args.output) / "artifacts" / "dmabuf-import-probe"
    path.mkdir(parents=True, exist_ok=True)
    return path


def compile_probe(cijoe, src, binary):
    """Compile the probe, trying nvcc then a plain gcc + libcuda link."""
    compile_cmds = [
        f"nvcc -o {binary} {src} -lcuda",
        (
            f"gcc -O2 -o {binary} {src} "
            "-I/usr/local/cuda/include -L/usr/local/cuda/lib64 -lcuda"
        ),
    ]

    for cmd in compile_cmds:
        err, state = cijoe.run(cmd)
        if not err:
            return 0
        log.info(f"compile failed ({cmd}):\n{state.output()}")

    return errno.ECOMM


def stage_probe(cijoe):
    """Copy the probe into a fresh directory on the target and compile it.

    Returns (err, workdir, binary). The directory is new per run, so two runs
    cannot overwrite each other's binary. Pass workdir to cleanup_probe().
    """
    probe = get_resources().get("auxiliary", {}).get(PROBE_RESOURCE, {})
    if not probe:
        log.error("Failed retrieving the probe source from auxiliary files")
        return errno.ENOENT, None, None

    err, state = cijoe.run(f"mktemp -d {PROBE_WORKDIR_PREFIX}XXXXXX")
    workdir = state.output().strip()
    if err or not workdir.startswith(PROBE_WORKDIR_PREFIX):
        log.error(f"Failed creating a work directory on the target: {workdir}")
        return errno.EIO, None, None

    src = f"{workdir}/probe.c"
    binary = f"{workdir}/probe"

    if not cijoe.put(probe.path, src):
        log.error("Failed transferring probe source to the target")
        cleanup_probe(cijoe, workdir)
        return errno.EIO, None, None

    err = compile_probe(cijoe, src, binary)
    if err:
        log.error("Failed compiling the probe on the target")
        cleanup_probe(cijoe, workdir)
        return err, None, None

    return 0, workdir, binary


def cleanup_probe(cijoe, workdir):
    """Remove a work directory made by stage_probe(), and nothing else."""
    if workdir and workdir.startswith(PROBE_WORKDIR_PREFIX):
        cijoe.run(f"rm -rf {workdir}")


def main(args, cijoe):
    err, workdir, binary = stage_probe(cijoe)
    if err:
        return err

    run_cmd = f"{binary} --size_mib {args.size_mib} --gpu_id {args.gpu_id}"
    if args.bdf:
        run_cmd += f" --bdf {args.bdf}"

    err, state = cijoe.run(run_cmd)
    output = state.output()
    cleanup_probe(cijoe, workdir)

    (artifacts_path(args) / "probe.out").write_text(output)
    print(output)

    if err:
        log.error(f"Probe failed with err({err})")
        return err

    return 0
