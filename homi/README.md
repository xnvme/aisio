# HOMI: Host Orchestrated Multipath I/O

HOMI is a service that orchestrates all components of the AiSIO SDK. For now,
this is purely a skeleton daemon.

## Installation

This is a guide on how to test the daemon skeleton. Installation is done with
meson and simplified with make.

```bash
make clean build install
```

or

```bash
make clean
meson setup builddir
meson compile -C builddir
meson install -C builddir
```

## Running HOMI

This can be done using the Makefile, or by using the systemd commands.

- With the Makefile:

    ```bash
    make start
    make stop
    ```

- Using systemd directly. `journalctl` can be used to inspect the syslogs.

    ```bash
    systemctl start homi
    journalctl -u homi -n10
    systemctl stop homi
    ```
