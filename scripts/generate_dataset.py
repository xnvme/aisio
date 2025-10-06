"""
Generate reproducible pseudo-datasets on a target system
========================================================

This command ties together dataset declarations from the configuration file
(`datasets.<name>`) with the auxiliary generator script
`auxiliary/generate_dataset.sh`.

When generating datasets consisting of many small files (e.g., millions),
it is significantly more efficient to:

1. Package the generation logic in a shell script,
2. Transfer it from the initiator to the target once, and
3. Execute it remotely.

This approach reduces overhead by replacing millions of SSH operations
with just a few, improving reliability and performance.
"""

from argparse import ArgumentParser
from cijoe.core.resources import get_resources
import logging as log


def add_args(parser: ArgumentParser):
    parser.add_argument(
        "--dataset_name",
        type=str,
        help="Name of the dataset to generate",
    )


def main(args, cijoe):
    if not (dataset := cijoe.getconf(f"datasets.{args.dataset_name}", {})):
        log.error(f"No dataset with dataset_name({args.dataset_name})")
        return 1

    if not (script := get_resources().get("auxiliary", {}).get("generate_dataset", {})):
        log.error("Failed retrieving the shell-script from auxiliary files")
        return 1

    dst = "/tmp/generate_dataset.sh"

    if not cijoe.put(script.path, dst):
        log.error("Failed transferring generator script from initator to target")
        return 1

    err, _ = cijoe.run(f"chmod +x {dst}")
    if err:
        log.error("Failed setting executable bit")
        return err

    cmd_args = " ".join(
        [f"--{key.replace('_', '-')} {val}" for key, val in dataset.items()]
    )

    err, _ = cijoe.run(f"{dst} {cmd_args} --jobs $(nproc)")
    if err:
        log.error(f"Failed generating dataset with err({err})")
        return err

    return 0
