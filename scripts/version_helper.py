#!/usr/bin/env python3
# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Identify the software stack a benchmark ran against.

The benchmark reads the target as it runs and records the result in its ``.out``
file; the plot collectors read the stamp back out of the results they select and
put it on the figures they emit, so a generated graph names the xNVMe build that
produced its data rather than whatever the target holds at plot time. The
configured branch or tag does not pin that build: a checkout sits at some commit
on it, and the target may carry a feature branch. Reading the checkout with
``git rev-parse`` resolves the commit itself.
"""

import logging as log
from collections import defaultdict
from typing import Dict, List

from cijoe.core.command import Cijoe


def origin_of(url: str) -> str:
    """
    Reduce a git remote URL to its ``<owner>/<repo>`` identity, covering both
    the https and the scp-like ssh spelling. URLs that do not carry those two
    trailing components are returned as they are.
    """

    trimmed = url.strip().removesuffix(".git").replace(":", "/")
    parts = [part for part in trimmed.split("/") if part]

    return "/".join(parts[-2:]) if len(parts) >= 2 else trimmed


def xnvme_version(cijoe: Cijoe) -> str:
    """
    Identify the xNVMe checkout on the target as it stands now, as
    ``<owner>/<repo>:<branch>@<sha>``. ``-dirty`` marks uncommitted changes,
    and a checkout without a tracked upstream falls back to the bare commit.
    Returns an empty string when the checkout cannot be read, leaving the
    stamp off the figure rather than failing the benchmark it annotates.
    """

    path = cijoe.getconf("xnvme.repository.path", "/root/git/xnvme")

    err, state = cijoe.run(f"git -C {path} rev-parse --short HEAD")
    if err:
        log.warning(f"Failed: git rev-parse of xnvme({path}); err({err})")
        return ""
    stamp = state.output().strip()

    err, state = cijoe.run(f"git -C {path} rev-parse --abbrev-ref HEAD")
    branch = state.output().strip() if not err else ""

    if branch and branch != "HEAD":
        err, state = cijoe.run(f"git -C {path} config --get branch.{branch}.remote")
        remote = state.output().strip() if not err else ""

        if remote:
            err, state = cijoe.run(f"git -C {path} remote get-url {remote}")
            if not err and state.output().strip():
                stamp = f"{origin_of(state.output())}:{branch}@{stamp}"

    err, state = cijoe.run(f"git -C {path} status --porcelain --untracked-files=no")
    if not err and state.output().strip():
        stamp = f"{stamp}-dirty"

    return stamp


def target_versions(cijoe: Cijoe) -> Dict[str, str]:
    """
    Identify the software the target runs a benchmark with, as a mapping from
    component to stamp. Recorded in each result file under ``versions``, so the
    build travels with the data it produced.
    """

    return {"xnvme": xnvme_version(cijoe)}


def merge_versions(versions: List[Dict[str, str]]) -> Dict[str, str]:
    """
    Reduce the ``versions`` of several runs to one mapping. Runs span builds when
    a benchmark continues into an existing results directory, and a component
    built differently across them is named by every stamp it carried rather than
    by one of them.
    """

    merged = defaultdict(set)
    for entry in versions:
        for component, stamp in (entry or {}).items():
            if stamp:
                merged[component].add(stamp)

    for component, stamps in merged.items():
        if len(stamps) > 1:
            log.warning(f"Runs span multiple {component} builds: {sorted(stamps)}")

    return {component: ", ".join(sorted(stamps)) for component, stamps in merged.items()}


def version_of(results: List[dict], component: str = "xnvme") -> str:
    """
    Read a component's stamp back out of a set of result files. Returns an empty
    string when none of them recorded one, which is the case for files written
    before the benchmark did so; the figure then carries no stamp instead of one
    read at plot time, which need not describe the build behind the data.
    """

    return merge_versions([res.get("versions") for res in results]).get(component, "")
