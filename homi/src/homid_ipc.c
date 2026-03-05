#include <errno.h>
#include <stdint.h>
#include <pthread.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#include <homid_ipc.h>
#include <homid_log.h>
#include <homi_proto.h>

static int
_open_socket(char *socket_path)
{
	struct sockaddr_un saddr;
	int fd, err = 0;

	fd = socket(AF_LOCAL, SOCK_STREAM, 0);
	if (fd < 0) {
		homid_log(LOG_ERR, "Failed: socket(); err(%d)", errno);
		return -errno;
	}

	saddr.sun_family = AF_LOCAL;
	strncpy(saddr.sun_path, socket_path, sizeof(saddr.sun_path));
	saddr.sun_path[sizeof(saddr.sun_path) - 1] = '\0';

	err = bind(fd, (struct sockaddr *)&saddr, sizeof(saddr));
	if (err) {
		homid_log(LOG_ERR, "Failed: bind(); err(%d)", errno);
		close(fd);
		return -errno;
	}

	return fd;
}

int
homid_ipc_open(char *socket_path, struct homid_ipc_connection **conn)
{
	struct homid_ipc_connection *cand;
	int fd, err = 0;

	cand = calloc(1, sizeof(*cand));
	if (!cand) {
		err = -errno;
		homid_log(LOG_CRIT, "Failed: calloc(); errno(%d)", err);
		return err;
	}

	fd = _open_socket(socket_path);
	if (fd < 0) {
		err = fd;
		homid_log(LOG_ERR, "Failed: _open_socket(); err(%d)", err);
		goto failed;
	}
	cand->fd = fd;

	err = listen(fd, HOMI_MAX_CONNECTS);
	if (err) {
		err = -errno;
		homid_log(LOG_ERR, "Failed: listen(); err(%d)", err);
		goto failed;
	}

	homid_log(LOG_INFO, "Listening for client connections ...");

	*conn = cand;

	return 0;

failed:
	homid_ipc_close(cand);

	return err;
}

void
homid_ipc_close(struct homid_ipc_connection *conn)
{
	if (!conn) {
		homid_log(LOG_INFO, "No homid_ipc_connection given; skipping homid_ipc_close()");
		return;
	}

	if (conn->fd >= 0) {
		close(conn->fd);
	}
}

static void *
worker(void *arg)
{
	int sock_fd = (int)(intptr_t)arg;
	struct homi_msg_header hdr;
	char *payload;
	int err;

	err = homi_proto_socket_read(sock_fd, &hdr, &payload);
	if (err) {
		homid_log(LOG_ERR, "Failed: homi_proto_socket_read(hdr); err(%d)", err);
		goto exit;
	}

	switch ((enum homi_msg_type)hdr.type) {
	case HOMI_MSG_TYPE_HELLOWORLD: {
		struct homi_req_helloworld *request = (struct homi_req_helloworld *)payload;
		char *response;

		if (!request) {
			homid_log(LOG_ERR, "Error: Payload required for HELLOWORLD request");
			goto exit;
		}

		homid_log(LOG_INFO, "Helloworld: received %d", request->value);

		response = "hello world!";
		hdr.payload_len = strlen(response) + 1;

		err = homi_proto_socket_write(sock_fd, &hdr, response, strlen(response) + 1);
		if (err) {
			homid_log(LOG_ERR, "Failed: homi_proto_socket_write(); err(%d)", err);
			goto exit;
		}

		break;
	}
	default:
		homid_log(LOG_WARNING, "Unknown message type: %u", hdr.type);
		break;
	}

exit:
	free(payload);
	close(sock_fd);
	return NULL;
}

int
homid_ipc_accept(struct homid_ipc_connection *conn)
{
	struct sockaddr addr;
	pthread_t thr_id;
	uint32_t len;
	int client_fd, err;

	len = sizeof(addr);

	homid_log(LOG_DEBUG, "Waiting for incoming connections...\n");
	client_fd = accept(conn->fd, &addr, &len);

	if (client_fd < 0) {
		homid_log(LOG_WARNING, "Failed: accept(); continuing");
		return 0;
	}

	err = pthread_create(&thr_id, NULL, worker, (void *)(intptr_t)client_fd);
	if (err) {
			homid_log(LOG_ERR, "Failed: pthread_create(); err(%d)", err);
			return err;
	}

	return 0;
}
