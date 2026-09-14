#!/usr/bin/env python3
# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Print a workflow's step names, less the skipped ones
====================================================

Steps added later still run; skipping a name that is not a step is an error.

  cijoe tasks/setup_nvstack.yaml \
    $(python3 .github/scripts/cijoe_steps.py tasks/setup_nvstack.yaml --skip check_gpu)
"""

import argparse
import sys
from pathlib import Path

import yaml


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("workflow", type=Path)
    parser.add_argument("--skip", nargs="+", default=[])
    args = parser.parse_args()

    names = [
        step["name"] for step in yaml.safe_load(args.workflow.read_text())["steps"]
    ]

    if unknown := sorted(set(args.skip) - set(names)):
        print(f"{args.workflow} has no step(s): {' '.join(unknown)}", file=sys.stderr)
        return 1

    print(" ".join(name for name in names if name not in args.skip))
    return 0


if __name__ == "__main__":
    sys.exit(main())
