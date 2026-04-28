(sec-experiments-tool-comparison)=
# Benchmark Tool Comparison

The preceding experiment uses bdevperf, SPDK's block-device benchmark, to measure
CPU-initiated I/O performance. The question arises whether the choice of
benchmarking tool and the choice of user space NVMe driver affect the results.
To address both questions, we make an experiment where three tools are under
comparison:

- **bdevperf**: SPDK's block device benchmark. I/O is issued through SPDK's bdev
  (block device) abstraction layer, which interposes between the application and
  the underlying NVMe driver. The bdev layer provides a uniform interface across
  storage backends but introduces additional indirection in the I/O path.

- **SPDK NVMe Perf** (``perf``): SPDK's NVMe-level benchmark. Unlike bdevperf,
  this tool bypasses the bdev abstraction and issues NVMe commands directly
  through SPDK's NVMe driver. This eliminates bdev-layer overhead and measures
  the performance of SPDK's NVMe driver in isolation.

- **xnvmeperf**: xNVMe's benchmark tool. I/O is issued through xNVMe's
  backend-agnostic API, which dispatches to a pluggable backend at runtime.
  Three backends are exercised in this experiment: the **spdk** backend, the
  **upcie** backend and the **upcie-cuda**.

## I/O Paths

Understanding what each comparison reveals requires a precise account of the
software layers traversed by each tool.

**bdevperf** submits I/O via ``spdk_bdev_readv_blocks_with_md()``, which
dispatches through the SPDK bdev layer before reaching SPDK's NVMe driver.

**perf** submits I/O via ``spdk_nvme_ns_cmd_read()`` and related functions,
calling SPDK's NVMe driver directly without bdev involvement.

**xnvmeperf with the spdk backend** submits I/O via
``spdk_nvme_ctrlr_cmd_io_raw_with_md()``, the same SPDK NVMe driver entry point
used for raw command passthrough, reached through xNVMe's abstraction layer.
Completions are reaped via ``spdk_nvme_qpair_process_completions()``. Like
``perf``, this path does not involve the SPDK bdev layer.

**xnvmeperf with the upcie backend** submits I/O through a separate, independent
NVMe driver. The **upcie** backend constructs NVMe submission queue entries
directly, enqueues them by writing to MMIO doorbells, and polls the completion
queue by reading phase bits, without involving SPDK at any point.

**xnvmeperf with the upcie-cuda backend** follows the same NVMe command
submission path as the **upcie** backend, but data buffers reside in GPU device
memory rather than host memory. Buffer allocation uses CUDA device memory via
``cuMemAlloc``, exported as a dma-buf file descriptor and imported through the
udmabuf-import mechanism to obtain the physical addresses of the GPU memory
pages. These addresses are used to populate the PRP list in the NVMe command,
causing the NVMe controller to transfer data directly to or from GPU memory over
the PCIe fabric via peer-to-peer DMA, without passing through host DRAM.

The following table summarizes the layers traversed by each tool:

| Tool                           | Benchmark tool | NVMe abstraction | SPDK bdev layer | NVMe driver | Buffer placement |
| ------------------------------ | -------------- | ---------------- | --------------- | ----------- | ---------------- |
| bdevperf                       | bdevperf       | —                | yes             | SPDK        | Host             |
| perf                           | perf           | —                | no              | SPDK        | Host             |
| xnvmeperf + spdk backend       | xnvmeperf      | xNVMe            | no              | SPDK        | Host             |
| xnvmeperf + upcie backend      | xnvmeperf      | xNVMe            | no              | uPCIe       | Host             |
| xnvmeperf + upcie-cuda backend | xnvmeperf      | xNVMe            | no              | uPCIe       | Device (P2P)     |

## Comparisons and Their Interpretability

### bdevperf vs. perf

Both tools are SPDK-native and share the same benchmark design. The only
structural difference between them is the presence of the SPDK bdev layer in
bdevperf's path. Performance differences between these two tools can therefore
be attributed to the bdev layer in isolation.

### perf vs. xnvmeperf (SPDK backend)

Both tools reach SPDK's NVMe driver without involving the bdev layer, but they
differ in two respects: the benchmark tool itself, and the xNVMe abstraction
layer that sits between xnvmeperf and SPDK. Performance differences between
these two tools reflect the combined effect of both factors and cannot be
attributed to either in isolation.

### xnvmeperf (SPDK backend) vs. xnvmeperf (uPCIe backend)

Both configurations use the same benchmark tool and the same xNVMe abstraction
layer. The only structural difference is the NVMe driver: SPDK in one case,
uPCIe in the other. Performance differences between these configurations
reflect differences in NVMe driver implementation.

### xnvmeperf (uPCIe backend) vs. xnvmeperf (uPCIe-cuda backend)

Both configurations use the same benchmark tool, the same xNVMe abstraction
layer, and the same uPCIe NVMe driver. The only structural difference is buffer
placement: the upcie backend uses host memory, while the upcie-cuda backend
allocates data buffers in GPU device memory and transfers data via peer-to-peer
DMA over the PCIe fabric, bypassing host DRAM entirely. Performance differences
between these two configurations therefore reflect the effect of P2P buffer
placement on the data path, independent of the NVMe driver or benchmark tool.

## Experimental Setup

The experiment was run on the {ref}`sec-env-hpc-server`, the same environment
as the conventional CPU-initiated setup. All NVMe devices are bound to user space
drivers. The CPU governor is set to ``performance`` with turbo boost and SMT
enabled. Each benchmark configuration is run five times and results are reported
as arithmetic means.

The independent variables are:

| Variable              | Parameter Set                                                             |
| --------------------- | ------------------------------------------------------------------------- |
| Tool and backend      | { bdevperf, perf, xnvmeperf+spdk, xnvmeperf+upcie, xnvmeperf+upcie-cuda } |
| Queue depth           | { 128 }                                                                   |
| I/O size              | { 512 }                                                                   |
| Number of CPU threads | { 1, 2 }                                                                  |
| Number of devices     | { 16 }                                                                    |

(sec-experiments-tool-comparison-results)=
## Results

This section presents the results of the benchmark tool comparison experiment
described in {ref}`sec-experiments-tool-comparison`. The experiment has two
sides: first, comparing bdevperf, SPDK NVMe Perf, and xnvmeperf with the SPDK
backend, where all three tools exercise the same underlying SPDK NVMe driver but
differ in the software layers above it; second, comparing xnvmeperf with the
SPDK backend against xnvmeperf with the uPCIe backends (``upcie`` and
``upcie-cuda``), where the tool and xNVMe abstraction layer are held constant,
with the **upcie** and **upcie-cuda** backends further isolating the effect of
P2P buffer placement by sharing the same uPCIe driver.

```{figure} /barplot-tool.png
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
