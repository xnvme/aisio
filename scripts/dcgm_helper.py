from cijoe.core.command import Cijoe
from pathlib import Path
from statistics import mean, quantiles
from typing import Dict, List, Optional, Tuple
import logging as log


# Raw PCIe line rate per lane in GB/s by link generation (matches the
# "line rate" convention used by the report rooflines: Gen5 x16 = 64 GB/s)
PCIE_LANE_GBPS = {1: 0.25, 2: 0.5, 3: 1.0, 4: 2.0, 5: 4.0, 6: 8.0}


def pcie_link_from_dcgm(dcgm) -> Optional[Tuple[int, int, float]]:
    """
    Derive ``(gen, width, line_rate_gbps)`` of the GPU's PCIe link from a
    result's ``"dcgm"`` entry, using fields 237 (link gen) and 238 (link
    width). Accepts both the per-run schema (stats are floats) and the
    combined schema (stats are ``[avg, stddev]`` pairs); returns None for
    legacy scalar entries or when the fields are missing. Uses the ``max``
    stat: ASPM parks the link at Gen1 while idle, so the maximum observed
    during a run is the operational link state.
    """
    if not isinstance(dcgm, dict):
        return None

    def stat_max(field):
        stats = dcgm.get(field)
        value = stats.get("max") if isinstance(stats, dict) else None
        if isinstance(value, (list, tuple)):
            value = value[0]
        return value

    gen, width = stat_max("237"), stat_max("238")
    if gen is None or width is None:
        return None
    gen, width = round(gen), round(width)
    lane_rate = PCIE_LANE_GBPS.get(gen)
    if lane_rate is None:
        return None
    return gen, width, lane_rate * width


class DcgmHelper:
    """
    Start and stop dcgmi dmon monitoring and parse the collected samples.

    Requires dcgmi and screen to be available on the target system. Fields
    are DCGM field IDs passed to ``dcgmi dmon -e``; profiling fields
    (DCGM_FI_PROF_*, 1xxx) and regular device fields can be mixed. The
    defaults cover:

    - 1009/1010: PCIe TX/RX bytes per second (headers + payload)
    - 1001/1002/1003: GR_ENGINE_ACTIVE, SM_ACTIVE, SM_OCCUPANCY — GPU
      compute cost of the persistent polling kernel in the upcie-cuda path
    - 1005: DRAM_ACTIVE — bottleneck discriminator (PCIe-bound vs HBM-bound)
    - 100/101: SM/MEM clocks, 112: throttle reason bitmask — run validity
    - 202: PCIe replay counter, 237/238: link gen/width — link health

    Configure via cijoe config:

        [dcgm]
        fields = ["1009", "1010"]
        gpu = 0
    """

    DEFAULT_FIELDS = [
        "1009", "1010",  # PCIe TX/RX bytes/s
        "1001", "1002", "1003", "1005",  # GRACT, SMACT, SMOCC, DRAMA
        "100", "101", "112",  # SM clock, MEM clock, throttle reasons
        "202", "237", "238",  # PCIe replay, link gen, link width
    ]

    def __init__(self, cijoe: Cijoe, gpu: Optional[int] = None, fields: Optional[List[str]] = None):
        self.cijoe = cijoe
        self.gpu = gpu if gpu is not None else cijoe.getconf("dcgm.gpu", 0)
        self.fields = fields if fields is not None else cijoe.getconf("dcgm.fields", self.DEFAULT_FIELDS)
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
        with keys ``samples``, ``mean``, ``p95``, ``min``, and ``max``. Values
        are in the native unit reported by dcgmi dmon (bytes/sec for PCIe
        fields, ratios for profiling activity fields, MHz for clocks). min/max
        are what matter for guard fields (112 throttle bits, 237/238 link
        state), where a mean over samples has no physical meaning.
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
                stats[field] = {"samples": [], "mean": None, "p95": None, "min": None, "max": None}
                continue
            stats[field] = {
                "samples": values,
                "mean": mean(values),
                "p95": quantiles(sorted(values), n=100, method="inclusive")[94],
                "min": min(values),
                "max": max(values),
            }

        return 0, stats
