from cijoe.core.command import Cijoe
from cijoe.core.resources import get_resources
from pathlib import Path
from re import match
from typing import List, Tuple, Union
import logging as log

class CpuFrequencyHelper():
    def __init__(self, cijoe: Cijoe):
        self.cijoe = cijoe
        self.fixed_freq = 0
        self.governor = None

        self._bin = Path("/tmp/cpu_freq_logger.sh")
        self._output = Path("/tmp/cpu_freq_logger.out")
        self._is_running = False
        self._steps = None
        self._smt = None
        self._turbo = None

    def get_cpu_frequency_steps(self) -> Tuple[int, List[float]]:
        """
        Read the available CPU frequency steps from `cpupower`.

        Returns
            `err, steps`, where err=0 indicates success and a non-zero value indicates an error.
        """

        err, state = self.cijoe.run('cpupower frequency-info | grep "available frequency steps"')
        if err or not state.output():
            log.error("Failed: cpupower")
            return 1, None

        line_regex = r"\s*available frequency steps:\s+(([\d.]+ GHz,? ?)+)"
        m = match(line_regex, state.output())
        steps = [float(s.split()[0]) for s in m.group(1).split(", ")]
        steps.sort()

        return 0, steps

    def set_cpu_freq(self, value: Union[float, str], cpus: List[int]) -> int:
        """
        For the given CPUs, set the CPU governor or fix the CPU frequencies.

        Arguments
            `value: Union[float, str]` Either a valid CPU governor, or a frequency in GHz.
            `cpus: List[int]` IDs for the CPUs to set the CPU governor or CPU frequency

        Returns
            `err` where 0 indicates success and a non-zero value indicates an error.
        """
        if match(r"\d+(.\d+)?", str(value)):
            freq, gvnr = float(value), "performance"
        else:
            freq, gvnr = 0, value

        if self.fixed_freq == freq and self.governor == gvnr:
            return 0

        err = self._clear_fixed_cpu_freq()
        if err:
            return err

        cmd = f"for cpu in {' '.join([str(c) for c in cpus])}; do cpupower -c $cpu frequency-set -g {gvnr}"

        if freq > 0:
            cmd += f" --max {value}GHz --min {value}GHz"

        cmd += "; done"

        err, _ = self.cijoe.run(cmd)
        if err:
            log.error("Failed: cpupower")
            return 1

        self.fixed_freq = freq
        self.governor = gvnr

        return 0

    def _clear_fixed_cpu_freq(self, governor: str = "ondemand") -> int:
        """
        Reset any previously set specific CPU frequencies for all hyper threads.

        Returns
            `err` where 0 indicates success and a non-zero value indicates an error.
        """

        err, _ = self.cijoe.run(f"cpupower frequency-set -g {governor} --max 4.0GHz --min 0.8GHz")
        if err:
            log.error("Failed: cpupower")
            return 1

        self.fixed_freq = 0
        self.governor = governor

        return 0

    def toggle_turbo(self, on: bool) -> int:
        """
        Enable or disable turbo mode
        """

        if self._turbo == on:
            return 0

        cmd = (
            f"""if [[ -f "/sys/devices/system/cpu/intel_pstate/no_turbo" ]]; then
                echo {0 if on else 1} > /sys/devices/system/cpu/intel_pstate/no_turbo
            else
                echo {1 if on else 0} > /sys/devices/system/cpu/cpufreq/boost
            fi"""
        )

        err, _ = self.cijoe.run(cmd)
        if err:
            return err

        self._turbo = on

        return 0

    def toggle_smt(self, on: bool) -> int:
        """
        Enable or disable Simultaneous Multi-Threading (SMT)
        """

        if self._smt == on:
            return 0

        err, _ = self.cijoe.run(f"echo {'on' if on else 'off'} > /sys/devices/system/cpu/smt/control")
        if err:
            return err

        self._smt = on

        return 0

    def start_logging(self) -> int:
        """
        Start the CPU frequencu logger

        Returns `err`, where 0 indicates success and a non-zero value indicates an error.
        """

        if self._is_running:
            return 0

        err, _ = self.cijoe.run(f"{self._bin} {self._output} 0.5")
        if err:
            log.error(f"Failed: {self._bin}")
            return err

        self._is_running = True

        return 0

    def stop_logging_and_parse(self) -> Tuple[int, List]:
        """
        Stop the logger and parse results from the frequency logger
        """

        self.cijoe.run(f"pkill -f cpu_freq_logger")
        self._is_running = False

        err, state = self.cijoe.run(f"cat {self._output}")
        if err:
            log.error(f"Failed: cat {self._output}")
            return 1, None

        lines = state.output().split("\n")
        lo, hi = int(len(lines)*0.1), int(len(lines)*0.9)
        data = [[int(f) for f in line.split()[1:]] for line in lines[lo:hi]]

        avgs = []
        for col in zip(*data):
            avg = sum(col) / len(col)
            var = sum((x - avg) ** 2 for x in col) / len(col)
            avgs.append((avg, var))

        return 0, avgs

    def transfer_cpu_frequency_logger(self) -> int:
        """
        Transfer the CPU frequency logger to the remote machine.

        Returns
            `err`, where 0 indicates success and a non-zero value indicates an error.
        """

        self.cijoe.run(f"pkill -f {self._bin}; rm -f {self._bin}")

        if not (script := get_resources().get("auxiliary", {}).get("cpu_freq_logger", {})):
            log.error("Failed retrieving the shell-script from auxiliary files")
            return 1

        if not self.cijoe.put(script.path, self._bin):
            log.error("Failed transferring CPU frequency logger script from initator to target")
            return 1

        return 0
