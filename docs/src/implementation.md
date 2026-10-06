<!--
SPDX-FileCopyrightText: Samsung Electronics Co., Ltd

SPDX-License-Identifier: BSD-3-Clause
-->

# Implementation

This section first describes the earlier proof-of-concept (PoC)
implementation, built on libnvm in its BaM-modified form, and then the current
implementation, including the Host-Orchestrated Multipath I/O (HOMI) reference
implementation.

## Proof-of-Concept Implementation

The PoC consisted of a set of functional software components that demonstrated
key aspects of accelerator-integrated storage I/O. These components were used
to validate feasibility, explore performance characteristics, and exercise
device-initiated I/O paths under controlled conditions.

```{figure} _static/aisio_overview_poc.drawio.png
:alt: Overview of the initial AiSIO PoC
:width: 700px
:align: center

Overview of the initial AiSIO PoC
```

The **AiSIO** PoC demonstrated functionality on Linux systems using:

- xNVMe for NVMe command construction and submission across both CPU-initiated
  and GPU-initiated I/O paths, including invocation directly from CUDA kernels,
  using libnvm {cite}`Markussen2021` in its BaM-modified form {cite}`bam2023`
  as the underlying PCIe access library.
- The NVIDIA GPU driver and its peer-to-peer memory interface for direct DMA
  between the NVMe controller and GPU device memory.
- The XAL metadata decoder for XFS.
- The SIL: Storage Iterator Library (now called FIL: File Iterator Library),
  a benchmark application that iterated over file-based datasets using XAL
  for extent resolution and exercised both CPU and GPU I/O paths.

The PoC is open-source, interoperates with unmodified XFS, and is reproducible
from the ``poc`` tag.

The PoC relied on hardware-assisted delegation using NVMe Single Root
I/O Virtualization (SR-IOV). NVMe Virtual Functions (VFs) were provisioned and
assigned statically to initiators. A single host-resident process performed
device initialization, queue provisioning, metadata handling, and I/O
submission. In this configuration, control-plane and data-path responsibilities
were co-located, and no separate persistent host-resident control-plane daemon
was present.

Accelerator access in the PoC was realized by assigning an NVMe Virtual Function
directly to the accelerator, enabling device-initiated I/O through
hardware-isolated queues. This allowed multiple initiators to access shared
namespaces concurrently, but did not exercise dynamic queue management or
centralized host orchestration.

The PoC included early implementations of several HOMI-related components, such
as user space NVMe driver extensions, accelerator-accessible I/O queue
provisioning, and file system extent extraction used to support file-backed
accelerator access. These components were functional but were composed in a
reduced form suitable for experimentation rather than as a complete system.

## Current Implementation

Where the PoC depended on libnvm and on NVIDIA's peer-to-peer memory interface,
the current implementation reaches the NVMe controller through uPCIe and GPU
device memory through dma-buf, neither of which is specific to NVIDIA hardware.
It is built from:

- xNVMe with its uPCIe backends, for NVMe command construction and submission
  across both CPU-initiated and GPU-initiated I/O paths.
- The dma-buf importer released by uPCIe, which resolves the physical addresses
  of GPU device memory.
- XAL, for file-to-block extent resolution.
- FIL, whose ``aisio-cpu``, ``aisio-p2p``, and ``aisio-gpu`` backends exercise
  CPU-initiated I/O into host memory, CPU-initiated P2P I/O, and GPU-initiated
  I/O.

The following subsections describe uPCIe, the dma-buf import mechanism,
device-initiated benchmarking in xnvmeperf, and HOMI.

### uPCIe

uPCIe is a collection of header-only C libraries for building user space PCIe
device drivers. It provides composable, zero-dependency abstractions that cover
PCIe device discovery and BAR mapping, DMA-capable memory allocation, and a
minimalistic NVMe driver built directly on top of these primitives.

AiSIO uses uPCIe as its user space NVMe driver. Being header-only, uPCIe
integrates directly into xNVMe — where it is available as a backend
for user space NVMe access, as described in the [xNVMe uPCIe backend
documentation](https://xnvme.io/en/next/background/backends/upcie/index.html) —
which in turn is the NVMe layer used throughout AiSIO, HOMI included.

uPCIe includes an optional GPU integration layer that adds CUDA-backed memory
management. This enables two distinct I/O modes. In the **CPU-initiated P2P
mode**, the CPU submits NVMe commands while data buffers reside in GPU device
memory, with data transferred between the NVMe controller and GPU device memory
via peer-to-peer PCIe DMA. In the **device-initiated mode**, CUDA kernels submit
and complete NVMe commands directly, without any CPU involvement.

For device-initiated I/O, ``xnvme_cuda_queue_create()`` allocates a GPU-resident
NVMe queue pair in CUDA device memory using ``cuMemAlloc``. The queue pair
structure holds virtual-address pointers to the submission queue (SQ) and
completion queue (CQ) — allocated from the GPU's DMA-capable heap — along with
a mapping of the NVMe doorbell registers from PCIe BAR0 into the GPU's address
space. It also tracks the SQ tail, CQ head, phase bit, and a clock-based timeout
derived from the GPU's SM clock rate.

CUDA kernels call ``xnvme_cuda_cmd_io()`` collectively across all threads
in a block, with the block size equal to the queue depth. A batch size sets how
many threads take part in a round. The remaining threads join the barriers
without submitting, which allows rounds with fewer commands than the queue
holds. The flow proceeds in six stages:

1. Each active thread enqueues its NVMe command into the SQ using word-by-word
   volatile pointer writes, bypassing the per-SM L1 cache so writes reach
   system DRAM and become visible to the NVMe DMA engine without waiting for
   cache eviction.
2. A ``__syncthreads()`` barrier ensures all commands are written before the
   doorbell is rung.
3. Thread 0 issues a ``__threadfence_system()`` fence and writes the updated SQ
   tail to the MMIO doorbell register, triggering the controller to fetch and
   execute the queued commands.
4. Each active thread polls its CQ entry using the phase bit to detect
   completion, with timeout tracked in GPU clock cycles.
5. A second barrier ensures all completions are reaped.
6. Thread 0 advances the CQ head, flipping the phase bit on wrap, and writes it
   to the CQ doorbell register.

The barriers are what make a block that spans several warps safe. Without them,
thread 0 could ring the SQ doorbell before other warps have written their
commands, or advance the CQ head before they have reaped.

Both modes rely on the NVMe command's Physical Region Page (PRP) list containing
the physical addresses of the data buffer. Obtaining these from CUDA device
memory is nontrivial, and is the subject of the following section.

### Device Memory Physical Address Resolution via dma-buf Import

The challenge is that device memory resides in device-local DRAM exposed to the
host through a PCIe Base Address Register (BAR1) aperture, and there is no
standard Linux kernel interface for retrieving its physical mappings from user
space. This has been addressed with an out-of-tree kernel module, the dma-buf
importer released by [uPCIe](https://github.com/safl/upcie). The module serves
three ioctl operations on its own ``/dev/dmabuf_import`` character device:
``DMABUF_IMPORT_ATTACH``, ``DMABUF_IMPORT_GET_MAP``, and
``DMABUF_IMPORT_DETACH``. These allow any exported dma-buf file descriptor to
be imported. The driver then performs the DMA mappings internally and returns
the resulting physical address array to the calling process. The mechanism is
not specific to CUDA or NVIDIA hardware; it works with any dma-buf exporter.
Being self-contained, it is delivered as a DKMS package that builds against the
distribution kernel and rebuilds itself on kernel updates.

For CUDA device memory, the flow is as follows. A CUDA-backed heap is initialized
by allocating device memory with ``cuMemAlloc``, then exporting it as a
dma-buf file descriptor via ``cuMemGetHandleForAddressRange`` with the
``CU_MEM_RANGE_HANDLE_TYPE_DMA_BUF_FD`` handle type. This file descriptor
is passed to the ``dmabuf_import_attach`` wrapper in the uPCIe library, which
opens ``/dev/dmabuf_import`` and issues ``DMABUF_IMPORT_ATTACH`` to obtain the
page count, followed by ``DMABUF_IMPORT_GET_MAP`` to retrieve an array of
``(dma_addr, len)`` tuples. These are indexed into a lookup table (LUT) keyed at
64 KiB granularity, the native page size for NVIDIA GPU device memory, enabling
runtime translation from any device memory virtual address to the corresponding
physical address.

### xnvmeperf Device-Initiated Benchmarking

xnvmeperf integrates device-initiated I/O through its ``cuda-run`` subcommand.
The host allocates GPU-resident NVMe queue pairs and DMA buffers in CUDA device
memory, builds NVMe commands with PRP lists populated from physical addresses
resolved via the dma-buf import mechanism described above, and uploads the
commands to the GPU. CUDA kernels then execute in a tight loop: one block per
queue, one thread per queue slot, submitting and completing I/O continuously
without returning to the CPU between rounds. A host-mapped flag signals the
kernels to stop after the configured runtime, at which point per-queue round
counts are read back and used to compute throughput. Sequential and random
access patterns are supported through separate kernel implementations; the
random kernel uses a per-thread linear congruential generator seeded from the
host to produce independent LBA sequences without shared-memory coordination.

### HOMI

HOMI realizes the control plane of the architecture described in Section
{ref}`sec-architecture`, enabling OS-managed, user space managed, and
device-initiated I/O paths to share an NVMe controller. It ships as the
``homi`` tool in xNVMe, a persistent host-resident process that owns the
controller state and DMA memory, and to which the processes doing I/O attach.
Each attached process creates and tears down its own I/O queue pairs at
runtime, so queue resources are provisioned dynamically across initiators.

Information about running HOMI is found in the [xNVMe homi
documentation](https://xnvme.io/tools/homi/index.html).
