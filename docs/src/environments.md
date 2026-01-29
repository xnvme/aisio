(sec-environment)=
# Environments

This section describes the system configurations used for experimenting
with AiSIO system software architectures, including the initial AiSIO
proof-of-concept and the development of the HOMI reference implementation. These
environments support evaluation, document constraints encountered during HOMI
development, and serve as reproducible reference builds for readers wishing to
explore similar architectures.

The same environments were also used to reproduce, where possible, benchmarks
from related work, specifically NVIDIA GPUDirect Storage (GDS) and Big
Accelerator Memory (BaM), ensuring controlled comparison under identical system
conditions.

The configurations reflect practical system builds intended to support
architectural exploration, implementation, and comparative evaluation, rather
than prescribing production deployment guidelines

## System Setup and Benchmarks

Brief introduction to CIJOE, configs / workflows / scripts.

* OS Installation
* NVIDIA Software Stack Setup
* Dataset Populaton on NVMe
* Running benchmarks

## V100 16GB

1x Gigabyte ...
1x AMD EPYC
2x V100 Discrete
4x Samsung 980 PRO

## H100 80G

| Hardware | Details                              |
| -------- | ------------------------------------ |
| CPU      | 2x Intel® Xeon® Gold 6442Y Processor |
| GPU      | 2x NVIDIA H100 Discrete              |
| Storage  | 16x Samsung SSD PM1753 32TB SSD      |

## RTX A5000 24GB

1x AMD EPYC
1x RTX A5000 24GB
4x Samsung 990 PRO 2TB

## RTX A2000 6GB

1x
1x RTX A2000 6GB
1x Samsung 980 PRO 1TB
