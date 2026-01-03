(sec-abstract)=
# Abstract

Accelerator-integrated Storage I/O (AiSIO) refers to a class of system software
architectures that elevate accelerators such as GPUs, inference accelerators,
and fixed-function units to first-class participants in the storage stack,
enabling them to participate directly in data movement or initiate I/O
themselves, while preserving compatibility and interoperability with existing
operating-system managed storage abstractions such as files and file systems.

Modern accelerators provide massive parallelism and high-bandwidth local memory,
yet their ability to access storage remains constrained by CPU-centered I/O
paths and opaque, proprietary driver stacks that are difficult to extend or
integrate with operating system infrastructure. As I/O demand continues to
grow, these constraints lead to persistent underutilization of both compute and
storage hardware.

AiSIO addresses these limitations through a structured separation between
host-resident control-plane responsibilities and high-bandwidth data-path
execution. The operating system retains authority over device management,
metadata handling, and policy enforcement, while accelerators participate
directly in data-path execution using mechanisms such as peer-to-peer DMA
and accelerator-accessible I/O queues. This separation allows accelerators to
initiate and drive I/O without undermining file-system semantics, safety, or
interoperability.

Host Orchestrated Multipath I/O (HOMI) serves as a reference implementation
of these principles. HOMI explores how OS-managed, user-space managed, and
device-initiated I/O paths can be orchestrated to coexist with shared access
to the same NVMe controller, either through software-mediated multiplexing
or hardware-assisted delegation. A host-resident control plane coordinates
device initialization, queue provisioning, and file-extent metadata, enabling
accelerators to access file-backed data without requiring modifications to
existing file systems.

This work presents HOMI as an experimental platform for studying
accelerator-integrated storage I/O in open and modifiable system software.
Through its design and evaluation, it demonstrates the feasibility of
cooperative multipath I/O architectures that improve hardware utilization while
preserving the guarantees and abstractions provided by operating-system managed
storage.
