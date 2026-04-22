import logging as log
from argparse import ArgumentParser


REQUIRED_KEYS = ["cpumask", "iopattern", "qdepth", "iosize", "runtime", "backend", "devices"]
CUDA_REQUIRED_KEYS = ["iopattern", "qdepth", "iosize", "runtime", "backend", "devices"]


def add_args(parser: ArgumentParser):
    parser.add_argument("--devices", type=str, default=[], nargs="+")
    parser.add_argument("--ndevs", type=int, default=0)
    parser.add_argument("--iopattern", type=str, default="randread")
    parser.add_argument("--qdepth", type=int, default=128)
    parser.add_argument("--iosize", type=int, default=512)
    parser.add_argument("--runtime", type=int, default=10)
    parser.add_argument("--cpumask", type=str, default="0x1")
    parser.add_argument("--backend", type=str, default="upcie")


def xnvmeperf_cmd(bin: str, args: dict) -> str:
    if any(key not in args for key in REQUIRED_KEYS):
        log.error(f"Failed: Missing arguments for {bin}")

    parameters = [
        f"{bin}",
        "run",
        f"--cpumask {args['cpumask']}",
        f"--qdepth {args['qdepth']}",
        f"--iosize {args['iosize']}",
        f"--runtime {args['runtime']}",
        f"--iopattern {args['iopattern']}",
        f"--be {args['backend']}",
        " ".join(args["devices"]),
    ]
    return " ".join(parameters)


def xnvmeperf_cuda_cmd(bin: str, args: dict) -> str:
    if any(key not in args for key in CUDA_REQUIRED_KEYS):
        log.error(f"Failed: Missing arguments for {bin} cuda-run")
        return ""

    parameters = [
        f"{bin}",
        "cuda-run",
        f"--qdepth {args['qdepth']}",
        f"--iosize {args['iosize']}",
        f"--runtime {args['runtime']}",
        f"--iopattern {args['iopattern']}",
        f"--be {args['backend']}",
    ]
    if args.get("nqueues"):
        parameters.append(f"--nqueues {args['nqueues']}")
    parameters.append(" ".join(args["devices"]))
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

    cmd = xnvmeperf_cmd("xnvmeperf", vars(args))
    err, _ = cijoe.run(cmd)

    return err
