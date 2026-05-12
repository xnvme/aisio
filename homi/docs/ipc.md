# HOMI IPC Interface

The daemon (`homid`) exposes a Unix domain socket that clients use to request
access to pre-loaded xal trees. The socket path is set by `ipc_socket` in
`homi.conf` (default: `/run/homi/homi.sock`).

## Connection model

Each request uses its own connection. The client connects, sends one request,
reads one response, and closes the socket. The daemon spawns a thread per
accepted connection to handle the request.

## Message framing

Every message begins with a `homi_msg_header`:

```c
struct homi_msg_header {
    enum homi_msg_type type;
    size_t payload_len;
};
```

The header is followed immediately by `payload_len` bytes of payload. A
`payload_len` of zero means no payload follows.

`homi_proto_socket_write` and `homi_proto_socket_read` (declared in
`homi_proto.h`) implement this framing. The write function sets `payload_len`
before sending; the read function heap-allocates the payload and returns it via
an output pointer.

## Message types

### `HOMI_MSG_TYPE_HELLOWORLD` (0)

A test round-trip. The daemon echoes a fixed string back.

| Direction | Type | Description |
|-----------|------|-------------|
| Request   | `homi_req_helloworld` | `int32_t value` — ignored by the daemon |
| Response  | `char *` | Null-terminated string `"hello world!"` |

### `HOMI_MSG_TYPE_XAL_CONNECT` (1)

Requests the shared memory names for a device's xal pools.

| Direction | Type | Description |
|-----------|------|-------------|
| Request   | `homi_req_xal_connect` | `char dev_uri[256]` — device URI as configured in `homi.conf` |
| Response  | `homi_res_xal_connect` | `err` (negative errno on failure), `xal_sb` (superblock), `shm_name[64]` |

On success (`res.err == 0`), the client maps three POSIX shared memory segments
derived from `shm_name`:

| Segment | Name | Access | Contents |
|---------|------|--------|----------|
| Inodes | `{shm_name}_inodes` | read-only | xal inode pool |
| Extents | `{shm_name}_extents` | read-only | xal extent pool |
| Dirty flag | `{shm_name}_dirty` | read-only | `_Atomic bool`; `true` while the daemon is running `xal_index()` |

The client must not read from the inode or extent pools while the dirty flag is
`true`. See [client.md](client.md) for how to wait safely.
