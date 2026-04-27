# aisio: Accelerator-integrated Storage I/O

This repository provides documentation, tools, and scripts for setting up and
exploring Accelerator-integrated Storage I/O. The guide below walks through the
full setup from a fresh Ubuntu installation to running `bench_aisio.yaml`.

## Prerequisites

Install `cijoe` on the host with `pipx`:

```
pipx install cijoe
```

## Step 1: Install Ubuntu 24.04

Install **Ubuntu Server 24.04.4** on the target machine. During installation,
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

## Step 3: Install the Custom Linux Kernel

Install a custom kernel with **UDMABUF import** support. This extends the
kernel's UDMABUF device to act as a dma-buf importer, enabling the zero-copy
GPU-to-storage path used by xNVMe uPCIe:

```
cijoe --monitor \
    -c configs/transport.toml \
    -c configs/udmabuf_import.toml \
    tasks/setup_udmabuf_import.yaml
```

## Step 4: Install the NVIDIA Software Stack

Install the **NVIDIA** drivers, CUDA toolkit, and GDS (GPUDirect Storage):

```
cijoe --monitor \
    -c configs/transport.toml \
    -c configs/nvstack.toml \
    tasks/setup_nvstack.yaml
```

## Step 5: Set Up AiSIO Components

Build and install the AiSIO software stack (xNVMe, SPDK, xal, fil):

```
cijoe --monitor \
    -c configs/transport.toml \
    -c configs/aisio.toml \
    tasks/setup_aisio.yaml
```

## Step 6: Set Up Datasets

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

## Step 7: Run Benchmarks

`bench_aisio.yaml` uses the xNVMe uPCIe path, so the NVMe device must be
unbound from the kernel driver before running. SSH into the target and unmount
the dataset volume, rebind the device, and allocate hugepages:

```
modprobe uio_pci_generic
umount /mnt/datasets
devbind --device '0000:01:00.0' --bind uio_pci_generic  # pci_addr from datasets.toml
hugepages setup --count 1024
```

`devbind` and `hugepages` are installed on the target as part of `setup_aisio.yaml`.

Then run the AiSIO benchmark suite:

```
cijoe --monitor \
    -c configs/transport.toml \
    -c configs/aisio.toml \
    -c configs/datasets.toml \
    tasks/bench_aisio.yaml
```
