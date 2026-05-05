#ifndef HOMIC_H
#define HOMIC_H

#include <homi_proto.h>

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

/**
 * Connect to xal for a specific device.
 *
 * Sends an XAL_CONNECT request to the daemon, maps the inode and extent pools
 * from POSIX shared memory, and constructs a read-only xal via xal_from_pools().
 * Also maps the concurrency state shared memory for the device.
 * Requires an active connection established with homic_connect().
 *
 * @param dev_uri    URI of the device to connect to.
 * @param out        Output: read-only xal struct backed by shared memory.
 * @param state_out  Output: read-only xal concurrency state backed by shared memory.
 * @return           0 on success, negative errno on failure.
 */
int
homic_connect_xal(char *dev_uri, struct xal **out, struct homi_xal_state **state_out);

/**
 * Begin a seqlock-protected read from xal shared memory.
 *
 * Checks dirty and spins until no write is in progress, then snapshots the
 * current seq_lock value into *seq_out. The caller must read and copy all needed
 * data from the xal pools before calling homic_xal_read_end(). If dirty is set,
 * the caller should reconnect via homic_connect_xal() and return -ESTALE.
 *
 * @param state    Concurrency state for the xal instance.
 * @param seq_out  Output: current seq_lock value to pass to homic_xal_read_end().
 * @return         0 on success, -ESTALE if the xal tree is dirty and must be refreshed.
 */
int
homic_xal_read_begin(struct homi_xal_state *state, int *seq_out);

/**
 * End a seqlock-protected read from xal shared memory.
 *
 * Verifies that seq_lock has not changed since homic_xal_read_begin(), confirming
 * that the read was consistent. Returns -EAGAIN if the data changed during the read;
 * the caller must discard any data copied and retry from homic_xal_read_begin().
 *
 * @param state  Concurrency state for the xal instance.
 * @param seq    The seq value returned by the matching homic_xal_read_begin() call.
 * @return       0 if the read was consistent, -EAGAIN if it must be retried.
 */
int
homic_xal_read_end(struct homi_xal_state *state, int seq);

#endif /* HOMIC_H */
