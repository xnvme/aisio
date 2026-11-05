#!/usr/bin/env python3
# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Whether a commit on main releases a version, and the notes to release it with

Given the subject of the commit, 'ver: bump to vYY.MM', this checks that YY.MM
is [aisio] release in configs/aisio.toml and that CHANGELOG.md has a section
for it, writes that section to stdout as the release notes, and
'version=YY.MM' to $GITHUB_OUTPUT. It exits non-zero, saying why, when any of
that is not so.
"""

import os
import re
import sys
import tomllib
from pathlib import Path

SUBJECT = re.compile(r"^ver: bump to v(\d{2}\.\d{2}(?:\.\d+)?)$")


def notes_for(changelog: str, version: str) -> str:
    """The text of the '## <version>' section, or '' when there is none"""

    section = re.search(
        rf"^## {re.escape(version)}\n(.*?)(?=^## |\Z)", changelog, re.M | re.S
    )
    return section.group(1).strip() if section else ""


def check(subject: str, root: Path):
    """The version and its notes; raises ValueError saying what is wrong"""

    bump = SUBJECT.match(subject.strip())
    if not bump:
        raise ValueError(f"not a version bump: {subject!r}")
    version = bump.group(1)

    config = tomllib.loads((root / "configs/aisio.toml").read_text())
    found = config.get("aisio", {}).get("release")
    if found != version:
        raise ValueError(
            f"the commit bumps to {version}, but [aisio] release is"
            f" {found if found else 'missing'}"
        )

    notes = notes_for((root / "CHANGELOG.md").read_text(), version)
    if not notes:
        raise ValueError(f"CHANGELOG.md has no '## {version}' section")

    return version, notes


def main():
    try:
        version, notes = check(sys.argv[1], Path.cwd())
    except (IndexError, ValueError) as exc:
        print(f"release: {exc}", file=sys.stderr)
        return 1

    print(notes)
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write(f"version={version}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
