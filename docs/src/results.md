(sec-results)=
# Results

In this section, we will present the results of running the experiments.

## Conventional CPU-initiated Setup

### Determining Device IOPS Capacity

To establish a device-side upper bound, we define device capacity as the maximum
IOPS observed in any single-device experiment. In our environment, we were able to
reach 3 857 938 IOPS with only one device, and as such, this was used as the
device capacity for our analysis.

% Average for all ndev=1: 3 099 640
% Median for all ndev=1: 3 766 518
% Average for ndev=1,gov=performance: 3 709 847
% Median for ndev=1,gov=performance: 3 844 043

### Optimal Parameterization

With all 16 devices utilized, we were able to reach this capacity of almost 62
million IOPS using 8 physical cores. The parameterization to achieve this was:

| Independent Variable     | Value              |
| ------------------------ | ------------------ |
| CPU frequency / governor | performance        |
| Turbo boost              | on                 |
| SMT                      | on                 |
| Thread siblings          | { used, not used } |
| Stress                   | { on, off }        |
| Queue depth              | 128                |
| I/O size                 | 512                |
| Number of cores          | 8                  |
| Number of devices        | 16                 |

When using thread siblings, it did not matter whether the unused CPUs were
stressed or idle. When not using thread siblings, stressing the unused CPUs caused
the IOPS to drop due to the resources of the physical cores being divided between
the bdevperf and stress-ng processes. The results for the parameterization above
were:

| Id | Thread siblings | Stress | Reached IOPS |
| -- | --------------- | ------ | ------------ |
| A  | used            | off    | 61 720 159   |
| B  | used            | on     | 61 622 306   |
| C  | not used        | off    | 61 712 325   |
| D  | not used        | on     | 41 065 835   |

Each parameterization has been given an id to allow for easy reference in the
following sections. Altering the values of the independent variables from the
best-performing parameter set, results in poorer performance. In the following, we
will describe how altering each variable independently affects the results. As the
parameterizations A, B and C elicit the best results, these will be at focus in
the following sections.

We saw that all three parameterizations respond similarly to changes in the
remaining independent variables. Because of this, we have only included the
results of parameterization C in our graphs for readability's sake. The presented
results for all graphs, are averages of running the experiments five times. Note
that variances are plotted as shaded areas around each line, but in most cases are
too small to be visible.

### Effect of the Independent Variables

In this section, we will inspect the effect on the results of changing the
independent variables.

#### CPU Frequency and Governors

We saw a significant decrease in reached IOPS when switching the CPU governor to
"powersave". On average, the results decreased by 64.19 % for parameterization
A-C.

| Parameterization Id | IOPS       | Change          |
| ------------------- | ---------- | --------------- |
| A                   | 23 972 222 | 61.2 % decrease |
| B                   | 23 879 418 | 61.3 % decrease |
| C                   | 18 422 224 | 70.2 % decrease |

When inspecting the CPU frequencies, we generally see that the performance CPU
governor keep the clock speed at 3.3 GHz for all CPUs, which is the maximum clock
speed we were able to reach with turbo boost enabled. The powersave governor
reduces the clock speed in order to reduce the power consumption, which explains

% A: Using, stress off: 23 972 222 - 61.16% decrease
% B: Using, stress on: 23 879 418 - 61.25% decrease
% C: Not using, stress off: 18 422 224 - 70.15% decrease
% D: Not using, stress on: 41 575 999 - 1.24% increase

#### Turbo Boost

When turning turbo boost off and thereby limiting the clock speed to 2.6 GHz, we
get small decrease, on average 4.4 % less IOPS.

| Parameterization Id | IOPS       | Change         |
| ------------------- | ---------- | -------------- |
| A                   | 59 731 756 | 3.2 % decrease |
| B                   | 59 570 168 | 3.3 % decrease |
| C                   | 57 606 912 | 6.7 % decrease |

% A: Using, stress off: 59 731 756 - 3.22% decrease
% B: Using, stress on: 59 570 168 - 3.33% decrease
% C: Not using, stress off: 57 606 912 - 6.65% decrease
% D: Not using, stress on: 33 003 158 - 19.63% decrease

However, we were able to reach similar results without turbo boost enabled by
doubling the amount of CPU cores, as we will go into detail with in a later
section.

#### SMT

When SMT is turned off, thread siblings are not available, and our results are
limited to parameterization C. Here, we saw a similar decrease as when turbo boost
was disabled. The measured CPU frequencies here do not exceed 2.6 GHz, indicating
that the performance CPU governor does not trigger turbo boost when SMT is
disabled, explaining the similar performance decrease.

| Parameterization Id | IOPS       | Change          |
| ------------------- | ---------- | --------------- |
| C                   | 57 965 380 | 6.1 % decrease  |
| D                   | 57 729 981 | 40.6 % increase |

Using a fixed CPU frequency with the *userspace* CPU governor of 3.0 GHz results
in higher IOPS when SMT is disabled, than the performance CPU governor.

| Parameterization Id | IOPS       | Change          |
| ------------------- | ---------- | --------------- |
| C                   | 61 664 783 | 0.1 % decrease  |
| D                   | 61 565 869 | 49.9 % increase |

Interestingly, we observe little difference between parameterization C and D
when SMT is disabled. This supports the explanation for why parameterization D
performs worse than A, B, and C with SMT disabled, each physical core can execute
only a single thread, eliminating contention but also preventing bdevperf from
benefiting from simultaneous multithreading.

% C: Not using, stress off: 57 965 380 - 6.07% decrease
% D: Not using, stress on: 57 729 981 - 40.58% increase
% C: 3GHz, Not using, stress off: 61 664 783 - 0.077% decrease
% D: 3GHz, Not using, stress on: 61 565 869 - 49.92% increase

#### Queue depth

We found that the results peaked when using a queue depth of 128. With turbo boost
enabled, we reached the device cap with both queue depths 128, 256 and 512, but
disabling turbo boost highlights the peak at 128.

```{figure} lineplot-spdk-qdepth.png
:alt: CPU bench results
:width: 700px
:align: center

Results of parameterization C with different queue depths.
```

#### I/O size

Increasing the I/O size to 4096 results in each operation taking more time, so the
reached IOPS decreases as seen in the graph. However, the bandwidth tells a
different story: it scales roughly proportionally with I/O size, doubling from
approximately 30 GiB/s at 512 bytes to approximately 215 GiB/s at 4096 bytes, where
it plateaus. This plateau coincides with the point at which IOPS drops sharply,
suggesting a bandwidth ceiling is reached rather than a CPU-side bottleneck.
Performance does not necessarily suffer from higher I/O sizes; the trade-off is
fewer, larger operations rather than degraded throughput.

```{figure} lineplot-spdk-iosize.png
:alt: CPU bench results
:width: 700px
:align: center

Results of parameterization C with different I/O sizes.
```

(sec-results-cpu-cores)=
#### Number of Cores

For the selected parameters, the results scale linearly with the amount of
physical CPU cores used until we reach a core-to-device ratio of 1:2. At this
point, we generally reach the device capacity when turbo boost is enabled.
However, disabling turbo boost results in an approximately 4.4 % decrease in IOPS,
and increasing the amount of CPUs gives diminishing returns, as seen in the graph
below. We are able to reach a similar result as with turbo boost enabled once the
core-to-device ratio is 1:1, meaning there is one core per device.

```{figure} lineplot-spdk-ncpus.png
:alt: CPU bench results
:width: 700px
:align: center

Results of parameterization C with and without turbo boost enabled.
```

#### Number of Devices

The results scale linearly with the amount of devices used.

```{figure} lineplot-spdk-ndevs.png
:alt: Graph showing the results of four benchmark results with optimal parameters
:width: 700px
:align: center

Results of parameterization C with different devices.
```

(sec-results-tool-comparison)=
## Benchmark Tool Comparison

This section presents the results of the benchmark tool comparison experiment
described in {ref}`sec-experiments-tool-comparison`. The experiment has two
sides: first, comparing bdevperf, SPDK NVMe Perf, and xnvmeperf with the SPDK
backend, where all three tools exercise the same underlying SPDK NVMe driver but
differ in the software layers above it; second, comparing xnvmeperf with the
SPDK backend against xnvmeperf with the uPCIe backends (``upcie`` and
``upcie-cuda``), where the tool and xNVMe abstraction layer are held constant,
with the **upcie** and **upcie-cuda** backends further isolating the effect of
P2P buffer placement by sharing the same uPCIe driver.

```{figure} barplot-tool.png
:alt: Results for running benchmarks with different tools and drivers
:width: 700px
:align: center

Results of running the experiment on a single core with one or two CPU threads.
```

% (tool):          (1 CPU thread) (2 CPU threads)
% bdevperf:              6340302     7408712
% spdk_nvme_perf:       10712199    15184483
%   -> without rdtsc:   12668440    15519287
% xnvmeperf-spdk:       14876017    17943035
% xnvmeperf-upcie:      37533134    47606095
% xnvmeperf-upcie-cuda: 37046501    47858195

### Benchmarking Tools Comparison

#### bdevperf vs. perf

**bdevperf** and **perf** share the same benchmark tool design and the same
underlying SPDK NVMe driver, so the difference between them reflects the SPDK bdev
abstraction layer alone. **perf** reaches approximately 70% higher IOPS than
**bdevperf** with one thread, and approximately twice the IOPS with two threads,
indicating that the bdev layer imposes substantial cost on this workload.

#### perf vs. xnvmeperf (SPDK Backend)

**xnvmeperf** with the SPDK backend reaches approximately 39% higher IOPS than **perf**
with one thread, and approximately 18% higher with two threads. As described in
{ref}`sec-experiments-tool-comparison`, this comparison is confounded: both the
benchmark tool and the xNVMe abstraction layer differ simultaneously, and the
result cannot be attributed to either factor alone.

A known contributor on the tool side is that **perf** performs per-I/O latency
tracking on the hot path. On every submission, it calls ``spdk_get_ticks()`` to
record a timestamp, and on every completion it calls ``spdk_get_ticks()`` again
to compute the elapsed time, then updates per-queue minimum, maximum, and total
TSC accumulators, and optionally records the sample in a histogram. In addition,
``spdk_get_ticks()`` is called on every iteration of the polling loop in
``work_fn``. ``spdk_get_ticks()`` maps to ``rdtsc``, a non-trivial instruction
that cannot be freely reordered; at tens of millions of IOPS the cumulative cost
of issuing it twice per I/O plus once per poll iteration becomes measurable.

Removing these calls from **perf** yields approximately 20% higher IOPS at one
thread, narrowing the gap to **xnvmeperf** to approximately 16%. The improvement
is substantially smaller at two threads (~2%). One possible explanation is that
SMT hides part of the ``rdtsc`` cost: when one hardware thread stalls on the
instruction, the other can continue making progress, partially absorbing the
latency rather than paying it in full. Even with latency tracking removed,
**xnvmeperf** remains ahead, indicating that tool design differences beyond
latency tracking also contribute to the result.

### NVMe Driver Comparison

Since all configurations in this section use **xnvmeperf**, backends are referred
to by name alone for brevity.

With the benchmark tool and xNVMe abstraction layer held constant, the **upcie**
backend reaches approximately 2.5 times the IOPS of the **spdk** backend across
both thread counts. As noted in {ref}`sec-experiments-tool-comparison`, this
comparison reflects differences in NVMe driver design, including the abstraction
layers within each driver, rather than the xNVMe abstraction layer, which is
held constant across both configurations. The **spdk** backend relies on SPDK,
which routes completions through ``spdk_nvme_qpair_process_completions`` operating
within SPDK's own runtime. The **upcie** backend relies on uPCIe, which uses a
leaner implementation that polls the completion queue directly by reading phase
bits and writes doorbells through direct MMIO, without an intervening runtime
layer. A contributing factor is that SPDK performs significantly more memory
operations per I/O: it copies the 64-byte command into an internal request
structure, clears approximately 315 bytes of request state via ``memset``, and
copies the payload metadata before the command reaches the submission queue.
uPCIe avoids these intermediate copies, referencing the command directly and
writing it once to the submission queue.

The **upcie-cuda** backend produces results within approximately 1% of the
**upcie** backend in both thread configurations. Since the two backends share
the same NVMe driver and differ only in buffer placement, this indicates that
routing the data path through P2P DMA to GPU device memory does not measurably
affect the IOPS achieved by the NVMe command submission path under these
conditions.

(sec-results-pcie-bandwidth)=
## PCIe Bandwidth Characterisation

This section presents the results of the experiment described in
{ref}`sec-experiments-pcie-bandwidth`.

```{figure} barplot-sat.png
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

### Small I/O: Link Underutilised

With 512-byte payloads, xnvmeperf reports 7.9 GB/s payload bandwidth and DCGM
measures 10.1 GB/s total PCIe receive traffic, corresponding to approximately 16%
of the PCIe Gen5 x16 line rate. This is consistent with the IOPS-bound regime
observed in {ref}`sec-results-tool-comparison`: at small I/O sizes the constraint
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
