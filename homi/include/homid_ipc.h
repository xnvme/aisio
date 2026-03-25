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
 * @param socket_path  Path to the socket
 * @param conn         Output: allocated connection object on success.
 * @return             0 on success, negative errno on failure.
 */
int
homid_ipc_open(char *socket_path, struct homid_ipc_connection **conn);

/**
 * Close the IPC listener socket and free the connection.
 *
 * @param conn  Connection to close. Safe to call with NULL.
 */
void
homid_ipc_close(struct homid_ipc_connection *conn);

/**
 * Accept an incoming client connection and dispatch a worker thread.
 *
 * Blocks until a client connects, then spawns a pthread to handle the
 * request. Returns immediately after the thread is created, ready to
 * be called again for the next connection.
 *
 * @param homid  Daemon state
 * @return       0 on success, negative errno on failure.
 */
int
homid_ipc_accept(struct homid *homid);

#endif /* HOMID_IPC_H */
