(sec-experimental-framework)=
# Experimental Framework

This section describes the system configuration, software stack, and benchmark
workflows used to produce the experimental results. It covers both the synthetic
NVMe benchmarks that characterize raw I/O performance and the file-based
benchmarks that evaluate end-to-end dataset loading.

## System Setup

All environment provisioning is automated using
[CIJOE](https://github.com/refenv/cijoe), a tool for systems development
and testing. CIJOE runs on a local initiator machine and connects to a
remote target over SSH. Shell commands and Python scripts are collected
into YAML workflow definitions that document the execution sequence and
combined purpose. Input values are kept separate from scripts in TOML
configuration files, so the same workflow can be replicated across
different environments without modifying the scripts themselves. After
execution, CIJOE generates a report covering command output, script
documentation, collected artifacts, and a workflow summary.

Step-by-step instructions for running the CIJOE setup tasks are provided
in the ``README.md`` of the AiSIO repository. The table below lists all
software components installed on each system, in installation order.

| Category | Component                  | Version              | Install       | Description                                                                                                                         |
| -------- | -------------------------- | -------------------- | ------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| OS       | Ubuntu Server              | 24.04.4              | ISO           | Base operating system; GA kernel required (HWE must be disabled)                                                                    |
| Kernel   | Linux + udmabuf-import     | 6.8 GA + patch       | Source        | Ubuntu GA kernel patched to add DMA-buf importer support to UDMABUF, enabling physical address resolution of device memory from user space |
| NVIDIA   | MLNX\_OFED                 | {{ ver_ofed }}       | Source        | Mellanox OFED with NVMe-oF, NFS-RDMA, and GPUDirect Storage support                                                                |
| NVIDIA   | Open Kernel Modules        | {{ ver_nokm }}       | APT           | NVIDIA open-source GPU kernel driver                                                                                                |
| NVIDIA   | CUDA Toolkit               | {{ ver_cuda }}       | APT           | CUDA compiler, runtime, and libraries                                                                                               |
| NVIDIA   | nvidia-fs                  | {{ ver_cuda }}       | APT           | GPUDirect Storage kernel module                                                                                                     |
| AiSIO    | fio                        | {{ ver_fio }}        | Source        | I/O benchmark tool; built from source for SPDK plugin integration                                                                   |
| AiSIO    | SPDK                       | {{ ver_spdk }}       | Source        | Storage Performance Development Kit; provides the user space NVMe driver and bdevperf                                              |
| AiSIO    | xNVMe                      | {{ ver_xnvme }}      | Source        | Unified NVMe command interface with uPCIe backend support                                                                           |
| AiSIO    | xal                        | {{ ver_xal }}        | Source        | XFS Abstraction Library for file-to-block extent resolution                                                                         |
| AiSIO    | fil                        | {{ ver_fil }}        | Source        | File Iterator Library; benchmark harness used to evaluate different I/O backends                                                    |
| Tools    | devbind                    | —                    | pipx          | NVMe PCIe driver binding utility                                                                                                    |
| Tools    | hugepages                  | —                    | pipx          | Huge page allocation management utility                                                                                             |

## Benchmarks

The benchmarks fall into two groups: synthetic benchmarks that issue I/O
directly against raw NVMe devices, and file-based benchmarks that load
datasets from an XFS filesystem on a dedicated NVMe device.

### Synthetic

Synthetic benchmarks issue I/O directly to NVMe devices via user space
drivers, bypassing the kernel filesystem stack. They require a device
configuration file listing the NVMe block devices to use.
``configs/devices_16.toml`` is provided as an example and must be edited
to match the target system. Device PCI addresses can be found with:

```
lspci | grep Non-Volatile
```

If the boot device is an NVMe device, it must be excluded from driver
rebinding by setting the ``xnvme.driver.prefix`` key in the
configuration file:

```toml
[xnvme.driver]
prefix = "PCI_BLACKLIST=0000:01:00.0"
```

Devices must be unbound from the kernel NVMe driver and bound to
``uio_pci_generic``. Huge pages are also required, as both SPDK and
xNVMe uPCIe rely on DMA-capable memory that must be physically
contiguous and pinned:

```
devbind --device '<pci_addr>' --bind uio_pci_generic
hugepages setup --count 1024
```

The benchmark workflows are parameterised by editing the ``run`` step in
the respective task file. The keys under ``with`` correspond to
independent variables. ``numcpus_range`` and ``numdevs_range`` are
inclusive tuples defining the range of values tested, not complete
lists. An optional ``results_dir`` key enables continuation of a
previous run, and ``repetitions`` controls the number of runs per
configuration (default: 5). When re-running benchmarks without changing
system state, the hugepage allocation and driver binding steps can be
skipped by specifying only the steps to execute:

```
cijoe \
    -c configs/transport.toml \
    -c configs/aisio.toml \
    -c configs/devices_16.toml \
    tasks/bench_io.yaml \
    run combine visualize
```

Results are rendered as an interactive HTML page at
``cijoe-output/artifacts/benchmark-results.html``, which allows results
from different parameterizations to be compared.

#### CPU-initiated I/O (``bench_io.yaml``)

Characterizes the maximum IOPS achievable through CPU-driven I/O using
SPDK's bdevperf across a wide parameter space. Described in detail in
{ref}`sec-experiments-cpu-initiated`.

```
cijoe --monitor \
    -c configs/transport.toml \
    -c configs/aisio.toml \
    -c configs/devices_16.toml \
    tasks/bench_io.yaml
```

#### CPU-initiated I/O: Software Abstraction Overhead (``bench_tools.yaml``)

Runs bdevperf, SPDK NVMe Perf, and xnvmeperf (with the spdk, upcie, and
upcie-cuda backends) under identical parameters to isolate the effect of
tool and driver implementation on measured IOPS. Described in detail in
{ref}`sec-experiments-tool-comparison`.

```
cijoe --monitor \
    -c configs/transport.toml \
    -c configs/aisio.toml \
    -c configs/devices_16.toml \
    tasks/bench_tools.yaml
```

#### CPU-Initiated P2P I/O: PCIe Bandwidth Saturation (``bench_pcie.yaml``)

Characterizes PCIe link utilization on the **upcie-cuda** path by running
xnvmeperf at varying I/O sizes while collecting hardware-level PCIe bandwidth
counters via DCGM and a reference P2P bandwidth measurement from
``p2pBandwidthLatencyTest``. Described in detail in
{ref}`sec-experiments-pcie-bandwidth`.

``nvstack.toml`` is required to supply the CUDA samples path and DCGM
field configuration used during the run.

```
cijoe --monitor \
    -c configs/transport.toml \
    -c configs/aisio.toml \
    -c configs/devices_16.toml \
    -c configs/nvstack.toml \
    tasks/bench_pcie.yaml
```

#### Device-initiated I/O: I/O Size Scaling (``bench_cuda_iosize.yaml``)

Characterizes the minimum CUDA thread count needed to saturate the PCIe link
under device-initiated I/O, using **xnvmeperf** with the ``cuda-run`` subcommand
and the **upcie-cuda** backend, with queue depth as the secondary variable.
Described in detail in {ref}`sec-experiments-cuda-iosize`.

``nvstack.toml`` is required to supply the CUDA samples path used during the
run.

```
cijoe --monitor \
    -c configs/transport.toml \
    -c configs/aisio.toml \
    -c configs/devices_16.toml \
    -c configs/nvstack.toml \
    tasks/bench_cuda_iosize.yaml
```

#### Device-initiated I/O: Queue Depth Scaling (``bench_cuda_qdepth.yaml``)

Characterizes how IOPS scales with queue depth under device-initiated I/O, using
**xnvmeperf** with the ``cuda-run`` subcommand and the **upcie-cuda** backend,
with the number of queues per device as the secondary variable. Described in
detail in {ref}`sec-experiments-cuda-qdepth`.

```
cijoe --monitor \
    -c configs/transport.toml \
    -c configs/aisio.toml \
    -c configs/devices_16.toml \
    tasks/bench_cuda_qdepth.yaml
```

### File-based

File-based benchmarks load datasets from an XFS filesystem on a dedicated
NVMe device. The device and mount point are specified in
``configs/datasets.toml``. The following workflow formats the device, mounts it,
and generates the synthetic datasets, and runs an XFS
defragmentation pass to ensure contiguous file layout:

```
cijoe --monitor \
    -c configs/transport.toml \
    -c configs/datasets.toml \
    tasks/setup_dataset.yaml
```

Three datasets are generated, each modeling a different real-world
workload in terms of file count and file size distribution:

**imagenetish** models an image classification dataset. It consists of
1000 classes with 1000 to 1400 files each (1.0–1.4 million files total),
with individual file sizes between 75 KB and 150 KB.

**tiktokish** models a short-form video library. It consists of 32 classes
with 14 files each (448 files total), with individual file sizes between
7 MiB and 8 MiB.

**filesize8gib** models a large-file workload. It consists of 20 files,
each exactly 8 GiB, used to evaluate performance with large individual
files.

All datasets are generated with a fixed random seed to ensure
reproducibility across systems.

The required driver binding depends on the benchmark: the AiSIO benchmark
uses the xNVMe uPCIe path and requires the device bound to
``uio_pci_generic`` with hugepages allocated:

```
umount /mnt/datasets
devbind --device '<pci_addr>' --bind uio_pci_generic
hugepages setup --count 1024
```

GDS, POSIX, and GDS transfer mode benchmarks operate through the kernel
NVMe driver and require the device bound to ``nvme`` with the filesystem
mounted:

```
devbind --device '<pci_addr>' --bind nvme
mount /dev/<nvme_dev> /mnt/datasets
```

#### AiSIO / uPCIe (``bench_aisio.yaml``)

This benchmark consists of two parts. First, the tiktokish and imagenetish
datasets are loaded through FIL using the ``aisio-cpu`` backend, measuring
end-to-end dataset loading performance over the AiSIO storage path. The
``filesize8gib`` dataset is excluded because individual files exceed the
256 MiB xNVMe uPCIe host-memory heap limit. Second, synthetic random-read
benchmarks are run with xnvmeperf using the ``upcie`` (CPU completion) and
``upcie-cuda`` (GPU completion) backends, measuring raw I/O throughput on
the uPCIe path.

```
cijoe --monitor \
    -c configs/transport.toml \
    -c configs/aisio.toml \
    -c configs/datasets.toml \
    tasks/bench_aisio.yaml
```

#### NVIDIA GPUDirect Storage (``bench_gds.yaml``)

This benchmark evaluates NVIDIA GPUDirect Storage using the FIL
interface. It loads all three datasets (imagenetish, tiktokish,
filesize8gib) through the ``gds`` backend, and runs synthetic sequential
and random-read benchmarks using gdsio.

```
cijoe --monitor \
    -c configs/transport.toml \
    -c configs/datasets.toml \
    tasks/bench_gds.yaml
```

#### POSIX (``bench_posix.yaml``)

This benchmark provides a POSIX I/O baseline by loading all three
datasets through the ``posix`` backend of FIL. It serves as a
baseline comparison against the GDS and AiSIO paths.

```
cijoe --monitor \
    -c configs/transport.toml \
    -c configs/datasets.toml \
    tasks/bench_posix.yaml
```

#### GDS Transfer Mode Comparison (``compare_gds_xfermodes.yaml``)

This workflow uses gdsio to evaluate different GDS transfer types for
small 4 KiB I/O. The GDS API exposes multiple transfer modes (XferType)
that differ in how data is moved between storage and GPU memory, and this
benchmark identifies which is most suitable for small-I/O workloads.

```
cijoe --monitor \
    -c configs/transport.toml \
    -c configs/datasets.toml \
    tasks/compare_gds_xfermodes.yaml
```
