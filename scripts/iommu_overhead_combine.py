"""
Combine uPCIe IOMMU overhead benchmark results
==============================================
"""

import errno
import json
import logging as log
from argparse import ArgumentParser
from collections import defaultdict
from pathlib import Path


def add_args(parser: ArgumentParser):
    parser.add_argument("--results-dir", type=Path, default=None)


def avg(values):
    values = [float(value) for value in values]
    return sum(values) / len(values)


def pct_delta(base, value):
    if not base:
        return None
    return (value - base) / base * 100.0


def load_results(results_dir):
    grouped = defaultdict(list)
    for path in results_dir.glob("*/*.json"):
        with path.open() as jfd:
            item = json.load(jfd)
        key = (
            item["label"],
            item["runner"],
            item["rw"],
            int(item["iosize"]),
            int(item["iodepth"]),
        )
        grouped[key].append(item)
    return grouped


def combine_group(entries):
    first = entries[0]
    iops = avg(entry["iops"] for entry in entries)
    mibs = avg(entry["mibs"] for entry in entries)

    result = {
        "label": first["label"],
        "driver": first["driver"],
        "iommu": first["iommu"],
        "runner": first["runner"],
        "rw": first["rw"],
        "iosize": int(first["iosize"]),
        "iodepth": int(first["iodepth"]),
        "repeat": len(entries),
        "runtime": first["runtime"],
        "cpumask": first["cpumask"],
        "iops": iops,
        "mibs": mibs,
    }

    if first["runner"] == "fio":
        result["lat_ns"] = avg(entry["lat_ns"] for entry in entries)
        result["tail_lat_ns"] = {}
        for name in ["p99_9", "p99_99", "p99_999"]:
            result["tail_lat_ns"][name] = avg(
                entry["tail_lat_ns"][name] for entry in entries
            )

    return result


def pair_results(combined):
    indexed = {}
    for result in combined:
        key = (result["runner"], result["rw"], result["iosize"], result["iodepth"])
        indexed.setdefault(key, {})[result["label"]] = result

    items = []
    for key in sorted(indexed, key=lambda item: (item[1], item[2], item[0], item[3])):
        pair = indexed[key]
        if "uio" not in pair or "vfio" not in pair:
            continue

        runner, rw, iosize, iodepth = key
        uio = pair["uio"]
        vfio = pair["vfio"]
        item = {
            "runner": runner,
            "rw": rw,
            "iosize": iosize,
            "iodepth": iodepth,
            "uio": uio,
            "vfio": vfio,
            "iops_delta_pct": pct_delta(uio["iops"], vfio["iops"]),
            "mibs_delta_pct": pct_delta(uio["mibs"], vfio["mibs"]),
        }

        if runner == "fio":
            item["lat_delta_pct"] = pct_delta(uio["lat_ns"], vfio["lat_ns"])
            item["tail_lat_delta_pct"] = {
                name: pct_delta(uio["tail_lat_ns"][name], vfio["tail_lat_ns"][name])
                for name in ["p99_9", "p99_99", "p99_999"]
            }

        items.append(item)

    return items


def main(args, cijoe):
    artifacts = Path(args.output) / "artifacts"
    results_dir = args.results_dir or artifacts / "iommu-overhead"
    if not results_dir.exists():
        log.error(f"Missing IOMMU overhead results directory: {results_dir}")
        return errno.ENOENT

    groups = load_results(results_dir)
    if not groups:
        log.error(f"No IOMMU overhead result JSON files found in {results_dir}")
        return errno.ENOENT

    combined = [combine_group(entries) for entries in groups.values()]
    items = pair_results(combined)
    if not items:
        log.error("No matching UIO/VFIO IOMMU overhead result pairs found")
        return errno.ENOENT

    payload = {"uPCIe IOMMU Overhead": items}

    with (artifacts / "benchmark-results.json").open("w") as jfd:
        json.dump(payload, jfd, indent=2)

    return 0
