# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

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
    for path in sorted(results_dir.glob("*/*.json")):
        with path.open() as jfd:
            item = json.load(jfd)
        key = (
            item["label"],
            item["runner"],
            item["rw"],
            int(item["iosize"]),
            int(item["iodepth"]),
            int(item.get("devcount", 1)),
            item.get("dev", ""),
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
        "devcount": int(first.get("devcount", 1)),
        "dev": first.get("dev", ""),
        "repeat": len(entries),
        "runtime": first["runtime"],
        "cpumask": first["cpumask"],
        "iops": iops,
        "mibs": mibs,
    }
    if "backend" in first:
        result["backend"] = first["backend"]

    if first["runner"] == "fio":
        result["lat_ns"] = avg(entry["lat_ns"] for entry in entries)
        result["tail_lat_ns"] = {}
        for name in ["p99_9", "p99_99", "p99_999"]:
            result["tail_lat_ns"][name] = avg(
                entry["tail_lat_ns"][name] for entry in entries
            )

    return result


def aggregate_devices(combined):
    grouped = defaultdict(list)
    for result in combined:
        key = (
            result["label"],
            result["runner"],
            result["rw"],
            result["iosize"],
            result["iodepth"],
            result["devcount"],
        )
        grouped[key].append(result)

    aggregated = []
    for entries in grouped.values():
        first = entries[0]
        # One fio row per device. Summing a group that holds any other number
        # would report the total under a count it does not belong to.
        if first["runner"] == "fio" and len(entries) != first["devcount"]:
            cause = (
                "the results mix different device sets"
                if len(entries) > first["devcount"]
                else "the run did not finish"
            )
            raise ValueError(
                f"{len(entries)} fio rows for a {first['devcount']}-device run "
                f"({first['label']} {first['rw']} "
                f"iosize={first['iosize']} iodepth={first['iodepth']}): {cause}"
            )
        item = {
            "label": first["label"],
            "driver": first["driver"],
            "iommu": first["iommu"],
            "runner": first["runner"],
            "rw": first["rw"],
            "iosize": first["iosize"],
            "iodepth": first["iodepth"],
            "devcount": first["devcount"],
            "repeat": first["repeat"],
            "runtime": first["runtime"],
            "devices": sorted(entry["dev"] for entry in entries if entry.get("dev")),
            "iops": sum(entry["iops"] for entry in entries),
            "mibs": sum(entry["mibs"] for entry in entries),
        }
        if "backend" in first:
            item["backend"] = first["backend"]

        if first["runner"] == "fio":
            item["lat_ns"] = avg(entry["lat_ns"] for entry in entries)
            item["tail_lat_ns"] = {}
            for name in ["p99_9", "p99_99", "p99_999"]:
                item["tail_lat_ns"][name] = avg(
                    entry["tail_lat_ns"][name] for entry in entries
                )

        aggregated.append(item)

    return aggregated


def pair_results(combined):
    indexed = {}
    for result in combined:
        key = (
            result["runner"],
            result["rw"],
            result["iosize"],
            result["iodepth"],
            result.get("devcount", 1),
        )
        indexed.setdefault(key, {})[result["label"]] = result

    items = []
    for key in sorted(
        indexed, key=lambda item: (item[1], item[2], item[4], item[0], item[3])
    ):
        pair = indexed[key]
        if "uio" not in pair or "vfio" not in pair:
            continue
        off = pair["uio"]
        on = pair["vfio"]

        runner, rw, iosize, iodepth, devcount = key
        item = {
            "runner": runner,
            "rw": rw,
            "iosize": iosize,
            "iodepth": iodepth,
            "devcount": devcount,
            "uio": off,
            "vfio": on,
            "iops_delta_pct": pct_delta(off["iops"], on["iops"]),
            "mibs_delta_pct": pct_delta(off["mibs"], on["mibs"]),
        }

        if runner == "fio":
            item["lat_delta_pct"] = pct_delta(off["lat_ns"], on["lat_ns"])
            item["tail_lat_delta_pct"] = {
                name: pct_delta(off["tail_lat_ns"][name], on["tail_lat_ns"][name])
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
    try:
        items = pair_results(aggregate_devices(combined))
    except ValueError as exc:
        log.error(str(exc))
        return errno.EINVAL
    if not items:
        log.error("No matching IOMMU overhead result pairs found")
        return errno.ENOENT

    payload = {"xNVMe/uPCIe IOMMU Overhead": items}

    with (artifacts / "benchmark-results.json").open("w") as jfd:
        json.dump(payload, jfd, indent=2)

    return 0
