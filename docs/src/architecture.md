(sec-architecture)=

# Architecture

AiSIO designates a class of system architectures that integrate accelerators
into the storage I/O path as first-class participants. AiSIO systems support
cooperative multipath I/O, in which conventional OS-managed storage paths
coexist with accelerator-accessible data paths. These architectures may unify
the operating system storage stack with accelerator-resident NVMe drivers
{cite}nvme-base-2.3, enabling accelerators to participate in data movement
or initiate I/O at high throughput, while preserving compatibility and
interoperability with Linux and the universal abstractions of files and their
implementations in existing file systems.

While AiSIO does not mandate a specific orchestration model, many realizations
share a common structural separation between control-oriented responsibilities
and high-bandwidth data-path execution. Metadata operations, protection
enforcement, and system coordination remain associated with the operating
system, while accelerators execute data-path operations using mechanisms such
as peer-to-peer DMA and MMIO. This separation allows each processing unit to
operate in its area of strength, with CPUs handling coordination and scheduling
and accelerators handling parallel data movement, while maintaining the safety
and correctness guarantees expected from operating system managed storage.

## Host Orchestrated Multipath I/O (HOMI)

HOMI is a reference architecture and implementation within the AiSIO class. It
realizes accelerator-integrated storage I/O using a host-orchestrated control
plane that enables accelerators to issue high-performance storage I/O while
preserving compatibility with kernel-managed file systems and Linux safety
guarantees.

In HOMI, responsibilities that must be centralized, coordinated, and
safely exposed before accelerator-initiated I/O can operate in a production
environment are brought together in a host-resident user-space daemon. This
daemon interfaces with the operating system storage stack, manages device
configuration, and enables accelerator-resident I/O paths without requiring
modification to existing file systems.

The HOMI daemon represents functionality that could alternatively be implemented
in dedicated hardware, such as a DPU or storage controller firmware. By
implementing this functionality in host software, HOMI avoids additional
hardware requirements while providing a concrete, open, and modifiable
realization of the AiSIO architecture.

## The Case for Multipath I/O

Modern systems require multiple concurrent I/O paths not because different
workloads favor different initiators, but because preserving interoperability
with operating system managed storage requires it. Applications, filesystems,
and OS infrastructure depend on host-initiated I/O paths that provide
safety, consistency, and universal abstractions. These paths cannot simply be
replaced—they must coexist with specialized fast paths optimized for direct
device-to-device data movement.

The need for this coexistence is already evident in the split between OS-managed
storage and SPDK-based applications. SPDK applications bypass the kernel to
achieve maximum performance, but in doing so they sacrifice interoperability
with filesystems, standard tooling, and other applications using conventional
paths. This creates an artificial boundary: storage is either managed by the
OS with full abstractions and safety guarantees, or it is managed by user-space
drivers with maximum performance but limited interoperability.

AiSIO bridges this divide by enabling multiple I/O paths to coexist:

**OS-managed paths** provide the foundation for interoperability. Filesystems,
VFS abstractions, permission models, and existing applications continue to
function as expected. Files can be created, read, written, and deleted through
standard interfaces. This path handles metadata operations, ensures consistency,
and provides the safety guarantees that applications depend on.

**Accelerator-initiated fast paths** treat devices as first-class I/O
initiators. Once the OS establishes file layout and permissions, accelerators
can retrieve data directly through peer-to-peer transfers without CPU or
main memory involvement. This eliminates the copy overhead and scheduling
latency inherent in host-mediated I/O while preserving the filesystem
abstraction—accelerators read and write files, not raw block ranges.

This architecture is particularly relevant for AI workloads where GPUs process
massive datasets stored in filesystems, but the need extends well beyond AI. Any
scenario requiring both OS-managed storage and high-performance direct access
benefits from multipath I/O: scientific computing, database acceleration, video
processing, and network-attached storage all exhibit similar requirements.

What makes AiSIO distinct is that it does not force a choice between OS
management and performance. Both paths operate concurrently on the same
filesystem. The OS path handles coordination and metadata. Fast paths handle
bulk data movement. Applications can use both: standard file operations
to establish working sets, then accelerator-initiated I/O to process data
efficiently. This preserves the universal abstractions that make operating
systems reliable while enabling the performance characteristics that modern
hardware can deliver.

### Software Components and Integration

HOMI integrates multiple components into a cohesive control plane:

**ublk**
: A Linux kernel mechanism that exposes block devices implemented in user
space. HOMI uses ublk to bridge kernel I/O requests to user-space handlers. When
applications or the kernel VFS layer issue I/O to the ublk block device, these
requests are delivered to HOMI's user-space process, which forwards them to the
cooperative NVMe driver. This enables the conventional OS path to coexist with
accelerator-initiated paths while presenting a standard block device interface
to the kernel.

**SPDK**
: The Storage Performance Development Kit provides a user-space NVMe driver
that bypasses the kernel I/O stack for reduced latency. HOMI configures SPDK
as a cooperative driver: unlike traditional SPDK deployments that consume all
available NVMe queue pairs, HOMI-managed SPDK reserves a subset of queues for
CPU-initiated I/O and leaves the remainder available for GPU assignment. This
partitioning is static and configured during system initialization based on
expected workload characteristics.

**xNVMe**
: Provides a unified cross-platform NVMe API layer that abstracts differences
between operating systems, backends, and execution contexts. HOMI uses xNVMe to
manage NVMe controller initialization, admin queue operations, and to provide
consistent interfaces whether commands originate from host code or GPU kernels.
xNVMe extensions support GPU memory addressing and direct queue access patterns
required for accelerator-initiated I/O.

**XAL (eXtent Access Library)**
: Integrated within HOMI, XAL decodes filesystem metadata to provide
file-to-block mappings without kernel involvement. XAL reads XFS on-disk
structures directly—including superblocks, allocation groups, inodes, and
extent trees—and constructs an in-memory index that GPU kernels can query
efficiently. When the filesystem is mounted and supports it, XAL uses FIEMAP
ioctls to retrieve extent information. For unmounted filesystems or when FIEMAP
is unavailable, XAL parses raw on-disk format structures to extract extent
mappings.

### Interaction with OS Kernel and Devices

HOMI orchestrates three concurrent I/O paths:

**Conventional kernel path**

Applications using standard POSIX file I/O interact with the kernel VFS and
filesystem layers. These requests eventually reach the ublk block device, which
delivers them to HOMI's user-space process. HOMI forwards them to SPDK, which
executes the I/O using its reserved NVMe queue pairs. Completions propagate
back through the same path. This path maintains full compatibility with existing
applications and kernel infrastructure.

**CPU-initiated fast path**
: Applications using user-space I/O libraries (io_uring, SPDK APIs) bypass
the kernel and submit I/O directly to HOMI-managed SPDK queues. This reduces
software overhead while still using CPU-initiated I/O and host memory buffers.

**Accelerator-initiated fast path**
: GPU kernels query HOMI's extent cache to translate file offsets into
physical block addresses, construct NVMe commands in GPU memory, submit them
to GPU-resident queue pairs, and process completions via polling. The NVMe
controller performs peer-to-peer DMA directly between SSD and GPU memory. The
CPU is not involved in data movement.

All three paths operate concurrently on the same filesystem. HOMI ensures
coherency by maintaining up-to-date extent information and coordinating queue
access. The kernel path provides safety and compatibility. The accelerator path
provides maximum performance for data-intensive operations.

### File Extent Caching for Data-Path Lookup

Accelerator-initiated I/O requires fast access to file-to-block mappings. A GPU
cannot perform pathname resolution or interact with kernel metadata structures.
It needs direct physical layout descriptions, provided at low latency and
without involving the kernel on every I/O.

**Cache maintenance**
: HOMI maintains a host-side index of inodes and extents for all files accessed
by accelerator workloads. This allows the data path to retrieve block ranges
instantly, without syscall overhead or kernel traversal. The cache resides in
host memory and is accessible to GPU kernels through mapped memory regions or
explicit query interfaces.

**Extent retrieval**
: HOMI delegates metadata operations to XAL, which provides extent information
through two mechanisms: FIEMAP ioctls when the filesystem is mounted, or
direct on-disk format parsing when needed. This dual approach ensures extent
information is always available regardless of filesystem mount state.

**Cache invalidation**
: HOMI subscribes to kernel filesystem events (via fanotify, inotify, or
similar mechanisms) that signal when file metadata has changed—truncation, write
allocation, hole punching, or defragmentation. These events trigger invalidation
or update of cached extents, ensuring the accelerator view of the file always
matches the kernel's state. For files modified through accelerator-initiated
writes, HOMI coordinates with the kernel to maintain consistency.

**Query interface**
: Accelerator kernels call into HOMI's extent cache through a lightweight
interface that returns physical block ranges for requested file offsets.
This lookup occurs entirely in host memory and completes in microseconds. The
interface supports batch queries to amortize lookup overhead for large I/O
operations.

### NVMe Controller Initialization and Admin Queue Setup

Before accelerators can submit I/O directly, the storage subsystem must
be brought into a state where both the host and GPU can share or partition
controller resources.

**Controller initialization**
: HOMI attaches to the NVMe controller through xNVMe and programs the controller
state needed for shared operation. This includes:

- Controller reset to known state
- Capability and feature discovery
- Namespace enumeration and configuration
- Queue depth and memory page size negotiation

**Admin queue setup**
: HOMI allocates and configures the admin queue in host memory. This keeps
all controller management operations under host control throughout operation,
ensuring that:

- Firmware-level interactions remain safe and coordinated
- Namespace management is not exposed to accelerators
- Controller resets or errors can be handled centrally
- Admin commands can be issued regardless of accelerator state

The admin queue remains CPU-managed in all AiSIO configurations. This provides
a stable control plane that survives accelerator errors, allows safe controller
reconfiguration, and maintains a clear separation between control operations
(host-managed) and data operations (accelerator-initiated).

### Accelerator I/O Driver Setup and Queue Management

To enable accelerator-initiated storage I/O, accelerators must host a sufficient
NVMe driver subset to construct and submit commands and process completions—an
I/O driver. The admin/control-plane is delegated to HOMI on the host. What
makes it accelerator-initiated is that the accelerator performs MMIO: it is
the accelerator whose runtime provides the means to perform operations with
the address space mapped for the NVMe device doorbells, and to store commands
and completions in accelerator-resident memory, along with payload and
payload-associated structures such as PRP and SG lists.

HOMI is responsible for bringing this environment into existence:

**Queue allocation in accelerator memory** — HOMI uses admin queue commands to
create I/O queue pairs (submission queues and completion queues) that reside in
accelerator memory. For each queue pair, HOMI:

- Allocates memory buffers in GPU-accessible address space
- Issues Create I/O Submission Queue and Create I/O Completion Queue admin commands
- Configures queue size, priority, and interrupt settings
- Establishes DMA mappings that allow the NVMe controller to access GPU memory

**Doorbell register mapping** — HOMI configures BAR mappings that allow the accelerator to perform MMIO writes to NVMe doorbell registers. These mappings enable the GPU to notify the controller of new submissions and completion queue head pointer updates without CPU involvement.

**Driver code loading and configuration** — HOMI loads the GPU-resident NVMe I/O driver code into GPU memory and configures its parameters:
- Queue locations and sizes
- Doorbell register addresses
- Extent cache access methods
- Safety limits (allowed namespace ranges, maximum transfer sizes)

**P2P DMA enablement** — HOMI coordinates with the kernel and PCIe subsystem to enable peer-to-peer DMA between the NVMe device and GPU. This involves:
- Verifying PCIe topology supports peer transfers
- Configuring IOMMU mappings if required
- Setting up address translation services (ATS) if available
- Testing connectivity before allowing accelerator I/O

**Queue partitioning** — HOMI implements static queue partitioning to enable concurrent CPU and GPU access. During initialization, HOMI allocates a fixed number of queue pairs to SPDK (for CPU-initiated I/O through the conventional and CPU fast paths) and makes the remainder available for GPU allocation. CPU-owned queues reside in host memory and are managed by SPDK. GPU-owned queues reside in GPU memory and are managed by the GPU-resident driver. Neither side accesses the other's queues.

This partitioning is configured based on expected workload characteristics and hardware capabilities. Once established, it remains static during operation. The NVMe controller handles concurrent access from multiple queue pairs internally, requiring no software arbitration on the data path.

### Fast-Path Operation Flow

Once HOMI completes initialization, the accelerator can perform I/O independently:

1. **Extent lookup** — GPU kernel queries HOMI's extent cache (via mapped host memory or query API) to translate file offset into physical block address and length
2. **Command construction** — GPU constructs NVMe command in GPU memory, including:
   - Opcode (Read, Write, etc.)
   - Namespace ID
   - Starting LBA and block count
   - Data pointer (PRP or SGL) referencing GPU memory buffers
   - Command identifier for completion matching
3. **Command submission** — GPU writes command to submission queue in GPU memory, updates tail pointer, and rings doorbell via MMIO write
4. **DMA transfer** — NVMe controller fetches command from GPU memory, performs peer-to-peer DMA directly between SSD and GPU memory buffers
5. **Completion processing** — GPU polls completion queue in GPU memory, identifies completed command by ID, processes status, and advances head pointer

The CPU is not involved in any of these data-path steps. All coordination occurs during initialization via HOMI; all data movement occurs through direct device-to-device transfers.

For read operations, data flows: SSD → GPU memory. For write operations: GPU memory → SSD. No host memory copies occur.

### Runtime Coordination and Error Handling

HOMI continues to provide control-plane services during operation:

**Dynamic extent updates** — When files are modified through conventional OS paths, HOMI receives filesystem event notifications and updates its extent cache accordingly, ensuring accelerator views remain consistent with kernel state. Cache updates occur asynchronously and do not block I/O operations using already-cached extents.

**Error detection and recovery** — HOMI monitors for controller errors, queue failures, and other exceptional conditions through:
- Periodic admin queue health checks
- Event notifications from the kernel
- Error reports from SPDK or GPU drivers
- PCIe AER (Advanced Error Reporting) events

When errors occur, HOMI coordinates recovery:
- Disables affected accelerator paths temporarily
- Maintains CPU path availability for continued operation
- Attempts controller reset and reinitialization if needed
- Re-establishes accelerator queues after successful recovery

**Path selection hints** — HOMI can provide recommendations to applications about which I/O path (CPU or GPU initiated) is likely to perform better for specific access patterns. These hints consider:
- Transfer size and alignment
- Sequential vs random access patterns
- Current queue depths and utilization
- Available bandwidth on each path

Applications remain free to override HOMI's recommendations. Path selection is advisory, not enforced.

**Resource monitoring** — HOMI tracks queue utilization, outstanding I/O counts, and bandwidth consumption across all paths. This information supports path selection decisions and can trigger load balancing or throttling when resources become constrained.

## Hardware-Assisted Delegation via SR-IOV

While HOMI-based architecture provides excellent performance on commodity hardware, systems equipped with NVMe devices supporting Single Root I/O Virtualization (SR-IOV) can delegate certain responsibilities to hardware, further reducing software overhead and improving isolation between I/O paths.

### SR-IOV Fundamentals for AiSIO

SR-IOV allows an NVMe device to expose multiple PCIe functions that share underlying hardware resources. The Physical Function (PF) provides full administrative control, while Virtual Functions (VFs) provide restricted operational interfaces. Each VF appears as an independent PCIe endpoint with its own configuration space, BARs, MSI-X vectors, and I/O queue sets.

Critically for AiSIO, **all functions access the same namespaces**. This shared namespace access distinguishes AiSIO's use of SR-IOV from virtualization scenarios where VFs partition storage between isolated tenants. AiSIO uses SR-IOV to create independent driver endpoints that allow the OS and GPU to operate concurrently without queue contention, not to provide security boundaries.

### What SR-IOV Changes in the Architecture

SR-IOV does not replace HOMI—it shifts specific responsibilities from software to hardware:

**What remains HOMI's responsibility:**
- Admin queue management for PF and all VFs
- Extent cache maintenance and invalidation
- Filesystem event monitoring
- Error detection and recovery coordination
- Driver initialization and configuration
- P2P DMA enablement verification

**What hardware now handles:**
- I/O queue arbitration between functions
- Queue set isolation (each VF has dedicated queues)
- Concurrent access coordination
- Resource partitioning enforcement

HOMI's role shifts from managing software-based queue partitioning to coordinating VF lifecycle, but HOMI remains essential to the architecture.

### SR-IOV Initialization Sequence

1. **HOMI configures PF** — HOMI's initialization code brings up the Physical Function using the same xNVMe-based controller initialization as in the base architecture
2. **Enable SR-IOV** — HOMI enables SR-IOV through PCIe configuration space and sets the number of active VFs based on available resources and workload requirements
3. **Initialize Admin Queues** — HOMI creates and manages admin queues for PF and all VFs in host memory, maintaining central control over administrative operations
4. **Assign VF to GPU** — HOMI coordinates VF assignment to the GPU driver stack through PCIe device binding mechanisms
5. **GPU maps VF resources** — GPU driver maps the VF's BARs, including controller registers and doorbell pages
6. **Create I/O queues via Admin Queue** — HOMI issues admin commands to create I/O queue pairs in GPU memory for the assigned VF
7. **Populate extent cache** — HOMI builds the extent cache using XAL, making it available to GPU kernels through the same interfaces as the base architecture
8. **Begin operation** — GPU can now submit I/O commands independently via its VF

### Fast-Path Operation with VF Assignment

Once initialization completes, fast-path operation remains identical from the GPU's perspective:

- GPU queries HOMI's extent cache for file-to-block mappings
- GPU constructs NVMe commands in GPU memory
- GPU submits commands to its VF's queue pairs and rings VF doorbells
- NVMe controller performs P2P DMA between SSD and GPU memory
- GPU polls VF completion queues and processes status

The key difference is invisible to the GPU kernel: instead of sharing queue pairs with CPU-initiated I/O through software coordination, the GPU has dedicated queue pairs provided by its assigned VF. The NVMe controller's internal arbitration logic handles concurrent access from PF and VFs, eliminating software coordination overhead.

### Benefits of Hardware Delegation

**Reduced software overhead** — HOMI no longer manages queue partitioning or coordinates access between CPU and GPU paths. Hardware arbitration eliminates context switches and synchronization costs.

**Hardware-enforced isolation** — Each VF provides genuinely independent queue sets. Queue full conditions, error states, and reset operations on one function do not affect others.

**Cleaner driver implementation** — The GPU driver interacts with a VF that looks and behaves like a dedicated NVMe controller, simplifying driver code and reducing edge cases.

**Improved debugging** — Hardware isolation makes it easier to diagnose whether issues originate from CPU or GPU paths. VF-specific errors, performance counters, and logs provide better visibility.

### Limitations and Requirements

**Hardware dependency** — Requires NVMe devices with robust SR-IOV implementations. Not all devices that advertise SR-IOV support it reliably. PCIe fabrics must correctly route peer-to-peer transactions to VF BARs.

**Platform variability** — BIOS settings, chipset capabilities, and PCIe topology significantly affect functionality. Platforms may require specific configuration (IOMMU settings, ACS configuration, BAR size allocation) for SR-IOV to function correctly.

**Reduced flexibility** — VF count is fixed at SR-IOV enablement and cannot be changed dynamically. Queue counts per VF are similarly constrained by device capabilities.

**HOMI still required** — Even with SR-IOV, HOMI provides admin queue management, extent caching, error coordination, and initialization. SR-IOV reduces HOMI's runtime overhead but does not eliminate it.

**No QoS guarantees** — While VFs provide isolation, the NVMe specification does not mandate QoS enforcement between functions. Bandwidth and latency guarantees depend on device-specific implementations.

### When to Use SR-IOV

SR-IOV provides advantages when:
- Hardware support is available and verified
- Workloads require lowest possible latency
- Multiple accelerators share the same NVMe device
- Simplified debugging justifies hardware dependency

HOMI-based architecture without SR-IOV is preferable when:
- Commodity hardware must be supported
- Platform SR-IOV support is unreliable
- Dynamic queue allocation is desired
- Deployment simplicity is prioritized

Both approaches implement the same fundamental architecture: HOMI provides control-plane coordination, accelerators execute data-plane operations, and multipath I/O enables concurrent CPU and GPU access. SR-IOV simply shifts queue arbitration from software to hardware.

## Summary

AiSIO's architecture achieves accelerator-integrated storage I/O through HOMI, a host-resident daemon that orchestrates control-plane operations while enabling accelerators to execute data-plane operations directly. HOMI integrates ublk, SPDK, xNVMe, and XAL into a cohesive system that provides:

- A unified extent cache enabling efficient file-to-block translation
- Cooperative NVMe driver initialization with shared or partitioned resources
- Concurrent multipath I/O supporting conventional kernel paths and accelerator-initiated fast paths
- Runtime coordination for error handling and cache consistency

The architecture supports two operational modes: HOMI-based queue management on commodity hardware, and SR-IOV-assisted delegation when specialized hardware is available. Both modes preserve full compatibility with unmodified filesystems and standard Linux kernel infrastructure while closing the performance gap inherent in CPU-centric I/O stacks.

This combination of efficiency, flexibility, and interoperability distinguishes AiSIO from prior approaches that sacrificed either performance or compatibility.
