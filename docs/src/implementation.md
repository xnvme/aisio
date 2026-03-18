# Implementation

This section distinguishes between the existing proof-of-concept (PoC)
implementations used for evaluation and experimentation, and the ongoing work
toward a full Host-Orchestrated Multipath I/O (HOMI) reference implementation.
The PoC represents a concrete, functional subset of the overall design, while
HOMI defines the target system architecture that is currently under active
development.

## Proof-of-Concept Implementation

The current PoC consists of a set of functional software components that
demonstrate key aspects of accelerator-integrated storage I/O. These components
are used to validate feasibility, explore performance characteristics, and
exercise device-initiated I/O paths under controlled conditions.

```{figure} _static/aisio_overview_poc.drawio.png
:alt: Overview of the initial AiSIO PoC
:width: 700px
:align: center

Overview of the initial AiSIO PoC
```

The **AiSIO** PoC demonstrates functionality on Linux systems using:

- A ublk-based cooperative block driver that integrates with SPDK.
- A modified SPDK NVMe driver with queue partitioning for accelerator access.
- GPU-resident NVMe I/O drivers implemented for accelerator execution.
- The XAL metadata decoder for XFS.
- CUDA-based integration for invoking AiSIO operations directly from kernels.

The PoC is open-source, reproducible, and interoperates with unmodified XFS.

The PoC relies primarily on hardware-assisted delegation using NVMe Single Root
I/O Virtualization (SR-IOV). NVMe Virtual Functions (VFs) are provisioned and
assigned statically to initiators. A single host-resident process performs device
initialization, queue provisioning, metadata handling, and I/O submission. In
this configuration, control-plane and data-path responsibilities are co-located,
and no separate persistent host-resident control-plane daemon is present.

Accelerator access in the PoC is realized by assigning an NVMe Virtual Function
directly to the accelerator, enabling device-initiated I/O through
hardware-isolated queues. This allows multiple initiators to access shared
namespaces concurrently, but does not yet exercise dynamic queue management or
centralized host orchestration.

The PoC includes early implementations of several HOMI-related components, such
as user space NVMe driver extensions, accelerator-accessible I/O queue
provisioning, and file system extent extraction used to support file-backed
accelerator access. These components are functional but are composed in a
reduced form suitable for experimentation rather than as a complete system.

## HOMI Reference Implementation (Work in Progress)

The HOMI reference implementation represents the intended realization of the
architecture described in Section {ref}`sec-architecture`. It extends beyond
the current PoC by introducing a host-resident orchestration layer responsible
for global coordination across OS-managed, user space managed, and
device-initiated I/O paths.

Key elements of the HOMI reference implementation that are under development
include a persistent host-resident control-plane daemon, dynamic provisioning
and assignment of NVMe queue resources across initiators, centralized caching of
file-to-block mappings, and coordinated lifecycle and policy management spanning
all I/O paths. Unlike the PoC, the reference implementation is designed to
support both software-mediated and hardware-assisted multipath configurations
within a unified orchestration framework.

The reference implementation is intended to serve as a stable and extensible
platform for exploring host-orchestrated multipath I/O, rather than as a
production-ready storage system. Development is ongoing, and future work
focuses on incrementally integrating existing PoC components into this broader
HOMI framework.

Information about building, installing and managing HOMI is found in the README
file in the ``homi`` directory of the AiSIO reference implementation.
