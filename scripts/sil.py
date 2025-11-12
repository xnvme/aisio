"""
A SIL-wrapper invoking it with arguments
========================================

Retargetable: True
------------------
"""

from argparse import ArgumentParser, _StoreAction


def add_args(parser: ArgumentParser):
    class StringToBoolAction(_StoreAction):
        def __call__(self, parser, namespace, values, option_string=None):
            setattr(namespace, self.dest, values == "true")

    parser.add_argument("--backends", type=str, default=["posix"], nargs="+")
    parser.add_argument("--dataset", type=str, default="imagenetish")
    parser.add_argument("--device", type=str, default="/dev/nvme1n1")
    parser.add_argument("--bin", type=str, default="sil")
    parser.add_argument("--batch_size", type=int, default=1)
    parser.add_argument("--batches", type=int, default=1)
    parser.add_argument("--gpu_nqueues", type=int, default=6)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument(
        "--random", choices=["true", "false"], default=False, action=StringToBoolAction
    )


def get_opts(args, cijoe, backend):
    mountpoint = cijoe.getconf("filesystems.dset.mountpoint")
    out = ""
    if backend == "posix":
        if mountpoint:
            out += f"--mnt {mountpoint} "
        out += "--buffered "
        return out
    if backend == "gds":
        if mountpoint:
            out += f"--mnt {mountpoint} "
        return out
    if backend == "aisio":
        out += f"--gpu-nqueues {args.gpu_nqueues} "
        if args.random:
            out += "--random "
        return out


def main(args, cijoe):
    prefix = "echo 3 > /proc/sys/vm/drop_caches;"

    for backend in args.backends:
        opts = get_opts(args, cijoe, backend)
        cmd = f"{prefix} {args.bin} {args.device} --data-dir {args.dataset} --batches {args.batches} --batch-size {args.batch_size} --backend {backend} {opts}"
        for _ in range(args.repetitions):
            err, _ = cijoe.run(cmd)
        if err:
            return 1

    return 0
