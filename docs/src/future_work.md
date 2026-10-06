<!--
SPDX-FileCopyrightText: Samsung Electronics Co., Ltd

SPDX-License-Identifier: BSD-3-Clause
-->

# Future Work

The work presented here is limited in scope to locally-attached NVMe storage,
leaving remote and disaggregated storage as an open direction. The following
sections describe the most significant areas of future work along this
dimension and others.

## Kernel Integration and Upstream Components

The dma-buf importer, which imports arbitrary dma-buf file descriptors and
exposes physical address mappings to user space, is currently maintained as an
out-of-tree kernel module. Upstreaming this interface, or contributing an
equivalent mechanism through a suitable kernel subsystem, would remove the
requirement to install and maintain it per system, and allow the user space
P2P path to be exercised on stock production systems.

The Linux kernel's io_uring and dma-buf integration for CPU-initiated P2P I/O
is under active development in mainline. As this path stabilizes, a direct
comparison between the kernel-managed and user space managed P2P architectures
described in Section {ref}`sec-architecture` becomes possible on identical
hardware — an evaluation that would clarify the performance and operational
trade-offs between the two approaches.

## Broader Accelerator Support

Device-initiated I/O is developed and validated against NVIDIA GPUs, using CUDA
for device memory allocation and dma-buf export. The I/O path itself is built on
xNVMe, uPCIe, and dma-buf, which operate on any dma-buf exporter, so it is not
NVIDIA-specific. AMD GPUs are supported for CPU-initiated P2P I/O through
xNVMe's ``upcie-hip`` backend, which allocates device memory with `hipMalloc`
and exports it as dma-buf with `hipMemGetHandleForAddressRange`.
Device-initiated I/O on AMD GPUs requires porting the device-resident NVMe
driver from CUDA to HIP.

## Multi-Accelerator Topologies

While multi-accelerator support is a goal of this work, only
single-accelerator configurations have been targeted so far. Achieving
multi-accelerator support requires accounting for PCIe topology effects on P2P
transfer latency and bandwidth, and managing concurrent access to shared
namespaces from multiple devices within the HOMI control plane.

## Remote Storage and RDMA

The current work is scoped to locally-attached NVMe storage. Extending AiSIO
to remote storage is an open direction, with two distinct approaches under
consideration. The first is NVMe-oF, carrying NVMe commands over
RDMA-capable transports such as RoCE or InfiniBand, which preserves the
block-level access model of the locally-attached case. The second is pNFS,
which exposes distributed storage while preserving file system semantics at
the protocol level. In both cases, the goal is to maintain the core
properties of the AiSIO architecture — P2P data movement directly into
accelerator memory and device-initiated I/O — while operating against remote
targets.

## Evaluating Device-Initiated Paths

Initial benchmarking of device-initiated I/O is in place: xnvmeperf's
``cuda-run`` subcommand drives NVMe I/O entirely from CUDA kernels, and I/O size
scaling and queue depth scaling experiments are complete. FIL's ``aisio-gpu``
backend carries device-initiated I/O to file-based workloads, where block
translation through XAL and the full AiSIO stack are exercised end-to-end. The
``bench_aisio`` workflow already runs it. The next step is an experiment that
reports performance on that path.
