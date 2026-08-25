<!--
SPDX-FileCopyrightText: Samsung Electronics Co., Ltd

SPDX-License-Identifier: BSD-3-Clause
-->

(sec-future-work)=

# Future Work

The work presented here is bounded in two important ways. First, HOMI is a
reference implementation under active development rather than a complete
system: several architectural components described in Section
{ref}`sec-architecture` are not yet realized in the current PoC. Second,
the scope is limited to locally-attached NVMe storage, leaving remote and
disaggregated storage as an open direction. The following sections describe
the most significant areas of future work along these dimensions and others.

## Completing the HOMI Reference Implementation

The most immediate area of future work is completing the HOMI reference
implementation described in Section {ref}`sec-architecture`. The current
PoC demonstrates key aspects of the design in a reduced form, but the
full reference implementation requires several components not yet in place:
a persistent host-resident control-plane daemon, dynamic provisioning and
reassignment of NVMe queue resources across initiators, and coordinated
lifecycle management spanning OS-managed, user space managed, and
device-initiated I/O paths. Dynamic queue management is of particular
importance, as it is a prerequisite for supporting workloads where the set
of active initiators changes at runtime. The current PoC relies exclusively
on SR-IOV for hardware-assisted queue isolation, a feature limited to
datacenter-grade NVMe devices. Completing the HOMI reference implementation
includes realizing the ublk-based software-mediated multipath configuration
described in Section {ref}`sec-architecture`, which removes this hardware
dependency and enables the architecture to operate on commodity storage
hardware.

## Kernel Integration and Upstream Components

Several capabilities this architecture depends on are absent from the software
it builds upon and cannot be supplied by it. They are enumerated here with
what each blocks and where responsibility for it lies, so that engaging with
the relevant communities becomes a matter of selecting an item. Each was
established by measurement on the evaluation machines rather than inferred
from documentation.

### Mapping accelerator memory into an I/O address space

`IOMMU_IOAS_MAP_FILE` accepts dma-buf file descriptors exported by `vfio-pci`
and rejects those exported by accelerator runtimes, so a controller operating
behind an IOMMU cannot perform DMA into accelerator memory.
Accelerator-initiated I/O is therefore confined to `uio_pci_generic`, where
the controller consumes physical addresses and no IOMMU is interposed, which
excludes the multi-tenant and virtualized deployments where an IOMMU is not
optional.

Measured on Linux 7.0.0-28-generic against both an NVIDIA RTX A6000 and an AMD
Radeon RX 7800 XT: mapping a `memfd` succeeds, while mapping a dma-buf
exported by either CUDA or HIP returns `ENOTSUP`.

Responsibility lies with the iommufd and dma-buf subsystems. The question is
not whether the ioctl can be relaxed but how an address space should respond
when an exporter relocates or revokes the underlying pages; `move_notify` is
the mechanism, and whether iommufd should carry that obligation is the
substance of the discussion.

### CPU mappings of exported device memory

A dma-buf exported from a PCIe BAR by `vfio-pci` provides no CPU mapping,
which was confirmed for every slice size attempted. This prevents a
controller's doorbell registers from being delegated to another process in
isolation: were such a mapping available, a process could be granted a
descriptor covering only the doorbell page, with no route to the controller's
configuration registers or to a device reset. Without one, the device file
descriptor itself must be transferred, and every process holding it shares a
single trust domain.

Responsibility lies with the VFIO subsystem. The export was designed for
peer-to-peer DMA, where CPU access is deliberately absent; adding it requires
that such mappings be revoked on device reset, which VFIO already implements
for mappings obtained through the device file descriptor.

### Accelerator runtime import of external descriptors

Where a CPU mapping is unavailable, an equivalent result would follow if the
accelerator runtime imported the descriptor itself. Neither vendor supports
this. The CUDA runtime rejects `CU_EXTERNAL_MEMORY_HANDLE_TYPE_DMABUF_FD` with
`CUDA_ERROR_NOT_SUPPORTED`, and a control experiment importing a dma-buf that
CUDA itself exported fails identically, establishing that the refusal concerns
dma-buf import in general rather than device memory or VFIO in particular. The
HIP runtime provides no dma-buf handle type at all, its
`hipExternalMemoryHandleType` enumeration terminating at `NvSciBuf`.

Responsibility lies with the respective vendors rather than with an upstream
community, and engagement accordingly takes the form of defect reports.

### Registration of I/O memory by the HIP runtime

An accelerator kernel signals a controller by writing a doorbell register
mapped into its address space, which under CUDA is achieved by registering a
host mapping of the BAR as I/O memory. The HIP runtime documents the
corresponding flag as unsupported and registration fails accordingly, so
accelerator-initiated submission is unavailable on AMD hardware irrespective
of the storage-side arrangement.

### Address visibility for imported descriptors

The udmabuf-import patch, which extends the udmabuf driver to import arbitrary
dma-buf file descriptors and expose physical address mappings to user space,
is currently maintained as an out-of-tree kernel patch, because no stable
userspace interface exposes those addresses. Upstreaming this interface, or
contributing an equivalent mechanism through a suitable kernel subsystem,
would remove the requirement for a custom kernel build and allow the user
space P2P path to be exercised on unmodified production systems.

Responsibility lies with the dma-buf subsystem. This is the least tractable of
the items enumerated here, since exposing such addresses to user space is
precisely what the interface is designed to avoid, and any engagement should
be framed around the translation problem to be solved rather than around a
particular interface.

### Convergence with kernel-managed peer-to-peer I/O

The Linux kernel's io_uring and dma-buf integration for CPU-initiated P2P I/O
is under active development in mainline. As this path stabilizes, a direct
comparison between the kernel-managed and user space managed P2P architectures
described in Section {ref}`sec-architecture` becomes possible on identical
hardware, an evaluation that would clarify the performance and operational
trade-offs between the two approaches.

## Broader Accelerator Support

The current PoC is developed and validated against NVIDIA GPUs using CUDA for
device memory allocation and dma-buf export. The I/O path itself — built on
xNVMe, uPCIe, and dma-buf — is not NVIDIA-specific, as these components
operate on any dma-buf exporter. The CUDA dependency is therefore confined to
the memory management layer. Extending support to AMD GPUs via ROCm requires
work in three areas. First, device memory allocation must be ported from
`cuMemAlloc` to the HIP equivalent. Second, dma-buf export must be adapted
from `cuMemGetHandleForAddressRange` to the corresponding amdgpu kernel driver
interface. Third, the device-resident NVMe driver must be ported from CUDA to
HIP; this is the most substantial effort.

## Multi-Accelerator Topologies

While multi-accelerator support is a goal of this work, only
single-accelerator configurations have been targeted so far. Dynamic queue
management is a prerequisite for this. Beyond that, achieving
multi-accelerator support also requires accounting for PCIe topology effects
on P2P transfer latency and bandwidth, and managing concurrent access to
shared namespaces from multiple devices within the HOMI control plane.

## Remote Storage and RDMA

The current work is scoped to locally-attached NVMe storage. Extending AiSIO
to remote storage is an open direction, with two distinct approaches under
consideration. The first is NVMe-oF, carrying NVMe commands over
RDMA-capable transports such as RoCE or InfiniBand, which preserves the
block-level access model of the locally-attached case. The second is pNFS,
which exposes distributed storage while preserving file system semantics at
the protocol level. In both cases, the goal is to maintain the core
properties of the AiSIO architecture — P2P data movement directly into
accelerator memory and device-initiated I/O — while operating against remote
targets.

## Evaluating Device-Initiated Paths

Initial benchmarking of device-initiated I/O is in place: xnvmeperf's
``cuda-run`` subcommand drives NVMe I/O entirely from CUDA kernels, and I/O
size scaling and queue depth scaling experiments are complete. The next step
is integrating device-initiated I/O into FIL to evaluate performance with
file-based workloads, where block translation through XAL and the full AiSIO
stack are exercised end-to-end.
