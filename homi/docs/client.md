# Using the HOMI client library

The `libhomic` library lets applications access the xal extent trees that
`homid` maintains. All functions are declared in `homic.h`.

## Prerequisites

- `homid` is running and has the target device configured in `homi.conf`.
- Link with `-lhomic`.

## Lifecycle

### 1. Connect

```c
err = homic_connect("/run/homi/homi.sock");
```

Opens a test connection to verify the daemon is reachable and initialises the
global client state. Must be called before any other `homic_*` function.

### 2. Connect to an xal tree

```c
struct xal *xal;

err = homic_connect_xal("/dev/nvme0n1", &xal);
```

Sends an `XAL_CONNECT` request to the daemon and maps the inode pool, extent
pool, and dirty flag from POSIX shared memory. The returned `xal` is a
read-only view backed by shared memory; do not call `xal_close` on it directly
— use `homic_disconnect` to release all mapped segments.

### 3. Wait until the pools are safe to read

```c
err = homic_xal_wait(xal);
```

Spins until the dirty flag is `false`, meaning the daemon has finished
reindexing and the inode and extent pools are consistent. Call this before
reading from the xal tree, and again after any operation that may have run
concurrently with a reindex.

### 4. Use the xal tree

The returned `xal` supports the full read-only xal API. Example: walk all
inodes from the root.

```c
err = homic_xal_wait(xal);
if (err) { /* handle */ }

struct xal_inode *root = xal_get_root(xal);

err = xal_walk(xal, root, my_callback, my_data);
```

To look up a file by path component, use `xal_get_inode` or traverse manually
via `xal_walk`.

### 5. Disconnect

```c
homic_disconnect();
```

Unmaps all shared memory segments and frees the global client state. Safe to
call even if `homic_connect_xal` was never called.

## Error handling

All `homic_*` functions return 0 on success and a negative errno value on
failure. The connection state is global; a failed `homic_connect_xal` does not
affect other already-connected xal instances.

## Concurrency

The dirty flag is updated by the daemon under acquire/release ordering.
`homic_xal_wait` uses `memory_order_acquire` when loading the flag, so once it
returns, all pool writes from the daemon are visible to the caller.

If the daemon logs `xal_index() failed; pools are stale, daemon restart
required`, the dirty flag may remain `true` indefinitely and `homic_xal_wait`
will spin forever. In that case the daemon must be restarted.
