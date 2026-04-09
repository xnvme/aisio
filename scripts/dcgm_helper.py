from cijoe.core.command import Cijoe
from pathlib import Path
from statistics import mean, quantiles
from typing import Dict, List, Optional, Tuple
import logging as log


class DcgmHelper:
    """
    Start and stop dcgmi dmon monitoring and parse the collected samples.

    Requires dcgmi and screen to be available on the target system. Fields
    are DCGM profiling field IDs passed to ``dcgmi dmon -e``. The defaults
    (1009, 1010) correspond to PCIe TX and RX bytes per second, which is the
    primary metric of interest for P2P transfers in the upcie-cuda path.

    Configure via cijoe config:

        [dcgm]
        fields = ["1009", "1010"]
        gpu = 0
    """

    def __init__(self, cijoe: Cijoe, gpu: Optional[int] = None, fields: Optional[List[str]] = None):
        self.cijoe = cijoe
        self.gpu = gpu if gpu is not None else cijoe.getconf("dcgm.gpu", 0)
        self.fields = fields if fields is not None else cijoe.getconf("dcgm.fields", ["1009", "1010"])
        self._output = Path("/tmp/dcgm_monitor.txt")
        self._is_running = False

    def start(self) -> int:
        """
        Start dcgmi dmon in the background via screen.

        Returns 0 on success, non-zero on failure.
        """
        if self._is_running:
            return 0

        self.cijoe.run(f"rm -f {self._output}")

        fields_arg = ",".join(self.fields)
        cmd = f'screen -dm bash -c "dcgmi dmon -d 100 -i {self.gpu} -e {fields_arg} > {self._output}"'
        err, _ = self.cijoe.run(cmd)
        if err:
            log.error("Failed: dcgmi dmon")
            return err

        self._is_running = True
        return 0

    def stop_and_parse(self) -> Tuple[int, Dict[str, dict]]:
        """
        Stop monitoring and parse collected samples.

        Returns ``(err, stats)`` where ``stats`` maps each field ID to a dict
        with keys ``samples``, ``mean``, and ``p95``. Values are in the native
        unit reported by dcgmi dmon (bytes/sec for PCIe fields).
        """
        self.cijoe.run("pkill -f dcgmi; sleep 0.2")
        self._is_running = False

        err, state = self.cijoe.run(f"cat {self._output}")
        if err:
            log.error(f"Failed: cat {self._output}")
            return 1, None

        raw: Dict[str, List[float]] = {f: [] for f in self.fields}
        for line in state.output().splitlines():
            stripped = line.strip()
            if not stripped.startswith("GPU"):
                continue
            # dmon line format: "GPU <id>   <val1>   <val2>   ..."
            parts = stripped.removeprefix(f"GPU {self.gpu}").split()
            for i, field in enumerate(self.fields):
                if i < len(parts):
                    try:
                        raw[field].append(float(parts[i]))
                    except ValueError:
                        pass  # skip N/A entries

        stats = {}
        for field, values in raw.items():
            if not values:
                stats[field] = {"samples": [], "mean": None, "p95": None}
                continue
            stats[field] = {
                "samples": values,
                "mean": mean(values),
                "p95": quantiles(sorted(values), n=100, method="inclusive")[94],
            }

        return 0, stats
