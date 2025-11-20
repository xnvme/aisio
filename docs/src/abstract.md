(sec-abstract)=
# Abstract

AiSIO denotes a class of system designs that enable accelerator integrated
storage I/O, allowing GPUs and other accelerators to participate directly in
data movement while preserving full compatibility with existing operating system
abstractions.

Modern accelerators provide massive parallelism and high bandwidth memory,
yet their ability to access storage remains limited by CPU centered I/O paths
and by proprietary driver stacks that are difficult to extend or integrate
with operating system infrastructure. As I/O demand continues to grow, these
constraints lead to persistent underutilization of both compute and storage
hardware.

AiSIO addresses this problem through an integrated multipath architecture that
combines conventional OS managed I/O with efficient accelerator resident paths
based on peer to peer transfers, accelerator local queues, and cooperative
control flows. This approach enables accelerators to retrieve data directly
from NVMe devices even when data is stored in file-systems implemented in the
operating system kernel, and without modification to these.

We present a proof of concept implementation that demonstrates how such a
design can be realized in open and modifiable system software, and we provide
an experimental evaluation that shows significant improvements in hardware
utilization compared to existing CPU centered and proprietary solutions.
