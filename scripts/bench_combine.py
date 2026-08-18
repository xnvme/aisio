# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Combine results from running I/O benchmarks
===========================================

Combine the results from running the CPU benchmarks in `bench_runall.py`.

Retargetable: True
------------------
"""

from argparse import ArgumentParser
from collections import defaultdict
from json import dump as json_dump, load as json_load
from pathlib import Path
from re import match
from typing import List, Tuple, Union
import logging as log

from cijoe.core.command import Cijoe

from version_helper import merge_versions


def add_args(parser: ArgumentParser):
    parser.add_argument("--results_dir", type=Path, default=None, help="Path to existing directory in which the results should be saved. Note: Already existing results will not be benchmarked again")


def main(args, cijoe: Cijoe):
    """Combine benchmark results into a single JSON"""

    artifacts = Path(args.output) / "artifacts"
    bdev_results = artifacts / "bench-results"

    if args.results_dir:
        bdev_results = args.results_dir

    all_results = defaultdict(list)

    REGEX = r".*-thrsib(?P<ht>[01])-freq_.*-stress(?P<st>[01])-SMT(?P<sm>[01])-turbo(?P<tu>[01])-\d"
    CUDA_REGEX = r"d\d+-c\d+-o\d+-q\d+-nq(?P<nq>\d+)-be_.*-tool_xnvmeperf-cuda-\d"

    for path in bdev_results.glob("*-0.out"):
        m = match(REGEX, path.stem)
        cuda_m = match(CUDA_REGEX, path.stem) if not m else None

        if m:
            ht, st, sm, tu = map(int, m.groups())
            label = (
                f"{'U' if ht else 'Not u'}sing thread siblings; "
                f"SMT {'on' if sm else 'off'}; "
                f"stress {'on' if st else 'off'}; "
                f"turbo {'on' if tu else 'off'}"
            )
        elif cuda_m:
            label = f"xnvmeperf-cuda; nqueues {int(cuda_m.group('nq'))}"
        else:
            log.error(f"Failed parsing filename({path.stem})")
            return 1

        repeated_results = []

        for run in bdev_results.glob(f"{path.stem[:-1]}*"):
            with open(run) as file:
                # Files written before the runs recorded a build stamp hold no
                # "versions" key, and the merge below wants one key set.
                repeated_results.append({"versions": {}, **json_load(file)})

        # err, result = get_average(repeated_results)
        err, result = merge_dicts(repeated_results, ["cpu_freqs", "iops", "mibs", "cpu_usage", "dcgm", "versions"])
        if err:
            log.error("Failed: merge_dicts()")
            return err

        if "tool" not in result:
            result["tool"] = "bdevperf"
            result["backend"] = "spdk"

        result["iops"] = avg_stddev(result["iops"])
        result["mibs"] = avg_stddev(result["mibs"])
        result["cpu_usage"] = avg_stddev(result["cpu_usage"])
        result["dcgm"] = combine_dcgm(result["dcgm"]) if "dcgm" in result else 0
        # The repeats carry a stamp each; the combined record keeps one mapping.
        result["versions"] = merge_versions(result.get("versions", []))

        all_results[label].append(result)

    with open(artifacts / "benchmark-results.json", "x") as file:
        json_dump(all_results, file, indent=2)

    return 0


def combine_dcgm(ns: List[Union[None, int, float, dict]]):
    """
    Aggregate the "dcgm" values of repeated runs.

    Runs without DCGM hold None; legacy result files hold a scalar (field
    1010 p95); current files hold a per-field dict of stats. For the dict
    schema, each stat is aggregated to (avg, stddev) across the repeats.
    """
    if not ns or not ns[0]:
        # safeguard against [None, None, None, None, None]
        return 0

    if isinstance(ns[0], dict):
        # Unlike avg_stddev(), only treat None as missing: guard fields
        # (112 throttle bits, 202 replay) are legitimately 0.0 in most runs
        # and a nonzero outlier must survive aggregation.
        def agg(values):
            if any(v is None for v in values):
                # A stat missing from some run: propagate None rather than 0,
                # so "not measured" stays distinct from a measured 0.0. The
                # guard fields (112 throttle, 202 replay) are legitimately 0.0,
                # and callers unpack (avg, stddev) or skip on None.
                return None
            avg = sum(values) / len(values)
            stddev = (sum((x - avg) ** 2 for x in values) / len(values)) ** 0.5
            return avg, stddev

        fields = {field: stats for run in ns for field, stats in run.items()}

        return {
            field: {
                stat_name: agg([run.get(field, {}).get(stat_name) for run in ns])
                for stat_name in stats
                if stat_name != "samples"
            }
            for field, stats in fields.items()
        }

    return avg_stddev(ns)


def avg_stddev(ns: List[Union[int, float]]):
    """Calculate the average and standard deviation of a list"""
    if not ns[0]:
        # safeguard against [None, None, None, None, None]
        return 0

    avg = sum(ns) / len(ns)
    stddev = (sum((x - avg) ** 2 for x in ns) / len(ns)) ** 0.5
    return avg, stddev


def merge_dicts(dicts: List[dict], include_all: List[str]) -> Tuple[int, dict]:
    """
    Merge a list of dicts into a single combined dict. All dicts must have the
    same set of keys, and all values for each key must be the same within each
    dict, except if the key is in the `include_all` list. In this case, the value
    for each list will be combined into a list of values for the key in each dict.

    Arguments
    - `dicts: List[dict]`: List of dicts with same key set.
    - `include_all: List[str]`: List of keys within the set. The call will not
      fail if given a key that is not within the dicts.

    Returns
    - `(err, merged): Tuple[int, dict]`
    """

    first, merged = dicts[0], {}
    keys = set(first.keys())

    if not all([set(d.keys()) == keys for d in dicts]):
        failed = next(d for d in dicts if set(d.keys()) != keys)
        log.error(f"Error: Expected keys of all dicts to be equal: {set(failed.keys())} != {keys}")
        return 1, None

    for key in keys:
        if key in include_all:
            merged[key] = [d[key] for d in dicts]
        else:
            if not all([d[key] == first[key] for d in dicts]):
                log.error(f"Error: Expected all values for non-excluded key({key}) to be equal")
                return 1, None
            merged[key] = first[key]

    return 0, merged
