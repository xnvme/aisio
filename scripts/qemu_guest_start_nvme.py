# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Start a qemu-guest with a single NVMe device
============================================

One controller with one namespace, at 0000:01:00.0 as in 'configs/datasets.toml'.

Retargetable: false
-------------------
"""

import errno
import logging as log
from argparse import ArgumentParser
from pathlib import Path

from cijoe.qemu.wrapper import Guest


def add_args(parser: ArgumentParser):
    parser.add_argument("--nvme_img_root", type=str, default=None)
    parser.add_argument("--guest_name", type=str, default=None)


def qemu_nvme_args(nvme_img_root):
    """Return the drives and qemu arguments, with the backing image in 'nvme_img_root'"""
    lbads = 12
    ctrl_id = "nvme0"
    drive_id = f"{ctrl_id}n1"
    root_port = "pcie_root_port1"

    drive = {
        "id": drive_id,
        "file": str(nvme_img_root / f"{drive_id}.img"),
        "format": "raw",
        "if": "none",
        "discard": "on",
        "detect-zeroes": "unmap",
    }
    controller = {
        "id": ctrl_id,
        "serial": "beef0000",
        "bus": root_port,
        "mdts": 7,
        "ioeventfd": "on",
    }
    ns = {
        "id": drive_id,
        "drive": drive_id,
        "bus": ctrl_id,
        "nsid": 1,
        "logical_block_size": 1 << lbads,
        "physical_block_size": 1 << lbads,
    }

    args = [
        "-device",
        f"pcie-root-port,id={root_port},chassis=1,slot=1",
        "-device",
        ",".join(["nvme"] + [f"{k}={v}" for k, v in controller.items()]),
        "-drive",
        ",".join(f"{k}={v}" for k, v in drive.items()),
        "-device",
        ",".join(["nvme-ns"] + [f"{k}={v}" for k, v in ns.items()]),
    ]

    return [drive], args


def main(args, cijoe):
    drive_size = "8G"
    guest_name = args.guest_name or cijoe.getconf("qemu.default_guest")
    if not guest_name:
        log.error("missing config value(qemu.default_guest)")
        return 1

    guest = Guest(cijoe, cijoe.config, guest_name)
    nvme_img_root = Path(args.nvme_img_root or guest.guest_path)

    drives, nvme_args = qemu_nvme_args(nvme_img_root)

    for drive in drives:
        err, _ = cijoe.run_local(f"[ -f {drive['file']} ]")
        if err:
            guest.image_create(drive["file"], drive["format"], drive_size)

    err = guest.start(extra_args=nvme_args)
    if err:
        log.error(f"guest.start() : err({err})")
        return err

    if not guest.is_up():
        log.error("guest.is_up() : False")
        return errno.EAGAIN

    return 0
