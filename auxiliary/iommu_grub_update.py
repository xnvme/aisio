#!/usr/bin/env python3
# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Update /etc/default/grub for the IOMMU overhead benchmark.
"""

import re
import sys
from pathlib import Path

mode = sys.argv[1]
if mode not in ("on", "off"):
    raise SystemExit(f"unsupported mode: {mode}")

# Strict invalidation only means anything on an IOMMU-on boot; the caller passes
# "0" for the off boot regardless of how the benchmark is configured.
iommu_strict = bool(int(sys.argv[2])) if len(sys.argv) > 2 else False

grub = Path("/etc/default/grub")
backup = Path("/etc/default/grub.aisio-iommu-overhead.bak")
text = grub.read_text()
if not backup.exists():
    backup.write_text(text)

cpuinfo = Path("/proc/cpuinfo").read_text(errors="ignore").lower()
vendor = "amd" if "authenticamd" in cpuinfo else "intel"
token = f"{vendor}_iommu={mode}"

DROP_TOKENS = {
    "intel_iommu=off",
    "amd_iommu=off",
    "iommu=off",
    "iommu=pt",
    "intel_iommu=on",
    "amd_iommu=on",
    "iommu.strict=0",
    "iommu.strict=1",
}


def tokens_for_mode():
    out = [token]
    if mode == "on" and iommu_strict:
        out.append("iommu.strict=1")
    return out


def update_value(match):
    value = match.group("value").strip()
    tokens = [t for t in value.split() if t not in DROP_TOKENS]
    tokens.extend(tokens_for_mode())
    return 'GRUB_CMDLINE_LINUX_DEFAULT="' + " ".join(tokens) + '"'


updated, count = re.subn(
    r'^GRUB_CMDLINE_LINUX_DEFAULT="(?P<value>[^"]*)"',
    update_value,
    text,
    count=1,
    flags=re.MULTILINE,
)
if count == 0:
    updated = (
        text.rstrip()
        + '\nGRUB_CMDLINE_LINUX_DEFAULT="'
        + " ".join(tokens_for_mode())
        + '"\n'
    )

grub.write_text(updated)
