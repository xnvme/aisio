<!--
SPDX-FileCopyrightText: Samsung Electronics Co., Ltd

SPDX-License-Identifier: BSD-3-Clause
-->

# Changelog

AiSIO is released by year and month, e.g. `v26.11`, each release being the lock
in `configs/aisio.toml` as it stands that month. A patch release within the
month adds the day it is cut, e.g. `v26.11.18`. `make bump NEW_VERSION=YY.MM`,
or `YY.MM.DD`, names the next one and opens its section below, whose notes are
then written. A merged commit with the subject `ver: bump to v<version>` is
tagged and released, with that section as the release notes.

## 26.11

The path this release stands behind is the I/O-modes benchmark. The README
walks from a fresh Ubuntu installation to `tasks/bench_io_modes.yaml`, with the
figures to expect on the hardware. The stack is built at the release lock. It
assumes the IOMMU translating and HOMI holding every drive, with qublk and
xal-server serving where files are involved, all through their systemd units.
cijoe is at v0.9.70. CI runs setup, the daemon smoke test, P2P into VRAM and
the I/O modes in the xnvme-devenv guest on an emulated AMD GPU.

The dataset benchmark and the OpenDS example are in place, under Preview in the
README. The report under `docs/` is renamed the AiSIO Technical Report. It is
about nine months behind, and points at the 2026 talks meanwhile.

xNVMe is pinned to the tag `for-aisio-02112026`, marked TEMPORARY in the lock,
until an xNVMe release carries the upcie backends, homi and `io_uring_dmabuf`.
uPCIe is at v0.10.4, xal at v0.3.4, fil at v0.5.0, OpenDS at v0.2.0, SPDK at
v26.05 and fio at fio-3.41.

On the hardware, Ubuntu's kernel `7.0.0-27-generic`, IOMMU translating, eight
drives on the H100's socket, at 512 B, the I/O modes ran at 53.9, 48.7, 55.3 and
48.2 M IOPS, recorded on 2026-11-03.
