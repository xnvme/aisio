"""
Visualize the benchmarks
========================

Parse the results from running scripts/bench_runall.py from JSON format, and
create the HTML file, which visualizes the data.

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
    parser.add_argument("--html_path", type=Path, default=None, help="Path to output HTML")
    parser.add_argument("--template", type=str, default="benchmark-io")


def main(args, cijoe):
    """Visualize the benchmark results"""

    artifacts = Path(args.output) / "artifacts"
    json_path = args.path if args.path else artifacts / "benchmark-results.json"
    html_path = args.html_path if args.html_path else artifacts / "benchmark-results.html"

    if not json_path.exists():
        log.error(f"Failed: could not find benchmark results on path({json_path})")
        return 1

    with open(json_path, "r") as file:
        results = json.load(file)

    datasets = convert_to_data(results)
    cpu_control_warning = any(
        not row.get("cpu_control_supported", True)
        for dataset in datasets
        for row in dataset["data"]
    )

    cuda_bandwidth = ""
    bandwidth_path = artifacts / "cuda-sample-p2p-bandwidth"

    if args.template == "benchmark-pcie" and bandwidth_path.exists():
        with open(artifacts / "cuda-sample-p2p-bandwidth", "r") as file:
            cuda_bandwidth = file.read()

    template_resource = get_resources().get("templates", {}).get(args.template, {})
    if not template_resource:
        log.error(f"Failed: could not find template resource({args.template})")
        return 1

    template_path = Path(template_resource.path).parent

    template_loader = jinja2.FileSystemLoader(template_path)
    template_env = jinja2.Environment(loader=template_loader)

    template = template_env.get_template(f"{args.template}.jinja2")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    with html_path.open("w") as body:
        body.write(template.render({
            "datasets": datasets,
            "cuda_bandwidth": cuda_bandwidth,
            "cpu_control_warning": cpu_control_warning,
        }))

    return 0


def convert_to_data(all_results: dict) -> list:
    """
    Convert the format of the results to fit the visualisation.

    Converts the results from having the form:
        {
          label1: [...data],
          label2: [...data],
        }
    To having form:
        [
          { label: label1, data: [...data] },
          { label: label2, data: [...data] },
        ]

    For cross-language compatibility, booleans are converted to integers, as
    Python spells (true, false) capitalized.
    """

    datasets = []

    for label, results in all_results.items():
        data = [{k:(int(v) if isinstance(v, bool) else v) for k,v in res.items()} for res in results]
        datasets.append({ "label": label, "data": data })

    return datasets
