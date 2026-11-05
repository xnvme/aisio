<!--
SPDX-FileCopyrightText: Samsung Electronics Co., Ltd

SPDX-License-Identifier: BSD-3-Clause
-->

# aisio: Accelerator-integrated Storage I/O

Accelerator-integrated Storage I/O (AiSIO) moves data between NVMe SSDs and GPU
memory at high bandwidth, while the file system on the SSD stays mounted and
usable by the rest of the host. This repository provides documentation, tools,
and scripts for setting up and exploring it.

This is AiSIO v26.11. In this release, the path to take is the I/O-modes
benchmark, `tasks/bench_io_modes.yaml` with `xnvmeperf`. The steps below lead
from a fresh Ubuntu installation to running it, in Step 7, with the figures to
expect on the hardware it ran on. The rest is included and its parts are in
place, but it still needs polish; it follows under Preview.

The technical report under `docs/` is outdated, about nine months behind, and
is being reworked. Since it was written, significant changes have made it into
the software ecosystem AiSIO builds on, and its experiments and integrations
have evolved with them: its experiments do not exercise HOMI, and its diagrams
and some names predate the current components. Where it disagrees with
`tasks/` and `configs/`, those are right. Its "This Report" section under
Future Work lists what is known.

## The Software Stack

| Component                                          | Role                                                                |
| -------------------------------------------------- | ------------------------------------------------------------------- |
| [xNVMe](https://github.com/xnvme/xnvme)            | NVMe library with the user-space uPCIe driver, and `xnvmeperf`      |
| [uPCIe](https://github.com/safl/upcie)             | Kernel modules giving that driver access to GPU memory              |
| [`homi`](https://xnvme.io/tools/homi/index.html)   | Control plane in xNVMe, holding a controller and sharing it         |
| [`qublk`](https://xnvme.io/tools/qublk/index.html) | ublk server in xNVMe, offering the controller as a block device     |
| [`xal-server`](https://github.com/xnvme/xal)       | Publishes the extents of a mounted XFS file system in shared memory |
| [fil](https://github.com/xnvme/fil)                | Dataset reader, and the `filperf` benchmark                         |
| [OpenDS](https://github.com/xnvme/opends)          | Vendor-neutral accelerator storage API, modeled on cuFile           |

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
  - **(X) GA Kernel**: the HWE kernel must be disabled
- Installation base:
  - **(X) Ubuntu Server** (not minimized)
- Storage (guided):
  - **(X) Use an entire disk**
  - **[ ] Set up this disk as an LVM group**: leave unchecked
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

Do this only on development machines: enabling root SSH access reduces system
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

## Step 4: Enable the IOMMU

AiSIO assumes the IOMMU translates: the drives are bound to `vfio-pci`, HOMI
holds each of them, and every client's memory, host or GPU, is mapped into the
drive's address space before the drive can reach it. SSH into the target and
add the parameter for your CPU to `GRUB_CMDLINE_LINUX_DEFAULT` in
`/etc/default/grub`, then run `update-grub` and reboot:

```
GRUB_CMDLINE_LINUX_DEFAULT="... intel_iommu=on"
# or
GRUB_CMDLINE_LINUX_DEFAULT="... amd_iommu=on"
```

Leave out `iommu=pt` and `iommu.passthrough=1`, which turn translation off.
Once Step 6 has installed uPCIe's `iommu` tool, `iommu show` reports the mode
as `strict`.

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

## Step 7: Run the I/O Modes

`tasks/bench_io_modes.yaml` exercises AiSIO as it is built: HOMI, the control
plane, holds the drives, and `xnvmeperf` reads from them as its client, in each
of the four ways AiSIO moves data between NVMe drives and a GPU. Take them in
order; each adds one thing to the one before. The terms are defined in the
technical report's Terminology section.

1. **CPU-initiated I/O**: the CPU submits the commands and the data lands in
   host memory. This is the baseline, and checks that the drives, HOMI and
   `xnvmeperf` work.
2. **CPU-initiated P2P I/O**: the same, with the data in GPU memory, moved by
   peer-to-peer DMA between the drive and the GPU.
3. **Accelerator-assisted P2P I/O**: still CPU-initiated; the CPU submits the
   commands, processes the completions and writes the doorbells. The controller
   writes the completions into GPU memory, and a compute kernel resident on the
   GPU only copies them into a completion queue mirror in host memory, where
   the CPU reads them.
4. **Accelerator-initiated P2P I/O**: GPU kernels submit the commands
   themselves. NVIDIA GPUs only, as xNVMe has GPU-initiated I/O for CUDA only.

Describe your machine in a copy of `configs/io_modes_dellr760.toml`, a Dell
R760 with an H100 and sixteen drives: the drives, the GPU, the CPUs and the
frequency to hold them at. The drives are only read, and should be formatted
first, so every block is deallocated and the drive serves reads without going
to its flash; format each while it is on the kernel's driver, which destroys
its data, for example:

```
nvme format --ses=0 --force /dev/nvme1n1
```

Every command and all it printed is in the cijoe report. The drives are left
on `vfio-pci`; `devbind --device <pci_addr> --bind nvme` puts one back on the
kernel's driver.

Each mode runs as steps of the task, named on the command line after the
steps that check and prepare the machine, `stack_check system drive_guard
bind frequency homi_start`, and before those that put it back, `homi_stop
frequency_restore`. `drive_guard` refuses drives the system is using; leave it
out and nothing stops `bind` from taking the system's own disk:

```
cijoe --monitor -c configs/transport.toml -c configs/aisio.toml \
    -c configs/io_modes_<machine>.toml \
    tasks/bench_io_modes.yaml stack_check system drive_guard bind \
    frequency homi_start \
    cpu_initiated_all cpu_initiated_gpu_node \
    homi_stop frequency_restore
```

For the other modes, replace the middle line with `p2p`, then `p2p_cq_mirror`,
then `gpu_initiated`. Without step names, the task runs all four in order.
Without a GPU of your own, the xnvme-devenv guest below runs the first three on
an emulated AMD GPU with `make guest-bench`, as CI does.

### What to Expect

On a two-socket server with eight PCIe Gen6 NVMe drives, linked at Gen5, on
the socket of an H100 PCIe, with Ubuntu's own kernel, the IOMMU translating
and the CPUs held at 3.0 GHz, the four modes at these pins read 512-byte
random blocks at, in million IOPS:

| Mode | Steps | M IOPS |
|---|---|---|
| CPU-initiated, the GPU's drives | `cpu_initiated_gpu_node` | 53.9 |
| CPU-initiated P2P | `p2p` | 48.7 |
| Accelerator-assisted P2P | `p2p_cq_mirror` | 55.3 |
| Accelerator-initiated P2P | `gpu_initiated` | 48.2 |

The accelerator-assisted mode is the fastest, above host memory: with the
completions in GPU memory beside the data, the drive writes to one
destination. Expect figures in proportion to your drives and GPU, and the
same order.

## Preview: Files, Datasets and OpenDS

What follows is in place, and the daemons it brings up are smoke-tested in
CI, but it has not been run on the hardware at these pins, and it needs
polish: the dataset benchmark, which brings in qublk, xal-server and fil on top
of HOMI, and the OpenDS example. It needs Steps 1 to 6.

### Set Up Datasets

Update `configs/datasets.toml` with the correct device information for your
NVMe SSD:

```toml
[filesystems.dset]
bdev     = "/dev/nvme0n1"      # block device path
pci_addr = "0000:01:00.0"      # PCI address (lspci | grep Non-Volatile)
```

Then format the device and populate it with datasets. Take care here: this
**formats** the NVMe device:

```
cijoe --monitor \
    -c configs/transport.toml \
    -c configs/datasets.toml \
    tasks/setup_dataset.yaml
```

### Run the Dataset Benchmark

`configure_daemons.yaml` moves the NVMe device from the kernel driver to
`vfio-pci`, allocates hugepages, and writes the configuration of the
systemd units `setup_aisio.yaml` installs. Run it once, and again after a
reboot, a change to `[aisio]` in `configs/aisio.toml`, or a run of the I/O
modes or the OpenDS example, which write the same units' configuration:

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
`vfio-pci`, so bind it back to `nvme` before running `setup_dataset.yaml`
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

### The OpenDS Example: Loading a Model with llama.cpp

`tasks/bench_llama_load.yaml` loads a large model into GPU memory with
llama.cpp, from a cold page cache, and times it: with llama.cpp's own loaders,
`mmap`, `none` and `dio`, which read the model into host memory and copy it
into VRAM, and with OpenDS's, `opends`, which has the drive write it into VRAM
over P2P, with HOMI holding the drive, the XFS mounted from qublk and
xal-server finding the file's extents. llama.cpp comes from a fork with the
OpenDS loader; the task builds it. [docs/src/implementation.md](docs/src/implementation.md#opends)
describes OpenDS.

It needs an NVIDIA GPU, the setup in Steps 1 to 6, and a known-good copy
of the model on the machine; nothing is downloaded. Only one drive is touched,
and each run prepares it afresh: a new XFS, and the model copied and checked. Describe the
drive, the model and its copy in a copy of `configs/llama_load_dellr760.toml`,
which loads Llama-3.3-70B Q6_K, 54 GiB, into an H100. Each loader's runs and
means are in `llama_load-<mode>.json` in the cijoe output:

```
cijoe --monitor -c configs/transport.toml -c configs/aisio.toml \
    -c configs/llama_load_<machine>.toml \
    tasks/bench_llama_load.yaml
```

## Develop in the xnvme-devenv guest

Without the hardware, AiSIO is developed and tested in a QEMU guest from
[xnvme-devenv](https://github.com/xnvme/xnvme-devenv): Ubuntu 26.10 with ROCm,
an emulated AMD GPU, and an NVMe controller behind the same PCIe switch, so
the controller can move data to and from the GPU's VRAM. The guest has no
IOMMU, so its configs bind the controller to `uio_pci_generic` instead of
`vfio-pci`, and the translating IOMMU AiSIO assumes is exercised only on real
hardware. CI runs the same make targets. It needs Docker and KVM on the host:

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
