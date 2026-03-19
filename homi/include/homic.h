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

#endif /* HOMIC_H */
