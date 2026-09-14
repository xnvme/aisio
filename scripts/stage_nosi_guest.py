# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Stage a nosi guest disk-image
=============================

Pulls the ``oras://`` image at ``[guest_image].url`` into the qcow2 at
``system-imaging.images.<image>.disk.path`` and grows it by
``[guest_image].grow`` (default ``8G``). Skips the pull when that digest and
growth are already staged. Requires ``withcache`` in the cijoe environment.

Retargetable: False
-------------------
"""

import logging as log
import tempfile
from argparse import ArgumentParser
from pathlib import Path


def add_args(parser: ArgumentParser):
    pass


def main(args, cijoe):
    url = cijoe.getconf("guest_image.url", None)
    if not url:
        log.info("config has no [guest_image].url; nothing to stage")
        return 0

    from withcache import oras

    grow = cijoe.getconf("guest_image.grow", "8G")
    image = cijoe.getconf("qemu.default_systemimage", None)
    disk = cijoe.getconf(f"system-imaging.images.{image}.disk", None)
    if not disk:
        log.error(f"missing config value(system-imaging.images.{image}.disk)")
        return 1
    dst = Path(disk["path"])
    dst.parent.mkdir(parents=True, exist_ok=True)

    digest = oras.parse_ref(url).digest
    stamp = Path(f"{dst}.stamp")
    if (
        digest
        and dst.exists()
        and stamp.exists()
        and stamp.read_text().strip() == f"{digest} {grow}"
    ):
        log.info(f"image already staged at {dst} ({digest}, +{grow}); skipping pull")
        return 0

    log.info(f"staging {url} -> {dst}")
    resolved = oras.resolve_ref(url)
    bearer = resolved.headers["Authorization"]

    # dst's filesystem, as /tmp is too small for the raw image
    with tempfile.TemporaryDirectory(dir=dst.parent) as workdir:
        gz = Path(workdir) / "guest.img.gz"
        raw = Path(workdir) / "guest.img"
        for cmd in [
            f"curl -fL --retry 5 --retry-all-errors -C - -H 'Authorization: {bearer}' "
            f"-o {gz} '{resolved.blob_url}'",
            f"gunzip {gz}",
            f"qemu-img convert -f raw {raw} -O qcow2 {dst}",
            f"qemu-img resize {dst} +{grow}",
        ]:
            err, _ = cijoe.run_local(cmd)
            if err:
                return err

    stamp.write_text(f"{digest} {grow}" if digest else "")
    return 0
