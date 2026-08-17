#!/usr/bin/env python3
# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

"""
PCIe peak-bandwidth reference
=============================

Run NVIDIA nvbandwidth's host_to_device_memcpy_ce test and record the achieved
bandwidth (GB/s) as the PCIe peak-bandwidth reference for the bench_pcie /
bench_cuda_iosize experiments. The copy runs from host memory into GPU memory
across the PCIe link of the GPU given by ``dcgm.gpu``, the same link the NVMe
devices transfer over under P2P. The binary is built by setup_nvstack.yaml.

Retargetable: True
------------------
"""

from pathlib import Path
from re import MULTILINE, search
import logging as log

from cijoe.core.command import Cijoe


def main(args, cijoe: Cijoe):
    """Run nvbandwidth and store the PCIe peak bandwidth"""

    artifacts = Path(args.output) / "artifacts"

    install_path = cijoe.getconf("nvidia.nvbandwidth.path", "/root/git/nvbandwidth")
    bin = Path(install_path) / "build" / "nvbandwidth"

    # The reference describes one link, so the run is pinned to the GPU the
    # benchmarks monitor: with a single device enumerated, nvbandwidth's matrix
    # holds that device alone.
    gpu = cijoe.getconf("dcgm.gpu", 0)

    err, state = cijoe.run(f"CUDA_VISIBLE_DEVICES={gpu} {bin} -t host_to_device_memcpy_ce")
    if err:
        log.error(f"Failed: run(nvbandwidth); err({err})")
        return err

    # nvbandwidth totals its per-GPU matrix in a "SUM <testcase> <value>" line
    m = search(
        r"^SUM host_to_device_memcpy_ce\s+([0-9.]+)", state.output(), flags=MULTILINE
    )
    if not m:
        log.error("Failed: unexpected output from nvbandwidth")
        return -1

    bandwidth = float(m.group(1))  # in GB/s

    with open(artifacts / "nvbandwidth-h2d", "x") as out:
        out.write(f"{bandwidth}")

    return 0
