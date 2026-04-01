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

The udmabuf-import patch, which extends the udmabuf driver to import arbitrary
dma-buf file descriptors and expose physical address mappings to user space,
is currently maintained as an out-of-tree kernel patch. Upstreaming this
interface, or contributing an equivalent mechanism through a suitable kernel
subsystem, would remove the requirement for a custom kernel build and allow
the user space P2P path to be exercised on unmodified production systems.

The Linux kernel's io_uring and dma-buf integration for CPU-initiated P2P I/O
is under active development in mainline. As this path stabilizes, a direct
comparison between the kernel-managed and user space managed P2P architectures
described in Section {ref}`sec-architecture` becomes possible on identical
hardware — an evaluation that would clarify the performance and operational
trade-offs between the two approaches.

## Device-Resident NVMe Driver

The PoC includes a device-resident NVMe driver built on xNVMe, using libnvm
as the underlying PCIe access library. This driver is now being
re-implemented to replace libnvm with uPCIe and dma-buf, aligning it with
the open, composable architecture described in this work. Until this
re-implementation is complete and stable, reliable benchmarking of
device-initiated I/O paths is not possible, and the HIP port needed to
extend support to AMD GPUs, described in the following section, cannot begin.

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
HIP; this is the most substantial effort, and is further complicated by the
driver still being under active development.

## Multi-Accelerator Topologies

While multi-accelerator support is a goal of this work, only
single-accelerator configurations have been targeted so far. Several of the
preceding items — in particular dynamic queue management and the
device-resident NVMe driver re-implementation — are prerequisites for this.
Beyond those, achieving multi-accelerator support also requires accounting for
PCIe topology effects on P2P transfer latency and bandwidth, and managing
concurrent access to shared namespaces from multiple devices within the HOMI
control plane.

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

The benchmarks presented in this work characterize CPU-initiated I/O with host
memory buffers and compare user space NVMe driver implementations. Systematic
evaluation of device-initiated configurations — measuring the impact of
removing the CPU from the command path — remains as future work, pending the
completion of the device-resident NVMe driver re-implementation described
above.
