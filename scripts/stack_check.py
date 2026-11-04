# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Check that the deployed AiSIO stack is the pinned one, and nothing shadows it
=============================================================================

Changes nothing. It fails, stating that the system's configuration is invalid
for AiSIO and naming each thing it found, when:

- a component's checkout is not at the commit its pin in the configuration
  names: [<name>.repository].tag, or the head of .branch on its remote
- xNVMe's library-info reports another version than its checkout
- uPCIe's DKMS modules are not at [upcie.dkms].version
- a library the stack installs resolves anywhere but --libdir, or has a
  second copy on the dynamic linker's path, or /etc/ld.so.preload, LD_PRELOAD
  or LD_LIBRARY_PATH could load something else in its place
- a program the stack installs is not the one in --bindir, or does not link
  the libraries in --libdir

Retargetable: True
------------------
"""

import errno
import logging as log
from argparse import ArgumentParser

COMPONENTS = ["xnvme", "xal", "fil", "opends"]
LIBRARIES = ["libxnvme.so.0", "libxal.so", "libopends_aisio.so", "libopends_ref.so"]
PROGRAMS = ["xnvme", "xnvmeperf", "homi", "qublk", "xal-server", "filperf"]


def add_args(parser: ArgumentParser):
    parser.add_argument("--libdir", type=str, default="/usr/local/lib/x86_64-linux-gnu")
    parser.add_argument("--bindir", type=str, default="/usr/local/bin")


def out(cijoe, cmd):
    err, state = cijoe.run(cmd)
    return err, state.output().strip()


def checkouts(cijoe):
    problems = []
    for name in COMPONENTS:
        repo = cijoe.getconf(f"{name}.repository", {})
        path = repo.get("path")
        if not path:
            continue
        ref = repo.get("tag") or f"origin/{repo.get('branch', '')}"
        err, want = out(cijoe, f"git -C {path} rev-parse '{ref}^{{commit}}'")
        if err:
            problems.append(f"{name}: {path} does not have {ref}")
            continue
        _, have = out(cijoe, f"git -C {path} rev-parse HEAD")
        if have != want:
            problems.append(f"{name}: {path} is at {have[:9]}, the pin is {want[:9]}")

    return problems


def deployed(cijoe):
    problems = []
    path = cijoe.getconf("xnvme.repository.path", "")
    if path:
        _, want = out(cijoe, f"git -C {path} describe --tags --always")
        _, info = out(cijoe, "xnvme library-info | grep -m1 vcs")
        if want not in info:
            problems.append(f"xnvme: library-info has '{info}', the checkout is {want}")

    version = cijoe.getconf("upcie.dkms.version", "")
    if version:
        _, status = out(cijoe, "dkms status 2>/dev/null")
        if version not in status:
            problems.append(f"upcie: no DKMS module at {version} in '{status}'")

    return problems


def linker(cijoe, libdir):
    problems = []
    _, preload = out(cijoe, "cat /etc/ld.so.preload 2>/dev/null")
    if preload:
        problems.append(f"/etc/ld.so.preload loads {preload}")
    _, env = out(cijoe, 'echo "$LD_PRELOAD$LD_LIBRARY_PATH"')
    if env:
        problems.append(f"LD_PRELOAD or LD_LIBRARY_PATH is set: {env}")

    _, cache = out(cijoe, "ldconfig -p")
    for lib in LIBRARIES:
        paths = {
            line.split("=>")[-1].strip()
            for line in cache.splitlines()
            if line.strip().startswith(lib + " ")
        }
        if not paths:
            continue
        stray = sorted(p for p in paths if not p.startswith(libdir + "/"))
        if stray:
            problems.append(f"{lib}: also at {', '.join(stray)}, outside {libdir}")

    return problems


def programs(cijoe, libdir, bindir):
    problems = []
    for prog in PROGRAMS:
        err, where = out(cijoe, f"command -v {prog}")
        if err:
            continue
        if where != f"{bindir}/{prog}":
            problems.append(f"{prog}: {where} comes first, not {bindir}/{prog}")
            continue
        _, libs = out(cijoe, f"ldd {where} | grep -E 'lib(xnvme|xal|opends)'")
        for line in libs.splitlines():
            if "=>" in line and f"=> {libdir}/" not in line:
                problems.append(f"{prog}: links {line.strip()}")

    return problems


def main(args, cijoe):
    problems = (
        checkouts(cijoe)
        + deployed(cijoe)
        + linker(cijoe, args.libdir)
        + programs(cijoe, args.libdir, args.bindir)
    )
    if not problems:
        return 0

    log.error("The system's configuration is invalid for AiSIO; nothing was changed:")
    for problem in problems:
        log.error(f"  {problem}")

    return errno.EINVAL
