# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Shared helpers for IOMMU boot-mode handling
===========================================
"""

import errno
import logging as log
import re

# Holds one entry per IOMMU unit the kernel registered. Neither intel_iommu=off
# nor amd_iommu=off gets as far as registering one, so it is empty then.
IOMMU_SYSFS = "/sys/class/iommu"
# uPCIe's iommufd path maps its hugetlb heap with IOMMU_IOAS_MAP_FILE, which
# Linux 6.13 added. On an older kernel the open fails with EOPNOTSUPP.
IOMMUFD_MAP_FILE_KERNEL = (6, 13)
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


def kernel_release_version(release):
    """(major, minor) of a 'uname -r' string such as '6.8.12-dmabuf'."""
    match = re.match(r"(\d+)\.(\d+)", release.strip())
    if not match:
        raise ValueError(f"unrecognized kernel release: {release!r}")
    return int(match.group(1)), int(match.group(2))


def kernel_supports_iommufd_map_file(release):
    return kernel_release_version(release) >= IOMMUFD_MAP_FILE_KERNEL


def check_vfio_kernel(cijoe):
    """Refuse a vfio run on a kernel whose iommufd cannot map uPCIe's heap."""
    err, state = cijoe.run("uname -r")
    if err:
        log.error(f"Failed reading the target's kernel release: {state.output()}")
        return err

    lines = state.output().strip().splitlines()
    release = lines[-1] if lines else ""
    try:
        supported = kernel_supports_iommufd_map_file(release)
    except ValueError as exc:
        log.error(str(exc))
        return errno.EINVAL
    if not supported:
        need = ".".join(map(str, IOMMUFD_MAP_FILE_KERNEL))
        log.error(
            f"vfio runs use the iommufd path, which needs Linux {need} or newer "
            f"for IOMMU_IOAS_MAP_FILE, but the target runs {release}"
        )
        return errno.EOPNOTSUPP

    return 0
