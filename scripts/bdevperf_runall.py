"""
Run I/O benchmarks using bdevperf
=================================

Run many benchmarks using SPDK's I/O benchmarking tool, bdevperf.

Retargetable: True
------------------
"""

from argparse import ArgumentParser
from itertools import product
from math import floor
from pathlib import Path
from sys import stderr
from time import time
from typing import Optional
import logging as log

from cijoe.core.command import Cijoe

from bdevperf_helper import BdevperfHelper
from cpu_freq_helper import CpuFrequencyHelper


def add_args(parser: ArgumentParser):
    parser.add_argument("--depths", type=int, default=[64], nargs="+", help="Queue depth to test")
    parser.add_argument("--sizes", type=int, default=[4096], nargs="+", help="I/O sizes to test")
    parser.add_argument("--numcpus_range", type=int, default=None, nargs="*", help="Range of how many CPUs to test")
    parser.add_argument("--numcpus_specific", type=int, default=None, nargs="*", help="The amount of CPUs to test")
    parser.add_argument("--numdevs_range", type=int, default=None, nargs="*", help="Range of how many devices to test")
    parser.add_argument("--numdevs_specific", type=int, default=None, nargs="*", help="The amount of devices to test")
    parser.add_argument("--cpu_freqs", type=str, default=["ondemand"], nargs="*", help="List of fixed CPU frequencies (in GHz) and governors to test")
    parser.add_argument("--turbo", type=int, default=[0,1], nargs="+", help="0 for turbo boost off, 1 for turbo boost on, [0,1] for testing both")
    parser.add_argument("--smt", type=int, default=[0,1], nargs="+", help="0 for SMT off, 1 for SMT on, [0,1] for testing both")
    parser.add_argument("--hyperthreads", type=int, default=[0,1], nargs="+", help="0 for hyper threads off, 1 for hyper threads on, [0,1] for testing both. Note that you cannot test with hyper threads if SMT is turned off")
    parser.add_argument("--stress", type=int, default=[0,1], nargs="+", help="0 for not stressing unused CPUs, 1 for stressing unused CPUs, [0,1] for testing both")
    parser.add_argument("--time", type=int, default=10, help="Time for for bdevperf to run for each test")
    parser.add_argument("--results_dir", type=Path, default=None, help="Path to existing directory in which the results should be saved. Note: Already existing results will not be benchmarked again")
    parser.add_argument("--repetitions", type=int, default=5, help="The amount of times each benchmark will be repeated. The result will be average of the repetitions")


def main(args, cijoe: Cijoe):
    """Run benchmarks using bdevperf"""

    out_path = Path(args.output)
    bdev_configs = out_path / cijoe.output_ident / "bdevperf-configs"
    bdev_results = out_path / "artifacts" / "bdevperf-results"

    if args.results_dir:
        bdev_results = args.results_dir

    cijoe.run_local(f"mkdir -p {bdev_configs} {bdev_results}")

    if (args.numcpus_range and args.numcpus_specific) or (not args.numcpus_range and not args.numcpus_specific):
        log.error("Failed: You must define exactly 1 of arguments: numcpus_range, numcpus_specific")
        return 1

    if (args.numdevs_range and args.numdevs_specific) or (not args.numdevs_range and not args.numdevs_specific):
        log.error("Failed: You must define exactly 1 of arguments: numdevs_range, numdevs_specific")
        return 1

    devices: list = cijoe.getconf("devices")
    if not devices:
        log.error("Failed: No devices defined in config")
        return 1

    cfm = CpuFrequencyHelper(cijoe)
    err = cfm.transfer_cpu_frequency_logger()
    if err:
        log.error("Failed: transfer_cpu_frequency_logger()")
        return err

    bdevperf = BdevperfHelper(cijoe, bdev_configs, bdev_results, cfm)
    if not bdevperf.initialised:
        log.error("Failed: couldn't not initialise the bdevperf")
        return 1

    test_devs = args.numdevs_specific
    if not test_devs:
        test_devs = create_range(args.numdevs_range, devices)

    test_cpus = args.numcpus_specific
    if not test_cpus:
        # The CPU range `test_cpus` describes the amount of CPUs that should be tested.
        # Without hyper threading, the range 4-8 describe that the benchmark will be run
        # first with 4 physical cores (0-3), then 5 physical cores (0-4), and so on. When
        # hyper threading is enabled, the amount of logical CPUs is doubled, and the IDs
        # shift. Now, the same range 4-8 need to be shifted to (7-16), as 1-6 describe the
        # hyper threads on the first 3 cores which are not in the 4-8 range.
        test_cpus = create_range(args.numcpus_range, bdevperf.cpu_pairs)

    tests = []

    if 0 in args.hyperthreads:
        tests += product([0], args.turbo, args.smt, args.stress, args.cpu_freqs, test_devs, test_cpus, args.sizes, args.depths)
    if 1 in args.hyperthreads:
        # shift range to match cpu hyperthreads
        test_cpus = [x for cpu in test_cpus for x in [cpu*2-1, cpu*2]]
        tests += product([1], args.turbo, args.smt, args.stress, args.cpu_freqs, test_devs, test_cpus, args.sizes, args.depths)

    tests = [(ht,tu,sm,st,f,d,c,o,q) for (ht,tu,sm,st,f,d,c,o,q) in tests if not (not sm and ht)]

    finished, total, now = 0, len(tests), time()

    for ht, tu, sm, st, freq, devs, cpus, iosz, qd in tests:
        err = cfm.toggle_smt(sm)
        if err:
            log.error(f"Failed: cfm.toggle_smt({sm})")
            return err

        err = cfm.toggle_turbo(tu)
        if err:
            log.error(f"Failed: cfm.toggle_turbo({tu})")
            return err

        err = bdevperf.use_thread_siblings(ht)
        if err:
            log.error(f"Failed: bdevperf.use_thread_siblings({ht})")
            return err

        bdevperf.stress = st

        suffix = f"-SMT{sm}-turbo{tu}"

        if not args.monitor:
            print_progress(finished, total, time()-now)

        now = time()

        for i in range(args.repetitions):
            err, result = bdevperf.run_benchmark(qd, iosz, devs, cpus, args.time, freq, f"{suffix}-{i}")
            if err:
                log.error("Failed: run_bdevperf()")
                return err

            if not result:
                log.error("Got no results")
                return 1

        finished += 1

    if not args.monitor:
        print_progress(finished, total, time()-now)

    return 0


def create_range(default: Optional[list], arr: list) -> range:
    """
    Create a range from A to B (both inclusive), either defined by the two elements in
    the given `default` list, or by the length of the given backup `arr`.

    Arguments
        `default: Optional[list]` A list of size 2, defining the start- and end-indices
            (1-indexed) of the range (both inclusive).

        `arr: list` The list the range should fit. If `default` is None, the range will be
            the full list.
    """
    lo, hi = 1, len(arr) + 1

    if not default:
        return range(lo, hi)

    if len(default) != 2:
        log.error(f"Error: given range must be of length 2 ({default}); ignoring")
        return range(lo, hi)

    if 1 <= default[0] <= len(arr):
        lo = default[0]
    else:
        log.error(f"Error: given start-index out of range({default[0]}); using 1 as start-index")

    if 1 <= default[1] <= len(arr):
        hi = default[1] + 1
    else:
        log.error(f"Error: given end-index out of range({default[1]}); using length of arr as end-index")

    return range(lo, hi)


def print_progress(finished: int, total: int, duration_s: float):
    """Prints a loading bar to stderr to indicate the progress"""

    width = 20 if total < 100 else 50
    progress = floor(finished / total * width)
    bar = f"[{'▒' * (progress)}{' ' * (width-progress)}]"

    remaining_time = (total-finished)*duration_s
    m, s = divmod(remaining_time, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    s, m, h, d = map(int, [s, m, h, d])
    remaining_string = f"({f'{d} days, ' if d else ''}{f'{h:0>2}:' if h else ''}{m:0>2}:{s:0>2} remaining)"

    stderr.write(f"\r{bar}  {finished} / {total} {remaining_string if int(duration_s) else ''}  ")
    if finished == total:
        stderr.write("\n")
    stderr.flush()
