"""
Validate DcgmHelper against a live GPU: start monitoring, generate a GPU load
with dcgmproftester, stop and parse, and print per-field stats.

The load and the dcgmi monitoring both run on whatever target the given cijoe
config points at: with a ``[cijoe.transport.ssh]`` section they run on the
remote target, without one they run on this machine.

Usage:

  cijoe -c configs/local_gpu.toml scripts/validate_dcgm_helper.py

Requirements on the target: dcgmi + running nv-hostengine, screen, and a
dcgmproftester binary (name varies with the CUDA build, e.g. dcgmproftester13).

Expected outcome:
  - idle:      all activity fields ~0, PCIe at background-noise level
  - PCIe load: PCIE_RX_BYTES in the GB/s range, activity fields near 0
  - SM load:   GR_ENGINE_ACTIVE/SM_ACTIVE clearly nonzero, PCIe near idle
"""

from dcgm_helper import DcgmHelper

NAMES = {
    "1001": "GR_ENGINE_ACTIVE",
    "1002": "SM_ACTIVE",
    "1003": "SM_OCCUPANCY",
    "1005": "DRAM_ACTIVE",
    "1009": "PCIE_TX_BYTES",
    "1010": "PCIE_RX_BYTES",
    "100": "SM_CLOCK",
    "101": "MEM_CLOCK",
    "112": "THROTTLE_REASONS",
    "202": "PCIE_REPLAY",
    "237": "PCIE_LINK_GEN",
    "238": "PCIE_LINK_WIDTH",
}


def report(tag, stats):
    print(f"\n=== {tag} ===")
    for field, s in stats.items():
        n = len(s.get("samples") or [])
        fmt = lambda v: f"{v:,.3f}" if v is not None else "None"
        print(
            f"  {field:>4} {NAMES.get(field, '?'):<17} samples={n:<4}"
            f" mean={fmt(s.get('mean'))} p95={fmt(s.get('p95'))}"
            f" min={fmt(s.get('min'))} max={fmt(s.get('max'))}"
        )


def find_proftester(cijoe):
    """Find a dcgmproftester binary on the target, newest CUDA build first."""
    for name in ["dcgmproftester13", "dcgmproftester12", "dcgmproftester11", "dcgmproftester4"]:
        err, _ = cijoe.run(f"command -v {name}")
        if not err:
            return name
    return None


def main(args, cijoe):
    err, state = cijoe.run("hostname")
    print(f"target hostname: {state.output().strip()} (err={err})")

    err, state = cijoe.run("dcgmi discovery -l")
    if err:
        print("FAILED: dcgmi discovery — is nv-hostengine running on the target?")
        print(state.output()[-500:])
        return err

    proftester = find_proftester(cijoe)
    if not proftester:
        print("FAILED: no dcgmproftester binary found on the target")
        return 1
    print(f"using load generator: {proftester}")

    for tag, load_cmd in [
        ("idle (no load, 3s)", "sleep 3"),
        (f"PCIe load: {proftester} -t 1010", f"{proftester} --no-dcgm-validation -t 1010 -d 8"),
        (f"SM load: {proftester} -t 1002", f"{proftester} --no-dcgm-validation -t 1002 -d 8"),
    ]:
        dcgm = DcgmHelper(cijoe)
        err = dcgm.start()
        if err:
            print(f"FAILED to start dcgm monitoring for: {tag}")
            return err

        err, state = cijoe.run(load_cmd)
        if err:
            print(f"load command failed ({tag}): {state.output()[-500:]}")

        err, stats = dcgm.stop_and_parse()
        if err:
            print(f"FAILED to parse dcgm output for: {tag}")
            return err
        report(tag, stats)

    return 0
