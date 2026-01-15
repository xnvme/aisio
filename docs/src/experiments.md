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

| Variable                 | Used values                            |
| ------------------------ | -------------------------------------- |
| Queue depth              | { 64, 128, 256 }                       |
| I/O size                 | { 512, 4096 }                          |
| Number of cores          | { 1, 2, ..., 8 }                       |
| Number of devices        | { 1, 2, ..., 16 }                      |
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

### Execution of the Experiment

The setup and execution of the experiment is automated by two cijoe workflows,
which necessitates a cijoe configuration file. See ``configs/bench-amd.toml`` for
an example configuration file.

#### Configuration file

The configuration file must contain the information about the following:

1. SSH transport info
1. Block devices
1. A prefix for the ``xnvme-driver`` script
1. OS name and version
1. Necessary repositories

You must change the values under the ``cijoe.transport.bench`` key to have the
correct remote hostname, username and path to a ssh key (or password). If you run
the cijoe script on same machine as the benchmarks, delete the full
``cijoe.transport.bench`` key completely. You may change the ``bench`` part of the
key, if you want. For example, if you want multiple transports to different remote
machines. Be aware that the it is only the first defined transport that is used.

The configuration file must also define a list of NVMe block devices. To find
these, run

    lspci | grep Non-Volatile

and change the `pci_addr` keys in the `[[devices]]` to match the PCI addresses of
the found devices. There are 12 block devices in the configuration file, but you
can add more or remove devices as needed. The ``iops`` key should describe the
expected peak IOPS the device is able to reach. If this is unknown, write any
number and run the benchmarks to find the value. These values are just used in the
visualisation to create a horizontal marker to indicate the peak IOPS.

The cijoe workflow assumes that if the boot device is an NVMe device, then the
``xnvme.driver.prefix`` key has been defined in the configuration file to add the
device's PCIe address to the PCI_BLACKLIST env variable for the xnvme-driver
script. Example:

    [xnvme.driver]
    prefix = "PCI_BLACKLIST=0000:01:00.0"

It's important that if the boot device is also an NVMe device that it is added in
the ``PCI_BLACKLIST``, since the xnvme-driver script otherwise might unbind it,
making the machine unusable (until next reboot).

The OS name and version should be lowercasem and can be found by running

    cat /etc/os-release

Lastly, this experiment requires SPDK and xNVMe to be installed on the system. The
example configuration file does not need any changes for the ``spdk.repository``
and ``xnvme.repository`` keys.

#### Setup of the experiment

The cijoe workflow in ``tasks/setup_benchmark_bdevperf.yaml`` is responsible for
installing all dependencies on the system. When the configuration file is created,
it can be run with command

    cijoe --monitor \
      tasks/setup_benchmark_bdevperf.yaml \
      -c config/YOUR_CONFIG_FILE.toml

#### Running the experiment

When the system has been setup, the cijoe workflow must be configured with the
right benchmarking parameters. In the file ``tasks/bench_bdevperf_cpu.yaml``, the
step "run" has multiple keys under "with" which represent the independent
variables of the experiment. The key ``results_dir`` is optional, but allows
continuation of previously run benchmarks. Note that the ``numcpus_range`` and
``numdevs_range`` are tuples describing the range of CPUs and block devices used
for testing, both inclusive, meaning it is not a complete list of values for these
independent variables. A key ``repetitions`` can be added to change the number of
times each benchmark is run; if not defined, the default is 5 repetitions.

When the "run" step has been parameterized, the workflow can be run with command

    cijoe --monitor \
      tasks/bench_bdevperf_cpu.yaml \
      -c config/YOUR_CONFIG_FILE.toml

This workflow makes sure to allocate hugepages and bind the block devices to
userspace drivers before running the benchmarks. This is not necessary to do
repeatedly if running the benchmarks multiple times in a row. These steps can be
skipped by specifying which steps to run in the command

    cijoe --monitor \
      tasks/bench_bdevperf_cpu.yaml \
      -c config/YOUR_CONFIG_FILE.toml \
      run visualize

In the final step, the results of the experiment is visualized on a graph in an
interactive HTML page, which can be found in the cijoe artifacts found in
``cijoe-output/artifacts/benchmark-results.html``. With this HTML page, the
results of different parametirizations can be compared.
