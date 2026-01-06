(sec-experiment)=
# Experiment

(meta text)

## Conventional CPU-initiated Setup

In the first experimental setup, the I/O is CPU-driven and the host-memory is
used for submission and completion queues, and for command payloads. All tests
are driven by SPDK's benchmarking tool, bdevperf, wrapped in a Python script that
automates running the experiment with different parameters.

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

| Variable                 | Used values                            |
| ------------------------ | -------------------------------------- |
| Queue depth              | { 64, 128, 256 }                       |
| I/O size                 | { 512, 4096 }                          |
| Number of devices        | { 1, 2, ..., 8 }                       |
| Number of cores          | { 1, 2, ..., 16 }                      |
| CPU frequency / governor | { powersave, performance, 3.0 GHz }    |
| Turbo boost              | { on, off }                            |
| SMT                      | { on, off }                            |
| Thread siblings          | { used, not used }                     |
| Stress                   | { on, off }                            |

The cartesian product of the sets of these variables, filtered to avoid an illegal
combination of (SMT off, thread siblings used), yields the full set of benchmark
runs.

### Metrics Collected

The collected metrics are:

| Metric                         | Reported by                                               |
| ------------------------------ | --------------------------------------------------------- |
| Completed IOPS                 | bdevperf                                                  |
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

Hardware

- CPU: 2x Intel® Xeon® Gold 6442Y Processor
- Block devices: 16x Samsung SSD PM1753
- ...

Firmware

- Block devices were bound to the uio-pci-generic userspace driver
- The CPU used the intel_pstate driver
- ...

### Stressing unused CPUs

The independent variable "Unused CPUs stressed vs. idle" describes whether the
tool stress-ng is used to put a workload on the logical CPUs, not covered by the
CPU mask given to bdevperf.

The purpose of testing with and without stressing the unused CPUs is to evaluate
how other processes in the system impact the achievable IOPS.
