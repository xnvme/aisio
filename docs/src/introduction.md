(sec-introduction)=

# Introduction

Few developments are reshaping system architecture as rapidly and decisively
as artificial intelligence. Unprecedented investment in AI infrastructure, the
emergence of large-scale AI factories, and the pace of research in training,
inference, and data-intensive models are collectively redefining requirements
for compute, memory, and storage systems. AiSIO arises directly from the need to
integrate accelerators into the I/O path in a coherent and interoperable way, so
that data movement and storage access can keep pace with modern workloads.

The need for such integration becomes clear when considering how accelerator
capabilities have advanced while their interaction with storage remains largely
mediated through conventional host-driven interfaces. This is not a failure of
CPU-centered I/O paths, which continue to provide essential guarantees around
correctness, sharing, and interoperability, but a reflection of integration
models that were not designed for accelerators capable of issuing and sustaining
I/O at massive scale. Proprietary drivers, closed runtimes, and narrowly scoped
programming models often place accelerators outside the mechanisms the operating
system uses to coordinate memory, devices, and storage access.

As I/O demand continues to grow, these integration boundaries increasingly
manifest as inefficiencies rather than hard limitations. Data is frequently
routed through host memory and CPU-managed paths even when accelerators are
capable of participating directly in data movement or initiating I/O themselves.
This leads to persistent underutilization of compute and storage resources, not
because existing operating-system abstractions are flawed, but because they lack
structured mechanisms for safely incorporating accelerators into the storage
subsystem.

A parallel evolution is therefore required within system software. Operating
system storage stacks, drivers, and abstractions were built around long-standing
principles such as file system semantics, block-device interfaces, protection,
metadata management, and uniform access to hardware. These principles remain
indispensable. At the same time, emerging workloads motivate additional paths
that allow accelerators to access storage more directly, through peer-to-peer
transfers, accelerator-accessible queues, and heterogeneous control flows, while
continuing to coexist with conventional OS-managed I/O.

Accelerator-integrated Storage I/O (AiSIO) designates a class of system
software architectures built around this cooperative multipath philosophy. In
AiSIO systems, the CPU and operating system retain responsibility for global
coordination, device management, metadata handling, and policy enforcement.
Accelerators, in turn, are elevated to first-class participants in the storage
subsystem, able to contribute to data-path execution or initiate I/O under
host coordination. This approach enables high-performance access paths without
abandoning existing file systems, applications, or operating-system managed
storage abstractions.

This unified and hybrid model is essential for constructing scalable and
efficient systems in the AI era. Rather than relying on a single I/O paradigm,
AiSIO architectures combine the strengths of diverse processing units, memory
tiers, and software layers within a single system. Host Orchestrated Multipath
I/O (HOMI) serves as a reference architecture and implementation within the
AiSIO class. HOMI demonstrates how these principles can be realized in open and
modifiable system software, enabling multiple I/O paths to coexist with shared
access to storage resources while preserving operating-system semantics.
