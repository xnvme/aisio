# Proof-of-Concept Implementation

The **AiSIO** PoC demonstrates functionality on Linux systems using:

- A ublk-based cooperative block driver that integrates with SPDK.
- A modified SPDK NVMe driver with queue partitioning for accelerator access.
- GPU-resident NVMe I/O drivers implemented for accelerator execution.
- The XAL metadata decoder for XFS.
- CUDA-based integration for invoking AiSIO operations directly from kernels.

The PoC is open-source, reproducible, and interoperates with unmodified XFS.
