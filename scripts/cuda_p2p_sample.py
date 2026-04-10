"""
Run I/O benchmarks
==================

Run many benchmarks using SPDK's I/O benchmarking tool, bdevperf.

Retargetable: True
------------------
"""

from pathlib import Path
from re import search
import logging as log

from cijoe.core.command import Cijoe


def main(args, cijoe: Cijoe):
  """Run cuda sample p2platency"""

  artifacts = Path(args.output) / "artifacts"

  sample_path = cijoe.getconf("nvidia.cuda.samples.path", None)
  if not sample_path:
    log.error("Failed: Missing path to cuda-samples")
    return -1

  bin = Path(sample_path) / "build" / "Samples" / "5_Domain_Specific" / "p2pBandwidthLatencyTest" / "p2pBandwidthLatencyTest"

  err, state = cijoe.run(f"{bin}")
  if err:
    log.error(f"Failed: run(p2pBandwidthLatencyTest); err({err})")
    return err

  regex = r"Bidirectional P2P=Enabled Bandwidth.*\n.*\n\s*\d+\s+([0-9.]+)\s+(?P<bw1>[0-9.]+).*\n\s*\d+\s+(?P<bw2>[0-9.]+)\s+([0-9.]+).*\n"
  m = search(regex, state.output())
  if not m:
    log.error("Failed: unexpected output from p2pBandwidthLatencyTest")
    return -1

  bandwidths = [float(v) for v in m.groupdict().values()]
  bandwidth = sum(bandwidths) / 2 #in GB/s

  with open(artifacts / "cuda-sample-p2p-bandwidth", "x") as out:
    out.write(f"{bandwidth}")

  return 0
