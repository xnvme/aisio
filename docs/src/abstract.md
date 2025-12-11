(sec-abstract)=
# Abstract

Accelerator-integrated Storage I/O (AiSIO) refers to a class of system
designs that elevate accelerators such as GPUs, inference accelerators, and
fixed-function units to first-class citizens within the storage stack, enabling
them to participate directly in data movement or initiate I/O themselves, while
preserving compatibility and interoperability with existing operating-system
storage abstractions such as files and file systems.

Modern accelerators provide massive parallelism and high bandwidth memory,
yet their ability to access storage remains limited by CPU centered I/O paths
and by proprietary driver stacks that are difficult to extend or integrate
with operating system infrastructure. As I/O demand continues to grow, these
constraints lead to persistent underutilization of both compute and storage
hardware.

AiSIO addresses this problem through an integrated multipath architecture that
combines conventional OS managed I/O with efficient accelerator resident paths
based on peer to peer transfers, accelerator local queues, and cooperative
control flows. Host-orchestrated Multipath I/O (HOMI) provides a reference
architecture and implementation of this class. HOMI enables accelerators to
retrieve data directly from NVMe devices even when that data resides in file
systems implemented in the operating system kernel, and it does so without
requiring any modification to these file systems.

We present HOMI as a proof of concept implementation that demonstrates how
AiSIO can be realized in open and modifiable system software. We also provide
an experimental evaluation showing that HOMI significantly improves hardware
utilization compared to existing CPU centered and proprietary solutions.
