#!/usr/bin/env python3
# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Identify the software stack a benchmark ran against.

The plot collectors stamp this onto the figures they emit, so a generated
graph names the xNVMe build that produced it. The configured branch or tag
does not pin that: a checkout sits at some commit on it, and the target may
carry a feature branch. Reading the checkout with ``git rev-parse`` resolves
the commit itself.
"""

import logging as log

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
    Identify the xNVMe checkout the target's binaries were built from, as
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
