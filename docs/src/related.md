(sec-related-work)=
# Related Work

A range of systems seek to reduce CPU involvement in accelerator data access,
each making different trade-offs between performance, programmability,
and interoperability. Broadly, prior work can be categorized by whether it
accelerates the data path while preserving CPU-initiated control, reassigns
I/O initiation and scheduling to accelerators through exclusive ownership, or
restructures file system services around accelerator execution models.

**GPUDirect Storage (GDS)** integrates peer-to-peer DMA into the
operating-system I/O stack to eliminate redundant host memory copies across
a range of storage backends, including locally attached NVMe devices,
RDMA-accessible remote storage, and distributed and parallel file systems
{cite}`nvidia-gds`. While this substantially improves data movement efficiency
and broadens GPU access to diverse storage infrastructures, all I/O remains
CPU-initiated and CPU-orchestrated, including request scheduling, metadata
processing, and error handling. GDS therefore accelerates the data path without
altering the initiator or control model of storage I/O.

**Big Accelerator Memory (BaM)** takes the opposite approach by enabling
GPU-initiated access to NVMe through exclusive device ownership and a custom
driver and metadata stack, allowing accelerators to both schedule and execute
I/O directly {cite}`bam2023,torp2025gpu_initiated_io`. This design achieves
near–line-rate performance by removing kernel and OS involvement from the
fast path, but does so by abandoning file systems, POSIX semantics, and
interoperability with OS-managed storage.

**uGDS** re-exposes this user-space, GPU-direct lineage behind an interface
that mirrors a subset of NVIDIA's cuFile/GDS API {cite}`ugds`. It builds on
the user-space NVMe and peer-to-peer DMA mechanisms established by BaM and
its antecedents, but, unlike BaM, retains a CPU-initiated control model: the
host constructs and submits NVMe commands and polls for completions, while
data is DMA'd directly between the SSD and GPU memory. It thus inherits BaM's
data-path mechanism without its GPU-initiated control model, placing its
initiator and scheduling model closer to GDS, and presents a GDS-style API
intended as a drop-in replacement for existing GDS applications. In practice
the interface operates only on raw block devices and provides no file system,
file, or path support, and no integration with OS-managed storage; its
compatibility is therefore confined to matching call signatures rather than
file-level semantics. The drop-in claim consequently holds only in the narrow
case of block-device access without file-system interoperability, and, as in
BaM, the short user-space fast path is obtained by forgoing POSIX semantics
and OS-managed storage abstractions.

**GeminiFS** introduces a GPU-centric companion file system that integrates
GPU execution with file system metadata operations through a custom kernel
module and modified on-disk formats {cite}`geminifs2025`. By coupling metadata
management closely to GPU execution, GeminiFS reduces CPU involvement in both
control and data paths, but does so by requiring changes to file system layout
and kernel infrastructure, limiting compatibility with existing Linux file
systems.

**GoFS** reorganizes file system metadata management and I/O services
around accelerator execution models, exposing file system functionality
through a specialized runtime rather than the conventional kernel storage
stack {cite}`gofs2025`. While this design aligns storage services with
accelerator-centric execution, it departs from OS-managed coordination and
does not interoperate with unmodified on-disk file system formats or kernel
semantics.

Accelerator-integrated Storage I/O (**AiSIO**) {cite}`aisio-fms2025,aisio-ocp2025`
differs from these approaches, and from the systems evaluated in prior work
{cite}`torp2025gpu_initiated_io`,
by preserving existing file system formats and Linux kernel semantics while
enabling both CPU-initiated and device-initiated I/O paths to coexist under
host orchestration. The Host-Orchestrated Multipath I/O (**HOMI**) reference
implementation demonstrates how accelerators can initiate and drive storage
I/O without assuming exclusive device ownership or undermining operating-system
managed storage abstractions.
