#!/usr/bin/env python3
# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Bump the AiSIO release to YY.MM[.N]
===================================

Writes the version to configs/aisio.toml, README.md and
docs/tooling/pyproject.toml, and opens an empty '## YY.MM' section in
CHANGELOG.md. The release workflow refuses an empty section, so the notes must
be written before 'ver: bump to vYY.MM' is merged.

  make bump NEW_VERSION=26.12
"""

import re
import sys
from pathlib import Path

VERSION = re.compile(r"\d{2}\.\d{2}(?:\.\d+)?")

# file, the line holding the version, and how to write it
EDITS = [
    ("configs/aisio.toml", r'^release = "[^"]*"$', 'release = "{}"'),
    ("docs/tooling/pyproject.toml", r'^version = "[^"]*"$', 'version = "{}"'),
    ("README.md", r"This is AiSIO v\S+?\.(?=\s)", "This is AiSIO v{}."),
]


def bump(root: Path, version: str):
    """Write version into root's files; raises ValueError saying what is wrong"""

    if not VERSION.fullmatch(version):
        raise ValueError(f"{version!r} is not YY.MM[.N]")

    for name, pattern, line in EDITS:
        path = root / name
        text, count = re.subn(
            pattern, line.format(version), path.read_text(), flags=re.M
        )
        if count != 1:
            raise ValueError(f"{name}: {count} matches of {pattern!r}, not 1")
        path.write_text(text)

    path = root / "CHANGELOG.md"
    text = path.read_text()
    if not re.search(rf"^## {re.escape(version)}$", text, re.M):
        first = re.search(r"^## ", text, re.M)
        at = first.start() if first else len(text)
        text = f"{text[:at].rstrip()}\n\n## {version}\n\n{text[at:]}".rstrip() + "\n"
        path.write_text(text)


def main():
    try:
        bump(Path.cwd(), sys.argv[1])
    except (IndexError, ValueError) as exc:
        print(f"bump: {exc}", file=sys.stderr)
        return 1

    print(f"Write the '## {sys.argv[1]}' notes in CHANGELOG.md, then commit")
    print(f"with the subject 'ver: bump to v{sys.argv[1]}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
