#ifndef HOMIC_H
#define HOMIC_H

/**
 * Connect to the homid daemon.
 *
 * Connects to the daemon via a socket to obtain the shared memory id,
 * then attaches to the segment for subsequent requests. Must be called before
 * any other homic functions. The connection is held globally; call
 * homic_disconnect() to release it.
 *
 * @param socket_path  Path to the daemon's socket.
 * @return  0 on success, negative errno on failure.
 */
int
homic_connect(char *socket_path);

/**
 * Disconnect from the homid daemon.
 *
 * Detaches from the shared memory segment and releases the global connection.
 * Safe to call if not connected.
 */
void
homic_disconnect();

/**
 * Send a helloworld request to the daemon.
 *
 * Sends value to the daemon and receives the response string in *out.
 * Requires an active connection established with homic_connect().
 *
 * @param value  Integer to send (ignored by the daemon).
 * @param out    Output: heap-allocated response string. Caller must free.
 * @return       0 on success, negative errno on failure.
 */
int
homic_helloworld(int32_t value, char **out);

/**
 * Connect to xal for a specific device.
 *
 * Sends an XAL_CONNECT request to the daemon, maps the inode and extent pools
 * from POSIX shared memory, and constructs a read-only xal via xal_from_pools().
 * Requires an active connection established with homic_connect().
 *
 * @param dev_uri  URI of the device to connect to.
 * @param out      Output: read-only xal struct backed by shared memory.
 * @return         0 on success, negative errno on failure.
 */
int
homic_connect_xal(char *dev_uri, struct xal **out);

#endif /* HOMIC_H */
