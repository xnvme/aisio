"""
Run full-device trim for fio/xNVMe compare workflows
====================================================

Retargetable: True
------------------
"""

from argparse import ArgumentParser
import logging as log
import re

from cijoe.core.command import Cijoe


def add_args(parser: ArgumentParser):
    parser.add_argument("--backend", type=str, required=True)
    parser.add_argument("--device", type=str, required=True)


def _parse_namespace_info(output: str) -> tuple[str, int] | None:
    nsid_match = re.search(r"^\s+nsid:\s+(?P<nsid>\S+)", output, re.MULTILINE)
    nsect_match = re.search(r"^\s+nsect:\s+(?P<nsect>\S+)", output, re.MULTILINE)
    if not nsid_match or not nsect_match:
        return None

    return nsid_match.group("nsid"), int(nsect_match.group("nsect"), 0)


def main(args, cijoe: Cijoe):
    err, state = cijoe.run(f"xnvme info --be {args.backend} {args.device}")
    if err:
        log.error("Failed: xnvme info")
        return err

    namespace = _parse_namespace_info(state.output())
    if namespace is None:
        log.error("Failed: could not discover nsid/nsect from xnvme info")
        return 1

    nsid, nsect = namespace
    command = (
        f"xnvme dsm {args.device} --be {args.backend} "
        f"--dev-nsid {nsid} --nsid {nsid} --ad --slba 0x0 --llb {nsect - 1}"
    )
    err, _ = cijoe.run(command)
    if err:
        log.error("Failed: xnvme dsm")
        return err

    return 0
