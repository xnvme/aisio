# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

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

    Statistics cover the samples in which the benchmark was transferring rather
    than the whole monitoring window. The window also spans process startup and
    teardown, whose duration varies with the configuration under test, so a mean
    taken across that idle time describes the length of the setup as much as the
    behaviour of the workload.

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

    # A sample counts as active when the GPU either runs a kernel or receives
    # payload. Both matter: the device-initiated path keeps a kernel resident,
    # whereas the CPU-initiated P2P path runs none at all and shows up solely as
    # PCIe traffic. The receive floor sits well above the idle background of a
    # few hundred KB/s and well below any transfer under test.
    ACTIVE_GRACT = 0.01
    ACTIVE_RX_BYTES = 100e6

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

    def _active_indices(self, raw: Dict[str, List[Optional[float]]], count: int) -> List[int]:
        """
        Select the samples taken while the benchmark was transferring, by GPU
        kernel residency or by PCIe receive traffic. Without either field to
        judge by — neither monitored, or reported as ``N/A`` throughout — every
        sample is kept.
        """

        gract = raw.get("1001") or []
        rx = raw.get("1010") or []
        if not any(value is not None for value in gract + rx):
            return list(range(count))

        def above(values: List[Optional[float]], idx: int, floor: float) -> bool:
            value = values[idx] if idx < len(values) else None
            return value is not None and value > floor

        def active(idx: int) -> bool:
            return above(gract, idx, self.ACTIVE_GRACT) or above(rx, idx, self.ACTIVE_RX_BYTES)

        return [idx for idx in range(count) if active(idx)]

    def stop_and_parse(self) -> Tuple[int, Dict[str, dict]]:
        """
        Stop monitoring and parse collected samples.

        Returns ``(err, stats)`` where ``stats`` maps each field ID to a dict
        with keys ``samples``, ``mean``, ``p95``, ``min``, and ``max``. Values
        are in the native unit reported by dcgmi dmon (bytes/sec for PCIe
        fields, ratios for profiling activity fields, MHz for clocks). min/max
        are what matter for guard fields (112 throttle bits,
        237/238 link state), where a mean over samples has no physical meaning.

        Only the transferring samples are described. ``active_fraction`` records
        the share of the window they made up, so a run whose setup dominated the
        window remains recognisable after the fact. A window holding no transfer
        at all is described whole, with ``active_fraction`` at zero. A sample a
        field reports as ``N/A`` holds its place in that field and is left out
        of its statistics, keeping the selection aligned across fields.
        """
        self.cijoe.run("pkill -f dcgmi; sleep 0.2")
        self._is_running = False

        err, state = self.cijoe.run(f"cat {self._output}")
        if err:
            log.error(f"Failed: cat {self._output}")
            return 1, None

        raw: Dict[str, List[Optional[float]]] = {f: [] for f in self.fields}
        for line in state.output().splitlines():
            stripped = line.strip()
            if not stripped.startswith("GPU"):
                continue
            # dmon line format: "GPU <id>   <val1>   <val2>   ..."
            parts = stripped.removeprefix(f"GPU {self.gpu}").split()
            for i, field in enumerate(self.fields):
                try:
                    raw[field].append(float(parts[i]))
                except (IndexError, ValueError):
                    # dcgmi reports "N/A" until a profiling field has produced
                    # its first sample. Recording the gap keeps every field the
                    # same length, so index i denotes the same sample instant
                    # in all of them, which is what the selection below reads.
                    raw[field].append(None)

        count = max((len(values) for values in raw.values()), default=0)
        active = self._active_indices(raw, count)
        active_fraction = len(active) / count if count else 0.0
        if not active:
            # The guard fields describe the link and the clocks whether or not
            # anything transferred, so the window is described whole rather
            # than left empty. active_fraction stays at zero, which is what
            # marks the statistics as covering an idle window.
            log.warning("No active samples in the dcgm window; describing all of it")
            active = list(range(count))

        stats = {}
        for field, values in raw.items():
            selected = [
                values[idx]
                for idx in active
                if idx < len(values) and values[idx] is not None
            ]
            if not selected:
                stats[field] = {"samples": [], "mean": None, "p95": None, "min": None, "max": None}
                continue
            ordered = sorted(selected)
            stats[field] = {
                "samples": selected,
                "mean": mean(selected),
                # quantiles() wants at least two points to interpolate between
                "p95": quantiles(ordered, n=100, method="inclusive")[94]
                if len(ordered) > 1
                else ordered[0],
                "min": ordered[0],
                "max": ordered[-1],
            }

        stats["active_fraction"] = {
            "samples": [],
            "mean": active_fraction,
            "p95": active_fraction,
            "min": active_fraction,
            "max": active_fraction,
        }

        return 0, stats
