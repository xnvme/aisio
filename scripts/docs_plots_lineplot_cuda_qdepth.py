#!/usr/bin/env python3
# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Parse xnvmeperf-cuda output files and produce a lineplot YAML for queue-depth scaling.

Example command:
    cijoe scripts/docs_plots_lineplot_cuda_qdepth.py -c configs/transport.toml --path "/root/bench-cuda-qdepth-results"
"""

import logging as log
import jinja2
from argparse import ArgumentParser
from collections import defaultdict
from json import loads as json_load
from pathlib import Path

from cijoe.core.command import Cijoe
from cijoe.core.resources import get_resources

from dcgm_helper import dcgm_stat
from version_helper import version_of


REQ = {
    "iosize": 512,
    "ndevs": 16,
    "tool": "xnvmeperf-cuda",
    "backend": "upcie-cuda",
}

# Queue depth and queue count both move SM activity and warp slot occupancy, so
# each is charted over the whole grid rather than a slice of it: a figure per
# field, drawn like the IOPS figure with the depth on the x-axis and one line
# per queue count.
ACTIVITY_FIGURES = {
    "1002": "lineplot-cuda-qdepth-sm.yaml",
    "1003": "lineplot-cuda-qdepth-occupancy.yaml",
}

# The IOPS the devices deliver when the workload stops being the constraint,
# determined in the CPU-initiated experiment. The figures draw it as a roofline
# and the activity figures mark the point on each line that first reaches it.
DEVICE_IOPS_ROOFLINE = 61727008

# A configuration counts as saturating at the shallowest depth reaching this
# share of the roofline. Queue counts above one arrive within a percent or two
# of it and then stay, so the depth it selects is insensitive to the exact
# share; a single queue never reaches it at any depth.
SATURATION_SHARE = 0.98


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
        return err, None, None, ""

    results = json_load(state.output())
    results.sort(key=lambda res: res["qdepth"])
    version = version_of(results)
    data = defaultdict(lambda: defaultdict(list))
    activity = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    for res in results:
        data[res["qdepth"]][res["nqueues"]].append(res["iops"])

        # GPU engine activity. "dcgm" is a per-field stats dict in new result
        # files; None or a scalar in older ones, which then simply yield an
        # empty activity plot.
        dcgm = res.get("dcgm")
        if not isinstance(dcgm, dict):
            continue
        for field, name in ACTIVITY_FIGURES.items():
            value = dcgm_stat(dcgm, field)
            if value is not None:
                activity[name][res["qdepth"]][res["nqueues"]].append(value * 100)

    return 0, data, activity, version


def avg_stddev(values):
    if not values:
        return 0, 0
    avg = sum(values) / len(values)
    stddev = (sum((x - avg) ** 2 for x in values) / len(values)) ** 0.5
    return avg, stddev


def saturating_depths(results):
    """
    The shallowest queue depth at which each queue count reaches the roofline.

    Keyed by the series name the figures use, so a figure charting something
    other than IOPS can still mark where the devices ran out of headroom. A
    queue count that never reaches it is absent rather than marked.
    """

    floor = DEVICE_IOPS_ROOFLINE * SATURATION_SHARE
    saturating = {}
    for qdepth in sorted(results):
        for nqueues, (iops, _) in sorted(results[qdepth].items()):
            series = f"nqueues_{nqueues}"
            if series not in saturating and iops >= floor:
                saturating[series] = qdepth

    return saturating


def main(args, cijoe):
    artifacts = Path(args.output) / "artifacts"

    if not args.path:
        args.path = artifacts / "bench-cuda-qdepth-results"

    template_name = "lineplot-cuda-qdepth.yaml"

    template_resource = get_resources().get("templates", {}).get(template_name, {})
    if not template_resource:
        log.error(f"Failed: could not find template resource({template_name})")
        return 1

    template_path = Path(template_resource.path).parent
    template_env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_path))
    template = template_env.get_template(f"{template_name}.jinja2")

    err, results, activity, version = collect(args, cijoe)
    if err:
        log.error("Failed: collect()")
        return err

    for qdepth, series in results.items():
        for nqueues, iops in series.items():
            results[qdepth][nqueues] = list(map(round, avg_stddev(iops)))

    out_path = artifacts / "lineplot-cuda-qdepth.yaml"
    with out_path.open("w") as body:
        body.write(template.render({
            "results": results,
            "device_roofline": DEVICE_IOPS_ROOFLINE,
            "xnvme_version": version,
        }))

    saturating = saturating_depths(results)

    for name, grid in activity.items():
        charted = defaultdict(dict)
        for qdepth in sorted(grid):
            for nqueues, values in sorted(grid[qdepth].items()):
                charted[qdepth][nqueues] = [round(v, 2) for v in avg_stddev(values)]

        out_path = artifacts / name
        with out_path.open("w") as body:
            body.write(template_env.get_template(f"{name}.jinja2").render({
                "results": charted,
                "saturating": saturating,
                "xnvme_version": version,
            }))

    return 0
