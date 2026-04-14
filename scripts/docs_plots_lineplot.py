#!/usr/bin/env python3
"""
Parse bdevperf output files and populate a data YAML file with mean IOPS and std dev.

Example command:
    cijoe scripts/docs_plots_lineplot.py -c configs/transport.toml --path "/root/bench-results" --tool bdevperf --driver SPDK --xaxis qdepth
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
    "qdepth": 128,
    "iosize": 512,
    "ndevs": 16,
    "cpu_governor": "performance",
    "stress": 0,
    "thr_sib": 0,
    "ncpus": 8,
}

BE_PP = {
    "spdk": "SPDK",
    "upcie": "uPCIe",
    "upcie-cuda": "uPCIe"
}


def add_args(parser: ArgumentParser):
    parser.add_argument("--path", type=str, help="Path to the results data")
    parser.add_argument("--backend", type=str, help="Prettyname for the driver / backend used")
    parser.add_argument("--tool", type=str, help="benchmarking tool")
    parser.add_argument("--xaxes", type=str, default=["ncpus"], nargs="+")


def collect(args, cijoe: Cijoe, xaxis):
    """Return {cores: {smt: [iops, ...]}} using SMT0+turbo0 and SMT1+turbo1+thrsib1."""

    cmd = [
        "jq -s '[.[] | select(",
        " and ".join([
            f".{k} == " + (
            f'"{v}"' if isinstance(v, str)
            else f'{str(v).lower()}' if isinstance(v, bool)
            else f'{v}')
            for k,v in REQ.items() if k != xaxis
        ]),
        f")]' {args.path}/*.out"
    ]

    err, state = cijoe.run(" ".join(cmd))
    if err:
        log.error(f"Failed: jq")
        return err, None

    results = json_load(state.output())
    results.sort(key=lambda res: res[xaxis])
    data = defaultdict(lambda: defaultdict(list))

    for res in results:
        tool, be = res.get("tool", "bdevperf"), res.get("backend", "spdk")
        if args.tool.lower() != tool or args.backend.lower() not in be:
            continue

        turbo, smt = map(int, [res["turbo"], res["smt"]])
        if turbo != smt:
            continue

        if "upcie" in be:
            label = be
        else:
            label = "turbo_" + ("on" if turbo else "off")

        x, iops = res[xaxis], res["iops"]
        data[x][label].append(iops)

    return 0, data


def avg_stddev(values):
    """Calculate the average and standard deviation of a list"""
    if not values:
        return 0, 0

    avg = sum(values) / len(values)
    stddev = (sum((x - avg) ** 2 for x in values) / len(values)) ** 0.5
    return avg, stddev


def main(args, cijoe):
    if not all([args.tool, args.backend]):
        log.error("Missing arguments: [tool, backend] must be defined")
        return -1

    artifacts = Path(args.output) / "artifacts"

    if not args.path:
        args.path = artifacts / "bench-results"

    template_name = "lineplot.yaml"

    template_resource = get_resources().get("templates", {}).get(template_name, {})
    if not template_resource:
        log.error(f"Failed: could not find template resource({template_name})")
        return 1

    template_path = Path(template_resource.path).parent
    template_loader = jinja2.FileSystemLoader(template_path)
    template_env = jinja2.Environment(loader=template_loader)

    template = template_env.get_template(f"{template_name}.jinja2")

    xlabels = {
        "qdepth": "Queue Depth",
        "ncpus": "Number of Physical CPU Cores",
        "ndevs": "Number of Devices",
        "iosize": "I/O Size",
    }

    for xaxis in args.xaxes:
        out_path = artifacts / f"lineplot-{args.backend.lower()}-{xaxis}.yaml"

        err, results = collect(args, cijoe, xaxis)
        if err:
            log.error("Failed: collect()")
            return err

        for x, result in results.items():
            for label, iops in result.items():
                results[x][label] = list(map(round, avg_stddev(iops)))

        with out_path.open("w") as body:
            body.write(template.render({
                "results": results,
                "driver": BE_PP.get(args.backend, args.backend),
                "tool": args.tool,
                "xlabel": xlabels[xaxis],
                "xaxis": xaxis,
            }))

    return 0
