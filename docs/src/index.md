<!--
SPDX-FileCopyrightText: Samsung Electronics Co., Ltd

SPDX-License-Identifier: BSD-3-Clause
-->

# AiSIO Technical Report

```{note}
For more recent information while this report is being updated, see the
presentations of AiSIO, "AiSIO: Orchestrating Storage I/O Across CPUs and
Accelerators":

* SNIA SDC: StorageAI, Denver, April 2026,
  [slides](https://www.snia.org/sites/default/files/2026-04/SNIA-SDCAI26-Lund-AiSIO-Orchestrating-Storage-IO-r14.pdf)
* SNIA Storage Developer Conference (SDC) 2026, Santa Clara, September 2026,
  [session](https://www.snia.org/sniadeveloper/session/19744)
```

```{warning}
This report is outdated, about nine months behind, and is being reworked.
Since it was written, significant changes have made it into the software
ecosystem AiSIO builds on, and its experiments and integrations have evolved
with them. Read it with that in mind:

* The experiments do not exercise HOMI. Their results describe the I/O paths
  without the control plane the architecture is built around.
* The architecture diagrams and some names predate the current components.

The experiment that exercises the whole stack through HOMI today is
`tasks/bench_io_modes.yaml`, with `xnvmeperf` as the client, in four modes
taken in order: CPU-initiated I/O, CPU-initiated P2P I/O, accelerator-assisted
P2P I/O and accelerator-initiated P2P I/O, as {ref}`sec-terminology` defines
them. The README walks through running it.

Where the report and the repository disagree, the repository is right: the
task files in `tasks/` and the configurations in `configs/` are what runs.
Section {ref}`sec-future-report` lists the known shortcomings and what is
being done about them.
```

```{toctree}
:maxdepth: 3
self
abstract
introduction
background
architecture
related
implementation
environments
experimental_framework
experiments/index
conclusion
future_work
references
```
