"""
Configure and verify IOMMU boot mode
====================================

This script edits `/etc/default/grub` on the CIJOE target, regenerates the
boot loader config, and verifies the active boot mode after reboot.
"""

import errno
import logging as log
import shlex
from argparse import ArgumentParser
from pathlib import Path

from cijoe.core.resources import get_resources

from iommu_common import cmdline_has_iommu_off, dmesg_indicates_iommu_enabled

GRUB_UPDATE_REMOTE = "/tmp/aisio-iommu-grub-update.py"
GRUB_UPDATE_RESOURCE = "iommu_grub_update"


def add_args(parser: ArgumentParser):
    parser.add_argument(
        "--mode",
        choices=["set-off", "set-on", "verify-off", "verify-on"],
        required=True,
    )


def quote_shell_arg(value):
    """Return a shell-quoted string for remote command construction."""
    return shlex.quote(str(value))


def artifacts_path(args):
    path = Path(args.output) / "artifacts" / "iommu-overhead"
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_target_file(cijoe, path):
    err, state = cijoe.run(f"cat {quote_shell_arg(path)}")
    if err:
        return err, None
    return 0, state.output()


def detect_grub_update_command(cijoe):
    """Return the distro-appropriate command to regenerate grub config."""
    err, _ = cijoe.run("command -v update-grub")
    if not err:
        return "update-grub"
    err, _ = cijoe.run("command -v grub2-mkconfig")
    if not err:
        return "grub2-mkconfig -o /boot/grub2/grub.cfg"
    return None


def upload_grub_update_script(cijoe):
    if not (
        script := get_resources().get("auxiliary", {}).get(GRUB_UPDATE_RESOURCE, {})
    ):
        log.error("Failed retrieving the grub update script from auxiliary files")
        return errno.ENOENT

    cijoe.run(f"rm -f {quote_shell_arg(GRUB_UPDATE_REMOTE)}")

    if not cijoe.put(script.path, GRUB_UPDATE_REMOTE):
        log.error("Failed transferring grub update script from initiator to target")
        return errno.EIO

    return 0


def set_mode(args, cijoe, mode):
    artifacts = artifacts_path(args)
    err, before = read_target_file(cijoe, "/etc/default/grub")
    if err:
        log.error(f"Failed reading /etc/default/grub: {err}")
        return err
    if before is not None:
        (artifacts / f"grub-before-{mode}.txt").write_text(before)

    grub_update = detect_grub_update_command(cijoe)
    if grub_update is None:
        log.error("No update-grub or grub2-mkconfig found on target")
        return errno.ENOENT

    err = upload_grub_update_script(cijoe)
    if err:
        log.error("Failed transferring grub update script")
        return err

    cmd = (
        f"python3 {quote_shell_arg(GRUB_UPDATE_REMOTE)} "
        f"{quote_shell_arg(mode)} && {grub_update}"
    )
    err, state = cijoe.run(cmd)
    (artifacts / f"update-grub-{mode}.txt").write_text(state.output())
    if err:
        log.error(f"Failed updating grub for IOMMU {mode}: {state}")
        return err

    err, after = read_target_file(cijoe, "/etc/default/grub")
    if err:
        log.error(f"Failed reading /etc/default/grub: {err}")
        return err
    if after is not None:
        (artifacts / f"grub-after-{mode}.txt").write_text(after)

    return 0


def verify_mode(args, cijoe, mode):
    artifacts = artifacts_path(args)

    err, cmdline_state = cijoe.run("cat /proc/cmdline")
    if err:
        log.error(f"Failed reading /proc/cmdline: {cmdline_state}")
        return err
    cmdline = cmdline_state.output()

    err, dmesg_state = cijoe.run("dmesg | grep -i -E 'DMAR|IOMMU|AMD-Vi' || true")
    if err:
        log.error(f"Failed reading dmesg: {dmesg_state}")
        return err
    dmesg = dmesg_state.output()

    (artifacts / f"iommu-verify-{mode}.txt").write_text(
        f"=== /proc/cmdline ===\n{cmdline}\n=== dmesg ===\n{dmesg}"
    )

    off_in_cmdline = cmdline_has_iommu_off(cmdline)
    enabled_in_dmesg = dmesg_indicates_iommu_enabled(dmesg)

    if (mode == "off") != off_in_cmdline:
        log.error(f"Expected IOMMU-{mode}, but /proc/cmdline shows the opposite")
        return errno.EINVAL

    if (mode == "on") != enabled_in_dmesg:
        log.error(f"Expected IOMMU-{mode}, but dmesg indicates the opposite")
        return errno.EINVAL

    return 0


def main(args, cijoe):
    if args.mode == "set-off":
        return set_mode(args, cijoe, "off")
    if args.mode == "set-on":
        return set_mode(args, cijoe, "on")
    if args.mode == "verify-off":
        return verify_mode(args, cijoe, "off")
    if args.mode == "verify-on":
        return verify_mode(args, cijoe, "on")
    return errno.EINVAL
