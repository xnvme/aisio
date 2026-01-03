(sec-background)=
# Background

This Background section provides a bottom-up technical foundation: it reviews
the PCIe transport on which devices communicate, the execution and memory
models of CPUs and accelerators, the behavior of NVMe controllers, the structure
of file systems and block devices, and the interfaces through which software
initiates and manages I/O. Readers already familiar with these topics may
proceed directly to the architecture, while others may return here as needed
when later sections depend on concepts introduced in this groundwork.

(sec-terminology)=
## Terminology

This section introduces a small set of terms used throughout the document to
avoid implicit assumptions about where coordination occurs, where data moves,
and which processing entity is responsible for initiating I/O. The terms defined
here describe logical roles rather than fixed subsystems or deployment
boundaries.

**Control plane**
: Logical coordination and management operations associated with I/O, such as
device configuration, queue allocation and management, metadata handling, and
policy enforcement. Control-plane operations may execute on the same processing
elements as data-path operations, depending on system design.

**Data path**
: The movement of I/O payloads through DMA engines and interconnects, including
device-to-host and device-to-device transfers.

**Fast path**
: The minimal sequence of operations required to complete an I/O request under a
given execution and memory model, excluding optional monitoring, fallback
handling, or recovery procedures.

**CPU-initiated I/O**
: I/O in which NVMe commands are constructed and submitted by software executing
on the host CPU. This includes both kernel-resident drivers and user-space
drivers, and is independent of whether data movement uses host memory or
peer-to-peer DMA. In the literature, this execution model is sometimes also
referred to as *host-initiated* I/O.

**Device-initiated I/O**
: I/O in which NVMe commands are constructed and submitted by software executing
on a PCIe-attached device, such as a GPU, DPU, or FPGA. Payloads reside in
device-local or device-accessible memory, and command submission proceeds
without host involvement on the data path, subject to host-managed coordination
and policy.

**OS-managed**
: Storage access paths that operate through kernel-resident drivers and the
operating system’s storage stack, including block layers, file systems, and
VFS-mediated interfaces. The operating system retains responsibility for device
initialization, queue management, metadata handling, and policy enforcement.

**User-space managed**
: Storage access paths in which NVMe devices are initialized and managed by
host-resident user-space software rather than kernel drivers. User-space managed
paths bypass the kernel storage stack and assume explicit responsibility for
queue management, scheduling, and safety mechanisms normally provided by the
operating system.

## CPUs

Modern CPU architecture is a sophisticated evolution of the **Von Neumann
Architecture**, which established the foundational concept of a processing unit
fetching instructions and data from a shared memory system. While the original
model relied on a single sequential flow, modern processors from manufacturers
like Intel, AMD, ARM, and RISC-V have expanded these core principles into a
highly parallel and specialized hierarchy.

### CPU Architecture and Components

The "Central Processing Unit" is now an **Execution Engine** composed of
distinct hardware units that handle the instruction fetch, decode, and execute
cycle. The **Arithmetic Logic Unit (ALU)** remains the primary worker for
whole-number calculations and logical branching, while the **Floating-Point
Unit (FPU)** acts as a dedicated specialist for complex decimal math. To handle
modern workloads like video and encryption, **SIMD (Single Instruction, Multiple
Data)** or **Vector Units** allow the processor to apply a single command across
large batches of data simultaneously.

Directing these units is the **Control Unit**, which functions as the manager
of the execution cycle. In contemporary designs, this unit is assisted by a
**Branch Predictor** that anticipates program flow to keep the execution units
fed with data, minimizing idle time. Data movement and memory protection are
managed by the **Memory Management Unit (MMU)**, which translates virtual
addresses used by software into physical addresses in RAM to ensure process
isolation. To bridge the speed gap between the fast processor and slow main
RAM, a tiered **Cache** hierarchy (L1, L2, and L3) stores progressively larger
amounts of data directly on the silicon.

For communication beyond internal memory, CPUs utilize various
**Interconnects**. The most common is the **PCIe Root Complex**, which serves as
the interface between the internal CPU fabric and the external PCIe hierarchy.
Specialized systems may also use alternative high-bandwidth interconnects like
**NVLINK** for direct GPU to CPU or GPU to GPU communication, offering higher
throughput than standard PCIe for specific high-performance workloads.

### CPU Frequency and Scaling

The clock frequency represents the speed at which the **Control Unit**
coordinates the fetch-decode-execute cycle, measured in billions of cycles
per second (GHz). In the classic Von Neumann model, this speed was generally
static, but modern CPUs use dynamic scaling to balance performance and power
consumption. Through **Voltage and Frequency Scaling**, a processor can reduce
its clock speed during light tasks to save energy and lower heat output.

Conversely, **Boost Clock** technology (also known as Turbo Boost) allows
the CPU to temporarily exceed its **base frequency**, which is the minimum
guaranteed clock speed, when a demanding task is detected and there is enough
thermal and electrical headroom. This opportunistic behavior ensures that the
ALU and FPU operate at their maximum potential only when needed, preventing the
chip from overheating. **CPU governors** control how the driver adjusts these
speeds; *powersave* and *performance* governors lock the frequency at limits,
while *ondemand* scales it dynamically based on load. These can be overridden
using CLI tools such as `cpufrequtils` or `linux-cpupower`.

### Simultaneous Multithreading (SMT)

To further increase efficiency, **Simultaneous Multithreading (SMT)**, referred
to as **Hyper-Threading** on Intel processors, allows each physical CPU core to
run two threads, creating twice as many logical cores as physical cores. It does
so by exposing two execution threads per core and utilizing idle time in one
thread to execute the instructions from the other. By maximizing the utility of
execution units during memory stalls (when the core is waiting for data from the
Cache or RAM), SMT ensures the physical core remains as productive as possible.

## Memory

Modern computer systems employ multiple memory technologies, each optimized
for different trade-offs in latency, bandwidth, capacity, and persistence.
The foundation of system memory is Dynamic Random-Access Memory (DRAM), which
stores data as electrical charge in capacitors and therefore requires continuous
refresh to retain its contents. When power is removed, all data in DRAM is lost,
and technologies with this property are described as volatile.

In computer systems, volatile memory technologies are typically referred
to simply as memory, and we will adopt that convention here. By contrast,
non-volatile memory technologies, such as NAND flash, retain their contents
across power cycles and are referred to as storage.

A further distinguishing characteristic between memory and storage is
addressability. Memory is typically exposed as a byte-addressable address
space, whereas storage technologies are commonly accessed through block-oriented
interfaces. For NAND flash and other storage media, this non-byte-addressable
access model arises from physical constraints of the underlying technology
itself, in contrast to DRAM, which naturally supports fine-grained byte access.

The volatile memory technologies used in modern systems are specialized
derivatives of DRAM. The most common variant is DDR (Double Data Rate SDRAM),
which serves as the main system memory in general-purpose computing platforms.
A power-optimized variant, LPDDR (Low-Power DDR), reduces energy consumption
through lower operating voltages and optimized signaling, and is widely used
across a broad range of systems, from mobile devices and single-board computers
to DPUs and tightly integrated accelerator platforms. For accelerator-attached
memory, GDDR and HBM prioritize bandwidth over latency, with HBM employing
three-dimensional stacked DRAM and ultra-wide interfaces to deliver extremely
high throughput and improved energy efficiency.

Beyond individual memory technologies, modern systems organize memory into
hierarchical tiers that trade capacity for latency and bandwidth. These tiers
are commonly grouped into main memory, device-attached memory, and on-chip
caches, each serving a distinct role within the memory hierarchy. Main memory,
typically implemented using DDR or LPDDR, is visible to the operating system
and provides large-capacity storage for CPU-centric execution. Device-attached
memory, commonly implemented using GDDR or HBM, is located close to accelerators
and optimized to sustain the high data rates required by massively parallel
compute engines.

At the lowest-latency end of the hierarchy are caches, which are tightly
integrated with compute units and optimized for rapid, fine-grained access.
Caches are typically implemented using SRAM and organized into multiple levels,
trading capacity for progressively lower latency and higher bandwidth. This
tiered organization underpins data locality, cache behavior, and memory access
patterns in both CPUs and accelerators.

Across these tiers, main memory and device-attached memory constitute the
primary software-visible pools of volatile memory. Whether backed by host DRAM,
accelerator-attached DRAM, or HBM, these pools are managed by system software
and exposed to programs through explicit allocation and addressing mechanisms.
From the perspective of both the programmer and the operating system, they are
programmed in broadly similar ways, despite differences in physical placement,
access latency, and bandwidth. At the lowest level, access to these memory
pools ultimately resolves to load and store operations, whether expressed in
high-level languages or directly as instructions that move data between memory
and processor registers.

In contrast, cache memories are primarily managed by hardware and are not
explicitly allocated or addressed by application code. Cache placement,
eviction, and coherence are handled transparently by the memory subsystem,
allowing software to reason in terms of larger, contiguous memory abstractions.
While exceptions exist, such as software-managed scratchpads or shared memories
on accelerators, caches are generally treated as an implicit performance
optimization rather than a directly programmable memory resource.

### Virtual Memory Abstraction

While applications ultimately rely on physical memory for storage, the operating
system (OS) abstracts this reality using **Virtual Memory**. Each running
program is given its own isolated, contiguous **virtual address space**. The
OS, with the help of the **Memory Management Unit (MMU)** in the CPU, translates
these virtual addresses into potentially non-contiguous **physical addresses**
in RAM using a **page table**.  This abstraction is critical for **process
isolation** (preventing programs from interfering with each other), **efficient
memory utilization** (allowing a contiguous virtual block to be backed by
scattered physical pages), and **memory capacity expansion** (enabling swapping,
where idle memory pages are temporarily moved to disk).

### Contiguous vs. Non-Contiguous Memory

The operating system manages memory using a sophisticated translation scheme.
From the perspective of an application, memory is a single, contiguous block of
**virtual addresses**. However, this block is typically mapped by the MMU into
non-contiguous, or scattered, **physical addresses** in RAM. This non-contiguous
allocation is the default, allowing the OS to efficiently utilize fragmented
physical memory.

**Contiguous Memory** refers to a special case where a requested block of memory
is backed by a single, unbroken sequence of physical addresses. This strict
physical contiguity is often a requirement for low-level hardware operations,
particularly those involving devices that must perform DMA transfers without
involving the MMU in address translation.

### Memory Pinning

**Memory Pinning** (also known as page locking or registering memory) is the
process of instructing the operating system to prevent a specific region of
application memory from being relocated or swapped out to disk. When a memory
region is pinned, its physical address is guaranteed to remain constant. This
is crucial for performance-sensitive contexts, especially those using DMA. If
a device is given a physical address for a DMA transfer, the memory must be
pinned; otherwise, the OS could move the data, causing the DMA operation to
target the wrong location and resulting in data corruption or an I/O fault.
Pinning memory temporarily reduces the pool of physical memory available for the
OS to manage, making it a resource-intensive operation typically restricted to
kernel code or privileged user-space drivers.

### Direct Memory Access (DMA)

**Direct Memory Access (DMA)** is a critical capability that allows peripheral
devices (such as network cards, disk controllers, or GPUs) to transfer data
directly to and from main system memory **without continuous CPU intervention**.
A specialized component, the **DMA Controller**, manages the entire transfer
process.  This offloading significantly reduces the CPU overhead and bus
traffic, which is essential for high-throughput operations. The device initiates
a transfer request, the DMA Controller moves the data, and then interrupts the
CPU only when the entire operation is complete.

### Non-Uniform Memory Access (NUMA)

Non-uniform memory access (NUMA) <REF linux-numa> is a design for computer
memory when multiple processors are available in a system and memory location
affects the memory access time.  NUMA nodes are an abstraction of the system's
hardware resources and represent groups of hardware that are physically closer
to each other than to the rest of the system. Memory access to memory within the
same node will often experience faster access time than to memory across nodes.

In high-throughput storage benchmarks the penalty of accessing memory across
NUMA nodes becomes negligible. When using multiple queues and threads most of
the time is spent moving data through the device’s internal parallel engines,
through PCIe, and on the CPUs that poll the queues. Under these conditions
the latency difference between local and remote NUMA access is hidden by the
concurrency of the system.

### Memory-Mapped I/O (MMIO)

**Memory-Mapped I/O (MMIO)** is a mechanism that allows the CPU to communicate
with peripheral devices by treating the device's control and data registers as
if they were standard memory locations. The device registers are assigned unique
addresses within the CPU's overall address space, separate from main system RAM.
The CPU then uses standard load and store instructions to read from or write to
these memory addresses, which directly manipulate the state of the I/O device.

Later we will take a closer look at thos PCIe attached devices expose register
and memory spaces.

## PCIe

PCIe is a message-based interconnect anchored at the Root Complex (RC),
typically integrated into the CPU, and branching downstream through ports,
bridges, and switches before terminating in endpoints such as NVMe drives, NICs,
and GPUs.

PCIe messages are encapsulated in Transaction Layer Packets (TLPs). The TLPs
relevant for device interaction are Memory Read and Memory Write Requests, which
are routed by address. Root Ports, switch ports, and bridges contain forwarding
windows that specify which address ranges they accept or forward. Memory
Requests propagate downstream or upstream through these windows until they reach
the endpoint that owns the targeted range.

All PCIe devices communicate using TLPs that carry read or write requests to
specific addresses. These packets move through the hierarchy by address-based
routing. Routing is performed by Root Ports, switch ports, and any intervening
bridges, each programmed with address windows that define which ranges of the
address space they forward. Memory TLPs propagate through these windows until
they reach the endpoint that claims the targeted range.

Endpoints expose their memory through Base Address Registers (BARs). A device
can provide up to six 32-bit BARs, three 64-bit BARs, or a mix thereof. Each
BAR defines a contiguous memory region. In practice, 32-bit BARs usually map
control registers, and 64-bit BARs map larger on-device memories. The operating
system maps each BAR region into host physical address space and programs the
necessary address windows in upstream ports and bridges. These mappings appear
in `/proc/iomem`.

MMIO and DMA are both expressed on PCIe as Memory TLPs that differ only in
initiator, direction, and size. All memory operations target host-physical
addresses mapped to host RAM or device BARs and may originate from the CPU or
from other PCIe endpoints.

This provides a simple mental model of PCIe. MMIO and DMA are both expressed as
Memory TLPs that target host physical addresses which may lie in host memory or
device memory and may be generated by the CPU or by other devices. We begin with
this simple view and now uncover the additional mechanisms that constrain or
extend this flexibility.

### Address Translation: ACS, IOMMU, IOVA, ATS, and ATC

PCIe endpoints can issue Memory Read and Memory Write TLPs whenever DMA bus
mastering is enabled. This protects only against driver mistakes, because a
malicious device can ignore the protocol and emit Memory TLPs even when bus
mastering is disabled. Bus mastering therefore provides software discipline and
not a security boundary.

Access Control Services (ACS) provide the first layer of hardware enforcement
inside the PCIe fabric. ACS rules on switch ports can block or redirect TLPs
originating from downstream devices, forcing them upstream toward the Root
Complex unless explicitly allowed. This applies to all TLP types including both
address-routed Memory Requests and ID-routed messages. By enforcing upstream
redirection ACS prevents unintended peer-to-peer traffic and constrains
device-to-device communication according to system policy.

The IOMMU provides stronger isolation. Instead of giving devices raw host
physical addresses, the operating system assigns them IO virtual addresses
(IOVAs). Devices issue DMA to these IOVAs, and the IOMMU translates each IOVA
into the corresponding host physical page while enforcing permissions.

Endpoints implementing Address Translation Services (ATS) can request IOVA to
physical translations from the IOMMU and store them in an on-device Address
Translation Cache (ATC). With valid ATC entries, an endpoint can issue DMA TLPs
directly to translated host-physical addresses without repeated IOMMU lookups.

ACS and the IOMMU constrain what a device is allowed to reach. Neither alters
the fundamental routing rules. Address-routed Memory Requests always follow
PCIe address-based routing. ID-routed messages always follow identifier-based
routing. ACS may block or force Memory Requests upstream. The IOMMU applies only
to Memory Requests that target IOVAs.

### Routing: Root Complex Mediated

In commodity systems, PCIe switches do not interpret Memory Request addresses
and therefore forward all Memory TLPs upstream to the Root Complex (RC). The
RC performs authoritative address decode and determines whether the target
corresponds to host memory or a device BAR.

If the target lies within a peer device's BAR region, the RC forwards the
request downstream through the appropriate Root Port. NVMe devices, GPUs, and
NICs generate only address-routed Memory TLPs, so all their DMA traffic follows
this pattern. Even zero-copy device-to-device transfers pass through the RC
decode path unless the system uses a switch with address-translation hardware.

### Routing: Switch Mediated

Some PCIe switches incorporate hardware capable of interpreting Memory Request
addresses locally. These expose Address Translation Units (ATUs) or peer-memory
windows that allow the switch to match incoming host-physical addresses against
configured ranges and forward Memory Requests directly downstream to another
endpoint without involving the RC.

This enables peer DMA within the switch fabric with reduced latency. However,
this is not part of the PCIe baseline specification. Only high-end switches
used in multi-GGPU backplanes, multi-host fabrics, or accelerator systems expose
ATUs, and translation windows must be programmed by firmware or the operating
system. Without ATU configuration, the switch forwards all Memory Requests
upstream to the RC.

Switch-mediated routing operates only on the host-physical address carried in
the TLP. ATS, ATC contents, and IOVA semantics do not affect switch routing. If
no ATU window matches, the switch forwards the request upstream regardless of
how the address was produced.

### Routing: Device-routed (ID-routed)

A smaller class of endpoints can generate TLPs that use identifier routing
instead of address routing. Such packets carry a Bus Device Function (BDF)
identifier. Switches route these packets downstream by matching the BDF to
the correct port. FPGAs, DPUs, NTBs, and a few accelerator ASICs can emit
ID-routed Writes or Messages and therefore perform peer communication without
RC involvement and without relying on switch ATUs. Commodity endpoints including
NVMe SSDs, GPUs, and NICs do not generate ID-routed traffic and rely exclusively
on address-routed Memory Requests.

(sec-pcie-functions)=

### Multi-function devices

PCIe devices are identified by a Bus–Device–Function (BDF) tuple. Under a single
Bus and Device number, a controller may expose multiple functions, each behaving
as an independent PCIe endpoint with its own configuration space, capabilities,
and BAR mappings. This allows a single physical device to present several
logically distinct interfaces while sharing the same underlying hardware.

#### Single- and Multi-Function Controllers

Some devices expose only one function, while others expose two or more. A
multi-function layout allows a controller to present multiple independent
control paths or operational domains, each with isolated registers and interrupt
lines but backed by common internal resources. This pattern is used in devices
that serve several roles or expose multiple ports through the same silicon.

#### SR-IOV

SR-IOV{cite}`pcisig:pcie_7_0` builds on the PCIe multi-function model by defining a
control relationship between a *physical function* (PF) and a set of lightweight
*virtual functions* (VFs) exposed by a single physical PCIe device. Each VF is
enumerated as an independent PCIe function with its own BDF, configuration
space, and BARs. The PF retains exclusive responsibility for device-wide
management and resource provisioning, while VFs expose isolated PCIe interfaces
that are bound to, possibly distinct, host-side device drivers and can be
assigned to separate software or hardware tenants, such as virtual machines,
containers, or accelerators.

At the PCIe level, SR-IOV provides a standardized mechanism for partitioning a
device’s internal resources into multiple independently addressable interfaces
with hardware-enforced isolation at the granularity of PCIe functions. This
isolation applies to configuration space, MMIO regions, interrupt delivery, and
DMA access as defined by the device, but does not imply isolation of higher-level
protocol state, shared media, or software-visible data structures unless
explicitly enforced by the device implementation.

For PCIe-attached NVMe controllers, the specification
standardizes{cite}`nvme-pcie-transport-1.3,nvme-base-2.3,nvme-nvm-cs-1.2` the use
of SR-IOV. The PF is responsible for controller initialization, administrative
operations, and the allocation of controller resources across VFs, including
I/O queue pairs, interrupt resources, and namespace access.

Of particular relevance is that NVMe permits namespaces to be shared across the
PF and multiple VFs. This enables concurrent access to the same underlying
storage through multiple PCIe functions, providing a standardized foundation for
multipath and multi-initiator I/O while preserving isolation between execution
domains at the level defined by the controller.

### Summary

Data movement in PCIe whether DMA or MMIO are sequences of Memory TLPs
whose routing depends on which component performs the decode. Devices that
generate address-routed TLPs rely on the RC unless a switch provides its own
decode windows. Devices capable of ID-routed TLPs can perform peer routing
independently. IOMMU translation, ATS caching, and ATC entries determine how
devices obtain the addresses they use, but they do not alter the routing model.
Together, RC mediated DMA, switch mediated peer DMA, and device routed peer DMA
describe all data transfer paths allowable in PCI Express systems and form the
architectural foundation for understanding performance and design tradeoffs in
accelerator integrated storage paths.

(sec-massively-parallel-processing-units)=
## Massively Parallel Processing Units

* SIMD, SPMD, and SIMT

* Arithmetic vs logic

* Memory bandwidth vs Compute Capability

(sec-nvme-controllers)=
## NVMe Controllers

All NVMe specification documents are freely available upon ratification and
distributed via the nvme express website. For details please to look in the
specification documents, however, since these have now grown into many thousands
of pages spread upon multiple documents, then see these subsections as a brief
overview on theory of operations and NVMe initiatlization and command processing
flows.

Directly to the first concept an NVMe Controller, this is the entity which
is accessible via a transport. Transports include, PCI, TCP, and RDMA. We are
currently focused on the locally attached storage devices over PCI. Thus, thus
initially we will cover how to initialize an NVMe controller over PCIe and touch
upon PCIe infra. for it.

On with it.

NVMe devices implement a command driven model in which the host constructs
commands, places them in submission queues, and notifies the controller through
memory mapped doorbells. Controllers retrieve commands through DMA, perform the
requested operations, and report completions through completion queues.

### Controller Enablement and the Admin Queue

To bring a controller online, the host must map the PCIe BAR into its address
space, reset and configure the controller through the Controller Configuration
register, and allocate the Admin Submission Queue and Admin Completion Queue in
DMA visible memory. Once prepared, the host may issue administrative commands
such as Identify Controller and Create I/O Queue Pair.

### I/O Queue Pairs

All data plane operations use queue pairs. The host allocates DMA visible
memory for the Submission Queue and Completion Queue, sets queue size and base
addresses, and registers the queues through administrative commands. Completion
may use interrupts or polling.

### Command Construction

Each I/O request is represented by a Submission Queue Entry. The driver selects
an opcode, namespace identifier, logical block address, transfer length, and
flags. A Command Identifier is assigned to link the request with its completion.
The SQE format is identical across kernel drivers, user space drivers, and
accelerator resident drivers.

### Payload Description

NVMe commands reference data buffers through the data pointer field, labelled
``DPTR``, which occupies ``CDW6``, ``CDW7``, ``CDW8``, and ``CDW9`` of the
command. The NVMe specification defines several possible interpretations of
``DPTR`` depending on the command opcode, the command set, and the data transfer
type. ``DPTR`` may encode:

* a single physical address
* two physical addresses, interpreted as PRP1 and PRP2
* a pointer to a PRP list page that describes the remaining pages
* an SGL descriptor or the beginning of an SGL segment or SGL segment list

PRPs describe buffers in page sized units. PRP1 always points to the first data
page. PRP2 either points to a second page or to a PRP list page that contains
entries for additional pages.

SGLs describe non contiguous or segmented buffers and may represent host memory,
device memory, or key and value formats, depending on the command.

Preparing payloads therefore involves selecting the correct DPTR encoding and
constructing the PRP or SGL structures referenced by the command.

### Doorbells and Completion

After preparing an SQE, the host writes it into the Submission Queue, updates
the tail pointer, and rings the doorbell through MMIO. The controller writes
completion entries directly into the Completion Queue. Completion detection uses
polling or interrupts. The host drains the CQE, checks the status code, retires
the Command Identifier, and advances the Completion Queue head pointer.

(sec-nvme-drivers)=
## NVMe Drivers

While NVMe controller behavior is defined by the NVMe specification, NVMe drivers
vary in residency, execution model, and access to device resources such as MMIO
registers and DMA engines. These differences influence how NVMe commands are
constructed, how submission and completion queues are allocated and managed,
where payloads are allocated, and how I/O processing is scheduled within the
system.

At a structural level, NVMe I/O consists of submission queue entries (SQEs),
completion queue entries (CQEs), and data transfer descriptors, such as physical
region pages (PRPs) or scatter–gather lists (SGLs), which describe the location
of I/O payloads in memory. NVMe drivers are responsible for constructing these
structures, placing them in memory accessible to the controller, and issuing
MMIO doorbell writes to notify the device of new work.

### Driver Residency

**Kernel-resident drivers**
integrate with the operating system block layer and rely on kernel scheduling.
They construct NVMe commands in host memory, allocate and manage submission and
completion queues on behalf of the kernel, and interact with controllers through
kernel-managed MMIO and DMA mechanisms. User-space I/O submission interfaces
such as libaio and io_uring operate on top of kernel-resident NVMe drivers and
provide alternative mechanisms for submitting I/O requests to the kernel.

**User-space drivers**
execute outside the kernel and typically rely on polling rather than interrupts
to reduce scheduling overhead. An example is SPDK {cite}`yang2017spdk`, which
implements an NVMe driver entirely in user space and bypasses the kernel NVMe
stack. In this model, NVMe command construction, queue management, and MMIO
interaction are handled directly from user space.

**Device-resident drivers**
execute on PCIe-attached devices such as GPUs, DPUs, or FPGAs. Depending on
hardware capabilities, such drivers may construct NVMe commands using
device-local or device-accessible memory and may perform MMIO operations
directly, provided the device supports outbound PCIe transactions and
peer-to-peer DMA.

(sec-io-initiator)=
### I/O Initiator Roles

The purpose of distinguishing I/O initiator roles is to make explicit which
processing entity is responsible for constructing and submitting NVMe commands
in a given I/O path. These definitions are introduced to avoid implicit
assumptions about execution context, memory placement, or data movement when
referring to NVMe I/O behavior, and to provide precise terminology that can be
used consistently throughout the document.

An I/O initiator is the processing entity that constructs NVMe commands and
submits them to the controller. This includes populating submission queue
entries, configuring data transfer descriptors such as PRPs or SGLs, and
triggering command processing through MMIO doorbells. Initiator roles can be
classified independently of driver residency, although the two are often
related.

**CPU-initiated I/O**
originates from software executing on the host CPU, either in kernel space or
user space. NVMe commands, including SQEs and associated PRPs or SGLs, are
constructed by the CPU, and PRPs or SGLs reference host memory for the data
payloads.

**CPU-initiated I/O with peer-to-peer data movement**
originates from software executing on the host CPU, either in kernel space or
user space. NVMe commands, including SQEs and associated PRPs or SGLs, are
constructed by the CPU, but PRPs or SGLs reference device-local or
device-accessible memory for the data payloads.

**Device-initiated I/O**
originates from software executing on a PCIe-attached device. NVMe commands,
including SQEs and associated PRPs or SGLs, are constructed by the device, and
PRPs or SGLs reference device-local or device-accessible memory for the data
payloads.

These classifications are descriptive rather than prescriptive, and are not
mutually exclusive; practical systems may combine different driver residency and
I/O initiator roles depending on hardware capabilities and software design.

(sec-dma-reachability)=
## DMA Reachability Requirements

NVMe command processing makes DMA reachability constraints explicit because
the controller retrieves submission queue entries (SQEs) through DMA and
resolves data movement based on addresses carried in the command, including any
indirection structures referenced by `DPTR`.

The core requirement is:

All memory that the controller may dereference during command execution must
be DMA reachable under the platform’s configured addressing, translation, and
routing mechanisms (for example, host physical addressing or IOVA mappings).

This includes:

- **Payload references (`DPTR`)**, whether direct (`PRP1`/`PRP2`) or indirect via
  PRP lists or SGLs
- **Indirection metadata**, including PRP list pages and SGL descriptor tables
  and any chained continuation structures
- **Auxiliary metadata**, such as buffers referenced via `MPTR` (when used)
- **Queue memory**, including SQEs and CQEs for both Admin and I/O queues

When `DPTR` uses PRP or SGL indirection, the PRP and SGL structures themselves
must be DMA reachable, since the controller must read them in order to resolve
the final payload addresses.

DMA reachability is typically straightforward when queues, payloads, and
indirection metadata reside in host DRAM. When any of these reside outside
host memory, such as in device-attached memory, reachability depends on
platform configuration, including PCIe routing behavior and IOMMU mappings and
permissions.

(sec-block-devices)=
## Block Devices

A block device exposes a linear address space divided into fixed-size units
known as blocks. Common sizes include 512 bytes, 4 KiB, and, increasingly,
large-block-size (LBS) devices with 64 KiB or larger blocks. Despite appearing
uniform and linear, this address space is not byte-addressable: the hardware
only reads and writes entire blocks, even though higher-level OS layers provide
interfaces that seem to support arbitrary byte offsets. This abstraction
unifies access to HDDs, SSDs, NVMe drives, and other media, while hiding their
underlying constraints and geometry.

When I/O is misaligned or smaller than the block size, the system must perform
a read–modify–write (RMW) cycle: reading the full block, updating the changed
bytes, and writing the whole block back. This introduces significant performance
penalties, increases latency and bandwidth consumption, and on flash-based
devices causes write-amplification, where a single logical write results
in multiple internal physical writes. As devices transition toward larger
64 KiB–128 KiB blocks, the cost of RMW grows accordingly. This has driven
efforts to augment or evolve the block interface, including Open-Channel SSDs,
Zoned Storage / NVMe Zoned Namespaces, Key–Value SSDs, and the more recent
NVMe Flexible Data Placement (FDP) feature, which provides a standardized,
placement-aware interface with growing industry adoption.

Although these lower-level details are abstracted away by the simplicity
of the block-device model, they remain important because their side effects
propagate up the storage stack, influencing file-system behavior and ultimately
application performance. As systems increasingly enable direct device-to-device
or accelerator-to-device communication, these abstractions can be bypassed
entirely, exposing the concrete NVMe protocol rather than the higher-level block
interface. Understanding the underlying constraints therefore becomes essential
when building systems where devices interact without traditional OS mediation.

(sec-filesystems)=
## Files and File Systems

File systems define on disk layout, metadata, and allocation.

**Extents** represent contiguous file regions through a starting block and
length.

**On disk format** encodes superblocks, inodes, allocation groups, and B tree
metadata.

**FIEMAP** reveals the physical extents of a file but requires the file system
to be mounted and does not expose all metadata needed for accelerator resident
scheduling.

(sec-posix)=
## POSIX Semantics

POSIX defines the interface for file access, specifying consistency rules,
permissions, and durability. These semantics assume CPU initiated access and
enforce memory coordination between user space and kernel space. This assumption
reinforces CPU centered I/O paths and limits how accelerators can interact with
storage.

## Software Components

This section briefly describes software components that are relevant to modern
Linux-based storage systems and user-space I/O stacks. The descriptions focus on
the functionality provided by each component, without prescribing how they are
combined or used.

**ublk**
: A Linux kernel mechanism for implementing block devices in user space
{cite}`ublk`. ublk provides a kernel-facing block device interface while
forwarding I/O requests to a user-space process for handling. It integrates with
the Linux block layer and virtual file system through standard block device
semantics.

**SPDK**
: The Storage Performance Development Kit is a collection of libraries and
drivers for building high-performance storage software in user space
{cite}`yang2017spdk,spdk`. SPDK includes a user-space NVMe driver that bypasses
the kernel I/O stack and employs polling-based I/O for low-latency access to NVMe
controllers. The framework exposes explicit control over NVMe queues, memory
management, and command submission.

**xNVMe**
: A cross-platform NVMe abstraction layer that provides a unified API for
NVMe command submission and completion across operating systems and backends
{cite}`xnvme_systor,xnvme_preprint,xnvme-io`. xNVMe abstracts differences in
NVMe command interfaces, queue management, and completion handling, allowing
NVMe interactions to be expressed through a consistent programming model.

**XAL (eXtents Access Library)**
: A library for retrieving file extent information from file systems
{cite}`xallib`. XAL obtains logical-to-physical block mappings either through
kernel-provided interfaces, such as the FIEMAP ioctl {cite}`linux-fiemap`, or
by decoding on-disk filesystem metadata structures directly. For example, XAL
can parse the on-disk format of the XFS filesystem, including superblocks,
allocation groups, inodes, and extent trees, to extract extent information
independently of the filesystem mount state.

## Transition to Architecture

The background above summarizes the mechanisms and constraints that shape modern
storage I/O, spanning PCIe transport and routing, memory and DMA visibility,
NVMe controller operation, and the software interfaces used to construct and
submit commands.

The next section builds on this foundation by presenting the system
architecture, using the terminology and models introduced here to describe its
components and I/O flows precisely.
