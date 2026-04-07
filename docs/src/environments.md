(sec-environment)=
# Environments

This section describes the system configurations used for experimenting
with AiSIO system software architectures, including the initial AiSIO
proof-of-concept and the development of a reference implementation. These
environments support evaluation, document constraints encountered during
development, and serve as reproducible reference builds for readers wishing to
explore similar architectures.

The same environments were also used to reproduce, where possible, benchmarks
from related work, specifically GDS {cite}`nvidia-gds` and BaM {cite}`bam2023`,
ensuring controlled comparison under identical system conditions.

The configurations reflect practical system builds intended to support
architectural exploration, implementation, and comparative evaluation, rather
than prescribing production deployment guidelines.

All environments are configured with the platform prerequisites for P2P DMA:
Resizable BAR enabled, Above 4G Decoding enabled, IOMMU disabled, and ACS
disabled. Note that the availability and naming of these options varies across
BIOS vendors; for example, Resizable BAR may appear as "ReBAR", "Resizable BAR
Support", or "Re-Size BAR Support".

(sec-env-hpc-server)=
## High-Performance Compute Server

An enterprise-grade dual-socket server with high-capacity NVMe storage, used
for the primary CPU-initiated I/O and benchmark tool comparison experiments.
The platform, GPU, and NVMe storage all operate at PCIe Gen5, providing
full-bandwidth connectivity throughout the system. With 32 × 64 GiB of DDR5, the
system provides 2 TiB of host memory.

| Hardware    | Details                            |
| ----------- | ---------------------------------- |
| Motherboard | Dell PowerEdge R760                |
| CPU         | 2x Intel® Xeon® Gold 6442Y         |
| Memory      | 32x 64GiB Samsung DDR5 4800MHz     |
| GPU         | 2x NVIDIA H100 80GB                |
| Storage     | 16x Samsung SSD PM1753 32TB        |

(sec-env-gpu-workstation)=
## Professional GPU Workstation

A workstation built around a professional-grade GPU with a high core-count
CPU, used for development and evaluation of the reference implementation. The
platform, GPU, and NVMe storage all operate at PCIe Gen4.

| Hardware    | Details                          |
| ----------- | -------------------------------- |
| Motherboard | Supermicro H12SSL-I                  |
| CPU         | 1x AMD EPYC 7532 32-Core (Rome)      |
| Memory      | 8x 32GiB Samsung DDR4 2667MHz        |
| GPU         | 1x NVIDIA RTX A5000 24GB             |
| Storage     | 4x Samsung 990 PRO 2TB               |

The system supports P2P between all seven PCIe slots, which can be populated
with varying combinations of GPUs, NVMe devices, and RDMA NICs, making it an
ideal testbed for accelerator-integrated storage I/O topologies.

(sec-env-desktop)=
## Desktop Workstation

A consumer desktop used for development and light experimentation. Both the
NVIDIA RTX A2000 6GB and the NVIDIA RTX PRO 2000 Blackwell 16GB have been used
and validated in this environment. The AMD B550 platform limits PCIe bandwidth
to Gen4 on CPU-direct slots, constraining the RTX PRO 2000 Blackwell below its
Gen5 capability. A single NVMe device limits aggregate storage bandwidth and
precludes multi-device parallelism.

| Hardware    | Details                                                    |
| ----------- | ---------------------------------------------------------- |
| Motherboard | MSI MAG B550M MORTAR WIFI                                  |
| CPU         | 1x AMD Ryzen 7 5800X 8-Core                                |
| Memory      | 2x 16GiB DDR4 2133MHz                                      |
| GPU         | 1x NVIDIA RTX PRO 2000 Blackwell 16GB / RTX A2000 6GB      |
| Storage     | 1x Samsung 980 PRO 1TB                                     |

Unlike the {ref}`sec-env-gpu-workstation`, P2P is only possible between devices
installed in the PCIe expansion slot labelled **PCI_E1** and the M.2 slot
labelled **M2_1**. These are connected to the CPU root complex whereas the other
PCIe and M.2 slots are connected to the platform controller hub (PCH).

(sec-env-legacy)=
## Legacy GPU Server

A server with legacy Volta-generation GPUs, used for pre-work
{cite}`torp2025gpu_initiated_io` and the initial AiSIO proof-of-concept
{cite}`aisio-fms2025,aisio-ocp2025`. Although the system is PCIe Gen4, the V100
is a PCIe Gen3 device, limiting peak GPU bandwidth to approximately 16 GB/s per
slot and constraining peer-to-peer DMA throughput compared to Gen4 systems.

| Hardware    | Details                            |
| ----------- | ---------------------------------- |
| Motherboard | Gigabyte G292-Z20                  |
| CPU         | 1x AMD EPYC 7402P 24-Core          |
| Memory      | 8x 32GiB SK Hynix DDR4 2400MHz     |
| GPU         | 2x NVIDIA V100 16GB                |
| Storage     | 4x Samsung 980 PRO 1TB             |

The system has four risers, each connected to the motherboard via a PCIe Gen4
x16 slot and carrying a Microsemi PCIe Gen4 switch with two x16 downstream
ports. Notably, data can move P2P via the switch without traversing the CPU
root complex.
