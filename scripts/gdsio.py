"""
A gdsio-wrapper, invoking it repeatedly with variying arguments
===============================================================

TODO:

* Add parameters for bin, mounpint and repetitions
* Add a generic way to pass gdsio arguments

Retargetable: True
------------------
"""

import errno
import logging as log


def main(args, cijoe):
    """Copies the file at args.src on the local machine to args.dst on the remote machine"""

    bin = "/usr/local/cuda/gds/tools/gdsio"
    mountpoint = "/mnt/gds01/gds_dir"
    gpu_index = 0
    nthreads = 1
    filesize = "8G"
    iosize = "4K"  # Size of each IO
    runtime = 10  # Runtime in seconds
    mode = 2  # read(0) | write(1) | randread(2) | randwrite(3)
    xfer_type = 0
    xfer_types = list(range(8))  # GPUD(0), CPUONLY(1), ... ,

    cmd = f"{bin} -D {mountpoint} -d {gpu_index} -w {nthreads} -s {filesize} -i {iosize} -I 1 -x {xfer_type}"
    err, _ = cijoe.run(cmd)
    if err:
        return 1

    for xfer_type in xfer_types:
        for rep in range(3):
            cmd = f"{bin} -D {mountpoint} -d {gpu_index} -w {nthreads} -s {filesize} -i {iosize} -T {runtime} -I {mode} -x {xfer_type}"
            err, _ = cijoe.run(cmd)
            if err:
                return 1

    return 0
