"""
Run I/O benchmarks using bdevperf
=================================

Run many benchmarks using SPDK's I/O benchmarking tool, bdevperf.

Retargetable: True
------------------
"""

from argparse import ArgumentParser
from collections import defaultdict
from itertools import product
from json import dump as json_dump
from math import floor
from pathlib import Path
from sys import stderr
from typing import Optional
import logging as log

from cijoe.core.command import Cijoe

from bdevperf_helper import BdevperfHelper
from cpu_freq_helper import CpuFrequencyHelper


def add_args(parser: ArgumentParser):
    parser.add_argument("--depths", type=int, default=[64], nargs="+", help="Queue depth to test")
    parser.add_argument("--sizes", type=int, default=[4096], nargs="+", help="I/O sizes to test")
    parser.add_argument("--numcpus_range", type=int, default=[1,1], nargs="*", help="Range of how many CPUs to test")
    parser.add_argument("--numdevs_range", type=int, default=[1,1], nargs="*", help="Range of how many devices to test")
    parser.add_argument("--cpu_freqs", type=str, default=["ondemand"], nargs="*", help="List of fixed CPU frequencies (in GHz) and governors to test")
    parser.add_argument("--turbo", type=int, default=[0,1], nargs="+", help="0 for turbo boost off, 1 for turbo boost on, [0,1] for testing both")
    parser.add_argument("--smt", type=int, default=[0,1], nargs="+", help="0 for SMT off, 1 for SMT on, [0,1] for testing both")
    parser.add_argument("--hyperthreads", type=int, default=[0,1], nargs="+", help="0 for hyper threads off, 1 for hyper threads on, [0,1] for testing both. Note that you cannot test with hyper threads if SMT is turned off")
    parser.add_argument("--stress", type=int, default=[0,1], nargs="+", help="0 for not stressing unused CPUs, 1 for stressing unused CPUs, [0,1] for testing both")
    parser.add_argument("--time", type=int, default=10, help="Time for for bdevperf to run for each test")
    parser.add_argument("--results_dir", type=Path, default=None, help="Path to existing directory in which the results should be saved. Note: Already existing results will not be benchmarked again")


def main(args, cijoe: Cijoe):
    """Run benchmarks using bdevperf"""

    out_path = Path(args.output)
    bdev_configs = out_path / cijoe.output_ident / "bdevperf-configs"
    bdev_results = out_path / cijoe.output_ident / "bdevperf-results"

    if args.results_dir:
        bdev_results = args.results_dir

    cijoe.run_local(f"mkdir -p {bdev_configs} {bdev_results}")

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

    test_devs = create_range(args.numdevs_range, devices)

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
        test_cpus = range(test_cpus[0]*2-1, test_cpus[-1]*2+1) # shift range to match cpu hyperthreads
        tests += product([1], args.turbo, args.smt, args.stress, args.cpu_freqs, test_devs, test_cpus, args.sizes, args.depths)
    
    tests = [(ht,tu,sm,st,f,d,c,o,q) for (ht,tu,sm,st,f,d,c,o,q) in tests if not (not sm and ht)]

    finished, total = 0, len(tests)
    all_results = defaultdict(list)

    for ht, tu, sm, st, freq, devs, cpus, iosz, qd in tests:
        cfm.toggle_smt(sm)
        cfm.toggle_turbo(tu)
        bdevperf.use_thread_siblings(ht)
        bdevperf.stress = st

        label = (
            f"{'U' if ht else 'Not u'}sing thread siblings; "
            f"SMT {'on' if sm else 'off'}; "
            f"stress {'on' if st else 'off'}; "
            f"turbo {'on' if tu else 'off'}"
        )
        suffix = f"-SMT{sm}-turbo{tu}"

        if not args.monitor:
            print_progress(finished, total)

        err, result = bdevperf.run_benchmark(qd, iosz, devs, cpus, args.time, freq, suffix)
        if err:
            log.error("Failed: run_bdevperf()")
            return err, None

        if not result:
            continue

        all_results[label].append(result)
        finished += 1

    if not args.monitor:
        print_progress(finished, total)

    with open(out_path / "artifacts" / "benchmark-results.json", "x") as file:
        json_dump(all_results, file, indent=2)

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


def print_progress(finished: int, total: int):
    """Prints a loading bar to stderr to indicate the progress"""

    width = 20 if total < 100 else 50
    progress = floor(finished / total * width)
    bar = f"[{'▒' * (progress)}{' ' * (width-progress)}]"
    stderr.write(f"\r{bar}  {finished} / {total} ")
    if finished == total:
        stderr.write("\n")
    stderr.flush()
