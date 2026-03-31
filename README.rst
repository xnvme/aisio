aisio: Accelerator-integrated Storage I/O
=========================================

This repository provides documentation, tools, and scripts for setting up and
exploring the Accelerator-integrated Storage I/O Proof-of-Concept.

In the following, then it is assumed that ``transport.toml`` has the connection
info to a freshly installed Ubuntu 24.04 (for instructions see
``tasks/nvstack.toml``). With that in place, then you can use **cijoe** as below.

Note: add a minimal cijoe install description along with the transport change
needed.

Start by installing a **custom Linux Kernel** with support for UDMABUF import::

	cijoe --monitor \
      -c configs/transport.toml \
      -c configs/udmabuf_import.toml \
      tasks/setup_udmabuf_import.yaml

Then install the **NVIDIA** Software Stack::

	cijoe --monitor \
		-c configs/transport.toml \
		-c configs/nvstack.toml \
		tasks/setup_nvstack.yaml

Then setup **datasets** on the locally-attached NVMe storage, do take care hare
as this formats the NVMe device::

	cijoe --monitor \
		-c configs/transport.toml \
		-c configs/datasets.toml \
		tasks/setup_dataset.yaml

Then setup the **AiSIO** components (xNVMe, SPDK, xal, sil)::

	cijoe --monitor \
		-c configs/transport.toml \
		-c configs/aisio.toml \
		tasks/setup_aisio.yaml

You can now go ahead and familiarize yourself, with the code-base, and adjust as
you see fit. To run benchmarks, then do::

	cijoe --monitor \
		-c configs/transport.toml \
		-c configs/aisio.toml \
		-c configs/datasets.toml \
		tasks/bench_aisio.yaml

Prerequisites
-------------

**cijoe** is a tool for introducing reproducibility to systems development and
testing. You can use it, without installing it, by running it via ``pipx`` or
``uv`` as above, or install it like ``pipx install cijoe``.
