(sec-experiments-pcie-bandwidth)=
# PCIe Bandwidth Characterization

With the **upcie-cuda** driver, NVMe command data payloads are transferred directly
to GPU device memory via P2P DMA, and therefore we want to inspect how much of the
available PCIe bandwidth the data path consumes relative to the link capacity.
Application-level benchmarks such as xnvmeperf report payload bytes, but do not
account for the NVMe and PCIe protocol traffic that accompanies each transfer. As
such, we also want to evaluate whether the payload bandwidth reported by the
benchmark tool agrees with what the PCIe hardware counters observe.

This experiment runs the **upcie-cuda** path and compares the payload bandwidth
reported by **xnvmeperf** against the total PCIe receive traffic independently
observed by DCGM. The difference between the two reveals the share of the link
consumed by NVMe and PCIe protocol traffic rather than payload. To contextualize
both figures against the practical ceiling of the P2P link, the experiment also
measures peak bidirectional P2P bandwidth using ``p2pBandwidthLatencyTest`` from
the CUDA samples suite.

## Independent Variables

The experiment fixes all parameters except NVMe command data payload size:

| Variable              | Value                  |
| --------------------- | ---------------------- |
| Tool and backend      | xnvmeperf + upcie-cuda |
| Queue depth           | 128                    |
| Number of CPU threads | 1                      |
| Number of devices     | 4                      |
| I/O size              | { 512, 4096, 8192 }    |

## Metrics Collected

| Metric                                  | Reported by                        |
| --------------------------------------- | ---------------------------------- |
| Payload bandwidth (GB/s)                | xnvmeperf                          |
| Total PCIe RX bandwidth (p95, bytes/s)  | DCGM field 1010 via ``dcgmi dmon`` |
| Peak P2P bidirectional bandwidth (GB/s) | ``p2pBandwidthLatencyTest``        |

DCGM field 1010 counts PCIe receive bytes per second at the GPU endpoint, capturing
all PCIe traffic directed to the GPU including NVMe payload, NVMe Submission Queue
Entries, Completion Queue Entries, and PRP list transfers. The p95 is taken over
100 ms samples collected during the benchmark run. **xnvmeperf** reports payload
bytes per second based on completed I/O operations and their requested sizes.

``p2pBandwidthLatencyTest`` from the CUDA samples suite runs a sustained
bidirectional P2P bandwidth test between two GPUs. The value recorded is the mean
of the per-direction bandwidth measured simultaneously in both directions.

## Environment

The benchmarks were run on the {ref}`sec-env-hpc-server`. NVMe devices are bound to
user space drivers. The CPU governor is set to ``performance`` with turbo boost and
SMT enabled. Each configuration is run five times and results are reported as
arithmetic means.

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
xnvmeperf; the upper segment is the remainder observed by DCGM. The dashed lines
mark the PCIe Gen5 x16 line rate (64.0 GB/s) and the reference P2P bandwidth from
``p2pBandwidthLatencyTest`` (55.98 GB/s).
```

### Small I/O: Link Underutilized

With 512-byte payloads, xnvmeperf reports 7.9 GB/s payload bandwidth and DCGM
measures 10.1 GB/s total PCIe receive traffic, corresponding to approximately 16%
of the PCIe Gen5 x16 line rate. This is consistent with the IOPS-bound regime
observed in {ref}`sec-experiments-tool-comparison-results`: at small I/O sizes the constraint
is NVMe command throughput, not PCIe link capacity.

### Large I/O: Link Approaches Saturation

With 4096- and 8192-byte payloads, DCGM measures approximately 57.8 GB/s in both
cases, approaching the ``p2pBandwidthLatencyTest`` reference of 55.98 GB/s and
reaching approximately 90% of the 64.0 GB/s line rate. The identical result at
both I/O sizes indicates that the PCIe link, rather than NVMe command throughput,
is the binding constraint at these I/O sizes. xnvmeperf reports approximately
45.2 GB/s of payload bandwidth for both sizes.

### PCIe Protocol Overhead

Across all three I/O sizes, the total PCIe receive bandwidth measured by DCGM
exceeds the payload bandwidth reported by xnvmeperf by a consistent factor of
approximately 1.28. The consistency of this ratio across I/O sizes and IOPS levels
indicates that the excess scales with bytes transferred rather than with operation
count.
