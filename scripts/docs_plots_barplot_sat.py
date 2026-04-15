#!/usr/bin/env python3
"""
Parse bdevperf output files and populate a data YAML file with mean IOPS and std dev.

Example command:
    cijoe scripts/docs_plots_barplot_sat.py -c configs/transport.toml --path "/root/bench-results" --devices 4
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
    "ncpus": 1,
    "cpu_governor": "performance",
    "stress": 0,
    "turbo": 1,
    "smt": 1,
    "thr_sib": 0,
    "backend": "upcie-cuda",
}

def add_args(parser: ArgumentParser):
    parser.add_argument("--path", type=str, help="Path to the results data")
    parser.add_argument("--devices", type=int, default=4, help="The number of devices used")

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
    data = { iosize: defaultdict(list) for iosize in [512, 4096, 8192] }

    for res in results:
        ndevs = res["ndevs"]
        if ndevs != args.devices:
            continue

        iosize, mibs, dcgm = res["iosize"], res["mibs"], res["dcgm"]
        nbytes = mibs * 1024 * 1024

        data[iosize]["payload_nbytes"].append(nbytes)
        data[iosize]["total_nbytes"].append(dcgm)

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

    out_path = artifacts / "barplot-sat.yaml"

    err, results = collect(args, cijoe)
    if err:
        log.error("Failed: collect()")
        return err

    for iosize, result in results.items():
        for type, mibs in result.items():
            results[iosize][type] = round(avg_stddev(mibs)[0])

    bandwidth_path = artifacts / "cuda-sample-p2p-bandwidth"
    with open(bandwidth_path, "r") as file:
        cuda_bandwidth = file.read()

    template_name = "barplot-sat.yaml"

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
            "devices": args.devices,
            "cuda_bandwidth": float(cuda_bandwidth),
        }))

    return 0
