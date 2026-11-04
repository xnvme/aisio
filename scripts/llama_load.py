# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Load a model with llama.cpp, from a cold page cache, and time it
================================================================

Runs llama.cpp's llama-completion --repetitions times with --load-mode
--mode, the page cache dropped before each run, answering --prompt in one
turn. Each run records llama.cpp's own load time, from start to the first
evaluation, and the wall time of the whole process. The runs and their means
go to 'llama_load-<mode>.json' in the step's output. --env is prepended to
the command, for the variables OpenDS reads.

A run with --mode opends must have loaded through OpenDS: llama.cpp falls
back to its own reader when OpenDS cannot open or read, and only warns, so a
run fails on any of those warnings. The timed runs log at llama.cpp's default
level, as verbose logging slows every loader. With --mode opends one more
run follows, untimed and verbose, which must print the loader's summary of
what it read through OpenDS; its count of reads and I/O rate are recorded.

Retargetable: True
------------------
"""

import errno
import json
import logging as log
import re
from argparse import ArgumentParser
from pathlib import Path

# What llama.cpp's OpenDS loader warns when it falls back to its own reader
OPENDS_FALLBACK = re.compile(r"opends_\w+(\([^)]*\))? failed|built without OpenDS")
# The loader's debug line once it has read through OpenDS
OPENDS_SUMMARY = re.compile(r"opends (\d+) ops .*\(([0-9.]+) GB/s\)")


def add_args(parser: ArgumentParser):
    parser.add_argument("--bin", type=str, required=True)
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--mode", type=str, required=True)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--prompt", type=str, default="What is the capital of France?")
    parser.add_argument("--env", type=str, default="")
    parser.add_argument("--extra", type=str, default="")


def run_once(args, cijoe, verbose=False):
    """One cold load; its timings, and in verbose runs what OpenDS reported"""

    cijoe.run("sync")
    err, _ = cijoe.run("echo 3 > /proc/sys/vm/drop_caches")
    if err:
        return err, None

    err, state = cijoe.run(
        f"echo '{args.prompt}' | /usr/bin/time -f 'wall_s=%e'"
        f" env {args.env} {args.bin} -m {args.model} -st --load-mode {args.mode}"
        f" {'-v' if verbose else ''} {args.extra}"
    )
    if err:
        return err, None

    output = state.output()
    load = re.findall(r"load time\s*=\s*([0-9.]+) ms", output)
    wall = re.findall(r"wall_s=([0-9.]+)", output)
    if not load or not wall:
        log.error("llama.cpp printed no load time, or time no wall time")
        return errno.EIO, None

    run = {"load_s": float(load[-1]) / 1000, "wall_s": float(wall[-1])}
    if args.mode != "opends":
        return 0, run

    fallback = OPENDS_FALLBACK.search(output)
    if fallback:
        log.error(f"not loaded through OpenDS: {fallback.group(0)}")
        return errno.EIO, None
    if not verbose:
        return 0, run

    summary = OPENDS_SUMMARY.search(output)
    if not summary:
        log.error("not loaded through OpenDS: no summary from its loader")
        return errno.EIO, None

    return 0, {"ops": int(summary.group(1)), "io_gbps": float(summary.group(2))}


def main(args, cijoe):
    if args.repetitions < 1:
        log.error("--repetitions must be at least 1")
        return errno.EINVAL

    runs = []
    for _ in range(args.repetitions):
        err, run = run_once(args, cijoe)
        if err:
            return err
        runs.append(run)

    result = {
        "mode": args.mode,
        "model": args.model,
        "runs": runs,
        "load_s_mean": sum(r["load_s"] for r in runs) / len(runs),
        "wall_s_mean": sum(r["wall_s"] for r in runs) / len(runs),
    }
    if args.mode == "opends":
        err, result["opends"] = run_once(args, cijoe, verbose=True)
        if err:
            return err
    dst = Path(cijoe.output_path) / cijoe.output_ident / f"llama_load-{args.mode}.json"
    dst.write_text(json.dumps(result, indent=2))
    log.info(
        f"{args.mode}: load {result['load_s_mean']:.2f} s,"
        f" whole process {result['wall_s_mean']:.2f} s"
    )

    return 0
