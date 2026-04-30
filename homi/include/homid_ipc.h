#ifndef HOMID_IPC_H
#define HOMID_IPC_H

struct homid_ipc_connection {
	int fd;
};

/**
 * Open the IPC listener socket.
 *
 * Creates and binds a Unix domain socket, then starts listening for incoming
 * client connections. The resulting connection object is returned via *conn
 * and must be released with homid_ipc_close().
 *
 * @param socket_path  Path to the Unix domain socket.
 * @param conn         Output: allocated connection object on success.
 * @return             0 on success, negative errno on failure.
 */
int
homid_ipc_open(char *socket_path, struct homid_ipc_connection **conn);

/**
 * Close the IPC listener socket and free the connection. Safe to call with
 * NULL.
 *
 * @param conn  Connection to close.
 */
void
homid_ipc_close(struct homid_ipc_connection *conn);

/**
 * Accept an incoming client connection and dispatch a worker thread.
 *
 * Blocks until a client connects. Creates a per-client shared memory segment,
 * sends its id to the client over the socket, then spawns a detached thread
 * that handles all requests from that client via shared memory. Returns
 * immediately after the thread is created.
 *
 * @param homid  Daemon state
 * @return       0 on success, negative errno on failure.
 */
int
homid_ipc_accept(struct homid *homid);

#endif /* HOMID_IPC_H */
