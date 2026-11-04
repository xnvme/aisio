#!/usr/bin/env python3
# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause
"""
drive_guard against a stand-in host: it refuses a controller holding the root
file system, swap, or a volume stacked on it, and one mounted elsewhere than
the task's mountpoint, one held by another device unmounted, and one whose
namespaces cannot be read; it lets through one mounted only there, one with
nothing mounted, and one already off the kernel's driver.

    python3 tests/test_drive_guard.py
"""

import subprocess
import sys
import tempfile
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import drive_guard  # noqa: E402


class State:
    def __init__(self, text):
        self.text = text

    def output(self):
        return self.text


class Host:
    """Controllers by PCI address, each with its namespaces and what lsblk lists
    on them, and the devices holding a namespace."""

    def __init__(self, controllers, holders=None):
        self.controllers, self.holders = controllers, holders or {}

    def run(self, command):
        if "for blk in /sys/block" in command:
            # the guard skips the hidden path disks itself
            assert "*c*) continue" in command
            pci = command.split("in */", 1)[1].split("/*", 1)[0]
            return 0, State("\n".join(self.controllers.get(pci, {})))
        if command.startswith("ls -A /sys/block/"):
            name = command.split("/sys/block/", 1)[1].split("/", 1)[0]
            return 0, State("\n".join(self.holders.get(name, [])))
        if command.startswith("lsblk -nro MOUNTPOINTS "):
            bdev = command.rsplit(" ", 1)[1]
            for namespaces in self.controllers.values():
                if bdev in namespaces:
                    return 0, State(namespaces[bdev])
        return 1, State("")


class Shell:
    """Runs the guard's sysfs query in a real shell against a made-up /sys/block."""

    def __init__(self, root):
        self.root = root

    def run(self, command):
        done = subprocess.run(
            ["bash", "-c", command.replace("/sys/block", f"{self.root}/sys/block")],
            capture_output=True,
            text=True,
        )
        return done.returncode, State(done.stdout)


def multipath(root):
    """A native-multipath namespace: the head nvme0n1, whose path under
    multipath/ leads to the controller, and the hidden path disk nvme0c0n1,
    whose own device link does."""

    ctrl = root / "devices" / "0000:01:00.0" / "nvme" / "nvme0"
    ctrl.mkdir(parents=True)
    head, path = (
        root / "sys" / "block" / "nvme0n1",
        root / "sys" / "block" / "nvme0c0n1",
    )
    (head / "multipath").mkdir(parents=True)
    path.mkdir(parents=True)
    (path / "device").symlink_to(ctrl)
    (head / "multipath" / "nvme0c0n1").symlink_to(path)
    return drive_guard.namespaces(Shell(root), "0000:01:00.0")


def check(name, ok):
    print(f"{'ok' if ok else 'FAIL'} {name}")
    return ok


def guard(controllers, devices, mountpoint="", **host):
    return drive_guard.main(
        Namespace(devices=devices, mountpoint=mountpoint), Host(controllers, **host)
    )


def main():
    system = {"0000:01:00.0": {"/dev/nvme0n1": "\n/boot/efi\n/\n"}}
    with tempfile.TemporaryDirectory() as tmp:
        found = multipath(Path(tmp))
    with tempfile.TemporaryDirectory() as tmp:
        # no /sys/block at all, as when sysfs is not mounted
        unreadable = drive_guard.namespaces(Shell(Path(tmp)), "0000:01:00.0") is None
    results = [
        check(
            "multipath: the head, not the hidden path disk without a node",
            found == ["/dev/nvme0n1"],
        ),
        check("the system disk is refused", guard(system, ["0000:01:00.0"]) == 1),
        check(
            "swap is refused",
            guard({"0000:02:00.0": {"/dev/nvme1n1": "[SWAP]\n"}}, ["0000:02:00.0"])
            == 1,
        ),
        check(
            "a volume stacked on it is refused",
            guard({"0000:02:00.0": {"/dev/nvme1n1": "\n\n/home\n"}}, ["0000:02:00.0"])
            == 1,
        ),
        check(
            "mounted elsewhere than the task's mountpoint is refused",
            guard(
                {"0000:02:00.0": {"/dev/nvme1n1": "/data\n"}},
                ["0000:02:00.0"],
                "/mnt/smoke",
            )
            == 1,
        ),
        check(
            "mounted only at the task's mountpoint passes",
            guard(
                {"0000:02:00.0": {"/dev/nvme1n1": "/mnt/smoke\n"}},
                ["0000:02:00.0"],
                "/mnt/smoke",
            )
            == 0,
        ),
        check(
            "nothing mounted passes",
            guard({"0000:02:00.0": {"/dev/nvme1n1": "\n"}}, ["0000:02:00.0"]) == 0,
        ),
        check(
            "a controller off the kernel's driver passes",
            guard({}, ["0000:03:00.0"]) == 0,
        ),
        check(
            "an unmounted namespace held by a volume group is refused",
            guard(
                {"0000:02:00.0": {"/dev/nvme1n1": "\n"}},
                ["0000:02:00.0"],
                holders={"nvme1n1": ["dm-0"]},
            )
            == 1,
        ),
        check("namespaces that cannot be read are refused, not passed", unreadable),
        check(
            "mounted at the task's mountpoint and elsewhere too is refused",
            guard(
                {"0000:02:00.0": {"/dev/nvme1n1": "/mnt/smoke\\x0a/data\n"}},
                ["0000:02:00.0"],
                "/mnt/smoke",
            )
            == 1,
        ),
        check(
            "an address without its domain is refused, not passed",
            guard({}, ["01:00.0"]) == 1,
        ),
        check(
            "one in use among several, given as one string, is refused",
            guard(
                {**system, "0000:02:00.0": {"/dev/nvme1n1": "\n"}},
                ["0000:02:00.0 0000:01:00.0"],
            )
            == 1,
        ),
    ]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
