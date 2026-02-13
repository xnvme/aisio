# HOMI: Host Orchestrated Multipath I/O

HOMI is a service that orchestrates all components of the AiSIO SDK. For now,
this is purely a skeleton daemon.

## Installation

The Meson build system is used to build and install HOMI. This is simplified with
make.

```bash
make
```

## Configuration

After installation, a configuration file is created at `/etc/homi/homi.conf`. The
configuration file lets you define:

1. The log level (an integer)
1. The device URIs (array of strings) that the service will manage.

## Start / stop

HOMI is a systemd service and can be managed with regular systemd commands. This
is, again, simplified with make.

```bash
make start
make stop
```

## Logs

The HOMI service uses systemd's journal for logging. This can be inspected with
`journalctl`, but is simplified with make, which prints out the latest 10 log
messages. If you want to view more log entries, you can use `journalctl` for this
and either remove the `-n` flag, or specify a larger amount.

```bash
make log
# or
journalctl -u homi
# or
journalctl -u homi -n30
```
