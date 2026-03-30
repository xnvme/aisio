import logging as log
from argparse import ArgumentParser
from pathlib import Path


REQUIRED_KEYS = ["cpumask", "iopattern", "qdepth", "iosize", "runtime", "devices"]


def add_args(parser: ArgumentParser):
    parser.add_argument("--devices", type=str, default=[], nargs="+")
    parser.add_argument("--ndevs", type=int, default=0)
    parser.add_argument("--iopattern", type=str, default="randread")
    parser.add_argument("--qdepth", type=int, default=128)
    parser.add_argument("--iosize", type=int, default=512)
    parser.add_argument("--runtime", type=int, default=10)
    parser.add_argument("--cpumask", type=str, default="0x1")


def spdk_nvme_perf_cmd(bin: str, args: dict) -> str:
    if any(key not in args for key in REQUIRED_KEYS):
        log.error(f"Failed: Missing arguments for {bin}")

    parameters = [
        f"{bin}",
        f"-c {args["cpumask"]}",
        f"-q {args["qdepth"]}",
        f"-o {args["iosize"]}",
        f"-t {args["runtime"]}",
        f"-w {args["iopattern"]}",
        " ".join(f'-r "trtype:PCIe traddr:{d}"' for d in args["devices"]),
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

    spdk_path = cijoe.getconf("spdk.repository.path", None)
    if not spdk_path:
        log.error("Failed: Missing SPDK repository path in config")
        return

    bin = Path(spdk_path) / "build" / "bin" / "spdk_nvme_perf"

    cmd = spdk_nvme_perf_cmd(bin, vars(args))
    err, _ = cijoe.run(cmd)

    return err
