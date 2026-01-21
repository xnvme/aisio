"""
Populate block devices using fio
================================

Populate block devices from cijoe config file using fio.

This can be undone by formatting each device using this command:

    ```
    nvme format /dev/nvmeXn1 --ses=1
    ```

Retargetable: True
------------------
"""

from pathlib import Path
import logging as log

from cijoe.core.command import Cijoe

from cpu_freq_helper import CpuFrequencyHelper


def populate_device(cijoe: Cijoe, spdk_path: Path, pcie_addr: str) -> int:
    fio_cmd = (
        f"LD_PRELOAD={Path(spdk_path) / 'build' / 'fio' / 'spdk_nvme'} "
        f"fio "
        f"--name=spdk "
        f'--filename="trtype=PCIe traddr={pcie_addr.replace(":",".")} ns=1" '
        f"--ioengine=spdk "
        f"--direct=1 "
        f"--rw=write "
        f"--size=100% "
        f"--bs=131072 "
        f"--iodepth=128 "
        f"--output-format=json "
        f"--thread=1 "
    )

    err, _ = cijoe.run(fio_cmd)
    if err:
        log.error(f"Failed: {fio_cmd}")
        return err

    return 0


def main(args, cijoe: Cijoe):
    """Populate block devices using bdevperf"""

    devices: list = cijoe.getconf("devices")

    spdk_path = cijoe.getconf("spdk.repository.path", None)
    if not spdk_path:
        log.error("Failed: Missing SPDK repository path in config")
        return 1

    spdk_path = Path(spdk_path)

    cfm = CpuFrequencyHelper(cijoe)

    err = cfm.toggle_smt(True)
    if err:
        log.error("Failed: cfm.toggle_smt(true)")
        return err

    err = cfm.toggle_turbo(True)
    if err:
        log.error("Failed: cfm.toggle_turbo(true)")
        return err

    for device in devices:
        err = populate_device(cijoe, spdk_path, device["pci_addr"])
        if err:
            log.error(f"Failed: populate_device({device['pci_addr']}); err({err})")
            return err

    return 0
