# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

import logging as log
import re
from argparse import ArgumentParser

REQUIRED_KEYS = [
    "cpumask",
    "iopattern",
    "qdepth",
    "iosize",
    "runtime",
    "backend",
    "devices",
]
CUDA_REQUIRED_KEYS = ["iopattern", "qdepth", "iosize", "runtime", "backend", "devices"]


def add_args(parser: ArgumentParser):
    parser.add_argument("--command", type=str, default="run")
    parser.add_argument("--devices", type=str, default=[], nargs="+")
    parser.add_argument("--ndevs", type=int, default=0)
    parser.add_argument("--iopattern", type=str, default="randread")
    parser.add_argument("--qdepth", type=int, default=128)
    parser.add_argument("--iosize", type=int, default=512)
    parser.add_argument("--runtime", type=int, default=10)
    parser.add_argument("--cpumask", type=str, default="0x1")
    parser.add_argument("--backend", type=str, default="upcie")
    parser.add_argument("--nqueues", type=int, default=1)
    parser.add_argument("--homi_id", type=int, default=0)
    parser.add_argument("--check", type=lambda v: v == "true", default=False)


def xnvmeperf_cmd(bin: str, args: dict) -> str:
    if any(key not in args for key in REQUIRED_KEYS):
        log.error(f"Failed: Missing arguments for {bin}")

    parameters = [
        f"{bin}",
        "run",
        f"--cpumask {args['cpumask']}",
        f"--qdepth {args['qdepth']}",
        f"--iosize {args['iosize']}",
        f"--runtime {args['runtime']}",
        f"--iopattern {args['iopattern']}",
        f"--be {args['backend']}",
    ]
    # Only the GPU-memory backends read it
    if args.get("gpu_id") is not None:
        parameters.append(f"--gpu-id {args['gpu_id']}")
    if args.get("homi_id"):
        parameters.append(f"--homi-id {args['homi_id']}")
    parameters.append(" ".join(args["devices"]))
    return " ".join(parameters)


def check_output(output: str) -> int:
    """
    Fail a run that completed no I/O or had any I/O fail; xnvmeperf exits zero
    either way, reporting both only in its 'Total:' row
    """

    match = re.search(r"^\s*Total:\s+([\d.]+)\s+([\d.]+)\s+(\d+)\s*$", output, re.M)
    if not match:
        log.error("Failed: no 'Total:' row in the xnvmeperf output")
        return 1

    iops, failed = float(match.group(1)), int(match.group(3))
    if failed or not iops:
        log.error(f"Failed: iops({iops}), failed({failed})")
        return 1

    return 0


def xnvmeperf_cuda_cmd(bin: str, args: dict) -> str:
    if any(key not in args for key in CUDA_REQUIRED_KEYS):
        log.error(f"Failed: Missing arguments for {bin} cuda-run")
        return ""

    parameters = [
        f"{bin}",
        "cuda-run",
        f"--qdepth {args['qdepth']}",
        f"--iosize {args['iosize']}",
        f"--runtime {args['runtime']}",
        f"--iopattern {args['iopattern']}",
        f"--be {args['backend']}",
        f"--nqueues {args['nqueues']}",
    ]
    if args.get("homi_id"):
        parameters.append(f"--homi-id {args['homi_id']}")
    parameters.append(" ".join(args["devices"]))
    return " ".join(parameters)


def main(args, cijoe):
    if bool(args.devices) == bool(args.ndevs):
        log.error(
            "Failed: Exactly one of arguments 'devices' and 'ndevs' must be defined; "
            f"got devices({args.devices}), ndevs({args.ndevs})"
        )
        return -1

    if args.ndevs:
        devs = cijoe.getconf("devices", None)
        args.devices = [d["pci_addr"] for d in devs[: args.ndevs]]

    if args.command == "cuda-run":
        cmd = xnvmeperf_cuda_cmd("xnvmeperf", vars(args))
    else:
        cmd = xnvmeperf_cmd("xnvmeperf", vars(args))

    err, state = cijoe.run(cmd)
    if err:
        return err

    return check_output(state.output()) if args.check else 0
