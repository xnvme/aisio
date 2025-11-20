(sec-introduction)=
# Introduction

Few developments today influence system architecture as immediately and
pervasively as AI, although quantum computing is poised to introduce
transformative long-term changes of its own. While quantum systems remain
specialized and emerging, AI workloads are already reshaping how compute,
memory, and storage architectures evolve. AiSIO arises directly from the need to
integrate accelerators into the I/O path in a coherent and interoperable way, so
that data movement and storage access can keep pace with modern workloads.

The need for such integration becomes clear when considering how accelerator
hardware has advanced, yet systems still rely on CPU centered I O paths. This
is not only a hardware limitation. It reflects poor utilization caused by weak
integration of accelerators into operating system infrastructure. Proprietary
drivers, runtimes, and programming models keep accelerators outside the
mechanisms that the operating system uses to manage memory and coordinate I/O.

I/O demand now grows faster than accelerator vendors can adapt their proprietary
stacks, and closed ecosystems prevent users from addressing bottlenecks or
extending functionality. As a result, data continues to pass through host
memory and CPU controlled paths even when accelerators are capable of direct
and efficient access to storage. This leads to persistent underutilization of
compute and storage. Open and modifiable system software is becoming essential
for achieving full hardware utilization and for building architectures that can
evolve with emerging workloads.

A parallel evolution is required within the operating system. OS storage stacks,
drivers, and abstractions were built around long standing principles such as
file system semantics, block device interfaces, security, metadata management,
and uniform access to hardware. These abstractions remain indispensable. Yet
emerging workloads increasingly require mechanisms that allow accelerators to
access storage directly through peer to peer transfers, accelerator resident
queues, and heterogeneous control flows, while still supporting conventional OS
managed paths. The operating system must therefore provide robust abstractions
alongside efficient bypass mechanisms, enabling flexibility without compromising
correctness, safety, or interoperability.

AiSIO denotes a class of system designs built around an integrated multipath
philosophy that treats accelerators as first class participants in the
storage subsystem. In this model, the CPU retains essential system management
responsibilities, accelerators can participate directly in data movement, and
the operating system coordinates both long standing abstractions and efficient
bypass mechanisms.

This unified and hybrid approach is essential for constructing scalable and
efficient systems in the AI era. It enables designs that do not rely on a single
I/O paradigm but instead combine the strengths of diverse processing units,
memory tiers, and software layers.
