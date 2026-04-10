def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def create_fio_job(
        pci_addr: str,
        iosize: int,
        depth: int,
        runtime: int,
        rw: str,
        backend: str,
        fio_size: str,
        time_based: bool = True,
) -> str:
    """
    Create a fio job string for a single xNVMe-backed benchmark point.
    """

    escaped_pci_addr = pci_addr.replace(":", r"\:")

    config = [
        "[global]",
        "thread=1",
        "direct=1",
        "group_reporting=1",
        "ioengine=xnvme",
        f"xnvme_be={backend}",
        "xnvme_dev_nsid=1",
        f"rw={rw}",
        f"bs={iosize}",
        f"iodepth={depth}",
        f"size={fio_size}",
        f"filename={escaped_pci_addr}",
    ]

    if time_based:
        config += [
            "time_based=1",
            f"runtime={runtime}",
        ]
    else:
        config += [
            f"io_size={fio_size}",
        ]

    return "\n".join(config + ["", "[job0]"])


def fio_xnvme_cmd(bin: str, fio_job: str) -> str:
    return f"printf %s {sh_quote(fio_job)} | {bin} - --output-format=json"
