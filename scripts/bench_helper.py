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

from bdevperf import bdevperf_cmd, create_config as bdevperf_config
from dcgm_helper import DcgmHelper
from fio_xnvme import create_fio_job, fio_xnvme_cmd
from spdk_nvme_perf import spdk_nvme_perf_cmd
from xnvmeperf import xnvmeperf_cmd, xnvmeperf_cuda_cmd


FIO_TIME_BASED_OFF = 0
FIO_PREFILL_BS = 131072
FIO_PREFILL_QD = 32


class BenchHelper():
    def __init__(
            self,
            cijoe: Cijoe,
            configs_path: Path,
            results_path: Path,
            cfm: CpuFrequencyHelper,
            tool: str = "bdevperf",
            backend: str = "spdk",
            fio_size: str = "16GiB",
    ):
        self.initialised = False

        self.cijoe = cijoe
        self.results_path = results_path
        self.configs_path = configs_path
        self.cfm = cfm
        self.stress = False
        self.backend = backend
        self.tool = tool
        self.fio_size = fio_size
        self.fio_prefilled = set()

        self.dcgm = DcgmHelper(cijoe) if backend == "upcie-cuda" else None

        self.use_thrsib = False
        err = self._create_cpumasks(self.use_thrsib)
        if err:
            log.error(f"Failed: _create_cpumasks()")
            return

        self.remote_config = Path("/tmp/bdevperf-config.json")
        self.devices: list = cijoe.getconf("devices")

        if tool in ["bdevperf", "spdk_nvme_perf"]:
            spdk_path = self.cijoe.getconf("spdk.repository.path", None)
            if not spdk_path:
                log.error("Failed: Missing SPDK repository path in config")
                return

            if tool == "bdevperf":
                self.bin = Path(spdk_path) / "build" / "examples" / "bdevperf"
            else:
                self.bin = Path(spdk_path)  / "build" / "bin" / "spdk_nvme_perf"
        elif tool in ["xnvmeperf", "xnvmeperf-cuda"]:
            self.bin = "xnvmeperf"
        elif tool == "fio_xnvme":
            self.bin = "fio"
        else:
            log.error(f"Failed: Unknown tool({tool})")
            return

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

    def run_benchmark(self, rw: str, depth: int, size: int, ndevs: int, ncpus: int, time: int, cpu_freq: float, suffix: str = "", nqueues: int = 1):
        if not self.initialised:
            log.error("Failed: benchmarker not initialised correctly")
            return 1, None

        is_cuda = self.tool == "xnvmeperf-cuda"

        if is_cuda:
            filename = (
                f"d{ndevs}-c{ncpus}-o{size}-q{depth}-nq{nqueues}-"
                f"be_{self.backend}-tool_{self.tool}"
                f"{suffix}.out"
            )
        else:
            filename = (
                f"d{ndevs}-c{ncpus}-o{size}-f_{self.fio_size}-"
                f"rw_{rw}-q{depth}-be_{self.backend}-tool_{self.tool}-"
                f"thrsib{1 if self.use_thrsib else 0}-"
                f"freq_{cpu_freq}-"
                f"stress{1 if self.stress else 0}"
                f"{suffix}.out"
            )
        res_path = self.results_path / filename

        if res_path.exists():
            with open(res_path, "r") as file:
                result = json.load(file)
                return 0, result

        bench_args = {
            "iopattern": rw,
            "qdepth": depth,
            "iosize": size,
            "runtime": time,
            "devices": [d["pci_addr"] for d in self.devices[0:ndevs]],
        }

        if not is_cuda:
            bench_args["cpumask"] = self.cpu_masks[ncpus]

        if self.tool == "fio_xnvme" and ndevs != 1:
            log.error("Failed: fio_xnvme currently supports exactly 1 device per benchmark point")
            return 1, None

        if is_cuda:
            selected_cpus = []
            command = f"/usr/bin/time "
        else:
            selected_cpus = [v[0] for v in self.cpu_pairs if int(bench_args["cpumask"], 16) & (1 << v[0])]
            if self.tool == "fio_xnvme" and rw in ["read", "randread"]:
                err = self._prepare_fio_read_working_set(self.devices[0]["pci_addr"], rw, self.backend)
                if err:
                    log.error("Failed: _prepare_fio_read_working_set()")
                    return err, None

            cpu_list = ",".join(str(cpu) for cpu in selected_cpus)
            command = f"taskset -c {cpu_list} /usr/bin/time "

        if self.tool == "bdevperf":
            config_local_path = self.configs_path / f"d{ndevs}.json"
            bdevperf_config(bench_args["devices"], config_local_path)
            self.cijoe.put(config_local_path, self.remote_config)

            bench_args["config_path"] = self.remote_config
            command += bdevperf_cmd(self.bin, bench_args)
        elif self.tool == "spdk_nvme_perf":
            command += spdk_nvme_perf_cmd(self.bin, bench_args)
        elif self.tool == "xnvmeperf":
            bench_args["backend"] = self.backend
            command += xnvmeperf_cmd(self.bin, bench_args)
        elif is_cuda:
            bench_args["backend"] = self.backend
            bench_args["nqueues"] = nqueues
            command += xnvmeperf_cuda_cmd(self.bin, bench_args)
        elif self.tool == "fio_xnvme":
            fio_job = create_fio_job(
                self.devices[0]["pci_addr"], size, depth, time, rw, self.backend, self.fio_size
            )
            command += fio_xnvme_cmd(self.bin, fio_job)
        else:
            log.error(f"Unknown tool: {self.tool}")
            return -1, None

        if self.stress and (stressed_cpus := [str(x) for x in range(len(self.cpu_pairs)) if x not in selected_cpus]):
            command = "\n".join([
                f"taskset -c {','.join(stressed_cpus)} stress-ng --cpu {len(stressed_cpus)} --timeout {time + 5}s &",
                "STRESS_PID=$!",
                command,
                "wait $STRESS_PID",
            ])

        def abort_monitors():
            self.cfm.stop_logging_and_parse()
            if self.dcgm:
                self.dcgm.stop_and_parse()

        self.cfm.set_cpu_freq(cpu_freq, selected_cpus)
        err = self.cfm.start_logging()
        if err:
            log.error("Failed: CpuFrequencyHelper.start_logging()")
            return err, None

        if self.dcgm:
            err = self.dcgm.start()
            if err:
                self.cfm.stop_logging_and_parse()
                log.error("Failed: DcgmHelper.start()")
                return err, None

        err, state = self.cijoe.run(command)
        if err:
            abort_monitors()
            log.error(f"Failed: {self.bin} for run with filename({filename})")
            return err, None

        output = state.output()
        err, cpu_usage = self._parse_time_output(output)
        if err:
            abort_monitors()
            log.error("Failed: BenchHelper._parse_time_output()")
            return err, None

        err, bench_result = self._parse_bench_results(output)
        if err:
            abort_monitors()
            log.error("Failed: BenchHelper._parse_bench_results()")
            return err, None

        err, cpu_freqs = self.cfm.stop_logging_and_parse()
        if err:
            if self.dcgm:
                self.dcgm.stop_and_parse()
            log.error("Failed: CpuFrequencyHelper.stop_logging_and_parse()")
            return err, None

        dcgm_stats = None
        if self.dcgm:
            err, dcgm_stats = self.dcgm.stop_and_parse()
            if err:
                log.error("Failed: DcgmHelper.stop_and_parse()")
                return err, None

        if self.cfm.cpu_control_supported and cpu_freqs:
            cpu_freqs = [[cpu_freqs[idx], self.cpu_pairs[idx]] for idx in selected_cpus]
        else:
            cpu_freqs = []

        result = {
            "rw": rw,
            "qdepth": depth,
            "iosize": size,
            "fio_size": self.fio_size,
            "ndevs": ndevs,
            "ncpus": ncpus,
            "nqueues": nqueues,
            "device_bdf": bench_args["devices"][0] if bench_args["devices"] else None,
            "cpu_usage": cpu_usage,
            "cpu_freqs": cpu_freqs,
            "fixed_freq": self.cfm.fixed_freq,
            "cpu_governor": self.cfm.governor,
            "cpu_control_supported": self.cfm.cpu_control_supported,
            "thr_sib": self.use_thrsib,
            "smt": 1 if "SMT1" in suffix else 0,
            "turbo": 1 if "turbo1" in suffix else 0,
            "stress": self.stress,
            "tool": self.tool,
            "backend": self.backend,
            "iops": bench_result["total"]["iops"],
            "mibs": bench_result["total"]["mibs"],
            "dcgm": dcgm_stats["1010"]["p95"] if self.dcgm else None,
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

    def _prepare_fio_read_working_set(self, pci_addr: str, rw: str, backend: str) -> int:
        key = (pci_addr, backend, self.fio_size, rw)
        if key in self.fio_prefilled:
            return 0

        fio_job = create_fio_job(
            pci_addr,
            FIO_PREFILL_BS,
            FIO_PREFILL_QD,
            FIO_TIME_BASED_OFF,
            "write",
            backend,
            self.fio_size,
            time_based=False,
        )

        err, _ = self.cijoe.run(fio_xnvme_cmd("fio", fio_job))
        if err:
            log.error(f"Failed: fio prefill for backend({backend}) and device({pci_addr})")
            return err

        self.fio_prefilled.add(key)
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
        elif self.tool == "spdk_nvme_perf":
            table_regex = r"\s*(?P<name>.+?)\s*?:\s+(?P<iops>[0-9.]+)\s+(?P<mibs>[0-9.]+)\s+(?P<avg_lat>[0-9.]+)\s+(?P<min_lat>[0-9.]+)\s+(?P<max_lat>[0-9.]+)"
        elif self.tool in ["xnvmeperf", "xnvmeperf-cuda"]:
            table_regex = r"\s*(?P<name>\w+):?\s+(?P<cpus>[0-9,]+)?\s+(?P<iops>[0-9.]+)\s+(?P<mibs>[0-9.]+)\s+(?P<fails>[0-9.]+)"
        elif self.tool == "fio_xnvme":
            return self._parse_fio_results(table)
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

    def _parse_fio_results(self, output: str) -> Tuple[int, dict[str, list]]:
        start = output.find("{")
        end = output.rfind("}")
        if start < 0 or end < 0 or end <= start:
            log.error("Failed: could not find fio JSON output")
            return 1, None

        try:
            payload = json.loads(output[start:end + 1])
        except json.JSONDecodeError:
            log.error("Failed: invalid fio JSON output")
            return 1, None

        jobs = payload.get("jobs", [])
        if not jobs:
            log.error("Failed: fio returned no jobs")
            return 1, None

        total_iops = 0.0
        total_mibs = 0.0
        devices = []
        for job in jobs:
            metrics = job.get("read", {})
            if not float(metrics.get("iops", 0.0)):
                write_metrics = job.get("write", {})
                if float(write_metrics.get("iops", 0.0)):
                    metrics = write_metrics
            iops = float(metrics.get("iops", 0.0))
            mibs = float(metrics.get("bw_bytes", 0.0)) / (1024 * 1024)
            total_iops += iops
            total_mibs += mibs
            devices.append({"iops": iops, "mibs": mibs})

        return 0, {
            "devices": devices,
            "total": {
                "iops": total_iops,
                "mibs": total_mibs,
            },
        }

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
