# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Shared helpers for IOMMU boot-mode handling
===========================================
"""

import re

# Holds one entry per IOMMU unit the kernel registered. Neither intel_iommu=off
# nor amd_iommu=off gets as far as registering one, so it is empty then.
IOMMU_SYSFS = "/sys/class/iommu"
IOMMU_OFF_CMDLINE_PATTERNS = [
    r"\bintel_iommu=off\b",
    r"\bamd_iommu=off\b",
    r"\biommu=off\b",
]


def iommu_units(cijoe):
    """The IOMMU units in sysfs, as 'ls -A' lists them, or '' when there are none."""
    err, state = cijoe.run(f"ls -A {IOMMU_SYSFS}")
    return "" if err else state.output().strip()


def cmdline_has_iommu_off(text):
    return any(
        re.search(pat, text, re.IGNORECASE) for pat in IOMMU_OFF_CMDLINE_PATTERNS
    )
