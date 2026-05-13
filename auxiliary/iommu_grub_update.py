#!/usr/bin/env python3
"""
Update /etc/default/grub for the IOMMU overhead benchmark.
"""

import re
import sys
from pathlib import Path


mode = sys.argv[1]
if mode not in ("on", "off"):
    raise SystemExit(f"unsupported mode: {mode}")

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
    "intel_iommu=on",
    "amd_iommu=on",
}


def update_value(match):
    value = match.group("value").strip()
    tokens = [t for t in value.split() if t not in DROP_TOKENS]
    tokens.append(token)
    return 'GRUB_CMDLINE_LINUX_DEFAULT="' + " ".join(tokens) + '"'


updated, count = re.subn(
    r'^GRUB_CMDLINE_LINUX_DEFAULT="(?P<value>[^"]*)"',
    update_value,
    text,
    count=1,
    flags=re.MULTILINE,
)
if count == 0:
    tokens = [token]
    updated = (
        text.rstrip() + '\nGRUB_CMDLINE_LINUX_DEFAULT="' + " ".join(tokens) + '"\n'
    )

grub.write_text(updated)
