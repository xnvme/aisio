#!/usr/bin/env python3
"""
Parse tool comparison output files and populate a data YAML file with mean IOPS.

Example command:
    cijoe scripts/docs_plots_barplot_tool.py -c configs/transport.toml --path "/root/bench-results"
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
    "stress": 0,
    "cpu_governor": "performance",
    "turbo": 1,
    "smt": 1,
    "thr_sib": 1,
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
            else f'{v}') for k,v in REQ.items()
        ]),
        f")]' {args.path}/*.out"
    ]

    err, state = cijoe.run(" ".join(cmd))
    if err:
        log.error(f"Failed: jq")
        return err, None

    results = json_load(state.output())

    data = { threads: defaultdict(list) for threads in range(1,5) }

    for res in results:
        threads = res["ncpus"]
        if threads not in data:
            continue

        tool, be = res["tool"], res["backend"]
        be = be.replace("-", "_") # upcie-cuda => upcie_cuda

        if tool == "bdevperf":
            label = "spdk_bdevperf"
        elif tool == "spdk_nvme_perf":
            label = tool
        else:
            label = f"{tool}_{be}"

        iops = res["iops"]
        data[threads][label].append(iops)

    return 0, data


def avg_stddev(values):
    """Calculate the average and standard deviation of a list"""
    if not values:
        return 0, 0

    avg = sum(values) / len(values)
    stddev = (sum((x - avg) ** 2 for x in values) / len(values)) ** 0.5
    return avg, stddev


def main(args, cijoe):
    artifacts = Path(args.output) / "artifacts"

    if not args.path:
        args.path = artifacts / "bench-results"

    out_path = artifacts / "barplot-tool.yaml"

    err, results = collect(args, cijoe)
    if err:
        log.error("Failed: collect()")
        return err

    for threads, result in results.items():
        for config, iops in result.items():
            results[threads][config] = round(avg_stddev(iops)[0])
        results[threads] = sorted(results[threads].items())

    template_name = "barplot-tool.yaml"

    template_resource = get_resources().get("templates", {}).get(template_name, {})
    if not template_resource:
        log.error(f"Failed: could not find template resource({template_name})")
        return 1

    template_path = Path(template_resource.path).parent
    template_loader = jinja2.FileSystemLoader(template_path)
    template_env = jinja2.Environment(loader=template_loader)

    template = template_env.get_template(f"{template_name}.jinja2")
    with out_path.open("w") as body:
        body.write(template.render({
            "results": results,
        }))

    return 0
