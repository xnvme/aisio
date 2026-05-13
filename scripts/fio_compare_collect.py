"""
Collect FIO/xNVMe compare raw results into a single JSON document
===============================================================

Retargetable: False
-------------------
"""

from argparse import ArgumentParser
from collections import defaultdict
from json import dump as json_dump, load as json_load
from pathlib import Path
from re import match
import logging as log

def add_args(parser: ArgumentParser):
    parser.add_argument(
        "--results_dirs",
        "--results-dirs",
        nargs="+",
        type=Path,
        required=True,
        help="Directories containing raw .out files for each workload",
    )
    parser.add_argument(
        "--output_path",
        "--output-path",
        type=Path,
        required=True,
        help="Path for the final merged benchmark-results.json",
    )


def main(args, cijoe):
    output_path = args.output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_results = defaultdict(list)
    include_all = ["cpu_freqs", "iops", "mibs", "cpu_usage"]

    for results_dir in args.results_dirs:
        if not results_dir.exists():
            log.error(f"Failed: missing raw results dir({results_dir})")
            return 1

        err = collect_results(results_dir, all_results, include_all)
        if err:
            return err

    final_results = {
        label: sorted(rows, key=sort_key)
        for label, rows in all_results.items()
    }

    if output_path.exists():
        output_path.unlink()

    with output_path.open("w") as handle:
        json_dump(final_results, handle, indent=2)

    return 0


def collect_results(results_dir: Path, all_results: dict, include_all: list[str]) -> int:
    for path in sorted(results_dir.glob("*-0.out")):
        label = parse_label(path.stem)
        if label is None:
            log.error(f"Failed parsing filename({path.stem})")
            return 1

        repeated_results = []
        for run in sorted(results_dir.glob(f"{path.stem[:-1]}*")):
            with run.open("r") as handle:
                repeated_results.append(json_load(handle))

        err, result = merge_dicts(repeated_results, include_all)
        if err:
            log.error("Failed: merge_dicts()")
            return err

        result["iops"] = avg_stddev(result["iops"])
        result["mibs"] = avg_stddev(result["mibs"])
        result["cpu_usage"] = avg_stddev(result["cpu_usage"])
        all_results[label].append(result)

    return 0


def parse_label(stem: str) -> str | None:
    regex = r".*-thrsib(?P<ht>[01])-freq_.*-stress(?P<st>[01])-SMT(?P<sm>[01])-turbo(?P<tu>[01])-\d"
    parsed = match(regex, stem)
    if not parsed:
        return None

    ht, st, sm, tu = map(int, parsed.groups())
    return (
        f"{'U' if ht else 'Not u'}sing thread siblings; "
        f"SMT {'on' if sm else 'off'}; "
        f"stress {'on' if st else 'off'}; "
        f"turbo {'on' if tu else 'off'}"
    )


def avg_stddev(ns: list[int | float]):
    avg = sum(ns) / len(ns)
    stddev = (sum((x - avg) ** 2 for x in ns) / len(ns)) ** 0.5
    return avg, stddev


def merge_dicts(dicts: list[dict], include_all: list[str]) -> tuple[int, dict]:
    first, merged = dicts[0], {}
    keys = set(first.keys())

    if not all(set(d.keys()) == keys for d in dicts):
        failed = next(d for d in dicts if set(d.keys()) != keys)
        log.error(f"Error: Expected keys of all dicts to be equal: {set(failed.keys())} != {keys}")
        return 1, None

    for key in keys:
        if key in include_all:
            merged[key] = [d[key] for d in dicts]
        else:
            if not all(d[key] == first[key] for d in dicts):
                log.error(f"Error: Expected all values for non-excluded key({key}) to be equal")
                return 1, None
            merged[key] = first[key]

    return 0, merged


def sort_key(row: dict) -> tuple:
    return (
        row.get("device_bdf", ""),
        row.get("rw", ""),
        row.get("iosize", 0),
        row.get("qdepth", 0),
        row.get("backend", ""),
        row.get("ncpus", 0),
        row.get("ndevs", 0),
    )
