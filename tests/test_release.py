#!/usr/bin/env python3
# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause
"""
.github/scripts/release.py, which decides whether a commit on main releases,
.github/scripts/bump.py, which 'make bump' runs to name the next one, and that the release in configs/aisio.toml is the one README.md names and
docs/tooling/pyproject.toml carries, since neither can read it from there.

    python3 tests/test_release.py
"""

import importlib.util
import re
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / f".github/scripts/{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release = load("release")
bump = load("bump")

CHANGELOG = """# Changelog

## 26.11

What 26.11 brings.

* and a list

## 26.10

What came before.
"""

failures = []


def project(tmp, version):
    (tmp / "configs").mkdir(exist_ok=True)
    (tmp / "configs/aisio.toml").write_text(f'[aisio]\nrelease = "{version}"\n')
    (tmp / "CHANGELOG.md").write_text(CHANGELOG)
    return tmp


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    found = release.check("ver: bump to v26.11", project(tmp, "26.11"))
    if found != ("26.11", "What 26.11 brings.\n\n* and a list"):
        failures.append(f"a bump to v26.11 releases {found!r}")

    for subject, version, problem in [
        ("fix(docs): something", "26.11", "not a version bump"),
        ("ver: bump to 26.11", "26.11", "not a version bump"),
        ("ver: bump to v26.11 and more", "26.11", "not a version bump"),
        ("ver: bump to v26.11", "26.12", "release is 26.12"),
        ("ver: bump to v26.12", "26.12", "no '## 26.12' section"),
    ]:
        try:
            release.check(subject, project(tmp, version))
            failures.append(f"{subject!r} against {version} releases")
        except ValueError as exc:
            if problem not in str(exc):
                failures.append(f"{subject!r} against {version}: {exc}")

FILES = (
    "configs/aisio.toml",
    "docs/tooling/pyproject.toml",
    "README.md",
    "CHANGELOG.md",
)


def named_in(root):
    """The release as each of root's files names it"""

    toml = tomllib.loads((root / FILES[0]).read_text())["aisio"]["release"]
    docs = tomllib.loads((root / FILES[1]).read_text())["project"]["version"]
    readme = re.findall(r"This is AiSIO v(\S+?)\.\s", (root / FILES[2]).read_text())
    return toml, docs, readme


# The bump, on a copy of this tree's files, reaches every place the release is named
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    for name in FILES:
        (tmp / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp / name).write_text((ROOT / name).read_text())
    current = named_in(ROOT)[0]
    notes = release.notes_for((ROOT / "CHANGELOG.md").read_text(), current)

    bump.bump(tmp, "99.12")
    bump.bump(tmp, "99.12")
    if named_in(tmp) != ("99.12", "99.12", ["99.12"]):
        failures.append(f"bump: names {named_in(tmp)!r}, not 99.12 everywhere")
    changelog = (tmp / "CHANGELOG.md").read_text()
    if changelog.count("## 99.12\n") != 1:
        failures.append("bump: CHANGELOG.md has not one '## 99.12'")
    elif changelog.index("## 99.12") > changelog.index(f"## {current}"):
        failures.append(f"bump: '## 99.12' is below '## {current}'")
    if release.notes_for(changelog, current) != notes:
        failures.append(f"bump: the '## {current}' notes changed")
    try:
        release.check("ver: bump to v99.12", tmp)
        failures.append("bump: releases with an empty '## 99.12' section")
    except ValueError as exc:
        if "no '## 99.12' section" not in str(exc):
            failures.append(f"bump: {exc}")
    for bad in ("26.1", "v26.12", "26.12-rc1"):
        try:
            bump.bump(tmp, bad)
            failures.append(f"bump: takes {bad!r}")
        except ValueError:
            pass

version, docs, readme = named_in(ROOT)
if docs != version:
    failures.append(f"docs/tooling/pyproject.toml: {docs!r} != {version!r}")
if readme != [version]:
    failures.append(f"README.md: names {readme!r}, not [{version!r}]")
try:
    release.check(f"ver: bump to v{version}", ROOT)
except ValueError as exc:
    failures.append(f"this tree does not release v{version}: {exc}")

for failure in failures:
    print(failure, file=sys.stderr)
sys.exit(1 if failures else 0)
