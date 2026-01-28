# HOMI: Host Orchestrated Multipath I/O

HOMI is a service that orchestrates all components of the AiSIO SDK. For now,
this is purely a skeleton daemon.

## Installation

This is a guide on how to test the daemon skeleton.

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

1. Start the service, and check the service journal.

    ```bash
    systemctl start homi
    journalctl -u homi
    ```

1. Stop the service.

    ```bash
    systemctl stop homi
    ```
