# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Unlock root SSH on a nosi guest
===============================

nosi images lock root; this opens root SSH through the passwordless-sudo 'odus'
operator. A no-op when root SSH already works. It sets a fixed root password and
enables password login, so it is only for throwaway guests.

Retargetable: False
-------------------
"""

import logging as log
import time
from argparse import ArgumentParser

ROOT_PASSWORD = "root"
SSHD_DROPIN = "/etc/ssh/sshd_config.d/00-ci-root.conf"


def add_args(parser: ArgumentParser):
    parser.add_argument("--root", type=str, default="root")
    parser.add_argument("--operator", type=str, default="odus")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--root-probe-timeout", type=int, default=30)


def wait_for_transport(cijoe, transport_name, timeout):
    began = time.time()
    while time.time() - began < timeout:
        err, _ = cijoe.run("true", transport_name=transport_name)
        if not err:
            return True
        time.sleep(5)
    return False


def main(args, cijoe):
    if wait_for_transport(cijoe, args.root, args.root_probe_timeout):
        log.info("root SSH already available; skipping unlock")
        return 0

    if not wait_for_transport(cijoe, args.operator, args.timeout):
        log.error(f"operator transport '{args.operator}' did not come up")
        return 1

    for command in [
        f"echo 'root:{ROOT_PASSWORD}' | sudo chpasswd",
        f"echo 'PermitRootLogin yes' | sudo tee {SSHD_DROPIN}",
        f"echo 'PasswordAuthentication yes' | sudo tee -a {SSHD_DROPIN}",
        "sudo systemctl restart ssh",
    ]:
        err, _ = cijoe.run(command, transport_name=args.operator)
        if err:
            log.error(f"root-unlock command failed: {command}")
            return err

    if not wait_for_transport(cijoe, args.root, args.timeout):
        log.error("root transport did not come up after unlock")
        return 1

    return 0
