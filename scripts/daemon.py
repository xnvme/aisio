# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Start or stop a daemon's systemd unit on the target
===================================================

'start' starts the unit, which for homi and qublk returns once the daemon is
ready, and with 'ready' set also waits until the unit's journal shows that
text; a unit that fails to start, stops first, or does not get ready within
the timeout fails the step. 'stop' stops the unit and fails unless the daemon
exits cleanly; one that had already stopped, or that systemd had to restart,
fails too. Either way what the journal holds from this run of the unit is
copied into the step's output as '<unit>.log'.

Retargetable: True
------------------
"""

import errno
import logging as log
import time
from argparse import ArgumentParser
from pathlib import Path


def add_args(parser: ArgumentParser):
    parser.add_argument("--command", choices=["start", "stop"], required=True)
    parser.add_argument("--unit", type=str, required=True)
    parser.add_argument("--ready", type=str, default="")
    parser.add_argument("--timeout", type=int, default=60)


def show(cijoe, unit, prop):
    _, state = cijoe.run(f"systemctl show -p {prop} --value {unit}")
    return state.output().strip()


def journal(cijoe, unit):
    """What the journal holds from the unit's current or last run"""

    invocation = show(cijoe, unit, "InvocationID")
    _, state = cijoe.run(
        f"journalctl --no-pager -o short-precise _SYSTEMD_INVOCATION_ID={invocation}"
    )
    return state.output()


def collect_log(cijoe, unit):
    dst = Path(cijoe.output_path) / cijoe.output_ident / f"{unit}.log"
    dst.write_text(journal(cijoe, unit))


def start(args, cijoe):
    # A unit that failed before keeps that state, which 'stop' would then read
    cijoe.run(f"systemctl reset-failed {args.unit}")

    err, _ = cijoe.run(f"systemctl start {args.unit}")
    if err:
        log.error(f"{args.unit} did not start")
        collect_log(cijoe, args.unit)
        return err

    for _ in range(args.timeout):
        if show(cijoe, args.unit, "ActiveState") != "active":
            log.error(f"{args.unit} stopped before getting ready")
            collect_log(cijoe, args.unit)
            return errno.EIO
        if args.ready in journal(cijoe, args.unit):
            collect_log(cijoe, args.unit)
            return 0
        time.sleep(1)

    log.error(f"{args.unit} did not log '{args.ready}' within {args.timeout}s")
    collect_log(cijoe, args.unit)
    return errno.ETIMEDOUT


def stop(args, cijoe):
    if show(cijoe, args.unit, "ActiveState") != "active":
        log.error(f"{args.unit} was not running when it was to be stopped")
        collect_log(cijoe, args.unit)
        return errno.EIO

    restarts = show(cijoe, args.unit, "NRestarts")

    err, _ = cijoe.run(f"systemctl stop {args.unit}")
    collect_log(cijoe, args.unit)
    if err:
        log.error(f"{args.unit} did not stop")
        return err

    result = show(cijoe, args.unit, "Result")
    if result != "success" or restarts != "0":
        log.error(f"{args.unit}: result({result}), restarts({restarts})")
        return errno.EIO

    return 0


def main(args, cijoe):
    return start(args, cijoe) if args.command == "start" else stop(args, cijoe)
