#ifndef HOMIC_H
#define HOMIC_H

#include <libxal.h>

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

/**
 * Wait until the xal pools are not being reindexed.
 *
 * Spins while the daemon is running xal_index(). Returns once it is safe to
 * read from the xal pools. Requires an active connection established with
 * homic_connect().
 *
 * @param xal  xal instance to wait on.
 * @return     0 on success, negative errno on failure.
 */
int
homic_xal_wait(struct xal *xal);

#endif /* HOMIC_H */
