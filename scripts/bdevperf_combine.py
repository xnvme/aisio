"""
Combine results from running CPU benchmarks
===========================================

Combine the results from running the CPU benchmarks in `bdevperf_runall.py`.

Retargetable: True
------------------
"""

from argparse import ArgumentParser
from collections import defaultdict
from json import dump as json_dump, load as json_load
from pathlib import Path
from re import match
import logging as log

from cijoe.core.command import Cijoe


def add_args(parser: ArgumentParser):
    parser.add_argument("--results_dir", type=Path, default=None, help="Path to existing directory in which the results should be saved. Note: Already existing results will not be benchmarked again")


def main(args, cijoe: Cijoe):
    """Run benchmarks using bdevperf"""

    artifacts = Path(args.output) / "artifacts"
    bdev_results = artifacts / "bdevperf-results"

    if args.results_dir:
        bdev_results = args.results_dir

    all_results = defaultdict(list)

    for path in bdev_results.glob("*-0.out"):
        REGEX = r".*-thrsib(?P<ht>[01])-freq_.*-stress(?P<st>[01])-SMT(?P<sm>[01])-turbo(?P<tu>[01])"
        m = match(REGEX, path.stem)
        if not m:
            log.error(f"Failed parsing filname({path.stem})")
            return 1

        ht, st, sm, tu = map(int, m.groups())
        label = (
            f"{'U' if ht else 'Not u'}sing thread siblings; "
            f"SMT {'on' if sm else 'off'}; "
            f"stress {'on' if st else 'off'}; "
            f"turbo {'on' if tu else 'off'}"
        )

        with open(path) as file:
            result = json_load(file)

        all_results[label].append(result)

    with open(artifacts / "benchmark-results.json", "x") as file:
        json_dump(all_results, file, indent=2)

    return 0