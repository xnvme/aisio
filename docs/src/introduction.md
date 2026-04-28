(sec-introduction)=

# Introduction

AI workloads have driven unprecedented demand for storage bandwidth. Training,
inference, and data-intensive models require accelerators to process massive
datasets, yet storage access remains constrained by three independent
bottlenecks: software abstraction overhead in the I/O stack, unnecessary data
copies through host memory, and the lack of mechanisms for accelerators to
participate directly in storage I/O. These are distinct problems with distinct
solutions, and existing systems address them in isolation, often through
proprietary or OS-incompatible means.

## Software Abstraction Overhead

The kernel storage stack interposes multiple software layers between an
application and the NVMe controller: system call entry, VFS dispatch,
file system logic, block-layer scheduling, and driver processing. Each layer
adds latency and CPU overhead. Successive generations of I/O interfaces have
worked to reduce this cost. Early interfaces such as pread/pwrite and POSIX aio
gave way to Linux-specific libaio, which reduced system call overhead through
kernel managed asynchronous I/O. io_uring advanced this further with shared
submission and completion rings between user space and the kernel, enabling
batched, polled I/O with minimal system call transitions. Most recently,
io_uring_cmd extends this model to pass NVMe commands through the kernel driver
with reduced block-layer overhead. Each generation reduced the software overhead,
but all remain within the kernel storage stack.

SPDK {cite}`yang2017spdk` demonstrated that moving the NVMe driver entirely to
user space, bypassing the kernel, eliminating interrupts and context switches,
and using polling-based completion, could achieve dramatically higher I/O
performance than any kernel path available at the time. It took roughly five
years before the Linux kernel introduced io_uring, which narrowed the
performance gap substantially. SPDK remains faster, though no longer by an order
of magnitude. The architectural trade-off persists: SPDK requires exclusive
device ownership, removing the NVMe controller from kernel management and
requiring OS-provided abstractions to be rebuilt in user space or foregone
entirely.

## Unnecessary Data Copies

Independent of software overhead, accelerator workloads suffer from redundant
data movement. When a GPU requires data from storage, the conventional path
routes it through host DRAM: the NVMe controller writes to host memory, and a
separate copy transfers the data to GPU memory. Peer-to-peer (P2P) DMA (see {ref}`sec-pcie`)
eliminates this intermediate copy by allowing the NVMe controller to transfer
data directly to GPU memory over the PCIe fabric.

NVIDIA GPUDirect Storage (GDS) {cite}`nvidia-gds` was the first widely deployed
system to achieve this, integrating P2P into the kernel I/O path through
vendor-specific kernel modifications. GDS enables CPU-initiated NVMe commands
with data buffers residing in GPU memory, bypassing host DRAM on the data path.
However, GDS is proprietary and tightly coupled to the NVIDIA driver stack.
Open alternatives using io_uring with dma-buf for P2P buffer management are
under development within the Linux kernel.

## Device-Initiated I/O

A third, independent direction is device-initiated I/O, where the accelerator
itself constructs and submits NVMe commands. This removes the host CPU from the
command path entirely, allowing the accelerator to drive I/O at its own pace
without waiting for CPU-mediated scheduling. Early academic work on this includes
libnvm {cite}`Markussen2021`, which demonstrated GPU-resident NVMe driver code
capable of submitting commands directly from GPU threads. BaM
{cite}`bam2023` extended this with NVMe queue partitioning and a demand-paging
model for fine-grained GPU-driven storage access.

On the proprietary side, NVIDIA's SCADA (SCalable Accelerated Data Access),
part of the StorageNext initiative, pursues device-initiated storage access
through a client-server architecture with a user space NVMe driver and a
proprietary GPU-oriented I/O protocol. SCADA interposes a user-configurable
software cache in GPU HBM between the application and storage; its performance
gains derive primarily from cache hits rather than from more efficient I/O
submission {cite}`nvidia-scada-fms2025`.

These systems achieve high performance but do so by abandoning file systems,
POSIX semantics, or interoperability with OS-managed storage, or by relying on
proprietary infrastructure.

## AiSIO

The presented approaches share a common limitation: each targets one bottleneck
without addressing the others, and each does so at a cost to OS interoperability
or file system semantics. An open system that combines all three approaches while
preserving OS-managed storage semantics does not yet exist.

Accelerator-integrated Storage I/O (AiSIO) designates a class of system
software architectures that address all three bottlenecks through open,
composable components while preserving interoperability with OS-managed storage.
AiSIO systems reduce software overhead through user space NVMe drivers,
eliminate unnecessary copies through P2P DMA with dma-buf, and enable
device-initiated I/O through device-resident NVMe drivers. The CPU and
operating system retain responsibility for global coordination, device
management, metadata handling, and policy enforcement. Accelerators participate
in data-path execution or initiate I/O under host coordination, using open
interfaces rather than proprietary driver stacks.

Host Orchestrated Multipath I/O (HOMI) serves as a reference architecture and
implementation within the AiSIO class. HOMI demonstrates how these principles
can be realized in open and modifiable system software, enabling multiple I/O
paths to coexist with shared access to storage resources while preserving
operating-system semantics.

This paper introduces AiSIO as a conceptual framework, defines a taxonomy of
I/O paths within that framework, presents the HOMI architecture, and describes a
proof-of-concept implementation evaluated through a series of synthetic
benchmarks.
