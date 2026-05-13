"""
Shared helpers for IOMMU boot-mode handling
===========================================
"""

import re

IOMMU_ENABLED_PATTERNS = [
    r"\bDMAR:\s+IOMMU enabled\b",
    r"\bAMD-Vi:\s+IOMMU enabled\b",
    r"\bIntel-IOMMU:\s+enabled\b",
    r"\bIOMMU enabled\b",
    r"\biommu:\s+Default domain type:\b",
    r"\bAdding to iommu group\b",
    r"\bDMAR:\s+Intel\(R\) Virtualization Technology for Directed I/O\b",
    r"\bDMAR:\s+dmar\d+:\s+Using Queued invalidation\b",
]
IOMMU_DISABLED_PATTERNS = [
    r"\bintel_iommu=off\b",
    r"\bamd_iommu=off\b",
    r"\biommu=off\b",
    r"\bIOMMU disabled\b",
    r"\bIOMMU not enabled\b",
]
IOMMU_OFF_CMDLINE_PATTERNS = [
    r"\bintel_iommu=off\b",
    r"\bamd_iommu=off\b",
    r"\biommu=off\b",
]


def dmesg_indicates_iommu_enabled(text):
    if any(re.search(pat, text, re.IGNORECASE) for pat in IOMMU_DISABLED_PATTERNS):
        return False
    return any(re.search(pat, text, re.IGNORECASE) for pat in IOMMU_ENABLED_PATTERNS)


def cmdline_has_iommu_off(text):
    return any(
        re.search(pat, text, re.IGNORECASE) for pat in IOMMU_OFF_CMDLINE_PATTERNS
    )
