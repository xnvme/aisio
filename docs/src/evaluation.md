# Evaluation

Performance was measured using a PCIe Gen5 H100 GPU and PCIe Gen5 NVMe SSD.

Key results:

- AiSIO reaches 88.5% of BaM performance.
- GDS achieves only 22.1% of BaM performance.
- AiSIO delivers a 3.9× improvement over GDS on small random I/O.
- Near–line-rate bandwidth is achieved for 4 KiB random reads.
- File-I/O workloads with widely varying file sizes are supported efficiently.
- CPU overhead is significantly reduced by offloading scheduling and data movement to accelerators.
