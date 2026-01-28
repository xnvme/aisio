# HOMI: Host Orchestrated Multipath I/O

HOMI is a service that orchestrates all components of the AiSIO SDK. For now,
this is purely a skeleton daemon.

## Installation

This is a guide on how to test the daemon skeleton. Installation can be done using
the Makefile by running

```bash
make build
```

Or by following these steps:

1. Compile the daemon.

    ```bash
    gcc daemon.c -o daemon.o
    ```

1. Check the service configuration file, ``home.service``. The Service.ExecStart
   field assumes the ``daemon.o`` location. Change this if necessary.

    - TODO: An build system should place the executable in a more permanent
      location.

1. Copy the service configuration file to the systemd files.

    ```bash
    cp ./homi.service /etc/systemd/system
    ```

## Running HOMI

This can be done using the Makefile, or by using the systemd commands.

- With the Makefile:

    ```bash
    make start
    makse stop
    ```

- Using systemd directly.

    ```bash
    systemctl start homi
    journalctl -u homi
    systemctl stop homi
    ```
