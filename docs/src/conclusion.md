(sec-conclusion)=
# Conclusion

This work introduced AiSIO as a class of system software architectures and HOMI
as a reference architecture within it, and presented a proof-of-concept
implementation. The experimental evaluation to date covers two synthetic
benchmark studies in a single hardware environment.

The CPU-initiated benchmark showed that approximately 62 million IOPS across 16
NVMe devices is achievable with SPDK bdevperf using only 8 physical cores, with
performance scaling linearly with both device count and core count. The NVMe
driver comparison showed that the **upcie** backend reaches approximately 2.5
times the IOPS of the **spdk** backend when the benchmark tool and xNVMe
abstraction layer are held constant, consistent with uPCIe's leaner command
path. A comparison of the **upcie** and **upcie-cuda** backends further showed
that routing the data path through P2P DMA to GPU device memory does not
measurably affect command submission throughput in this synthetic workload.

Several parts of the plan remain open. File-based benchmarks comparing the
AiSIO uPCIe path against GDS and POSIX have not yet been run. The HOMI PoC
covers the SR-IOV multipath configuration; the ublk-based software-mediated
path, the host-resident control-plane daemon, and device-initiated I/O paths
are not yet complete. The work required to address these is described in the
following chapter.
