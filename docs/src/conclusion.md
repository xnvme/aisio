(sec-conclusion)=
# Conclusion

This work introduced AiSIO as a class of system software architectures and HOMI
as a reference architecture within it, and presented a reference implementation.
The experimental evaluation to date covers five synthetic benchmark studies in a
single hardware environment, structured to characterize the resource efficiency
of the uPCIe and uPCIe-cuda data paths from the ground up.

The {ref}`sec-experiments-cpu-initiated` experiment established a ceiling of
approximately 61.7 million IOPS across 16 NVMe devices, requiring 8 physical cores
running at full utilization under busy-polling, with performance scaling linearly
with both device count and core count. This serves as the roofline and CPU cost
reference against which the subsequent experiments are compared.

The {ref}`sec-experiments-tool-comparison` experiment showed that successive
layers of the SPDK stack each impose measurable overhead, and that replacing the
SPDK driver with the leaner uPCIe driver yields approximately 2.5 times the IOPS
when the benchmark tool and xNVMe abstraction layer are held constant. More
significantly, the uPCIe path reaches the device IOPS roofline with only three CPU
threads, fewer than half the cores required by the SPDK baseline. Routing the
data path through P2P DMA to GPU device memory via upcie-cuda does not measurably
affect command throughput, validating a core assumption of the AiSIO design.

The {ref}`sec-experiments-pcie-bandwidth` experiment showed that a single CPU
thread driving four NVMe devices is sufficient to saturate the PCIe Gen5 x16 link
at I/O sizes of 4 KiB and above, pushing total PCIe traffic to approximately
57.8 GB/s and reaching approximately 90% of the line rate. Protocol overhead
accounts for a consistent 28% above payload bandwidth across all tested I/O sizes
and operating regimes, indicating it scales with bytes transferred rather than
operation count.

The device-initiated experiments examined how GPU threads can drive NVMe I/O
directly. The {ref}`sec-experiments-cuda-iosize` experiment showed that the
thread count required to saturate the PCIe link decreases monotonically with
I/O size: at 64 KiB just 32 CUDA threads across 16 devices suffice, while at
512 bytes the constraint shifts to device IOPS rather than link capacity. The
{ref}`sec-experiments-cuda-qdepth` experiment showed that a single queue per
device cannot reach the device IOPS roofline regardless of queue depth, and that
adding a second queue breaks this ceiling. With 4096 total CUDA threads, the
61.7 million IOPS roofline is reached under 512-byte device-initiated I/O, and
additional queues beyond four per device add thread count without further gain.

Taken together, these results demonstrate that eliminating software abstraction
layers from the I/O path enables full hardware utilization with a fraction of the
CPU resources required by conventional approaches, and that the P2P data path to
GPU memory can be saturated with similarly modest resource requirements under both
CPU-initiated and device-initiated I/O.

Several parts of the plan remain open. File-based benchmarks comparing the
AiSIO uPCIe path against GDS and POSIX have not yet been run. The HOMI PoC
covers the SR-IOV multipath configuration and device-initiated I/O; the
ublk-based software-mediated path and the host-resident control-plane daemon
are not yet complete. The work required to address these is described in the
following chapter.
