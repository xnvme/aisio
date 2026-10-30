<!--
SPDX-FileCopyrightText: Samsung Electronics Co., Ltd

SPDX-License-Identifier: BSD-3-Clause
-->

# aisio: Accelerator-integrated Storage I/O

Accelerator-integrated Storage I/O (AiSIO) moves data between NVMe SSDs and GPU
memory at high bandwidth, while the file system on the SSD stays mounted and
usable by the rest of the host. This repository provides documentation, tools,
and scripts for setting up and exploring it. The guide below walks through the
full setup from a fresh Ubuntu installation to running `bench_aisio.yaml`.

## The Software Stack

| Component                                          | Role                                                                |
| -------------------------------------------------- | ------------------------------------------------------------------- |
| [xNVMe](https://github.com/xnvme/xnvme)            | NVMe library with the user-space uPCIe driver, and `xnvmeperf`      |
| [uPCIe](https://github.com/safl/upcie)             | Kernel modules giving that driver access to GPU memory              |
| [`homi`](https://xnvme.io/tools/homi/index.html)   | Control plane in xNVMe, holding a controller and sharing it         |
| [`qublk`](https://xnvme.io/tools/qublk/index.html) | ublk server in xNVMe, offering the controller as a block device     |
| [`xal-server`](https://github.com/xnvme/xal)       | Publishes the extents of a mounted XFS file system in shared memory |
| [fil](https://github.com/xnvme/fil)                | Dataset reader, and the `filperf` benchmark                         |

`homi`, `qublk` and `xal-server` are independent daemons, and they meet in one
read path. `homi` holds the NVMe controller, so several processes can use it at
once. `qublk` is one of those processes, and the kernel mounts the dataset
volume from its `/dev/ublkb1`. `xal-server` indexes that file system, so a
reader can find a file's blocks without going through the kernel. `filperf`
looks up the file in the index and reads its blocks from the controller through
`homi`, driven by the CPU (`aisio-cpu`), by the GPU (`aisio-gpu`), or peer to
peer into GPU memory (`aisio-p2p`).

[docs/src/architecture.md](docs/src/architecture.md) describes the architecture
in depth.

## Prerequisites

Install `cijoe` on the host with `pipx`, at the version CI runs:

```
pipx install cijoe==0.9.70
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
[cijoe.task]
fail_fast=true

[cijoe.targets.machine.ssh]
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

Build and install the AiSIO software stack (xNVMe, SPDK, xal, fil, OpenDS):

```
cijoe --monitor \
    -c configs/transport.toml \
    -c configs/aisio.toml \
    tasks/setup_aisio.yaml
```

The sources are checked out under `/root/aisio`, so checkouts the system has
elsewhere, such as in `/root/git`, are left alone; a later config can set each
`[<name>.repository].path`. The stack installs under `/usr/local`, replacing any
xNVMe, xal or fil installed there before. The dependencies are installed without
upgrading the system, so packages the system holds, such as the NVIDIA driver's,
keep their versions.

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

`configure_daemons.yaml` moves the NVMe device from the kernel driver to
`uio_pci_generic`, allocates hugepages, and writes the configuration of the
systemd units `setup_aisio.yaml` installs. Run it once, and again after a reboot
or a change to `[aisio]` in `configs/aisio.toml`:

```
cijoe --monitor \
    -c configs/transport.toml \
    -c configs/aisio.toml \
    -c configs/datasets.toml \
    tasks/configure_daemons.yaml
```

`bench_aisio.yaml` starts `homi`, `qublk` and `xal-server`, mounts the dataset
volume from `/dev/ublkb1` instead of the kernel's NVMe block device, and stops
them at the end. Nothing is formatted. The device stays bound to
`uio_pci_generic`, so bind it back to `nvme` before running `setup_dataset.yaml`
again. If a run fails, run `configure_daemons.yaml` to stop what it left
running.

Run the AiSIO benchmark suite:

```
cijoe --monitor \
    -c configs/transport.toml \
    -c configs/aisio.toml \
    -c configs/datasets.toml \
    tasks/bench_aisio.yaml
```

## Develop in the xnvme-devenv guest

Without the hardware, AiSIO is developed and tested in a QEMU guest from
[xnvme-devenv](https://github.com/xnvme/xnvme-devenv): Ubuntu 26.10 with ROCm,
an emulated AMD GPU, and an NVMe controller behind the same PCIe switch, so
the controller can move data to and from the GPU's VRAM. CI runs the same
make targets. It needs Docker and KVM on the host:

```
make devenv
```

That starts a shell in xnvme-devenv's host container, with this checkout
mounted at `/aisio`. In it, boot the guest, set up the AiSIO components with
`setup_aisio.yaml`, and run the smoke tests, which drive the daemons with I/O
and do peer-to-peer I/O between the controller and VRAM:

```
make guest-start guest-provision guest-test
```

Run `make guest-test` again after changing a task or script. The guest's SSH
is on port 4200 of the host, as `root` with password `root`. `make guest-stop`
stops it. `RIG` layers further rig files on the default
`compute-node-emulated`, for example `RIG="compute-node-emulated my.toml"`.

## License

AiSIO is licensed under the BSD 3-Clause License; see [LICENSE](LICENSE) for the
full text. Individual files carry an `SPDX-License-Identifier` tag, and the
repository follows the [REUSE](https://reuse.software/) specification, so
`reuse lint` reports the licensing of every file.
