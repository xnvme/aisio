(sec-background)=
# Background

This Background section provides a bottom-up technical foundation: it reviews
the PCIe transport on which devices communicate, the execution and memory
models of CPUs and accelerators, the behavior of NVMe controllers, the structure
of file systems and block devices, and the interfaces through which software
initiates and manages I/O. Readers already familiar with these topics may
proceed directly to the architecture, while others may return here as needed
when later sections depend on concepts introduced in this groundwork.

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

SR-IOV extends the multi-function concept by enabling a device to dynamically
create many lightweight virtual functions (VFs) alongside one physical function
(PF). Each VF appears as its own BDF entry. The PF manages and provisions
resources, and each VF exposes its own configuration space and BAR regions and
can be assigned to a distinct software or hardware tenant such as a virtual
machine, a container, or another isolated execution domain.

SR-IOV provides a PCIe-level mechanism for carving a device’s internal resources
into multiple independent and securely separated interfaces, without assuming
anything about the higher-level protocols or device types implemented behind
those interfaces.

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

While controller behavior is fixed by the NVMe specification, NVMe drivers
differ widely in residency, capabilities, and access to MMIO. Driver residency
determines how they manage queue memory, construct commands, and interact with
the operating system.

### Driver Residency

**Kernel resident drivers** integrate with the operating system block layer,
rely on kernel scheduling, and use host memory for all queues and data buffers.

**User space drivers** avoid kernel scheduling overhead through polling and
minimize system calls. Examples include SPDK and io uring based drivers. They
remain CPU centered and use host memory.

**Accelerator resident drivers** run on GPUs, DPUs, or FPGAs. They may place
queue pairs and data buffers in accelerator memory and may perform MMIO
doorbell writes directly if the accelerator supports outbound PCIe and peer to
peer DMA. This model enables accelerators to participate directly in I/O.

(sec-io-initiator)=
### I/O Initiator Roles

Driver residency determines the processing unit that initiates I/O.

**CPU initiated**
Commands and DMA buffers are located in host memory.

**CPU initiated with peer to peer transfers**
Commands originate on the CPU, but DMA moves data directly between devices.

**Accelerator initiated**
A driver running on the accelerator issues commands and uses accelerator local
memory for queues and data.

AiSIO originally aimed to unlock accelerator initiated I/O. Experimental results
showed that no single initiator is always optimal. AiSIO therefore exposes a
multipath I/O model where CPUs, GPUs, DPUs, and other accelerators can initiate
I/O as appropriate for the workload and hardware capabilities.

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

### Software Components and Integration

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


**Conventional kernel path**

Applications using standard POSIX file I/O interact with the kernel VFS and
filesystem layers. These requests eventually reach the ublk block device, which
delivers them to HOMI's user-space process. HOMI forwards them to SPDK, which
executes the I/O using its reserved NVMe queue pairs. Completions propagate
back through the same path. This path maintains full compatibility with existing
applications and kernel infrastructure.

**Host-initiated fast path**
: Applications using user-space I/O libraries (io_uring, SPDK APIs) bypass
the kernel and submit I/O directly to HOMI-managed SPDK queues. This reduces
software overhead while still using CPU-initiated I/O and host memory buffers.

**Device-initiated fast path**
: GPU kernels query HOMI's extent cache to translate file offsets into
physical block addresses, construct NVMe commands in GPU memory, submit them
to GPU-resident queue pairs, and process completions via polling. The NVMe
controller performs peer-to-peer DMA directly between SSD and GPU memory. The
CPU is not involved in data movement.

All three paths operate concurrently on the same filesystem. HOMI ensures
coherency by maintaining up-to-date extent information and coordinating queue
access. The kernel path provides safety and compatibility. The accelerator path
provides maximum performance for data-intensive operations.


(sec-dma-visibility)=
## DMA Visibility Requirements

A central constraint across all components in this background is that any
memory region accessed by the NVMe controller must be reachable through DMA.
This requirement applies to all structures that participate in an I/O
operation:

* data buffers referenced through PRPs or SGLs
* PRP list pages and SGL descriptor chains
* Submission Queue Entries for administrative and I/O queues
* Completion Queue Entries for administrative and I/O queues
* the memory pages containing ASQ, ACQ, I/O Submission Queues, and I/O Completion Queues

For CPU resident drivers this is straightforward because DRAM is inherently DMA
visible. For accelerator resident drivers, device memory may not be reachable
unless the accelerator supports mechanisms to export physical addresses or to
reference memory through pretranslated I/O mappings. Some accelerators depend on
ATS or similar services, while others cannot provide DMA visible memory at all.

If any memory region referenced by DPTR, PRP lists, SGL descriptors, SQEs, or
CQEs is not DMA visible, the command may be submitted but will not complete
successfully.

Ensuring DMA visibility for these structures is therefore a core requirement for
any I/O path in AiSIO. This requirement influences driver design, queue
placement, payload construction, and the feasibility of fast paths in systems
that combine CPUs with GPUs, DPUs, and other accelerators.

(sec-nomenclature)=
## Nomenclature

**Control path** refers to coordination and metadata operations rather than
bulk data movement.

**Data path** refers to the movement of payload data through DMA engines or peer
to peer transfers.

**Fast path** refers to the minimal sequence of operations needed to move data
efficiently.

In AiSIO, these concepts determine which processing unit performs coordination
and which performs data movement in each I/O flow.

## Transition to Architecture

The components described in this background outline the constraints, mechanisms,
and responsibilities that define how storage I/O operates in contemporary
systems. They also highlight the hardware and software limitations that prevent
accelerators from participating directly in data movement.

The next section builds on this foundation by presenting the AiSIO architecture,
which unifies these elements into a multipath design that enables CPUs, GPUs,
xPUs, and other accelerators to cooperate efficiently as peers in the storage
system.
