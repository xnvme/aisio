#ifndef HOMIC_H
#define HOMIC_H

/**
 * Connect to the homid daemon.
 *
 * Opens a Unix domain socket connection to the daemon. Must be called before
 * any other homic functions. The connection is held globally; call
 * homic_disconnect() to release it.
 *
 * @return  0 on success, negative errno on failure.
 */
int
homic_connect(char *socket_path);

/**
 * Disconnect from the homid daemon.
 *
 * Closes the socket and releases the global connection. Safe to call if not
 * connected.
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
homic_helloworld(int value, char **out);

#endif /* HOMIC_H */
