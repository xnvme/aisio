import json
import logging as log
from argparse import ArgumentParser
from pathlib import Path


REQUIRED_KEYS = ["cpumask", "iopattern", "qdepth", "iosize", "runtime", "config_path", "devices"]


def add_args(parser: ArgumentParser):
    parser.add_argument("--devices", type=str, default=[], nargs="+")
    parser.add_argument("--ndevs", type=int, default=0)
    parser.add_argument("--iopattern", type=str, default="randread")
    parser.add_argument("--qdepth", type=int, default=128)
    parser.add_argument("--iosize", type=int, default=512)
    parser.add_argument("--runtime", type=int, default=10)
    parser.add_argument("--cpumask", type=str, default="0x1")


def create_config(devices: list, path: Path) -> int:
    """
    Create a configuration json file for running bdevperf, following the format of
    /path/to/spdk/test/bdev/bdevperf/conf.json
    """

    if path.exists():
        return 0

    subsystem = {
        "subsystem": "bdev",
        "config": []
    }

    for i, device in enumerate(devices):
        item = {
            "method": "bdev_nvme_attach_controller",
            "params": {
                "name": f"nvme{i:02d}",
                "trtype": "PCIe",
                "traddr": device
            }
        }
        subsystem["config"].append(item)

    with open(path, "x") as file:
        json.dump({ "subsystems": [subsystem] }, file, indent=2)

    return 0


def bdevperf_cmd(bin: str, args: dict) -> str:
    if any(key not in args for key in REQUIRED_KEYS):
        log.error(f"Failed: Missing arguments for {bin}")

    parameters = [
        f"{bin}",
        f"-c {args["config_path"]}",
        f"-m {args["cpumask"]}",
        f"-q {args["qdepth"]}",
        f"-o {args["iosize"]}",
        f"-t {args["runtime"]}",
        f"-w {args["iopattern"]}",
    ]
    return " ".join(parameters)


def main(args, cijoe):
    if bool(args.devices) == bool(args.ndevs):
        log.error(
            "Failed: Exactly one of arguments 'devices' and 'ndevs' must be defined; "
            f"got devices({args.devices}), ndevs({args.ndevs})"
        )
        return -1

    if args.ndevs:
        devs = cijoe.getconf("devices", None)
        args.devices = [d["pci_addr"] for d in devs[:args.ndevs]]

    config_path = Path(args.output) / cijoe.output_ident / "bdevperf_config.json"

    spdk_path = cijoe.getconf("spdk.repository.path", None)
    if not spdk_path:
        log.error("Failed: Missing SPDK repository path in config")
        return

    bin = Path(spdk_path) / "build" / "examples" / "bdevperf"

    err = create_config(args.devices, config_path)
    if err:
        log.error("Failed: create_config()")
        return err

    args.config_path = "/tmp/bdevperf_config.json"

    # If run on remote, cijoe.put is necessary
    cijoe.put(config_path, args.config_path)

    cmd = bdevperf_cmd(bin, vars(args))
    err, _ = cijoe.run(cmd)

    return err
