# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause
"""
Refuse to take a drive the system is using
==========================================

For every NVMe controller in 'devices', by PCI address, as arguments or
space-separated within one, finds the namespaces the kernel has for it and
fails when any of them, or anything stacked on them, such as a partition, an
LVM or LUKS volume or swap, is in use, other than at 'mountpoint', or is held
by another device, such as an LVM volume group or an md array, mounted or not. Run it
before a step binds the controllers to a user-space driver or formats them,
so the system's own disk is never taken. A controller already off the
kernel's driver has no namespaces and passes.

Retargetable: True
------------------
"""

import logging as log
import re
from argparse import ArgumentParser

# a full PCI address; one without its domain would match no sysfs path and
# pass as a controller off the kernel's driver
PCI_ADDR = re.compile(r"^[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]$")


def add_args(parser: ArgumentParser):
    parser.add_argument("--devices", type=str, default=[], nargs="+")
    parser.add_argument("--mountpoint", type=str, default="")


def namespaces(cijoe, pci_addr):
    """The block devices of the controller's namespaces, by its PCI address, or
    None when they cannot be read. With native multipath the hidden path disks,
    nvme<X>c<Y>n<Z>, have no device node and are skipped; only the paths under
    the head's /sys/block/<ns>/multipath lead to the address, so both are
    followed."""

    err, state = cijoe.run(
        "test -d /sys/block || exit 1;"
        ' for blk in /sys/block/nvme*n*; do case "${blk##*/}" in *c*) continue ;; esac;'
        ' for dev in "$blk" "$blk"/multipath/*; do'
        f' case "$(readlink -f "$dev/device")" in */{pci_addr}/*) echo "/dev/${{blk##*/}}" ;; esac;'
        " done; done | sort -u"
    )
    return state.output().split() if not err else None


def in_use(cijoe, bdev, mountpoint):
    """What holds 'bdev' or anything stacked on it, other than 'mountpoint'."""

    err, state = cijoe.run(f"lsblk -nro MOUNTPOINTS {bdev}")
    if err:
        return [f"lsblk failed on {bdev}"]
    # raw output escapes the newline between a device's several mountpoints
    mounts = state.output().replace("\\x0a", "\n").split("\n")
    uses = [m for m in mounts if m.strip() and m.strip() != mountpoint]
    name = bdev.rsplit("/", 1)[1]
    _, state = cijoe.run(
        f"ls -A /sys/block/{name}/holders /sys/block/{name}/{name}p*/holders 2>/dev/null | grep -v ':$'"
    )
    return uses + [f"holder {h}" for h in state.output().split()]


def main(args, cijoe):
    if not args.devices:
        log.error("no devices given")
        return 1
    held = {}
    addrs = [d for arg in args.devices for d in arg.split()]
    for pci_addr in addrs:
        if not PCI_ADDR.match(pci_addr):
            held[pci_addr] = [
                "not a full PCI address, domain included, such as 0000:01:00.0"
            ]
    for pci_addr in (a for a in addrs if a not in held):
        found = namespaces(cijoe, pci_addr)
        if found is None:
            held[pci_addr] = ["its namespaces could not be read"]
            continue
        for bdev in found:
            uses = in_use(cijoe, bdev, args.mountpoint)
            if uses:
                held[f"{pci_addr} ({bdev})"] = uses
    for device, uses in held.items():
        log.error(f"{device} is in use at {', '.join(uses)}; refusing to take it")
    return 1 if held else 0
