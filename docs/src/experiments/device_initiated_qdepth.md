<!--
SPDX-FileCopyrightText: Samsung Electronics Co., Ltd

SPDX-License-Identifier: BSD-3-Clause
-->

(sec-experiments-cuda-qdepth)=
# Device-initiated I/O: Queue Depth Scaling

The previous experiment showed that at 512-byte I/O the PCIe link cannot be
saturated regardless of thread count, and that the constraint is device IOPS,
which was established to be 61.7 M IOPS in the {ref}`sec-experiments-cpu-initiated` experiment.
This experiment holds I/O size fixed at 512 bytes and sweeps queue depth across
a wide range, with the number of queues per device as the secondary variable.
The aim is to identify the queue depth at which each queue-count configuration
saturates under device-initiated I/O.

**xnvmeperf** drives device-initiated I/O via the ``cuda-run`` subcommand
with the **upcie-cuda** backend. The subcommand distributes NVMe queues across
devices: with ``nqueues=N`` and 16 devices, each device is assigned N queue
pairs; each in-flight command is serviced by a dedicated CUDA thread. The total
thread count equals queue depth × ``nqueues`` × number of devices. Increasing
either dimension raises both the thread count and the number of commands in
flight. The experiment sweeps both dimensions to identify which combination
first reaches device saturation.

## Independent Variables

| Variable              | Parameter Set                                    |
| --------------------- | ------------------------------------------------ |
| Queue depth           | { 1, 2, 4, 8, 16, 32, 64, 128, 256, 512 }        |
| Number of queues      | { 1, 2, 4, 8, 16 }                               |
| I/O size              | 512                                              |
| Number of devices     | 16                                               |
| Tool and backend      | xnvmeperf (cuda-run) + upcie-cuda                |

## Metrics Collected

| Metric                                   | Reported by                              |
| ---------------------------------------- | ---------------------------------------- |
| Completed IOPS                           | xnvmeperf                                |
| SM activity (fraction of SMs occupied)   | DCGM field 1002 (SM_ACTIVE)              |
| Warp slot occupancy                      | DCGM field 1003 (SM_OCCUPANCY)           |
| GPU memory bandwidth utilization         | DCGM field 1005 (DRAM_ACTIVE)            |
| SM clock                                 | DCGM field 100 (SM_CLOCK)                |
| Run validity guards                      | DCGM fields 101/112/202/237/238          |

The DCGM fields are collected as described in {ref}`sec-dcgm-sampling`.

## Environment

The benchmarks were run on the {ref}`sec-env-hpc-server`. NVMe devices are bound
to user space drivers. The CPU governor is set to ``performance`` with turbo
boost and SMT enabled. Each configuration is run five times and results are
reported as arithmetic means.

The namespaces are formatted before the run, as described in
{ref}`sec-device-fill-state`.

## Execution of the Experiment

Instructions for running ``bench_cuda_qdepth.yaml`` are provided in
{ref}`sec-experimental-framework`.

(sec-experiments-cuda-qdepth-results)=
## Results

Results are presented as IOPS vs. queue depth, with one line per number of
queues (``nqueues`` ∈ { 1, 2, 4, 8, 16 }). All configurations use **xnvmeperf**
with the ``cuda-run`` subcommand and the **upcie-cuda** backend, 16 NVMe
devices, and 512-byte I/O.

```{figure} /lineplot-cuda-qdepth.png
:alt: IOPS vs. queue depth for xnvmeperf (cuda-run) with varying nqueues
:width: 700px
:align: center

IOPS vs. queue depth for xnvmeperf (cuda-run), 16 NVMe devices, 512 B I/O.
All nqueues ≥ 2 configurations reach the 61.7 M IOPS roofline at qdepth=128;
nqueues=1 reaches only 86.7% (53.5 M IOPS) at qdepth=512.
```

The results reveal a sharp divide between single-queue and multi-queue
operation. With ``nqueues=1``, IOPS scales sub-linearly with queue depth and
fails to saturate the devices even at ``qdepth=512`` (53.5 M IOPS, 86.7% of the
61.7 M roofline). All multi-queue configurations (``nqueues`` ≥ 2) saturate the
devices completely, converging to ~61.5 M IOPS with very low variance once the
threshold queue depth is reached. At ``qdepth=128``, ``nqueues=2`` delivers 61.5
M IOPS. This is a 45% gain over the 42.4 M achieved by ``nqueues=1`` at the same
depth. Further queue doublings yield no measurable improvement.

The minimum queue depth required to saturate the devices varies by ``nqueues``:

| ``nqueues`` | Min. ``qdepth`` to saturate | Total CUDA threads |
| ----------- | --------------------------- | ------------------ |
| 1           | > 512 (not reached)         | > 8192             |
| 2           | 128                         | 4096               |
| 4           | 64                          | 4096               |
| 8           | 64                          | 8192               |
| 16          | 64                          | 16384              |

Total CUDA thread count is ``qdepth × nqueues × ndevs`` (16 devices).
``nqueues=2`` and ``nqueues=4`` are equally thread-efficient, both saturating
the devices at 4096 total threads. ``nqueues=8`` and ``nqueues=16`` reach
the roofline at the same ``qdepth=64`` but require 2× and 4× as many threads
respectively for no throughput gain, making them suboptimal.

On thread count alone, ``nqueues=4`` with ``qdepth=64`` is as economical as
``nqueues=2`` with ``qdepth=128``, since both saturate the devices at 4096 total
threads and the former needs only half the per-queue depth, halving the number
of commands in flight per queue. Thread count is not the only cost, however, and
the activity results below separate the two.

### GPU Compute Cost of the Polling Kernel

Queue depth and queue count both move SM activity and warp slot occupancy, so
each field is charted across the whole grid, in the shape of the IOPS figure
above. A ring marks the shallowest depth at which each queue count reaches the
IOPS roofline, the depths tabulated above, so each figure carries the throughput
its costs are weighed against. Any depth beyond a ring costs more without adding
throughput.

```{figure} /lineplot-cuda-qdepth-sm.png
:alt: SM activity vs. queue depth for xnvmeperf (cuda-run) with varying nqueues
:width: 700px
:align: center

SM activity (DCGM field 1002) vs. queue depth for xnvmeperf (cuda-run), 16 NVMe
devices, 512 B I/O. Each queue count holds a flat line across the depth sweep
and the lines step up with the queue count, until ``nqueues=8`` and
``nqueues=16`` come to rest on one another near 96%. ``nqueues=1`` carries no
ring, since it never reaches the roofline at any depth. The number written on a
line is a single reading from it; the table below gives the mean across the
sweep.
```

```{figure} /lineplot-cuda-qdepth-occupancy.png
:alt: Warp slot occupancy vs. queue depth for xnvmeperf (cuda-run) with varying nqueues
:width: 700px
:align: center

Warp slot occupancy (DCGM field 1003) vs. queue depth for the same runs, on a
log axis. The lines are flat out to ``qdepth=32`` and then climb in step,
staying parallel. Each queue count that saturates the SSDs does so low on its
climb, so the depth beyond that point is spent on warp slots alone.
```

No DRAM activity sample exceeds 1.7%, so at this I/O size the data the SSDs read
into GPU memory places no meaningful load on it and neither figure is measuring
one.

Neither field follows the IOPS curve: what the polling kernel costs the GPU is
set by how it is laid out across the device, not by how much I/O it completes.

#### The Cost of a Queue

Queue depth leaves the multiprocessor footprint untouched, but the queue count
does not. SM activity holds the same value across the whole depth sweep at any
given ``nqueues`` and doubles with each doubling of the queue count:

| ``nqueues`` | Blocks (``nqueues × ndevs``) | SM active (depth-sweep mean) | IOPS at ``qdepth=128`` |
| ----------- | --------------------------- | ---------------------------- | ---------------------- |
| 1           | 16                          | 13.3%                        | 42.4 M                 |
| 2           | 32                          | 26.8%                        | 61.5 M                 |
| 4           | 64                          | 53.2%                        | 61.4 M                 |
| 8           | 128                         | 95.7%                        | 61.4 M                 |
| 16          | 256                         | 95.9%                        | 61.4 M                 |

The activity column is the mean of each line over all ten queue depths, and no
depth departs from its queue count's value by more than 1.7 percentage points.
The
IOPS column is quoted at ``qdepth=128``, where every multi-queue configuration
has reached the roofline.

This is the behaviour expected of one resident block per queue per device. Each
configuration places ``nqueues × ndevs`` blocks on the GPU, and for as long as
they fit on the multiprocessors available, each occupies one: the 16 blocks at
``nqueues=1`` measure just under the 14.0% that 16 of the 114 multiprocessors
would be, and the proportion holds through ``nqueues=4``. At ``nqueues=8`` the
128 blocks outnumber the 114 multiprocessors, so activity saturates near 96% and
the further doubling to 256 blocks adds nothing. The knee therefore falls where
``nqueues × ndevs`` passes the multiprocessor count, not at any queue count in
particular. With fewer multiprocessors on the GPU, or with more devices
attached, fewer queues would reach it.

#### The Cost of Queue Depth

Queue depth is not paid for in multiprocessors but in warp slots, and both the
flat part of the occupancy curve and the climb that follows come from one thread
per outstanding command and a warp of 32 threads. While the queue is no deeper
than a warp is wide, a block's commands fit within a single warp, so each of the
``nqueues × ndevs`` blocks holds one warp slot however deep its queue, which is
why the lines are flat out to ``qdepth=32``. Beyond it each doubling of the
depth doubles the warps a block needs, the constant step the lines rise in.

The lines stay parallel because queue depth and queue count enter the thread
count as equal factors. Against the 7296 warp slots this GPU holds, 64 on each
of its 114 multiprocessors, the span runs from 0.19% at a single queue and the
shallowest depths to 53.9% at ``nqueues=16``, ``qdepth=512``.

The two costs together price the saturating configuration. ``nqueues=2`` at
``qdepth=128`` drives the SSDs to the 61.7 M IOPS roofline while the polling
kernel holds **26.8% of the multiprocessors and 1.74% of the warp slots**. It is
present on a quarter of the device and takes almost none of the capacity of what
it sits on, so those multiprocessors stay open to another kernel being
co-resident on them. The polling loop therefore interferes by
presence rather than by exhaustion. A compute kernel sharing this GPU can still
be given warp slots almost anywhere, but from ``nqueues=8`` upward it shares
nearly every multiprocessor with a spinning poller. Depth becomes a
cost in its own right only at the top right of the occupancy figure, where it
reaches 26.9% and 53.9%, configurations that buy no throughput over
``nqueues=2`` to begin with.

This is what separates the two configurations the thread count left equivalent.
``nqueues=4`` with ``qdepth=64`` and ``nqueues=2`` with ``qdepth=128`` are
indistinguishable in warp slots, but the former holds half the multiprocessors
where the latter holds a quarter.

### Run Validity

The transferring share of the monitoring window varies more across this sweep
than any other, since setting up the queues takes longer the more of them there
are: at ``qdepth=512`` it falls from 75% at ``nqueues=1`` to 12% at
``nqueues=16``. Restricting the statistics to those samples is what keeps the
means from describing the setup instead of the workload.

The guard fields agree that the runs are comparable. The SM and memory clocks
hold at 1755 MHz and 1593 MHz with the throttle reason bits clear, the replay
counter stays at zero, and the link fields report Gen5 x16 throughout.

## Summary

A single queue per device cannot saturate the devices at 512-byte I/O regardless
of queue depth. Adding a second queue breaks this ceiling: ``nqueues=2`` with
``qdepth=128`` reaches the 61.7 M IOPS roofline at 4096 total threads, and
``nqueues=4`` with ``qdepth=64`` matches it on thread count with half the
per-queue depth. Beyond ``nqueues=4``, additional queues increase thread count
without improving throughput.

The GPU-side cost separates the configurations that the IOPS curve leaves
equivalent. The polling kernel occupies one multiprocessor per queue per device,
so its footprint is set by the queue count alone and doubles with it, from 13.3%
of the GPU at ``nqueues=1`` to 26.8% at 2 and 53.2% at 4, and effectively all of
it from 8 upward, where the queues outnumber the multiprocessors. Queue depth is
paid for in warp slots instead, which stay below 7% wherever a queue count first
saturates the devices.

Saturating the devices therefore costs 26.8% of the multiprocessors and 1.74% of
the warp slots, at ``nqueues=2`` with ``qdepth=128``. That is half the GPU
``nqueues=4`` costs for the same throughput, which makes ``nqueues=2`` the
configuration to choose.

Together with the I/O size scaling results, these findings characterize the
thread count and queue configuration required to fully utilize device-initiated
I/O across both the bandwidth-bound and IOPS-bound regimes, and what each
configuration leaves of the GPU for the workload it feeds.
