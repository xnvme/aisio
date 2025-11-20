(sec-architecture)=
# Architecture

**AiSIO** implements a cooperative, multi-path I/O architecture that unifies the
conventional OS storage stack with accelerator-resident NVMe @{cite nvme-base-2.3} IO-drivers. This
architecture enables accelerators to initiate I/O at line rate while preserving
full interoperability with Linux and the universal abstractions of files and
their implementations in  existing file systems.

Two architectural variants exist:

- **Software-DPU (swDPU)** – a pure software multi-path design using `ublk`,
  SPDK, and xNVMe.

- **Hardware-managed multi-path (SR-IOV)** – using NVMe SR-IOV Virtual Functions
  to give the GPU its own I/O queue sets while the CPU retains control over
  administrative tasks.

Both designs share a common philosophy: the CPU performs metadata operations
and setup, while the GPU executes data-path operations using direct P2P DMA
and MMIO.

## The case for a multi-path IO architecture

The **AiSIO** initiative spans exploration of new IO-paths, optimization of
existing, and their interoperability. Why is that? you may ask, well the reason
is simply that there are no silver bullets, there are simply trade-offs to be
made when using a given IO-paths.

Considering CPU-initiated projects such as.. the same challenge.. 
The advent and widespread adoption of user-space storage stacks, and their
continued existance and evolution,

## Common Components

## Control Path (CPU-Resident)

The CPU participates only in metadata and control operations:

- **Filesystem Metadata Access**

  - Performed through XAL (eXtent Access Library), which parses on-disk XFS structures (superblock, AGs, inodes, extents) and exposes extent maps to the GPU.

  XAL parses XFS on-disk metadata directly, constructing an in-memory index
of superblocks, allocation groups, inodes, and extents. Compute kernels can
retrieve precise file-layout mappings without the file system being mounted.
This enables accelerators to issue precise block-level NVMe commands.

- **I/O Path Forking** – SPDK-based cooperative NVMe driver setup ensures the kernel has its own I/O queue pairs, while leaving the majority available for GPU usage.

- **Index Construction and Sharing** – XAL creates a filesystem index in host memory that can be queried by compute kernels.

## Data Path (GPU-Resident)

The GPU performs:

- NVMe command construction in GPU memory
- Posting of commands to I/O queues residing in GPU memory
- Direct P2P DMA transfers between the SSD and GPU memory

This eliminates host memory copies and closes the performance gap seen in CPU-initiated stacks such as GDS.

---

# AiSIO Multi-Path Architecture

AiSIO provides **two concurrent I/O paths**:

1. **Conventional OS Path** (CPU-initiated)
2. **Accelerator-Initiated Fast Path** (GPU-initiated)

Both paths operate on the same filesystem while sharing common metadata.

---

# Software-DPU (swDPU) Multi-Path

The swDPU architecture creates a *software-defined DPU* using commodity hardware and user-space components.

## Components

### ublk
Exposes a user-space block device where I/O requests from the kernel NVMe stack arrive. The ublk server forwards these to a cooperative SPDK NVMe driver.

### SPDK (Cooperative Driver)
Modified so that it does **not** consume all NVMe queue pairs, leaving the majority free for GPU assignment. It handles CPU-initiated I/O efficiently.

### xNVMe
Provides unified NVMe APIs for CPU and GPU, extended to support GPU invocation and BaM-like low-level access.

### XAL
Decodes XFS on-disk metadata and exposes extent information for GPU consumption.

## Fast-Path Operation (swDPU)

1. GPU requests file offsets from XAL.
2. GPU constructs NVMe commands, targeting GPU memory buffers.
3. Commands are posted to GPU-owned I/O queues in GPU memory.
4. SSD performs P2P DMA directly into GPU memory.

## Characteristics

- Works on all commodity hardware
- Achieves ~88% of BaM performance while retaining filesystem interoperability
- Provides the broadest platform compatibility

---

# Hardware-Managed Multi-Path (SR-IOV / VF-Accelerated)

AiSIO’s second architecture uses **NVMe SR-IOV** to expose multiple PCIe functions (PF and VFs) that all access the same NVMe namespaces, each with its own driver context and queue sets.

SR-IOV *can* provide isolation and QoS, but **this is not AiSIO’s motivation**. AiSIO uses VFs to create **independent driver endpoints** so that the OS and GPU can operate on the same namespace without interfering with each other's queues.

## Hardware Mechanisms

SR-IOV provides:

- A Physical Function (PF) for host control
- Multiple Virtual Functions (VFs), each with:
  - Independent PCIe config space
  - Separate BAR regions
  - Private MSI-X vectors
  - Private I/O queue sets (SQ/CQ)
- Shared namespaces for PF and all VFs

This allows assigning:
- PF or one VF → Linux kernel NVMe driver
- Another VF → GPU NVMe driver

## HW-Managed Fast Path

In this model, the **Admin Queue (AQ)** always remains **host-managed**.

### Sequence

1. Host configures PF and enables SR-IOV.
2. Host initializes AQ for PF and all VFs (AQ is always in host memory, CPU-handled).
3. AiSIO assigns one VF to the GPU as its I/O endpoint.
4. GPU maps the VF’s BARs, including doorbells and I/O queue memory.
5. GPU posts I/O commands to the VF's Submission Queues.
6. NVMe device performs P2P DMA directly to GPU memory.
7. CPU remains on the control path only (admin operations, metadata, scheduling).

## Why SR-IOV Helps AiSIO

AiSIO uses SR-IOV for:

- Independent driver contexts (kernel and GPU)
- Dedicated queue sets for the GPU
- Hardware arbitration instead of software
- Zero interference between OS and GPU I/O paths

Not for:
- tenant isolation
- QoS partitioning
- multi-tenant virtualization

## Trade-Offs

- Requires NVMe devices with strong SR-IOV support
- Requires PCIe P2P DMA routing
- Most platform-specific architecture
- Offers the lowest possible latency and cleanest separation of CPU vs GPU queues

---

# Comparison: swDPU vs HW-Managed

| Feature | swDPU | SR-IOV / HW-Managed |
|--------|--------|----------------------|
| Hardware requirements | Commodity hardware | NVMe SR-IOV + P2P-capable PCIe fabric |
| Fast-path arbitration | Software (SPDK/ublk) | Hardware (dedicated VF queues) |
| Admin Queue | Host-managed | Host-managed |
| GPU queue ownership | GPU allocates queues in GPU memory | GPU owns VF I/O queues |
| CPU involvement | Metadata only | Metadata only |
| Performance | ~88% of BaM | Expected to exceed swDPU |
| Interoperability | Full filesystem support | Same |
| Deployment | Easiest, most portable | Hardware-dependent |

