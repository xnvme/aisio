"""
Convert benchmark results to CSV
================================

Convert the results from running scripts/bdevperf_runall.py from JSON format, and
create the html file, which visualises the data.

Retargetable: False
-------------------
"""
import json
import jinja2
import logging as log
from argparse import ArgumentParser
from cijoe.core.resources import get_resources
from pathlib import Path


def add_args(parser: ArgumentParser):
    parser.add_argument("--path", type=Path, default=None, help="Path to results.json")


def main(args, cijoe):
    """Convert the benchmark results to CSV format"""

    artifacts = Path(args.output) / "artifacts"
    json_path = args.path if args.path else artifacts / "benchmark-results.json"
    html_path = artifacts / "benchmark-results.html"

    if not json_path.exists():
        log.error(f"Failed: could not find benchmark results on path({json_path})")
        return 1

    results = {}
    datasets = []

    with open(json_path, "r") as file:
        results = json.load(file)

    for res in results.items():
        datasets.append(convert_to_data(*res))

    template_resource = get_resources().get("templates", {}).get("benchmark-visualisation.html", {})
    if not template_resource:
        log.error("Failed: could not find template resource")
        return 1

    template_path = Path(template_resource.path).parent

    template_loader = jinja2.FileSystemLoader(template_path)
    template_env = jinja2.Environment(loader=template_loader)

    template = template_env.get_template("benchmark-visualisation.html.jinja2")
    with html_path.open("w") as body:
        body.write(template.render({ "datasets": datasets }))

    return 0


def convert_to_data(label: str, results: list[dict]):
    data = []

    for res in results:
        res["iops"] = res["total"]["iops"]
        del res["devices"]
        del res["total"]
        for k, v in res.items():
            if isinstance(v, bool):
                res[k] = int(v)
        data.append(res)

    return {"label": label, "data": data}