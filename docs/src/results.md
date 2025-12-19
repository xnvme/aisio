(sec-results)=
# Results

In this section, we will present the results of running the experiments.

## Conventional CPU-initiated Setup

### Determining Device IOPS Capacity

To establish a device-side upper bound, we define device capacity as the maximum
IOPS observed in any single-device experiment. In our environment, we were able to
reach 3 857 938 IOPS with only one device, and as such, this was used as the
device capacity for our analysis.

[Average for all ndev=1]: # (3 099 640)
[Median for all ndev=1]: # (3 766 518)
[Average for ndev=1,gov=performance]: # (3 709 847)
[Median for ndev=1,gov=performance]: # (3 844 043)

### Optimal Parameterization

With all 16 devices utilized, we were able to reach this capacity of almost 62
million IOPS using 8 physical cores. The parameterization to achieve this was:

| Independent Variable     | Value              |
| ------------------------ | ------------------ |
| CPU frequency / governor | performance        |
| Turbo boost              | on                 |
| SMT                      | on                 |
| Thread siblings          | { used, not used } |
| Stress                   | { on, off }        |
| Queue depth              | 128                |
| I/O size                 | 512                |
| Number of cores          | 8                  |
| Number of devices        | 16                 |

When using thread siblings, it did not matter whether the unused CPUs were
stressed or idle. When not using thread siblings, stressing the unused CPUs caused
the IOPS to drop due to the resources of the physical cores being divided between
the bdevperf and stress-ng processes. The results for the parameterization above
were:

| Id | Variables                                | Reached IOPS |
| -- | ---------------------------------------- | ------------ |
| A  | Thread siblings: used<br>Stress: off     | 61 720 159   |
| B  | Thread siblings: used<br>Stress: on      | 61 622 306   |
| C  | Thread siblings: not used<br>Stress: off | 61 712 325   |
| D  | Thread siblings: not used<br>Stress: on  | 41 065 835   |

Each parameterization has been given an id to allow for easy reference in the
following sections. Altering the values of the independent variables from the
best-performing parameter set, results in poorer performance. In the following, we
will describe how altering each variable independently affects the results. As the
parameterizations A, B and C elicit the best results, these will be at focus in
the following sections.

We saw that all three parameterizations respond similarly to changes in the
remaining independent variables. Because of this, we have only included the
results of parameterization C in our graphs for readability's sake. The presented
results for all graphs, are averages of running the experiments five times. Note
that variances are plotted as shaded areas around each line, but in most cases are
too small to be visible.

### Effect of the Independent Variables

In this section, we will inspect the effect on the results of changing the
independent variables.

#### CPU Frequency and Governors

We saw a significant decrease in reached IOPS when switching the CPU governor to
"powersave". On average, the results decreased by 64.19 % for parameterization
A-C.

| Parameterization Id | IOPS       | Change          |
| ------------------- | ---------- | --------------- |
| A                   | 23 972 222 | 61.2 % decrease |
| B                   | 23 879 418 | 61.3 % decrease |
| C                   | 18 422 224 | 70.2 % decrease |

When inspecting the CPU frequencies, we generally see that the performance CPU
governor keep the clock speed at 3.3 GHz for all CPUs, which is the maximum clock
speed we were able to reach with turbo boost enabled. The powersave governor
reduces the clock speed in order to reduce the power consumption, which explains

[A: Using, stress off]: # (23 972 222 - 61.16% decrease)
[B: Using, stress on]: # (23 879 418 - 61.25% decrease)
[C: Not using, stress off]: # (18 422 224 - 70.15% decrease)
[D: Not using, stress on]: # (41 575 999 - 1.24% increase)

#### Turbo Boost

When turning turbo boost off and thereby limiting the clock speed to 2.6 GHz, we
get small decrease, on average 4.4 % less IOPS.

| Parameterization Id | IOPS       | Change         |
| ------------------- | ---------- | -------------- |
| A                   | 59 731 756 | 3.2 % decrease |
| B                   | 59 570 168 | 3.3 % decrease |
| C                   | 57 606 912 | 6.7 % decrease |

[A: Using, stress off]: # (59 731 756 - 3.22% decrease)
[B: Using, stress on]: # (59 570 168 - 3.33% decrease)
[C: Not using, stress off]: # (57 606 912 - 6.65% decrease)
[D: Not using, stress on]: # (33 003 158 - 19.63% decrease)

However, we were able to reach similar results without turbo boost enabled by
doubling the amount of CPU cores, as we will go into detail with in a later
section.

#### SMT

When SMT is turned off, thread siblings are not available, and our results are
limited to parameterization C. Here, we saw a similar decrease as when turbo boost
was disabled. The measured CPU frequencies here do not exceed 2.6 GHz, indicating
that the performance CPU governor does not trigger turbo boost when SMT is
disabled, explaining the similar performance decrease.

| Parameterization Id | IOPS       | Change          |
| ------------------- | ---------- | --------------- |
| C                   | 57 965 380 | 6.1 % decrease  |
| D                   | 57 729 981 | 40.6 % increase |

Using a fixed CPU frequency with the *userspace* CPU governor of 3.0 GHz results
in higher IOPS when SMT is disabled, than the performance CPU governor.

| Parameterization Id | IOPS       | Change          |
| ------------------- | ---------- | --------------- |
| C                   | 61 664 783 | 0.1 % decrease  |
| D                   | 61 565 869 | 49.9 % increase |

Interestingly, we observe little difference between parameterization C and D
when SMT is disabled. This supports the explanation for why parameterization D
performs worse than A, B, and C with SMT disabled, each physical core can execute
only a single thread, eliminating contention but also preventing bdevperf from
benefiting from simultaneous multithreading.

[C: Not using, stress off]: # (57 965 380 - 6.07% decrease)
[D: Not using, stress on]: # (57 729 981 - 40.58% increase)
[C: 3GHz, Not using, stress off]: # (61 664 783 - 0.077% decrease)
[D: 3GHz, Not using, stress on]: # (61 565 869 - 49.92% increase)

#### Queue depth

We found that the results peaked when using a queue depth of 128. With turbo boost
enabled, we reached the device cap with both queue depths 128, 256 and 512, but
disabling turbo boost highlights the peak at 128.

```{figure} _static/bench_cpu-queuedepth.png
:alt: CPU bench results
:width: 700px
:align: center

Results of parameterization C with different queue depths.
```

#### I/O size

Increasing the I/O size to 4096 results in each operation taking more time and
therefore the reached IOPS decreases as seen in the graph. However, it is relevant
to look at the bandwidth, as we saw a significant increase in bandwidth when
increasing the I/O size. Performance does not necessarily suffer from higher I/O
sizes, only the amount of operations completed per second.

```{figure} _static/bench_cpu-iosize_iops.png
:alt: CPU bench results
:width: 700px
:align: center

Results of parameterization C with different I/O sizes.
```

```{figure} _static/bench_cpu-iosize_mibs.png
:alt: CPU bench results
:width: 700px
:align: center

Measured bandwidth for parameterization C with different I/O sizes.
```

(sec-results-cpu-cores)=
#### Number of Cores

For the selected parameters, the results scale linearly with the amount of
physical CPU cores used until we reach a core-to-device ratio of 1:2. At this
point, we generally reach the device capacity when turbo boost is enabled.
However, disabling turbo boost results in an approximately 4.4 % decrease in IOPS,
and increasing the amount of CPUs gives diminishing returns, as seen in the graph
below. We are able to reach a similar result as with turbo boost enabled once the
core-to-device ratio is 1:1, meaning there is one core per device.

```{figure} _static/bench_cpu-cores.png
:alt: CPU bench results
:width: 700px
:align: center

Results of parameterization C with and without turbo boost enabled.
```

#### Number of Devices

The results scale linearly with the amount of devices used.

```{figure} _static/bench_cpu-devices.png
:alt: Graph showing the results of four benchmark results with optimal parameters
:width: 700px
:align: center

Results of parameterization C with different devices.
```
