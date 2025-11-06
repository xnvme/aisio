aisio: Accelerator-initiated Storage I/O
========================================

This repository provides documentation, tools, and scripts for setting up and
exploring the Accelerator-initiated Storage I/O Proof-of-Concept.

In the following, then it is assumed that ``transport.toml`` has the connection
info to a freshly installed Ubuntu 24.04. With that in place, then you can use
**cijoe** as below.

Installation of the NVIDIA Software Stack on top of Ubuntu 24.04.3::

	pipx run cijoe \
		--monitor \
		-c configs/transport.toml \
		-c configs/nvstack.toml \
		tasks/setup_nvstack.yaml

Then install the AiSIO components::

	pipx run cijoe \
		--monitor \
		-c configs/transport.toml \
		-c configs/aisio.toml \
		tasks/setup_aisio.yaml

You can now go ahead and familiarize yourself, with the code-base, and adjust as
you see fit. To run benchmarks, then do::

	pipx run cijoe \
		--monitor \
		-c configs/transport.toml
		tasks/benchmark.yaml

Prerequisites
-------------

**cijoe** is a tool for introducing reproducibility to systems development and
testing. You can use it, without installing it, by running it via ``pipx`` or
``uv`` as above, or install it like ``pipx install cijoe``.
