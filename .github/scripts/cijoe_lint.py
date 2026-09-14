#!/usr/bin/env python3
# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Lint the cijoe workflows without a target
=========================================

Loads each workflow as 'cijoe' does before running it: scripts resolve,
templates render against the configs, and each step's 'with' parses.
'cijoe --integrity-check' renders without the 'config' and 'local' keys
and neither loads scripts nor parses 'with'. Without '-c', every
'configs/*.toml' is loaded. Run from the repository root:

  python3 .github/scripts/cijoe_lint.py
"""

import argparse
import sys
import tempfile
from pathlib import Path

from cijoe.cli.cli import create_combined_toml, parse_args
from cijoe.core.resources import Config, Workflow, get_resources


def with_arguments(step):
    """Return the argv cijoe builds from a step's 'with'"""

    arguments = []
    for key, value in step.get("with", {}).items():
        if isinstance(value, list):
            arguments += [f"--{key}", *[f"{el}" for el in value]]
        else:
            if isinstance(value, bool):
                value = str(value).lower()
            arguments += [f"--{key}", f"{value}"]
    return arguments


def cijoe_arguments(path):
    """Return the options cijoe parses when running the workflow at 'path'"""

    argv, sys.argv = sys.argv, ["cijoe", str(path)]
    try:
        _, args = parse_args()
    finally:
        sys.argv = argv
    return args


def lint(path, config, resources):
    """Return the errors cijoe would raise loading the workflow at 'path'"""

    workflow = Workflow(path)
    errors = workflow.load(cijoe_arguments(path), config)
    if errors:
        return errors

    for step in workflow.state["steps"]:
        script = resources["scripts"][step["uses"]]
        try:
            script.load()
        except Exception as exc:
            errors.append(f"step({step['name']}): script({step['uses']}) : {exc}")
            continue

        parser = argparse.ArgumentParser(prog=step["uses"], exit_on_error=False)
        if script.argparser_func:
            script.argparser_func(parser)
        try:
            parser.parse_args(with_arguments(step))
        except (argparse.ArgumentError, SystemExit) as exc:
            errors.append(f"step({step['name']}): with : {exc}")

    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--config", "-c", type=Path, action="append")
    parser.add_argument("workflows", type=Path, nargs="*")
    args = parser.parse_args()

    configs = args.config or sorted(Path("configs").glob("*.toml"))
    workflows = args.workflows or sorted(Path("tasks").glob("*.yaml"))
    resources = get_resources()

    with tempfile.TemporaryDirectory() as tmpdir:
        combined = Path(tmpdir) / "config.toml"
        create_combined_toml(configs, combined)
        config = Config(combined)
        if errors := config.load():
            print("\n".join(errors), file=sys.stderr)
            return 1

        failed = 0
        for path in workflows:
            errors = lint(path, config, resources)
            print(f"{'FAIL' if errors else 'ok':4} {path}")
            for error in errors:
                print(f"     {error}")
            failed += bool(errors)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
