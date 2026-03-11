"""
BenchHelper
===========

Helper class for running benchmarks with SPDK's I/O benchmarking tool, bdevperf.

A note about CPU masks
----------------------
The CPU masks define which CPUs are used for running the benchmarks and are calculated
from the output of command

    lscpu -e

On a system with hyper threading enabled, the script prioritises adding CPUs running on
the same core. On a system where CPUs are paired in blocks of 8, meaning CPU 0 and 8 run
on core 0, CPU 1 and 9 run on core 1, etc., this script will use CPUs in order (0, 8, 1,
9, 2, ...). This will ensure that the lowest number of cores needed are used for any run.

Example: if you want to use 3 CPUs, instead of using cpu mask 0x0007 (0000 0000 0000 0111),
resulting in using a hyper thread on core 0, 1 and 2, it will return 0x0013
(0000 0001 0000 0011), resulting in two hyper threads on core 0, and one hyper threead on
core 1.
"""

from cpu_freq_helper import CpuFrequencyHelper
from cijoe.core.command import Cijoe
from pathlib import Path
from re import match, search
from typing import Tuple
import json
import logging as log


class BenchHelper():
    def __init__(
            self,
            cijoe: Cijoe,
            configs_path: Path,
            results_path: Path,
            cfm: CpuFrequencyHelper,
            tool: str = "bdevperf",
            backend: str = "spdk",
    ):
        self.initialised = False

        self.cijoe = cijoe
        self.results_path = results_path
        self.configs_path = configs_path
        self.cfm = cfm
        self.stress = False
        self.backend = backend
        self.tool = tool

        self.use_thrsib = False
        err = self._create_cpumasks(self.use_thrsib)
        if err:
            log.error(f"Failed: _create_cpumasks()")
            return

        self.remote_config = Path("/tmp/bdevperf-config.json")
        self.devices: list = cijoe.getconf("devices")

        if tool == "bdevperf":
            spdk_path = self.cijoe.getconf("spdk.repository.path", None)
            if not spdk_path:
                log.error("Failed: Missing SPDK repository path in config")
                return

            self.bin = Path(spdk_path) / "build" / "examples" / "bdevperf"
        elif tool == "xnvmeperf":
            self.bin = "xnvmeperf run"
        else:
            log.error(f"Failed: Unknown tool({tool})")

        self.initialised = True

    def use_thread_siblings(self, use_thrsib: bool) -> int:
        if self.use_thrsib == use_thrsib:
            return 0

        if not self.initialised:
            log.error("Failed: benchmarker not initialised correctly")
            return 1

        err = self._create_cpumasks(use_thrsib)
        if err:
            log.error(f"Failed: _create_cpumasks()")
            return err

        self.use_thrsib = use_thrsib

        return 0

    def run_benchmark(self, depth: int, size: int, ndevs: int, ncpus: int, time: int, cpu_freq: float, suffix: str = ""):
        if not self.initialised:
            log.error("Failed: benchmarker not initialised correctly")
            return 1, None

        filename = (
            f"d{ndevs}-"
            f"c{ncpus}-"
            f"o{size}-"
            f"q{depth}-"
            f"be_{self.backend}-"
            f"tool_{self.tool}-"
            f"thrsib{1 if self.use_thrsib else 0}-"
            f"freq_{cpu_freq}-"
            f"stress{1 if self.stress else 0}"
            f"{suffix}"
            ".out"
        )
        res_path = self.results_path / filename

        if res_path.exists():
            with open(res_path, "r") as file:
                result = json.load(file)
                return 0, result

        if self.tool == "bdevperf":
            config_local_path = self.configs_path / f"d{ndevs}.json"
            self._create_bdevperf_config(self.devices[0:ndevs], config_local_path)
            self.cijoe.put(config_local_path, self.remote_config)

        mask = self.cpu_masks[ncpus]
        selected_cpus = [v[0] for v in self.cpu_pairs if int(mask, 16) & (1 << v[0])]

        self.cfm.set_cpu_freq(cpu_freq, selected_cpus)

        err = self.cfm.start_logging()
        if err:
            log.error("Failed: CpuFrequencyHelper.start_logging()")
            return err, None

        command = f"/usr/bin/time {self.bin} "

        if self.tool == "bdevperf":
            run_parameters = [
                f"-c {self.remote_config}",
                f"-m {mask}",
                f"-q {depth}",
                f"-o {size}",
                f"-t {time}",
                "-w randread"
            ]
            command += " ".join(run_parameters)
        elif self.tool == "xnvmeperf":
            run_parameters = [
                f"--cpumask {mask}",
                f"--qdepth {depth}",
                f"--iosize {size}",
                f"--runtime {time}",
                "--iopattern randread",
                f"--be {self.backend}",
                " ".join(d["pci_addr"] for d in self.devices[0:ndevs]),
            ]
            command += " ".join(run_parameters)
        else:
            log.error(f"Unkown tool: {self.tool}")
            return -1

        if self.stress and (stressed_cpus := [str(x) for x in range(len(self.cpu_pairs)) if x not in selected_cpus]):
            command = "\n".join([
                f"taskset -c {','.join(stressed_cpus)} stress-ng --cpu {len(stressed_cpus)} --timeout {time + 5}s &",
                "STRESS_PID=$!",
                command,
                "wait $STRESS_PID",
            ])

        err, state = self.cijoe.run(command)
        if err:
            log.error(f"Failed: {self.bin} for run with filename({filename})")
            return err, None

        output = state.output()
        err, cpu_usage = self._parse_time_output(output)
        if err:
            log.error("Failed: BenchHelper._parse_time_output()")
            return err, None

        err, bench_result = self._parse_bench_results(output)
        if err:
            log.error("Failed: BenchHelper._parse_bench_results()")
            return err, None


        err, cpu_freqs = self.cfm.stop_logging_and_parse()
        if err:
            log.error("Failed: CpuFrequencyHelper.stop_logging_and_parse()")
            return err, None

        cpu_freqs = [[cpu_freqs[idx], self.cpu_pairs[idx]] for idx in selected_cpus]

        result = {
            "qdepth": depth,
            "iosize": size,
            "ndevs": ndevs,
            "ncpus": ncpus,
            "cpu": cpu_usage,
            "cpu_freqs": cpu_freqs,
            "fixed_freq": self.cfm.fixed_freq,
            "cpu_governor": self.cfm.governor,
            "thr_sib": self.use_thrsib,
            "tool": self.tool,
            "backend": self.backend,
            "iops": bench_result["total"]["iops"],
            "mibs": bench_result["total"]["mibs"],
        }

        with open(res_path, "x") as file:
            json.dump(result, file, indent=2)

        return 0, result

    def _create_cpumasks(self, use_thrsib: bool):
        """
        Find the appropriate CPU masks from the output of `lscpu -e`.

        Arguments
            `use_thrsib: bool` defines whether hyper thread siblings should be
            used, resulting in the hyper threads being run on the same cores.

        Returns
            `(err, cpu_masks)` where a non-zero value for `err` describes that an error
            occured either while running `lscpu` or while parsing the output.
        """

        err, state = self.cijoe.run("lscpu -e")
        if err:
            log.error(f"Failed: lscpu -e")
            return err,

        table_regex = r"\s*(?P<cpu>\d+)\s+\d+\s+\d+\s+(?P<core>\d+).*"
        matches = filter(None, [match(table_regex, row) for row in state.output().split("\n")])
        if not matches:
            log.error("Failed: output of 'lspci -e' did not match the expected format")
            return 1,

        cpu_pairs = [[int(v) for v in match.groupdict().values()] for match in matches]

        if use_thrsib:
            pairs = sorted(cpu_pairs, key=lambda p: p[1])
        else:
            pairs = cpu_pairs

        # pairs.sort(key=lambda p: p[1] % 2 == 1) # ONLY used for testing NUMA nodes

        cpu_masks = {}
        for i, (cpu, _) in enumerate(pairs):
            n = i+1
            if i == 0:
                cpu_masks[n] = 1 << cpu
            else:
                cpu_masks[n] = cpu_masks[n-1] | (1 << cpu)

        for n in cpu_masks.keys():
            cpu_masks[n] = f"{cpu_masks[n]:04x}"

        self.cpu_masks = cpu_masks
        self.cpu_pairs = cpu_pairs

        return 0

    def _create_bdevperf_config(self, devices: list, path: Path) -> int:
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
                    "traddr": device["pci_addr"]
                }
            }
            subsystem["config"].append(item)

        with open(path, "x") as file:
            json.dump({ "subsystems": [subsystem] }, file, indent=2)

        return 0

    def _parse_bench_results(self, table: str) -> Tuple[int, dict[str, list]]:
        """
        Parse the table-formattet stdout output from running the benchmark into an ansible json
        object.

        Returns `(err, result)`, where a non-zero value for `err` describes that the
        output did not match the expected format.
        """

        result = { "devices": [] }
        table_regex = None

        if self.tool == "bdevperf":
            table_regex = r"\s*(?P<name>\w+)\s+:\s+(?P<runtime>[0-9.]+)?\s+(?P<iops>[0-9.]+)\s+(?P<mibs>[0-9.]+)\s+(?P<fails>[0-9.]+)\s+(?P<tos>[0-9.]+)\s+(?P<avg_lat>[0-9.]+)\s+(?P<min_lat>[0-9.]+)\s+(?P<max_lat>[0-9.]+)"
        elif self.tool == "xnvmeperf":
            table_regex = r"\s*(?P<name>\w+):?\s+(?P<cpus>[0-9,]+)?\s+(?P<iops>[0-9.]+)\s+(?P<mibs>[0-9.]+)\s+(?P<fails>[0-9.]+)"
        else:
            log.error(f"Unkown tool: {self.tool}")
            return -1, None

        matches = filter(None, [match(table_regex, row) for row in table.split("\n")])

        for m in matches:
            device_result = {k: float(v) if v else None for (k, v) in m.groupdict().items() if k != "name"}
            if m.group("name") == "Total":
                result["total"] = device_result
            else:
                result["devices"].append(device_result)

        return 0, result

    def _parse_time_output(self, output: str) -> Tuple[int, int]:
        """
        Find the CPU usage from /usr/bin/time in from the output of /usr/bin/time.

        Returns `(err, cpu_usage)`, where a non-zero value for `err` describes that the
        output did not match the expected format.
        """

        time_regex = r"(?P<user>[0-9.]+)user (?P<system>[0-9.]+)system (?P<elapsed>[0-9.:]+)elapsed (?P<cpu>[0-9.]+)%CPU .*k"
        m = search(time_regex, output)

        if not m:
            log.error("Failed: could not find CPU usage in output")
            return 1, None

        return 0, int(m.group("cpu"))
