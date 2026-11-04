# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Prepare the drive holding the llama model: file system and model
================================================================

For tasks/bench_llama_load.yaml. Makes the drive at --pci_addr ready for a
run, from whatever state it is in: binds it to the kernel's nvme driver,
makes a fresh XFS labelled --label on its namespace, mounts it at
--mountpoint, and copies the model into its 'models' directory. No other
controller is touched.

It stops before writing anything when the drive is not usable for this: no
such PCI device, no namespace once bound, a namespace mounted anywhere but at
--mountpoint, or one holding the root file system.

The model is the configuration section --section: 'files', lines as
'sha256sum' prints them, and 'source_dir', a known-good copy on the machine.
Each file is copied and must match its checksum. Nothing is downloaded; a
machine without the copy fails here, before the drive is formatted.

Retargetable: True
------------------
"""

import errno
import logging as log
import time
from argparse import ArgumentParser


def add_args(parser: ArgumentParser):
    parser.add_argument("--pci_addr", type=str, required=True)
    parser.add_argument("--mountpoint", type=str, required=True)
    parser.add_argument("--label", type=str, required=True)
    parser.add_argument("--section", type=str, required=True)
    parser.add_argument("--timeout", type=int, default=30)


def namespace(cijoe, pci_addr, timeout):
    """The block device of the controller's namespace, once the kernel has it"""

    # With native multipath the head's 'device' is the subsystem, and only the
    # paths under /sys/block/<ns>/multipath lead to the controller's address
    find = (
        "for blk in /sys/block/nvme*n*; do"
        ' case "${blk##*/}" in *c*) continue ;; esac;'
        ' for dev in "$blk" "$blk"/multipath/*; do'
        f' case "$(readlink -f "$dev/device")" in */{pci_addr}/*)'
        ' echo "/dev/${blk##*/}" ;; esac;'
        " done; done | sort -u"
    )
    for _ in range(timeout):
        err, state = cijoe.run(find)
        if not err and state.output().split():
            return state.output().split()[0]
        time.sleep(1)

    return None


def model_files(cijoe, section):
    """The model's files as (sha256, name), all present in source_dir"""

    model = cijoe.getconf(section, {})
    files, src = model.get("files", []), model.get("source_dir", "")
    if not files or not src:
        log.error(f"{section}: needs 'files' and 'source_dir'")
        return None, None

    pairs = [line.split() for line in files]
    for _, name in pairs:
        if cijoe.run(f"test -f {src}/{name}")[0]:
            log.error(f"{name}: no copy at {src}")
            return None, None

    return src, pairs


def usable(cijoe, args, bdev):
    """Whether the namespace may be formatted: not root, mounted nowhere else"""

    _, state = cijoe.run(f"lsblk -nro MOUNTPOINTS {bdev}")
    for target in state.output().split():
        if target == "/":
            log.error(f"{bdev} holds the root file system; not touching it")
            return False
        if target != args.mountpoint:
            log.error(f"{bdev} is mounted at {target}; not touching it")
            return False

    return True


def main(args, cijoe):
    if cijoe.run(f"test -e /sys/bus/pci/devices/{args.pci_addr}")[0]:
        log.error(f"no PCI device at {args.pci_addr}")
        return errno.ENODEV

    src, pairs = model_files(cijoe, args.section)
    if not pairs:
        return errno.ENOENT

    err, _ = cijoe.run(f"devbind --device {args.pci_addr} --bind nvme")
    if err:
        return err

    bdev = namespace(cijoe, args.pci_addr, args.timeout)
    if not bdev:
        log.error(f"{args.pci_addr} has no namespace after {args.timeout}s")
        return errno.ENODEV
    if not usable(cijoe, args, bdev):
        return errno.EBUSY

    cijoe.run(f"umount {args.mountpoint}")
    err, _ = cijoe.run(f"mkfs.xfs -f -m reflink=0 -L {args.label} {bdev}")
    if err:
        return err
    cijoe.run(f"mkdir -p {args.mountpoint}")
    err, _ = cijoe.run(f"mount -o noatime {bdev} {args.mountpoint}")
    if err:
        return err

    dst = f"{args.mountpoint}/models"
    cijoe.run(f"mkdir -p {dst}")
    for sha256, name in pairs:
        err, _ = cijoe.run(f"cp {src}/{name} {dst}/{name}")
        if err:
            return err
        err, _ = cijoe.run(f"echo '{sha256}  {name}' | (cd {dst} && sha256sum -c)")
        if err:
            log.error(f"{name}: the copy from {src} does not match its checksum")
            return errno.EIO

    err, _ = cijoe.run(f"sync; df -h {args.mountpoint}; ls -l {dst}")

    return err
