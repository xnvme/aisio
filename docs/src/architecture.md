<!--
SPDX-FileCopyrightText: Samsung Electronics Co., Ltd

SPDX-License-Identifier: BSD-3-Clause
-->

(sec-architecture)=

# Architecture

Accelerator-integrated Storage I/O (AiSIO) architectures are characterized
by the coexistence of multiple I/O paths within a single system, spanning
conventional OS-managed storage stacks, host-resident user space frameworks,
and device-initiated execution on accelerators. These architectures are designed
to enable high-performance data access without sacrificing compatibility with
existing file systems, applications, and operating-system storage abstractions.
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
of software-mediated solutions that combine kernel and user space components,
enabling rapid iteration and experimentation with alternative I/O paths. Among
contemporary operating systems, Linux uniquely satisfies these requirements at
scale, and therefore serves as the reference platform for the architectures and
implementations described in this work.

AiSIO designs adopt a structural separation between control-oriented
responsibilities and high-bandwidth data-path execution. Metadata management,
protection enforcement, and system coordination remain associated with the
operating system, while accelerators participate in data-path execution using
mechanisms suited to parallel data movement. This separation allows each
processing unit to operate in its area of strength, while preserving the safety
and correctness guarantees that applications and file systems depend on.

## I/O Path Taxonomy

To reason about how AiSIO system architectures support multipath coexistence, we
characterize I/O paths along three independent axes: infrastructure, initiator,
and buffer placement.

**Infrastructure** describes which software layer owns the NVMe driver and
manages the controller's queues.

- *Kernel managed*: the kernel NVMe driver performs controller initialization,
  queue allocation, command submission, and completion handling. The kernel
  retains full control over device management, file system integration, and
  protection enforcement.
- *User space managed*: a user space NVMe driver performs these responsibilities
  directly from user space. This eliminates kernel transitions, interrupt
  overhead, and block-layer processing, but requires OS-provided abstractions
  (block devices, scheduling, isolation) to be rebuilt in the user space runtime
  or foregone entirely.

**Initiator** describes which processing entity constructs and submits NVMe
commands.

- *CPU-initiated*: software executing on the host CPU constructs NVMe submission
  queue entries, populates data transfer descriptors (PRPs or SGLs), and writes
  doorbell registers. This applies to both kernel managed and user space managed
  infrastructure.
- *Device-initiated*: software executing on a PCIe-attached accelerator (such as
  a GPU) constructs and submits NVMe commands from device-resident driver code.
  Host-side software remains responsible for device initialization, queue
  provisioning, and metadata resolution, but the accelerator drives the data
  path independently once the queues are established.

**Buffer placement** describes where data buffers and queue structures reside,
and determines whether peer-to-peer (P2P) DMA (see {ref}`sec-pcie`) is involved.

- *Host memory*: data buffers reside in host DRAM. The NVMe controller performs
  DMA to and from host memory. When an accelerator needs the data, a separate
  copy from host memory to device memory is required.
- *Device memory*: data buffers reside in accelerator-accessible memory,
  typically GPU BAR space. The NVMe controller transfers data directly to or
  from the accelerator over the PCIe fabric via P2P DMA, bypassing host DRAM
  entirely. Queue structures may also reside in device memory when the
  accelerator must access them directly.

These axes are independent. The following table summarizes how existing and
AiSIO system architectures map onto the three axes:

| Components                             | Infrastructure | Initiator | Buffers |
| -------------------------------------- | -------------- | --------- | ------- |
| pread, libaio, io_uring                | Kernel         | CPU       | Host    |
| SPDK                                   | User space     | CPU       | Host    |
| xNVMe/uPCIe                            | User space     | CPU       | Host    |
| GDS                                    | Kernel         | CPU       | Device  |
| io_uring + dma-buf                     | Kernel         | CPU       | Device  |
| xNVMe/uPCIe + CUDA/dma-buf             | User space     | CPU       | Device  |
| xNVMe/uPCIe + ROCm/dma-buf             | User space     | CPU       | Device  |
| BaM, SCADA                             | User space     | Device    | Device  |
| xNVMe/uPCIe + CUDA (device-resident)   | User space     | Device    | Device  |

The conventional kernel paths occupy the top-left corner: kernel managed,
CPU-initiated, host memory. SPDK and xNVMe/uPCIe move the infrastructure to
user space while remaining CPU-initiated with host memory buffers; benchmarks
comparing these are presented in {ref}`sec-experiments-tool-comparison`. GDS
changes buffer placement to device memory while remaining kernel managed. The
remaining rows represent the AiSIO system architectures described in the
following sections, which combine device memory, user space or kernel
infrastructure, and (in the device-resident case) device-initiated I/O.

### The Coexistence Problem

The coexistence problem arises from the infrastructure axis. On Linux, a PCIe
function can be bound to only one driver at a time. When the kernel NVMe driver
owns a function, no user space driver can access it, and vice versa. This means
that kernel managed and user space managed I/O paths cannot operate on the same
NVMe controller simultaneously through the same PCIe function. Device-initiated
I/O inherits this constraint, since it relies on user space infrastructure to
provision queues and manage the controller.

As a consequence, running multiple infrastructure types against a single NVMe
controller requires either hardware support for partitioning at the PCIe
function level (such as SR-IOV, which exposes multiple independent functions
from a single physical device) or a software architecture that takes exclusive
ownership of the function in user space and re-exports a block device interface
back to the kernel (such as ublk). Without one of these mechanisms, the system
must choose a single infrastructure type per controller, forgoing multipath
coexistence.

## AiSIO System Architectures

The following subsections describe three P2P system architectures within the
AiSIO class, realized as open-source alternatives to the proprietary and
academic systems described in the introduction. All three use peer-to-peer
(P2P) DMA to transfer data directly between the NVMe controller and
accelerator memory over the PCIe fabric, bypassing host DRAM. They share a
common foundation in upstream and open-source components (io_uring, dma-buf,
xNVMe, and uPCIe) and differ in which entity initiates I/O and which software
layer manages the NVMe command path.

Notably, the same xNVMe and uPCIe components also support conventional
CPU-initiated I/O with host memory buffers. Benchmarks demonstrate that this
configuration outperforms the current state-of-the-art in user space I/O
(SPDK) (see {ref}`sec-experiments-tool-comparison`). This is a direct
consequence of xNVMe's design: by abstracting the NVMe command path behind a
unified API, xNVMe allows applications to switch between I/O paths
(kernel managed, user space managed, or device-initiated, with host or P2P
buffers) without modifying application code. Different paths enable different
optimizations, and the choice can be made at deployment time rather than at
development time.

### CPU-Initiated I/O with P2P Memory and Kernel Infrastructure

The host CPU constructs and submits NVMe commands through the kernel storage
stack using io_uring. Data buffers reside in GPU memory, exported as dma-buf
objects and imported into the kernel for use as I/O targets. The kernel NVMe
driver populates PRPs or SGLs with physical addresses in GPU BAR space, causing
the NVMe controller to issue PCIe Memory Read or Write TLPs directed at the GPU
rather than at host memory.

Queue pairs are allocated in host memory and managed entirely by the kernel NVMe
driver. The kernel retains full control over command lifecycle, device
management, and file system integration. The P2P data path is established
through composable, upstream kernel interfaces (dma-buf for GPU memory sharing
and io_uring for asynchronous NVMe command submission) without requiring
proprietary driver modifications.

### CPU-Initiated I/O with P2P Memory and User-Space Infrastructure

The host CPU constructs and submits NVMe commands through a user space NVMe
driver. xNVMe provides unified NVMe command construction and submission, while
uPCIe manages PCIe resource access from user space. Data buffers reside in GPU
memory, and dma-buf is used to establish P2P mappings that expose GPU BAR
addresses to the user space driver. The driver constructs NVMe commands with
PRPs or SGLs pointing to these GPU physical addresses, and the NVMe controller
transfers data directly to or from GPU memory via P2P DMA.

Queue pairs are allocated in host memory and managed by the user space driver.
By operating outside the kernel, this path eliminates kernel transitions,
interrupt overhead, and block-layer processing. The trade-off is that the kernel
no longer mediates access to the NVMe device: queue isolation, P2P memory
safety, and coexistence with OS-managed storage must be handled by the
user space runtime or by a host-resident control plane such as HOMI.

### Device-Initiated I/O with P2P Memory and User-Space Infrastructure

The accelerator itself constructs and submits NVMe commands from GPU-resident
driver code. As in the CPU-initiated user space configuration, xNVMe and uPCIe
handle device initialization, queue provisioning, and P2P setup on the host.
The key difference is in where the queue pairs reside and who drives the data
path.

Queue pair memory (submission queues, completion queues, and associated
structures) is allocated in GPU memory via dma-buf, making it directly
accessible to the device-resident NVMe I/O driver. The host provisions these
queues and registers them with the NVMe controller, but the GPU subsequently
operates on them independently: constructing submission queue entries,
populating PRPs or SGLs referencing GPU-local data buffers, and writing doorbell
registers to trigger command processing. Completions are polled directly by the
GPU from completion queue entries residing in its own memory.

Data buffers likewise reside in GPU memory with P2P mappings established through
dma-buf. The entire submission-transfer-completion cycle proceeds over the PCIe
fabric between the GPU and the NVMe controller. The host CPU is involved only in
control-plane operations: queue provisioning, file-to-block metadata resolution,
and error recovery.

## Host Orchestrated Multipath I/O (HOMI)

Host Orchestrated Multipath I/O (HOMI) is a reference implementation that
addresses the coexistence problem described above. Rather than forcing a choice
between I/O path classes, HOMI enables OS-managed, user space managed, and
device-initiated paths to operate concurrently on the same NVMe controller.

The term *host orchestrated* reflects a deliberate architectural choice. The
host retains responsibility for global coordination, metadata management, and
policy enforcement, while enabling accelerators to participate directly in
data-path execution. HOMI resolves the driver exclusivity constraint through three
strategies: software-mediated multiplexing via *ublk* {cite}`ublk`,
hardware-assisted delegation via SR-IOV, and delegation of device descriptors
to unrelated processes under `vfio-pci`. All three are described in the
subsections below.

A foundational component of HOMI is a host-resident daemon that centralizes
control-plane responsibilities shared across all I/O paths. This daemon is
responsible for device discovery and initialization, NVMe control operations,
and the extraction and caching of file-extent information from the host file
system. It exposes interfaces through which user space processes and
accelerators can obtain access to NVMe resources, including handles required to
establish I/O queue pairs for direct command submission.

Accelerators cannot interact directly with kernel metadata structures or perform
pathname resolution. HOMI therefore extracts file extent information on the host
and makes it available through controlled interfaces, allowing accelerators to
translate file offsets into physical block ranges without kernel involvement on
the data path.

HOMI is intentionally scoped as a reference implementation. It focuses on
exposing and coordinating multiple I/O paths rather than on providing a complete
storage solution or introducing new file system semantics. Design choices
favor explicitness and observability over generality, allowing the impact of
architectural decisions to be studied in isolation.

### HOMI via Software-Mediated Multipath (ublk)

In its software-mediated configuration, HOMI realizes multipath I/O using a
user space block interface based on *ublk*. In this mode, the NVMe controller is
initialized and managed by a user space NVMe driver under host control, rather
than by the operating system kernel. This places both the control plane and the
data plane for the storage device in user space, while preserving a conventional
block-device interface toward the kernel.

The user space NVMe driver performs full controller bring-up and administrative
operations, and provisions I/O queue pairs for multiple consumers. One set
of queues is dedicated to servicing I/O requests originating from the kernel
through the *ublk* interface, enabling OS-managed file systems and applications
to operate without modification. These queues reside in host memory and are used
for CPU-initiated I/O.

In addition to kernel-facing paths, the same user space driver provisions I/O
queues for other user space processes that require direct access to the NVMe
device. This allows high-performance user space storage frameworks to coexist
with OS-managed I/O paths, ensuring that no single process monopolizes device
ownership and that multiple user space consumers can be supported concurrently.

In parallel, the user space driver provisions additional I/O queue pairs that
reside in accelerator-accessible memory and are reserved for device-initiated
I/O. These queues are used exclusively by accelerators to submit NVMe
commands directly, allowing data-path execution to bypass host memory and CPU
involvement.

Queue ownership is static for the lifetime of the system configuration. Kernel
I/O paths, user space processes, and accelerator-initiated I/O paths do not
share queues, and none can access the queue resources of another. Concurrency
is provided by the NVMe controller’s native support for multiple queue pairs,
eliminating the need for software arbitration on the data path.

This configuration requires no specialized hardware support and allows
AiSIO systems to operate on commodity platforms. The trade-off is that queue
provisioning, isolation, and coordination across kernel, user space, and device
initiators are implemented entirely in software, placing greater responsibility
on the host-resident user space control plane.

### HOMI via Hardware-Assisted Delegation (SR-IOV)

When supported by the NVMe device and platform, HOMI can realize
host-orchestrated multipath I/O with hardware assistance via Single Root I/O
Virtualization (SR-IOV). In this configuration, the NVMe controller exposes
multiple PCIe functions that share the same namespaces while providing
independent I/O queue resources.

As in the software-mediated configuration, HOMI retains responsibility for
global orchestration, system coordination, and file system integration. The
host remains the sole authority for device discovery, lifecycle management,
and policy enforcement. However, SR-IOV shifts responsibility for I/O queue
isolation and arbitration from software into the NVMe controller hardware.

In the SR-IOV configuration, the Physical Function (PF) is host-managed and
retains administrative control over the device. Virtual Functions (VFs) are
created and assigned to different initiators, including accelerators and, when
required, user space processes. Each VF provides an independent operational
interface with its own set of I/O queues, BAR mappings, and interrupt resources,
while all functions continue to access the same underlying namespaces.

```{figure} _static/aisio_overview_homi_userspace_mgmt.drawio.png
:alt: HOMI via Hardware-Assisted Delegation (SR-IOV)
:width: 700px
:align: center

Overall system architecture showing data flow between components.
```

This hardware-level partitioning allows kernel managed I/O paths, user space
processes, and device-initiated I/O paths to coexist without sharing queue
resources or requiring host-mediated queue arbitration on the data path. From
the perspective of each initiator, the assigned VF behaves as a dedicated NVMe
endpoint, simplifying driver logic and reducing cross-path interference.

Despite this delegation, HOMI remains essential to the architecture. The
host control plane continues to manage administrative operations, coordinate
file system metadata, maintain the file-extent cache, and handle error detection
and recovery. SR-IOV therefore complements HOMI by reducing software overhead on
the data path, rather than replacing host orchestration.

Compared to software-mediated multipath, SR-IOV improves isolation and reduces
runtime coordination costs, but introduces hardware dependencies and limits
flexibility in queue allocation. As a result, it represents an alternative
realization of the same architectural principles, rather than a fundamentally
different design.

### HOMI via Descriptor Delegation (vfio-pci and iommufd)

The software-mediated and hardware-assisted configurations both assume that
consumers can be given queue resources by a host-resident daemon. Neither
addresses how a consumer obtains the device access those queues require when
the controller is driven from user space behind an IOMMU. Under `vfio-pci`,
the operating system enforces exclusivity at the level of the device file
itself, and a consumer that arrives after the daemon is already running has
no route to the controller. Descriptor delegation is the configuration that
resolves this, and it is the one realized in the reference implementation.

The constraint is absolute rather than a matter of policy. A second process
can open the character device, which makes an independent path look feasible,
but binding it with `VFIO_DEVICE_BIND_IOMMUFD` fails because a device cannot
be bound to more than one `iommufd` context. Since the kernel restricts access
to the device until binding completes, every subsequent operation fails with
it, and the consumer obtains neither region information nor a BAR mapping.
What does succeed in that process is opening `/dev/iommu`, allocating an I/O
address space, and mapping memory into it, which yields a valid-looking
address space attached to no device.

Delegation therefore proceeds from the daemon outward. The daemon binds the
device, establishes the I/O address space, and passes the resulting file
descriptors to a consumer over a unix domain socket using `SCM_RIGHTS`, which
is the only mechanism Linux provides for transferring a descriptor between
unrelated processes. The consumer receives the device descriptor, the
`iommufd` descriptor, and a descriptor for each memory region backing queues
and data buffers. It then maps the BAR itself, reaching the doorbells directly,
and registers memory of its own choosing into the shared address space. A
consumer running as an ordinary user, holding neither root nor
`CAP_SYS_ADMIN`, has been shown to read controller registers through its own
mapping and to map its own buffers through the delegated `iommufd`.

Two properties of this arrangement were established by measurement rather than
assumed, and both simplify the design. Pinned-page accounting does not bound
delegation: with `RLIMIT_MEMLOCK` reduced to 64 KiB on either side, mappings
of two megabytes continued to succeed, so there is no accounting argument for
routing registration through the privileged daemon. Lifetime is likewise not
bounded by the daemon: after the daemon exits and closes its descriptors, a
consumer continues to read controller registers and to map further memory
through the descriptors it holds, because those descriptors keep both the
device and the address space alive.

Memory regions are delegated as descriptors rather than as filesystem paths.
Host memory is already backed by an anonymous file, and accelerator memory is
exported as a dma-buf, so passing the descriptor makes both kinds of region
the same shape. It also removes a constraint that path-based sharing imposes
without anyone choosing it: re-opening another process's descriptor through
`/proc` requires ptrace-mode access, which obliges consumers to share the
daemon's user identity, defeating the purpose of delegating to unprivileged
consumers.

Because the socket is the only rendezvous, it also serves the coordination
functions that named objects served previously. Binding the socket address
elects the daemon, which is the function a lock file performed. A closed
connection is how the death of a consumer is observed, which is more reliable
than inferring it from a reference count that a terminated process never
decremented, and it is the signal by which queue resources are reclaimed.
Peers are authenticated with `SO_PEERCRED`, which the kernel vouches for. The
socket carries attachment and control-plane requests only, and is never on the
data path.

The consequence to state plainly is that delegated consumers share a single
trust domain. A consumer that maps the BAR can write the controller
configuration register and reset the device, and one holding the device
descriptor can detach it from the address space by ioctl. Nothing in the
delegation prevents this, and no variation of it can. Where mutual protection
between consumers is required, the answer is not a refinement of this
configuration but a kernel driver, which arbitrates because it owns the
device.

A second consequence bounds what delegation offers to accelerators
specifically. Submitting commands from the host is an ordinary store into a
mapping the consumer already holds, so an unprivileged consumer can drive a
delegated controller. Submitting from an accelerator kernel additionally
requires the accelerator runtime to register I/O memory, which is refused to
unprivileged processes, and the refusal is unrelated to delegation: a process
that opens the device itself is refused identically. Device-initiated
submission is therefore privileged whether or not delegation is used, which
narrows the benefit for those consumers to sharing a controller rather than to
avoiding privilege.

Compared to the software-mediated configuration, descriptor delegation removes
the host round trip on the data path, since consumers ring doorbells
themselves rather than passing requests through the daemon. Compared to
SR-IOV, it requires no hardware support and no platform virtualization
features, and it places no limit on the number of consumers beyond available
queue resources. What it does not provide is isolation. SR-IOV gives each
initiator an independent function whose failures are contained by hardware,
whereas delegation gives every consumer full authority over the shared
controller. The three configurations therefore trade along different axes,
and descriptor delegation is the one that is realizable on commodity hardware
while preserving direct data-path access.

#### Alternatives Considered

Several apparently simpler arrangements were examined and eliminated, and they
are recorded because each is a plausible first proposal.

Routing doorbell writes through the daemon would remove consumer access to
memory-mapped registers entirely and dispose of the trust question. It is
disqualified because the doorbell must be reachable from whatever submits, and
accelerator kernels submit their own commands; returning to the host to ring
the doorbell reintroduces precisely the round trip that device-initiated paths
exist to eliminate.

Exporting only the doorbell region as a dma-buf, rather than delegating the
whole device, would have granted consumers the registers they need without the
authority to reset the controller. The export mechanism exists, but the
resulting descriptor carries no CPU mapping, and neither major accelerator
runtime imports a dma-buf as a device pointer, so the region cannot be reached
by either the host or the accelerator. This is the one rejected alternative
that could cease to be rejected: either a runtime gaining dma-buf import, or
the exporter implementing CPU mapping, would revive it.

Reopening the daemon's descriptors through `/proc` works for memory, where
re-opening the inode of an anonymous file yields the same memory, but does not
generalize to the device, because opening a character device that way invokes
the driver anew and yields a fresh, unbound descriptor. Pulling a descriptor
with `pidfd_getfd` runs in the wrong direction, since the caller pulls from
the target under ptrace-mode access, which an unprivileged consumer cannot
obtain over a privileged daemon, and no counterpart exists that pushes a
descriptor into another process. Inheriting descriptors across process
creation avoids the socket entirely but contradicts the usage model, in which
the daemon is already running when an independently started program decides to
attach.

Assigning each consumer a distinct address space with PASID is the hardware
answer to per-process isolation, and the attach operation exists on current
kernels. It is disqualified because it would require the controller to
associate queues with process address space identifiers, which is not
generally how NVMe controllers behave. Transferring an address space with
`IOMMU_IOAS_CHANGE_PROCESS` addresses a different problem, namely a daemon
restarting beneath live consumers, rather than concurrent sharing.

Finally, retaining named shared-memory objects and introducing a socket only
for descriptor passing would preserve two rendezvous mechanisms with two
lifetime models, including the stale-object detection that the socket was
introduced to make unnecessary. Where the socket exists at all, it should be
the only way in.
