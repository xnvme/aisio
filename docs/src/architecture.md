(sec-architecture)=

# Architecture

Accelerator-integrated Storage I/O (AiSIO) architectures are characterized
by the coexistence of multiple I/O paths within a single system, spanning
conventional OS-managed storage stacks, host-resident user-space frameworks,
and device-initiated execution on accelerators. These architectures are designed
to enable high-performance data access without sacrificing compatibility with
existing filesystems, applications, and operating-system storage abstractions.
Rather than replacing established OS storage mechanisms, AiSIO focuses on
controlled sharing of storage resources and coordinated operation across
heterogeneous initiators.

While the architectural principles discussed in this section are not inherently
tied to a specific operating system, practical realization of AiSIO systems
imposes several non-negotiable requirements on the underlying OS. First,
the operating system must be supported by accelerator and device vendors,
including the availability of production-quality GPU and accelerator drivers
that enable peer-to-peer DMA and low-level device interaction. Second, the
OS must expose a sufficiently transparent and extensible NVMe storage stack,
allowing system software to reason about controller ownership, queue management,
and PCIe function boundaries. Finally, the OS must permit the construction
of software-mediated solutions that combine kernel and user-space components,
enabling rapid iteration and experimentation with alternative I/O paths. Among
contemporary operating systems, Linux uniquely satisfies these requirements at
scale, and therefore serves as the reference platform for the architectures and
implementations described in this work.

Modern systems require such coexistence not because workloads favor different
initiators, but because interoperability with operating system managed storage
is a hard requirement. Applications, filesystems, and OS infrastructure depend
on host-initiated I/O paths that provide safety, consistency, and universal
abstractions. These paths cannot simply be replaced. At the same time, emerging
workloads motivate specialized fast paths that reduce host involvement and
enable direct device-to-device data movement.

Many AiSIO designs therefore adopt a structural separation between
control-oriented responsibilities and high-bandwidth data-path execution.
Metadata management, protection enforcement, and system coordination remain
associated with the operating system, while accelerators participate in
data-path execution using mechanisms suited to parallel data movement. This
separation allows each processing unit to operate in its area of strength, while
preserving the safety and correctness guarantees expected from operating system
managed storage.

This architecture is particularly relevant for AI workloads where GPUs process
massive datasets stored in filesystems, but the underlying requirements extend
well beyond AI. Any scenario that demands coexistence between OS-managed storage
and high-performance direct access benefits from multipath I/O. Scientific
computing, database acceleration, video processing, and network-attached storage
exhibit similar pressures on the storage stack.

To reason about how such system software architectures support this form of
coexistence in practice, we distinguish between three classes of I/O paths
commonly encountered in AiSIO systems.

**OS-managed** I/O paths provide the interoperability baseline. They preserve
the conventional kernel storage stack, including filesystems, VFS layers,
permission enforcement, and existing applications. All file operations proceed
through standard interfaces, ensuring correct metadata handling, consistency,
and durability. This path maintains the safety and semantic guarantees required
by the operating system and its applications.

**User-space managed** I/O paths remain host-resident but shift both control and
data plane responsibilities from kernel space to user space. Frameworks such as
SPDK initialize and manage NVMe devices directly on the host, including driver
bring-up, admin-queue configuration, and I/O queue management. By bypassing
the kernel storage stack, this path eliminates interrupts, context switches,
and redundant data copies, enabling low-latency and high-throughput I/O. As a
result, abstractions normally provided by the operating system, such as block
devices, scheduling, isolation, and safety guarantees, must be explicitly
rebuilt on top of the user-space runtime.

**Device-initiated** I/O paths extend user-space managed I/O by allowing devices
to initiate storage operations directly. Accelerators such as GPUs issue NVMe
commands and move data using peer-to-peer DMA, while host-side system software
components remain responsible for device bring-up, queue management, and system
coordination. This path reduces host involvement on the fast path, but shifts
substantial responsibility for correctness, safety, and integration with file
systems and applications out of the kernel and into specialized runtimes.

Taken in isolation, each I/O path addresses a distinct set of requirements.
OS-managed paths preserve interoperability, safety, and file system semantics.
User-space managed paths deliver predictable, high-performance access on the
host. Device-initiated paths reduce host resource consumption by allowing
accelerators to initiate and drive I/O directly.

AiSIO further distinguishes between hardware-partitioned coexistence and
software-mediated coexistence. This distinction follows directly from the design
of the Linux NVMe driver {cite}`linux-nvme`, which assumes exclusive ownership
of a PCIe function, including administrative control, error handling, and
queue management. While this assumption could in principle be altered, it is
intentionally not. Prior efforts to relax function-level ownership have taken
the form of out-of-tree extensions rather than upstream changes.

Examples include NVMeDirect {cite}`nvmedirect` and vendor-specific kernel
modifications in GPU driver stacks used to support GPUDirect Storage
{cite}`nvidia-gds`, which accelerate data movement while explicitly preserving
kernel ownership of the NVMe controller. Other systems, such as libnvm
{cite}`Markussen2021` and Big Accelerator Memory (BaM) {cite}`bam2023`, take
the opposite approach by removing the NVMe device from kernel control entirely
and assigning exclusive ownership to a user-space runtime or accelerator. None
of these efforts introduce a model for fine-grained sharing of NVMe controllers
between independent initiators.

As a result, safe coexistence between OS-managed and accelerator-initiated
access within a single NVMe controller requires either hardware support for
partitioning at the PCIe function level, such as multiple physical functions or
SR-IOV, or a host-resident control plane that mediates access through user-space
NVMe drivers.

The overarching goal is to evaluate the feasibility of AiSIO system
implementations that allow these I/O paths to coexist within a single system
without compromising operating system semantics.

## Host Orchestrated Multipath I/O (HOMI)

Host Orchestrated Multipath I/O (HOMI) is a reference implementation used
to explore accelerator-integrated Storage I/O within the framework of system
software architectures described in the previous section. HOMI does not define
a single prescriptive design, but instead serves as an experimental platform for
studying how OS-managed, user-space managed, and device-initiated I/O paths can
be orchestrated to coexist within a single system.

The term *host orchestrated* reflects a deliberate architectural choice. In
HOMI, the host operating system retains responsibility for global coordination,
metadata management, and policy enforcement, while enabling accelerators to
participate directly in data-path execution. This mirrors the control- and
data-path separation described for AiSIO systems and allows new I/O paths to be
introduced without undermining operating system semantics.

HOMI supports multiple orchestration strategies that reflect different points
in the AiSIO design space. It can realize host-orchestrated multipath I/O
either through hardware-supported virtualization using SR-IOV, or through
software-mediated multiplexing via a user-space block interface using *ublk*
{cite}`ublk`. These strategies impose different constraints on isolation, queue
ownership, and resource sharing, and enable the exploration of architectural
trade-offs between hardware-assisted and software-mediated multipath designs.

A second foundational component of HOMI is a host-resident daemon that
centralizes control-plane responsibilities shared across all I/O paths. This
daemon is responsible for device discovery and initialization, NVMe control
operations, and the extraction and caching of file-extent information from the
host file system. By maintaining a coherent view of storage devices and file
layout, it provides a common coordination point between OS-managed, user-space
managed, and device-initiated I/O paths.

The daemon exposes interfaces through which user-space processes and devices
can obtain access to NVMe resources, including handles required to establish I/O
queue pairs for direct command submission.

This design allows queue ownership and scheduling decisions to be orchestrated
at the host level, enabling accelerators and user-space components to initiate
I/O without assuming responsibility for device management or administrative
control.

As a result, accelerators and user-space components can initiate I/O while
remaining integrated with kernel-managed storage semantics.

HOMI is intentionally scoped as a reference implementation. It focuses on
exposing and coordinating multiple I/O paths rather than on providing a complete
storage solution or introducing new file system semantics. Design choices
favor explicitness and observability over generality, allowing the impact of
architectural decisions to be studied in isolation.

### Control-Plane Services and Responsibilities

At the core of HOMI is a host-resident daemon that centralizes control-plane
responsibilities shared across all I/O paths. This daemon provides
the coordination required to allow OS-managed, user-space managed, and
device-initiated I/O paths to coexist without transferring full device control
out of the operating system.

The control plane is responsible for storage device discovery and
initialization, NVMe controller management, and the mediation of access to
controller resources. All administrative operations, including controller
configuration and error recovery, remain host-managed, ensuring that storage
devices can be safely operated regardless of accelerator state.

In addition to device management, the control plane maintains a cached view of
file-to-block mappings for files accessed through non-OS-managed I/O paths, that
is, via user-space or device-resident NVMe I/O drivers.

Accelerators cannot interact directly with kernel metadata structures or perform
pathname resolution. HOMI therefore extracts file extent information on the host
and makes it available through controlled interfaces, allowing accelerators to
translate file offsets into physical block ranges without kernel involvement on
the data path.

By centralizing these responsibilities, HOMI enables accelerators and user-space
runtimes to initiate I/O directly while preserving kernel-managed storage
semantics, filesystem consistency, and system-wide coordination.

### HOMI via Software-Mediated Multipath (ublk)

In its software-mediated configuration, HOMI realizes multipath I/O using a
user-space block interface based on *ublk*. In this mode, the NVMe controller is
initialized and managed by a user-space NVMe driver under host control, rather
than by the operating system kernel. This places both the control plane and the
data plane for the storage device in user space, while preserving a conventional
block-device interface toward the kernel.

The user-space NVMe driver performs full controller bring-up and administrative
operations, and provisions I/O queue pairs for multiple consumers. One set
of queues is dedicated to servicing I/O requests originating from the kernel
through the *ublk* interface, enabling OS-managed filesystems and applications
to operate without modification. These queues reside in host memory and are used
for CPU-initiated I/O.

In addition to kernel-facing paths, the same user-space driver provisions I/O
queues for other user-space processes that require direct access to the NVMe
device. This allows high-performance user-space storage frameworks to coexist
with OS-managed I/O paths, ensuring that no single process monopolizes device
ownership and that multiple user-space consumers can be supported concurrently.

In parallel, the user-space driver provisions additional I/O queue pairs that
reside in accelerator-accessible memory and are reserved for device-initiated
I/O. These queues are used exclusively by accelerators to submit NVMe
commands directly, allowing data-path execution to bypass host memory and CPU
involvement.

Queue ownership is static for the lifetime of the system configuration. Kernel
I/O paths, user-space processes, and accelerator-initiated I/O paths do not
share queues, and none can access the queue resources of another. Concurrency
is provided by the NVMe controller’s native support for multiple queue pairs,
eliminating the need for software arbitration on the data path.

This configuration requires no specialized hardware support and allows
AiSIO systems to operate on commodity platforms. The trade-off is that queue
provisioning, isolation, and coordination across kernel, user-space, and device
initiators are implemented entirely in software, placing greater responsibility
on the host-resident user-space control plane.

### HOMI via Hardware-Assisted Delegation (SR-IOV)

When supported by the NVMe device and platform, HOMI can realize
host-orchestrated multipath I/O with hardware assistance via Single Root I/O
Virtualization (SR-IOV). In this configuration, the NVMe controller exposes
multiple PCIe functions that share the same namespaces while providing
independent I/O queue resources.

As in the software-mediated configuration, HOMI retains responsibility for
global orchestration, system coordination, and file-system integration. The
host remains the sole authority for device discovery, lifecycle management,
and policy enforcement. However, SR-IOV shifts responsibility for I/O queue
isolation and arbitration from software into the NVMe controller hardware.

In the SR-IOV configuration, the Physical Function (PF) is host-managed and
retains administrative control over the device. Virtual Functions (VFs) are
created and assigned to different initiators, including accelerators and, when
required, user-space processes. Each VF provides an independent operational
interface with its own set of I/O queues, BAR mappings, and interrupt resources,
while all functions continue to access the same underlying namespaces.

```{figure} _static/aisio_overview_homi_userspace_mgmt.drawio.png
:alt: HOMI via Hardware-Assisted Delegation (SR-IOV)
:width: 700px
:align: center

Overall system architecture showing data flow between components.
```

This hardware-level partitioning allows kernel-managed I/O paths, user-space
processes, and device-initiated I/O paths to coexist without sharing queue
resources or requiring host-mediated queue arbitration on the data path. From
the perspective of each initiator, the assigned VF behaves as a dedicated NVMe
endpoint, simplifying driver logic and reducing cross-path interference.

Despite this delegation, HOMI remains essential to the architecture. The
host control plane continues to manage administrative operations, coordinate
file-system metadata, maintain the file-extent cache, and handle error detection
and recovery. SR-IOV therefore complements HOMI by reducing software overhead on
the data path, rather than replacing host orchestration.

Compared to software-mediated multipath, SR-IOV improves isolation and reduces
runtime coordination costs, but introduces hardware dependencies and limits
flexibility in queue allocation. As a result, it represents an alternative
realization of the same architectural principles, rather than a fundamentally
different design.
