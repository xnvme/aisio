# Related Work

A range of systems seek to reduce CPU involvement in GPU data access,
each making different trade-offs between performance, programmability, and
interoperability.

**GDS (GPUDirect Storage)** integrates peer-to-peer DMA into the OS I/O stack
and eliminates host copies, but the approach is strictly CPU-initiated and
remains limited by host-side scheduling overhead.

**BaM (Big Accelerator Memory)** provides GPU-initiated access to NVMe using a
custom driver and metadata structures, achieving high performance but abandoning
interoperability: it does not support file systems, requires custom array
metadata formats, and consumes significant GPU-memory capacity for outstanding
I/O.

**GeminiFS** proposes a GPU-centric companion file system requiring modified
on-disk metadata and a custom kernel module, offering tight metadata integration
but sacrificing compatibility with unmodified Linux file systems.

**GoFS** reorganizes metadata and I/O services around accelerator execution
models but requires specialized runtime infrastructure and does not interoperate
with existing on-disk file systems.

**AiSIO** differs by preserving existing file-system formats and Linux
kernel semantics while enabling both CPU-initiated and device-initiated
accelerator-integrated I/O.
