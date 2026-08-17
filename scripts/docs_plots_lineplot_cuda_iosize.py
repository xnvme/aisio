#!/usr/bin/env python3
# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

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

from version_helper import version_of


REQ = {
    "nqueues": 1,
    "ndevs": 16,
    "tool": "xnvmeperf-cuda",
    "backend": "upcie-cuda",
}

# The GPU-activity plot holds queue depth fixed at the saturation point of
# the bandwidth sweep.
SM_QDEPTH = 128
SM_FIELDS = {
    "1002": "SM_active",
    "1003": "SM_occupancy",
    "1005": "DRAM_active",
}

# The clock shares the sweep but not the unit of the activity fields, so it is
# charted against a second axis in MHz.
STATE_FIELDS = {
    "100": "SM_clock",
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
        return err, None, None, None, ""

    results = json_load(state.output())
    results.sort(key=lambda res: res["iosize"])
    version = version_of(results)
    data = defaultdict(lambda: defaultdict(list))
    sm_data = defaultdict(lambda: defaultdict(list))
    state_data = defaultdict(lambda: defaultdict(list))

    for res in results:
        nbytes = res["mibs"] * 1024 * 1024  # bytes/s
        data[res["iosize"]][res["qdepth"]].append(nbytes)

        # GPU engine activity at the fixed queue depth. "dcgm" is a
        # per-field stats dict in new result files; None or a scalar in
        # older ones, which then simply yield an empty activity plot.
        dcgm = res.get("dcgm")
        if res["qdepth"] != SM_QDEPTH or not isinstance(dcgm, dict):
            continue
        for field, key in SM_FIELDS.items():
            stats = dcgm.get(field)
            value = stats.get("mean") if isinstance(stats, dict) else None
            if value is not None:
                sm_data[res["iosize"]][key].append(value * 100)  # ratio -> %

        for field, key in STATE_FIELDS.items():
            stats = dcgm.get(field)
            value = stats.get("mean") if isinstance(stats, dict) else None
            if value is not None:
                state_data[res["iosize"]][key].append(value)  # MHz

    return 0, data, sm_data, state_data, version


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

    bandwidth_path = artifacts / "nvbandwidth-h2d"
    with open(bandwidth_path, "r") as f:
        h2d_bandwidth = float(f.read())

    err, results, sm_results, state_results, version = collect(args, cijoe)
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
            "h2d_bandwidth": h2d_bandwidth,
            "xnvme_version": version,
        }))

    for iosize, metrics in sm_results.items():
        for key, values in metrics.items():
            sm_results[iosize][key] = [round(v, 2) for v in avg_stddev(values)]
        for key, values in state_results.get(iosize, {}).items():
            sm_results[iosize][key] = [round(v, 2) for v in avg_stddev(values)]

    sm_template_name = "lineplot-cuda-iosize-sm.yaml"
    sm_template = template_env.get_template(f"{sm_template_name}.jinja2")
    out_path = artifacts / sm_template_name
    with out_path.open("w") as body:
        body.write(sm_template.render({
            "results": sm_results,
            "xnvme_version": version,
        }))

    return 0
