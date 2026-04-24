#!/usr/bin/env python3
"""
Parse xnvmeperf-cuda output files and produce a lineplot YAML for I/O size scaling.

Example command:
    cijoe scripts/docs_plots_lineplot_cuda_iosize.py -c configs/transport.toml --path "/root/bench-cuda-iosize-results"
"""

import logging as log
import jinja2
from argparse import ArgumentParser
from collections import defaultdict
from json import loads as json_load
from pathlib import Path

from cijoe.core.command import Cijoe
from cijoe.core.resources import get_resources


REQ = {
    "nqueues": 1,
    "ndevs": 16,
    "tool": "xnvmeperf-cuda",
    "backend": "upcie-cuda",
}


def add_args(parser: ArgumentParser):
    parser.add_argument("--path", type=str, help="Path to the results data")


def collect(args, cijoe: Cijoe):
    cmd = [
        "jq -s '[.[] | select(",
        " and ".join([
            f".{k} == " + (
            f'"{v}"' if isinstance(v, str)
            else f'{str(v).lower()}' if isinstance(v, bool)
            else f'{v}')
            for k, v in REQ.items()
        ]),
        f")]' {args.path}/*.out"
    ]

    err, state = cijoe.run(" ".join(cmd))
    if err:
        log.error("Failed: jq")
        return err, None

    results = json_load(state.output())
    results.sort(key=lambda res: res["iosize"])
    data = defaultdict(lambda: defaultdict(list))

    for res in results:
        nbytes = res["mibs"] * 1024 * 1024  # bytes/s
        data[res["iosize"]][res["qdepth"]].append(nbytes)

    return 0, data


def avg_stddev(values):
    if not values:
        return 0, 0
    avg = sum(values) / len(values)
    stddev = (sum((x - avg) ** 2 for x in values) / len(values)) ** 0.5
    return avg, stddev


def main(args, cijoe):
    artifacts = Path(args.output) / "artifacts"

    if not args.path:
        args.path = artifacts / "bench-cuda-iosize-results"

    template_name = "lineplot-cuda-iosize.yaml"

    template_resource = get_resources().get("templates", {}).get(template_name, {})
    if not template_resource:
        log.error(f"Failed: could not find template resource({template_name})")
        return 1

    template_path = Path(template_resource.path).parent
    template_env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_path))
    template = template_env.get_template(f"{template_name}.jinja2")

    bandwidth_path = artifacts / "cuda-sample-p2p-bandwidth"
    with open(bandwidth_path, "r") as f:
        cuda_bandwidth = float(f.read())

    err, results = collect(args, cijoe)
    if err:
        log.error("Failed: collect()")
        return err

    for iosize, series in results.items():
        for qdepth, nbytes in series.items():
            results[iosize][qdepth] = list(map(round, avg_stddev(nbytes)))

    out_path = artifacts / "lineplot-cuda-iosize.yaml"
    with out_path.open("w") as body:
        body.write(template.render({
            "results": results,
            "cuda_bandwidth": cuda_bandwidth,
        }))

    return 0
