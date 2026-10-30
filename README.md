<!--
SPDX-FileCopyrightText: Samsung Electronics Co., Ltd

SPDX-License-Identifier: BSD-3-Clause
-->

# aisio: Accelerator-integrated Storage I/O

This repository provides documentation, tools, and scripts for setting up and
exploring Accelerator-integrated Storage I/O. The guide below walks through the
full setup from a fresh Ubuntu installation to running `bench_aisio.yaml`.

## Prerequisites

Install `cijoe` on the host with `pipx`:

```
pipx install cijoe
```

## Step 1: Install Ubuntu 26.04

Install **Ubuntu Server 26.04** on the target machine. During installation,
make the following selections:

- Kernel:
  - **(X) GA Kernel** — the HWE kernel must be disabled
- Installation base:
  - **(X) Ubuntu Server** (not minimized)
- Storage (guided):
  - **(X) Use an entire disk**
  - **[ ] Set up this disk as an LVM group** — leave unchecked
- Profile:
  ```
  Your name:   <choose>
  Server name: aisio
  Username:    <choose>
  Password:    <choose>
  ```
  The server name becomes the hostname. It must match `hostname` in
  `configs/transport.toml`, or update that field to use an IP address.
- SSH: **[X] Install OpenSSH server**

After first boot, enable root SSH login so cijoe can connect:

```
sudo passwd root
sudo sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
sudo systemctl restart ssh
```

Do this only on development machines — enabling root SSH access reduces system
security.

## Step 2: Prepare Ubuntu

Configure `configs/transport.toml` with the hostname and root credentials of
your target machine:

```toml
[cijoe.workflow]
fail_fast=true

[cijoe.transport.ssh]
hostname = "aisio"
username = "root"
password = "<password>"
```

Then install packages, disable automatic upgrades, blacklist the Nouveau driver,
and reboot:

```
cijoe --monitor \
    -c configs/transport.toml \
    tasks/setup_ubuntu.yaml
```

## Step 3: Install the uPCIe Kernel Modules

Install the out-of-tree kernel modules released by uPCIe. The **dma-buf
importer** resolves the DMA addresses of GPU memory, enabling the zero-copy
GPU-to-storage path used by xNVMe uPCIe, and the **IOMMU physical-address
mapper** reaches that memory with the IOMMU left on. Both arrive in one DKMS
package, so they build against the stock Ubuntu GA kernel and rebuild
themselves on kernel updates:

```
cijoe --monitor \
    -c configs/transport.toml \
    -c configs/aisio.toml \
    tasks/setup_upcie_modules.yaml
```

## Step 4: Disable IOMMU

SSH into the target and edit the `/etc/default/grub` to disable IOMMU. Add the
appropriate parameter for your CPU in the `GRUB_CMDLINE_LINUX_DEFAULT`.

```
GRUB_CMDLINE_LINUX_DEFAULT="... intel_iommu=off"
# or
GRUB_CMDLINE_LINUX_DEFAULT="... amd_iommu=off"
```

## Step 5: Install the NVIDIA Software Stack

Install the **NVIDIA** driver and CUDA toolkit:

```
cijoe --monitor \
    -c configs/transport.toml \
    tasks/setup_nvstack.yaml
```

## Step 6: Set Up AiSIO Components

Build and install the AiSIO software stack (xNVMe, SPDK, xal, fil):

```
cijoe --monitor \
    -c configs/transport.toml \
    -c configs/aisio.toml \
    tasks/setup_aisio.yaml
```

## Step 7: Set Up Datasets

Update `configs/datasets.toml` with the correct device information for your
NVMe SSD:

```toml
[filesystems.dset]
bdev     = "/dev/nvme0n1"      # block device path
pci_addr = "0000:01:00.0"      # PCI address (lspci | grep Non-Volatile)
```

Then format the device and populate it with datasets. Take care here — this
**formats** the NVMe device:

```
cijoe --monitor \
    -c configs/transport.toml \
    -c configs/datasets.toml \
    tasks/setup_dataset.yaml
```

## Step 8: Run Benchmarks

`bench_aisio.yaml` moves the NVMe device from the kernel driver to `homi`,
allocates hugepages, and starts `qublk` and `xal-server` through the systemd
units `setup_aisio.yaml` installs. The dataset volume is then mounted from
`/dev/ublkb1` instead of the kernel's NVMe block device. Nothing is formatted,
and the daemons are stopped at the end. The device stays bound to
`uio_pci_generic`, so bind it back to `nvme` before running `setup_dataset.yaml`
again.

Run the AiSIO benchmark suite:

```
cijoe --monitor \
    -c configs/transport.toml \
    -c configs/aisio.toml \
    -c configs/datasets.toml \
    tasks/bench_aisio.yaml
```

## License

AiSIO is licensed under the BSD 3-Clause License; see [LICENSE](LICENSE) for the
full text. Individual files carry an `SPDX-License-Identifier` tag, and the
repository follows the [REUSE](https://reuse.software/) specification, so
`reuse lint` reports the licensing of every file.
