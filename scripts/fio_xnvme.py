import logging as log
from shlex import quote


REQUIRED_KEYS = ["devices", "iosize", "qdepth", "rw", "backend", "fio_size"]
PREFILL_REQUIRED_KEYS = ["devices", "backend", "fio_size"]
FIO_PREFILL_BS = 131072
FIO_PREFILL_QD = 32


def _escape_pci_addr(pci_addr: str) -> str:
    return pci_addr.replace(":", r"\:")


def fio_xnvme_cmd(bin: str, args: dict) -> str:
    if any(key not in args for key in REQUIRED_KEYS):
        log.error(f"Failed: Missing arguments for {bin}")
        return ""

    if len(args["devices"]) != 1:
        log.error("Failed: fio_xnvme expects exactly one device")
        return ""

    pci_addr = _escape_pci_addr(args["devices"][0])

    parameters = [
        f"{bin}",
        "--name=job0",
        "--thread=1",
        "--direct=1",
        "--group_reporting=1",
        "--ioengine=xnvme",
        f"--xnvme_be={args['backend']}",
        "--xnvme_dev_nsid=1",
        f"--rw={args['rw']}",
        f"--bs={args['iosize']}",
        f"--iodepth={args['qdepth']}",
        f"--io_size={args['fio_size']}",
        f"--filename={quote(pci_addr)}",
        "--output-format=json",
    ]
    return " ".join(parameters)


def fio_xnvme_prefill_cmd(bin: str, args: dict) -> str:
    if any(key not in args for key in PREFILL_REQUIRED_KEYS):
        log.error(f"Failed: Missing prefill arguments for {bin}")
        return ""

    if len(args["devices"]) != 1:
        log.error("Failed: fio_xnvme prefill expects exactly one device")
        return ""

    pci_addr = _escape_pci_addr(args["devices"][0])

    parameters = [
        f"{bin}",
        "--name=prefill",
        "--thread=1",
        "--direct=1",
        "--group_reporting=1",
        "--ioengine=xnvme",
        f"--xnvme_be={args['backend']}",
        "--xnvme_dev_nsid=1",
        "--rw=write",
        f"--bs={FIO_PREFILL_BS}",
        f"--iodepth={FIO_PREFILL_QD}",
        f"--io_size={args['fio_size']}",
        f"--filename={quote(pci_addr)}",
        "--output-format=json",
    ]
    return " ".join(parameters)
