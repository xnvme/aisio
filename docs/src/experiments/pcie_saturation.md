<!--
SPDX-FileCopyrightText: Samsung Electronics Co., Ltd

SPDX-License-Identifier: BSD-3-Clause
-->

(sec-experiments-pcie-bandwidth)=
# CPU-Initiated P2P I/O: PCIe Bandwidth Saturation

The {ref}`sec-experiments-tool-comparison` experiment showed that the
**upcie-cuda** backend matches **upcie** in IOPS within measurement variance,
confirming that routing data through P2P DMA to GPU device memory does not
measurably affect command throughput. Both preceding experiments were conducted
at 512-byte I/O, where each command carries so little data that the PCIe link
operates far below capacity even at tens of millions of IOPS. The bottleneck
is how fast commands can be submitted and completed, not how much data the link
can carry. At larger I/O sizes the bottleneck shifts: as each command carries
more payload, the PCIe link itself becomes the limiting factor. The question
this experiment asks is how few CPU resources and devices are required to reach
that point.

This experiment fixes CPU threads at 1 and devices at 4, then sweeps I/O size
across three points (512, 4096, and 8192 bytes), measuring both the payload
bandwidth reported by xnvmeperf and the total PCIe receive traffic observed by
DCGM at the GPU endpoint. The gap between the two reveals the share of the link
consumed by NVMe and PCIe protocol traffic rather than payload: Submission and
Completion Queue Entries, PRP list transfers, and framing. A reference
host-to-device bandwidth from ``nvbandwidth`` establishes the practical ceiling
of the link under sustained transfers into GPU memory.

## Independent Variables

The experiment fixes all parameters except NVMe command data payload size:

| Variable              | Value                  |
| --------------------- | ---------------------- |
| Tool and backend      | xnvmeperf + upcie-cuda |
| Queue depth           | 128                    |
| Number of CPU threads | 1                      |
| Number of devices     | 4                      |
| I/O size              | { 512, 4096, 8192 }    |

Four devices were selected to ensure that the PCIe link, rather than aggregate
device capacity, is the binding constraint at large I/O sizes. The Samsung PM1753
is rated at 14.5 GB/s bandwidth, and four devices therefore provide up to
4 × 14.5 GB/s = 58 GB/s aggregate, which is sufficient to stress the PCIe Gen5 x16
link (64 GB/s line rate) rather than leave it underutilized.

## Metrics Collected

| Metric                                   | Reported by                              |
| ---------------------------------------- | ---------------------------------------- |
| Payload bandwidth (GB/s)                 | xnvmeperf                                |
| PCIe RX bandwidth (bytes/s)              | DCGM field 1010 (PCIE_RX_BYTES)          |
| SM activity (fraction of SMs occupied)   | DCGM field 1002 (SM_ACTIVE)              |
| GPU memory bandwidth utilization         | DCGM field 1005 (DRAM_ACTIVE)            |
| PCIe link generation and width           | DCGM fields 237/238                      |
| Run validity guards                      | DCGM fields 100/101/112/202              |
| Host-to-device PCIe bandwidth (GB/s)     | ``nvbandwidth``                          |

The DCGM fields are collected as described in {ref}`sec-dcgm-sampling`.

## Environment

The benchmarks were run on the {ref}`sec-env-hpc-server`. NVMe devices are bound to
user space drivers. The CPU governor is set to ``performance`` with turbo boost and
SMT enabled. Each configuration is run five times and results are reported as
arithmetic means.

The namespaces are formatted before the run, as described in
{ref}`sec-device-fill-state`.

## Execution of the Experiment

Instructions for running ``bench_pcie.yaml`` are provided in
{ref}`sec-experimental-framework`.

(sec-experiments-pcie-bandwidth-results)=
## Results

```{figure} /barplot-sat.png
:alt: Stacked bar chart of PCIe bandwidth by I/O size
:width: 700px
:align: center

PCIe RX bandwidth by NVMe command data payload size, measured with 4 PCIe Gen5
NVMe SSDs transferring data P2P to a PCIe Gen5 GPU via the upcie-cuda backend.
Each bar is stacked: the lower segment is the payload bandwidth reported by
xnvmeperf; the upper segment is the remainder observed by DCGM, taken as the p95
of field 1010 rather than the mean, since the transferring samples include the
ramp up. The dashed lines
mark the PCIe line rate (64.0 GB/s for the Gen5 x16 link derived from the
measured DCGM link fields 237/238) and the reference host-to-device bandwidth
from ``nvbandwidth`` (53.3 GB/s). Result files that predate the link
fields fall back to an assumed Gen5 x16 link, labelled ``(assumed)``.
```

### Small I/O: Link Underutilized

With 512-byte payloads, xnvmeperf reports 7.9 GB/s payload bandwidth and DCGM
measures 10.1 GB/s total PCIe receive traffic, corresponding to approximately 16%
of the PCIe Gen5 x16 line rate. This is consistent with the IOPS-bound regime
observed in the {ref}`software abstraction overhead results
<sec-experiments-tool-comparison-results>`: at small I/O sizes the constraint is
NVMe command throughput, not PCIe link capacity.

### Large I/O: Link Approaches Saturation

With 4096- and 8192-byte payloads, DCGM measures approximately 57.8 GB/s in both
cases, exceeding the ``nvbandwidth`` reference of 53.3 GB/s and
reaching approximately 90% of the 64.0 GB/s line rate. The identical result at
both I/O sizes indicates that the PCIe link, rather than NVMe command throughput,
is the binding constraint at these I/O sizes. xnvmeperf reports approximately
45.2 GB/s of payload bandwidth for both sizes. This saturation is achieved
with a single CPU thread and only four NVMe devices, demonstrating that the
uPCIe-cuda path requires minimal CPU and device resources to fully utilize the
PCIe link at larger I/O sizes.

### PCIe Protocol Overhead

Across all three I/O sizes, the total PCIe receive bandwidth measured by DCGM
exceeds the payload bandwidth reported by xnvmeperf by a consistent factor of
approximately 1.28. The ratio holds across both the IOPS-bound regime at 512 bytes
and the bandwidth-bound regime at 4096 and 8192 bytes, spanning a range where IOPS
differ by an order of magnitude. This indicates that the excess scales with bytes
transferred rather than with operation count, making the 28% overhead a stable
characterization of the P2P data path regardless of operating regime.

## Summary

At small I/O sizes the P2P link operates far below capacity. At 4 KiB and above,
a single CPU thread driving four NVMe devices is sufficient to push total PCIe
traffic to approximately 57.8 GB/s, exceeding the practical host-to-device
ceiling of 53.3 GB/s and reaching approximately 90% of the Gen5 x16 line rate.
Protocol overhead accounts for a consistent 28% above payload bandwidth across
all tested I/O sizes, indicating it scales with bytes transferred rather than
operation count.
