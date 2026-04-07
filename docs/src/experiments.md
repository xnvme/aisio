(sec-experiments)=
# Experiments

(meta text)

## Conventional CPU-initiated Setup

In the first experimental setup, the I/O is CPU-driven and the host-memory is
used for submission and completion queues, and for command payloads. All tests
are driven by SPDK's benchmarking tool, bdevperf, wrapped in a Python script that
automates running the experiment with different parameters. The results are
reported as the average of running each benchmark five times to reduce the impact
of variance between runs.

### Independent variables

For the experiment, five environmental conditions were defined as independent
variables:

- Fixed CPU frequency or CPU governor
- Turbo boost enabled vs. disabled
- SMT enabled vs. disabled
- Thread siblings used vs. not used
- Unused CPUs stressed vs. idle

Furthermore, a single run of bdevperf is run with the following arguments:

- Queue depth
- I/O size
- Configuration file
- CPU mask
- Time in seconds
- Read-write type

Each run lasted 10 seconds, and the read-write type used was "randread" for all
runs. The configuration file and CPU mask describe how many and which block
devices and CPUs to use, respectively. The independent variables defined from
these arguments were queue depth, I/O size, number of devices and number of
physical cores.

The construction of the bdevperf configuration file with the right amount of block
devices was automated, given the total list of devices on the system and the
desired amount for this specific run.

To construct the CPU mask, logical CPUs were added depending on their ID in
increasing order until the desired amount of cores was reached. NUMA nodes were
not considered, as experiments showed it did not have a significant impact on the
results. When using thread siblings, the amount of logical CPUs used are doubled,
as there are two threads on each of the cores.

The complete list of independent variables and the values for the variables are:

| Variable                 | Parameter Set              |
| ------------------------ | -------------------------- |
| CPU frequency / governor | { powersave, performance } |
| Turbo boost              | { on, off }                |
| SMT                      | { on, off }                |
| Thread siblings          | { used, not used }         |
| Stress                   | { on, off }                |
| Queue depth              | { 64, 128, 256 }           |
| I/O size                 | { 512, 4096 }              |
| Number of cores          | { 1, 2, 4, 8 }             |
| Number of devices        | { 1, 2, 4, 8, 16 }         |

The Cartesian product of the variable sets, excluding the illegal combination of
SMT off with thread siblings used, defines the full set of benchmark runs.

After identifying the parameterization which yielded the highest IOPS, we
individually expanded the set of values for each variable to explore the results
beyond the initial selection. The expanded parameter set is listed below. Note
that not all combinations in the expanded parameter set were tested.

| Variable                 | Expanded Parameter Set                 |
| ------------------------ | -------------------------------------- |
| CPU frequency / governor | { powersave, performance }             |
| Queue depth              | { 8, 16, 32, 64, 128, 256, 512, 1024 } |
| I/O size                 | { 512, 1024, 2048, 4096, 8192 }        |
| Number of cores          | { 1, 2, ..., 16 }                      |
| Number of devices        | { 1, 2, ..., 16 }                      |

### Metrics Collected

The collected metrics are:

| Metric                         | Reported by                                               |
| ------------------------------ | --------------------------------------------------------- |
| Completed IOPS                 | bdevperf                                                  |
| Bandwidth (MiB/s)              | bdevperf                                                  |
| CPU utilisation (%)            | ``/usr/bin/time``                                         |
| Measured CPU frequencies (kHz) | ``/sys/devices/system/cpu/cpuX/cpufreq/scaling_cur_freq`` |

All numbers are reported as arithmetic means over the 10-second measurement
interval.

As bdevperf uses busy polling, it will always result in approx. N\*100% CPU
utilisation, where N is the number of used logical CPUs.

The CPU frequencies of each logical CPU is collected by a minimal shell script
that reads from ``/sys/devices/system/cpu/cpuX/cpufreq/scaling_cur_freq`` every
0.5 seconds for each used CPU with ID ``X``. The read frequencies, reported in
kHz, are appended to a log and later averaged. This script is started before
running the benchmarks and stopped immediately after. To account for the time
before and after the benchmarks where the script is running, but bdevperf is
not, the first and last 10% of the reported cpu frequencies are discarded.

### Environment

The benchmarks were run on the **H100 80G** machine described in the Environments
section. All block devices were empty and bound to the uio-pci-generic user space
driver. The CPU used the intel_cpufreq driver.

#### Empty vs. Populated Block Devices

In this work, the goal is to measure the maximum IOPS the CPU and I/O stack are
capable of driving. For this reason, benchmarks are executed against empty block
devices. Using empty devices minimizes variability introduced by data layout,
garbage collection, and background maintenance operations, allowing results to
more directly reflect CPU scheduling, interrupt handling, and I/O submission and
completion paths.

While this methodology may produce IOPS figures that exceed those seen in real-
world, data-bearing workloads, it provides a clearer upper bound on CPU-driven I/O
capability. These results should therefore be interpreted as a measure of system
overhead and scalability rather than as an indicator of application-level storage
performance.

Because of this, the theoretical device capacity for random reads of 3.2 million
IOPS of the Samsung PM1753 is not applicable in these experiments. To determine a
relevant cap, we use the maximum IOPS reached from any experiment using only one
device. The determined capacity was only used in the analysis of the results to
evaluate whether the benchmark was capped by the device, CPU, or the
parameterization.

#### Stressing Unused CPUs

The independent variable "Unused CPUs stressed vs. idle" describes whether the
tool stress-ng is used to put a workload on the logical CPUs, not covered by the
CPU mask given to bdevperf.

The purpose of testing with and without stressing the unused CPUs is to evaluate
how other processes in the system impact the achievable IOPS.

### Execution of the Experiment

The execution of the experiment is automated by a cijoe workflow, which
necessitates multiple cijoe configuration files. Most are given in this
repository, but the ``configs/devices_16.toml`` configuration file is an example
and must be edited to match the system you are running on.

#### Configuration File

A configuration file must contain the information about the following:

1. Block devices
1. A prefix for the ``xnvme-driver`` script

This configuration file must define a list of NVMe block devices. To find
these, run

    lspci | grep Non-Volatile

and change the `pci_addr` keys in the `[[devices]]` to match the PCI addresses of
the found devices. There are 16 block devices in the example configuration file,
but you can add more or remove devices as needed.

The cijoe workflow assumes that if the boot device is an NVMe device, then the
``xnvme.driver.prefix`` key has been defined in the configuration file to add the
device's PCIe address to the PCI_BLACKLIST env variable for the xnvme-driver
script. Example:

    [xnvme.driver]
    prefix = "PCI_BLACKLIST=0000:01:00.0"

It's important that if the boot device is also an NVMe device that it is added in
the ``PCI_BLACKLIST``, since the xnvme-driver script otherwise might unbind it,
making the machine unusable (until next reboot).

#### Setup of the Experiment

The machine must be provisioned as described in the AiSIO repository README file,
and the devices on the machine can be populated with the task defined in
``tasks/populate_devices.yaml`. When the configuration file is created,
it can be run with command

    cijoe --monitor \
      tasks/populate_devices.yaml \
      -c configs/aisio.toml \
      -c configs/devices_16.toml

#### Running the Experiment

When the system has been setup, the cijoe workflow must be configured with the
right benchmarking parameters. In the file ``tasks/bench_io.yaml``, the
step "run" has multiple keys under "with" which represent the independent
variables of the experiment. The key ``results_dir`` is optional, but allows
continuation of previously run benchmarks. Note that the ``numcpus_range`` and
``numdevs_range`` are tuples describing the range of CPUs and block devices used
for testing, both inclusive, meaning it is not a complete list of values for these
independent variables. A key ``repetitions`` can be added to change the number of
times each benchmark is run; if not defined, the default is 5 repetitions.

When the "run" step has been parameterized, the workflow can be run with command

    cijoe --monitor \
      tasks/bench_io.yaml \
      -c configs/aisio.toml \
      -c configs/devices_16.toml

This workflow makes sure to allocate hugepages and bind the block devices to
user space drivers before running the benchmarks. This is not necessary to do
repeatedly if running the benchmarks multiple times in a row. These steps can be
skipped by specifying which steps to run in the command

    cijoe \
      tasks/bench_io.yaml \
      -c configs/aisio.toml \
      -c configs/devices_16.toml
      run combine visualize

In the final step, the results of the experiment is visualized on a graph in an
interactive HTML page, which can be found in the cijoe artifacts found in
``cijoe-output/artifacts/benchmark-results.html``. With this HTML page, the
results of different parametirizations can be compared.

(sec-experiments-tool-comparison)=
## Benchmark Tool Comparison

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

### I/O Paths

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

### Comparisons and Their Interpretability

#### bdevperf vs. perf

Both tools are SPDK-native and share the same benchmark design. The only
structural difference between them is the presence of the SPDK bdev layer in
bdevperf's path. Performance differences between these two tools can therefore
be attributed to the bdev layer in isolation.

#### perf vs. xnvmeperf (SPDK backend)

Both tools reach SPDK's NVMe driver without involving the bdev layer, but they
differ in two respects: the benchmark tool itself, and the xNVMe abstraction
layer that sits between xnvmeperf and SPDK. Performance differences between
these two tools reflect the combined effect of both factors and cannot be
attributed to either in isolation.

#### xnvmeperf (SPDK backend) vs. xnvmeperf (uPCIe backend)

Both configurations use the same benchmark tool and the same xNVMe abstraction
layer. The only structural difference is the NVMe driver: SPDK in one case,
uPCIe in the other. Performance differences between these configurations
reflect differences in NVMe driver implementation.

#### xnvmeperf (uPCIe backend) vs. xnvmeperf (uPCIe-cuda backend)

Both configurations use the same benchmark tool, the same xNVMe abstraction
layer, and the same uPCIe NVMe driver. The only structural difference is buffer
placement: the upcie backend uses host memory, while the upcie-cuda backend
allocates data buffers in GPU device memory and transfers data via peer-to-peer
DMA over the PCIe fabric, bypassing host DRAM entirely. Performance differences
between these two configurations therefore reflect the effect of P2P buffer
placement on the data path, independent of the NVMe driver or benchmark tool.

### Experimental Setup

The experiment uses the same hardware environment as the conventional
CPU-initiated setup described in {ref}`sec-experiments`. All NVMe devices are
bound to user space drivers. The CPU governor is set to ``performance`` with
turbo boost and SMT enabled. Each benchmark configuration is run five times
and results are reported as arithmetic means.

The independent variables are:

| Variable              | Parameter Set                                                             |
| --------------------- | ------------------------------------------------------------------------- |
| Tool and backend      | { bdevperf, perf, xnvmeperf+spdk, xnvmeperf+upcie, xnvmeperf+upcie-cuda } |
| Queue depth           | { 128 }                                                                   |
| I/O size              | { 512 }                                                                   |
| Number of CPU threads | { 1, 2 }                                                                  |
| Number of devices     | { 16 }                                                                    |

### Results

Results are presented in {ref}`sec-results-tool-comparison`.
