"""
Run compare-specific fio/xNVMe prefill
======================================

Retargetable: True
------------------
"""

from argparse import ArgumentParser
import logging as log

from cijoe.core.command import Cijoe

from fio_xnvme import fio_xnvme_prefill_cmd


def add_args(parser: ArgumentParser):
    parser.add_argument("--backend", type=str, required=True)
    parser.add_argument("--device", type=str, required=True)
    parser.add_argument("--fio_size", type=str, required=True)


def main(args, cijoe: Cijoe):
    command = fio_xnvme_prefill_cmd(
        "fio",
        {
            "devices": [args.device],
            "backend": args.backend,
            "fio_size": args.fio_size,
        },
    )
    if not command:
        log.error("Failed: could not construct fio_xnvme prefill command")
        return 1

    err, _ = cijoe.run(command)
    if err:
        log.error("Failed: fio_xnvme prefill")
        return err

    return 0
