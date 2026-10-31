# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

"""
A FIL-wrapper invoking it with arguments
========================================

Retargetable: True
------------------
"""

from argparse import ArgumentParser, _StoreAction


def add_args(parser: ArgumentParser):
    class StringToBoolAction(_StoreAction):
        def __call__(self, parser, namespace, values, option_string=None):
            setattr(namespace, self.dest, values == "true")

    parser.add_argument("--backend", type=str, default="posix")
    parser.add_argument("--dataset", type=str, default="imagenetish")
    parser.add_argument("--device", type=str, default="")
    parser.add_argument("--bin", type=str, default="filperf")
    parser.add_argument("--batch_size", type=int, default=1)
    parser.add_argument("--batches", type=int, default=1)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--gpu_nqueues", type=int, default=4)
    parser.add_argument("--queue_depth", type=int, default=128)
    parser.add_argument("--homi_id", type=int, default=1)
    parser.add_argument("--xal_shm", type=str, default="/xal_dev0")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--copy_to_gpu", action=StringToBoolAction, default=True)
    parser.add_argument("--mnt", type=str, default=None)


def get_opts(args, backend):
    """
    The options of 'backend': posix and cufile read through the file system; the
    aisio ones read the controller through the homi server holding it, finding
    the extents in the index xal-server publishes
    """

    out = ""
    if backend == "posix":
        out += "--buffered "
    elif backend in ("aisio-cpu", "aisio-gpu", "aisio-p2p"):
        out += f"--homi-id {args.homi_id} --xal-shm {args.xal_shm} "
        if backend == "aisio-gpu":
            out += f"--gpu-nqueues {args.gpu_nqueues} "
        if backend == "aisio-cpu" and args.copy_to_gpu:
            out += "--copy-to-gpu "
        out += f"--queue-depth {args.queue_depth} "
    return out


def main(args, cijoe):
    prefix = "echo 3 > /proc/sys/vm/drop_caches;"

    mountpoint = args.mnt or cijoe.getconf("filesystems.dset.mountpoint")
    datadir = f"{mountpoint}/{args.dataset}" if mountpoint else args.dataset
    # posix and cufile take no device uri
    device = "" if args.backend in ("posix", "cufile") else args.device

    opts = get_opts(args, args.backend)
    warmup_opt = f"--warmup {args.warmup} " if args.warmup else ""
    cmd = f"{prefix} {args.bin} {device} --data-dir {datadir} --batches {args.batches} --batch-size {args.batch_size} --backend {args.backend} {opts}{warmup_opt}--summary"
    for _ in range(args.repetitions):
        err, _ = cijoe.run(cmd)
    if err:
        return 1

    return 0
