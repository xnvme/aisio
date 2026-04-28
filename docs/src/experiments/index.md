# Experiments

This section presents the experiments conducted to evaluate AiSIO.
The experiments are structured to build on each other. The first establishes the
CPU-initiated IOPS ceiling and the optimal system configuration. The second
quantifies the software abstraction overhead at each layer of the CPU-initiated
I/O stack and shows how much of that overhead the uPCIe path eliminates. The
third identifies where the I/O size crosses from IOPS-bound to bandwidth-bound
operation. The final two examine device-initiated I/O, first varying I/O size to
find the saturation boundary, then varying queue depth and queue count to find
the combination that reaches device saturation.

```{toctree}
:maxdepth: 1
cpu_initiated
tool_comparison
pcie_saturation
device_initiated_iosize
device_initiated_qdepth
```
