# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Start or stop a daemon on the target
====================================

'start' runs the command in the background, detached from the SSH session, and
waits until its log shows the 'ready' text; a daemon that exits first, or does
not get ready within the timeout, fails the step. 'stop' sends SIGTERM, waits
for the daemon to exit, and fails unless it exits with status zero; one that
had already exited fails too. Either way the log is copied into the step's
output as '<name>.log'.

The pid, exit status and log live in '<rundir>/<name>.{pid,rc,log}'. A daemon
that logs to syslog rather than stdout and stderr is given 'journal: true'; what
the journal holds from its pid then goes in '<name>.log.journal' beside it.

Retargetable: True
------------------
"""

import errno
import logging as log
import shlex
import time
from argparse import ArgumentParser
from pathlib import Path


def add_args(parser: ArgumentParser):
    parser.add_argument("--command", choices=["start", "stop"], required=True)
    parser.add_argument("--name", type=str, required=True)
    parser.add_argument("--cmd", type=str, default="")
    parser.add_argument("--ready", type=str, default="")
    parser.add_argument("--journal", type=lambda v: v == "true", default=False)
    parser.add_argument("--rundir", type=str, default="/tmp/aisio-daemons")
    parser.add_argument("--timeout", type=int, default=60)


def paths(args):
    base = f"{args.rundir}/{args.name}"
    return f"{base}.pid", f"{base}.rc", f"{base}.log"


def logs(args):
    """The daemon's log files; one with what the journal holds from it, if any"""

    _, _, logfile = paths(args)
    return [logfile, f"{logfile}.journal"] if args.journal else [logfile]


def exists(cijoe, path):
    err, _ = cijoe.run(f"test -e {path}")
    return not err


def read_log(cijoe, args):
    """Return the daemon's log, refreshing what it has in the journal first"""

    pid, _, _ = paths(args)
    if args.journal:
        cijoe.run(
            f"journalctl --no-pager -o short-precise _PID=$(cat {pid})"
            f" > {logs(args)[1]}"
        )
    _, state = cijoe.run(f"cat {' '.join(logs(args))}")
    return state.output()


def collect_log(cijoe, args):
    read_log(cijoe, args)
    for path in logs(args):
        dst = Path(cijoe.output_path) / cijoe.output_ident / Path(path).name
        if not cijoe.get(path, str(dst)):
            log.error(f"could not copy {path} from the target")


def start(args, cijoe):
    pid, rc, logfile = paths(args)

    if not args.cmd or not args.ready:
        log.error("'start' needs 'cmd' and 'ready'")
        return errno.EINVAL

    err, _ = cijoe.run(
        f"mkdir -p {args.rundir} && rm -f {pid} {rc} {' '.join(logs(args))}"
    )
    if err:
        return err

    # The wrapper outlives the SSH session and records the daemon's exit status,
    # which no later session could otherwise 'wait' for
    wrapper = (
        f"stdbuf -oL -eL {args.cmd} > {logfile} 2>&1 < /dev/null & "
        f"echo $! > {pid}; wait $!; echo $? > {rc}"
    )
    err, _ = cijoe.run(
        f"setsid -f sh -c {shlex.quote(wrapper)} > /dev/null 2>&1 < /dev/null"
    )
    if err:
        return err

    for _ in range(args.timeout):
        if exists(cijoe, rc):
            cijoe.run(f"cat {rc}")
            log.error(f"{args.name} exited before getting ready")
            collect_log(cijoe, args)
            return errno.EIO
        if exists(cijoe, pid) and args.ready in read_log(cijoe, args):
            collect_log(cijoe, args)
            return 0
        time.sleep(1)

    log.error(f"{args.name} did not log '{args.ready}' within {args.timeout}s")
    collect_log(cijoe, args)
    return errno.ETIMEDOUT


def stop(args, cijoe):
    pid, rc, _ = paths(args)

    if not exists(cijoe, pid):
        log.error(f"{args.name} was not started")
        return errno.ENOENT

    if exists(cijoe, rc):
        cijoe.run(f"cat {rc}")
        log.error(f"{args.name} died before it was stopped")
        collect_log(cijoe, args)
        return errno.EIO

    cijoe.run(f"kill -TERM $(cat {pid})")

    for _ in range(args.timeout):
        if exists(cijoe, rc):
            break
        time.sleep(1)
    else:
        log.error(f"{args.name} did not exit within {args.timeout}s of SIGTERM")
        cijoe.run(f"kill -KILL $(cat {pid})")
        collect_log(cijoe, args)
        return errno.ETIMEDOUT

    collect_log(cijoe, args)

    err, _ = cijoe.run(f"test $(cat {rc}) -eq 0")
    if err:
        cijoe.run(f"cat {rc}")
        log.error(f"{args.name} exited with a non-zero status")
        return errno.EIO

    return 0


def main(args, cijoe):
    return start(args, cijoe) if args.command == "start" else stop(args, cijoe)
