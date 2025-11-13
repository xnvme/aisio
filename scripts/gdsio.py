"""
A gdsio-wrapper, invoking it repeatedly with variying arguments
===============================================================

Retargetable: True
------------------
"""

from argparse import ArgumentParser


def add_args(parser: ArgumentParser):
    parser.add_argument("--bin", type=str, default="/usr/local/cuda/gds/tools/gdsio")
    parser.add_argument("--dir", type=str, default="/mnt/gds01/gds_dir")
    parser.add_argument("--nthreads", type=int, default=1)
    parser.add_argument("--gpu_index", type=int, default=0)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument(
        "--mode",
        type=int,
        default=2,
        help="read(0), write(1), randread(2), randwrite(3)",
    )
    parser.add_argument("--iosize", type=str, default="4K")
    parser.add_argument(
        "--xfer_types",
        type=int,
        default=[0, 1, 2, 3, 4, 5, 6, 7],
        nargs="+",
        help="GPU_DIRECT(0), CPU_ONLY(1), CPU_GPU(2), CPU_ASYNC_GPU(3), CPU_CACHED_GPU(4), GPU_DIRECT_ASYNC(5), GPU_BATCH(6), GPU_BATCH_STREAM(7)",
    )


def main(args, cijoe):
    bin = args.bin
    dir = args.dir
    gpu_index = args.gpu_index
    nthreads = args.nthreads
    filesize = "8G"
    iosize = args.iosize  # Size of each IO
    runtime = 10  # Runtime in seconds

    # Precondition by creating the files
    cmd = f"{bin} -D {dir} -d {gpu_index} -w {nthreads} -s {filesize} -i {iosize} -I 1 -x 0"
    err, _ = cijoe.run(cmd)
    if err:
        return 1

    for xfer_type in args.xfer_types:
        cmd = f"{bin} -D {dir} -d {gpu_index} -w {nthreads} -s {filesize} -i {iosize} -T {runtime} -I {args.mode} -x {xfer_type}"
        for rep in range(args.repetitions):
            err, _ = cijoe.run(cmd)
            if err:
                return 1

    return 0
