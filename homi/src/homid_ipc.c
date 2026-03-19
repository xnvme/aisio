#include <errno.h>
#include <pthread.h>
#include <semaphore.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ipc.h>
#include <sys/shm.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#include <homid.h>
#include <homid_ipc.h>
#include <homid_log.h>
#include <homi_proto.h>

struct worker_args {
	int shmid;
	struct homi_shm *shm;
	struct homid *homid;
};

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

	unlink(socket_path);
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

	homid_log(LOG_INFO, "Listening for client connections on %s", socket_path);

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
	struct worker_args *wargs = arg;
	struct homid *homid = wargs->homid;
	struct homi_msg_header hdr;
	void *payload;
	int err;

	homid_log(LOG_NOTICE, "New client connected with shmid(%d); Listening for requests ...", wargs->shmid);

	while (1) {
		sem_wait(&wargs->shm->req_ready);

		if (wargs->shm->done) {
			break;
		}

		err = homi_proto_shm_read(wargs->shm, &hdr, &payload);
		if (err) {
			homid_log(LOG_ERR, "Failed: homi_proto_shm_read(); err(%d)", err);
			sem_post(&wargs->shm->res_ready);
			continue;
		}

		switch ((enum homi_msg_type)hdr.type) {
		case HOMI_MSG_TYPE_HELLOWORLD:
			struct homi_req_helloworld *request = (struct homi_req_helloworld *)payload;
			char *response = "hello world!";

			if (!request) {
				homid_log(LOG_ERR, "Error: Payload required for HELLOWORLD request");
				break;
			}

			homid_log(LOG_INFO, "Helloworld: received %d", request->value);

			err = homi_proto_shm_write(wargs->shm, &hdr, response, strlen(response) + 1);
			if (err) {
				homid_log(LOG_ERR, "Failed: homi_proto_shm_write(); err(%d)", err);
			}

			break;
		}
		default:
			homid_log(LOG_WARNING, "Unknown message type: %u", hdr.type);
			break;
		}

		sem_post(&wargs->shm->res_ready);
	}

	sem_destroy(&wargs->shm->req_ready);
	sem_destroy(&wargs->shm->res_ready);
	shmdt(wargs->shm);
	shmctl(wargs->shmid, IPC_RMID, NULL);

	homid_log(LOG_NOTICE, "Client with shmid(%d) disconnected", wargs->shmid);

	free(wargs);

	return NULL;
}

int
homid_ipc_accept(struct homid *homid)
{
	struct homid_ipc_connection *conn;
	struct worker_args *wargs;
	pthread_t thr_id;
	ssize_t n;
	int client_fd, err;

	if (!homid) {
		homid_log(LOG_ERR, "Error: No homid struct given");
		return -EINVAL;
	}

	conn = homid->conn;

	homid_log(LOG_DEBUG, "Waiting for incoming connections...");

	client_fd = accept(conn->fd, NULL, NULL);
	if (client_fd < 0) {
		homid_log(LOG_WARNING, "Failed: accept(); continuing");
		return 0;
	}

	wargs = calloc(1, sizeof(*wargs));
	if (!wargs) {
		err = -errno;
		homid_log(LOG_CRIT, "Failed: calloc(); err(%d)", err);
		close(client_fd);
		return err;
	}

	wargs->shmid = shmget(IPC_PRIVATE, sizeof(struct homi_shm), 0660);
	if (wargs->shmid < 0) {
		err = -errno;
		homid_log(LOG_ERR, "Failed: shmget(); err(%d)", err);
		goto failed;
	}

	wargs->shm = shmat(wargs->shmid, NULL, 0);
	if (wargs->shm == (void *)-1) {
		err = -errno;
		homid_log(LOG_ERR, "Failed: shmat(); err(%d)", err);
		wargs->shm = NULL;
		goto failed;
	}

	wargs->shm->done = 0;
	wargs->homid = homid;

	err = sem_init(&wargs->shm->req_ready, 1, 0);
	if (err < 0) {
		err = -errno;
		homid_log(LOG_ERR, "Failed: sem_init(req_ready); err(%d)", err);
		goto failed;
	}

	err = sem_init(&wargs->shm->res_ready, 1, 0);
	if (err < 0) {
		err = -errno;
		homid_log(LOG_ERR, "Failed: sem_init(res_ready); err(%d)", err);
		goto failed;
	}

	n = write(client_fd, &wargs->shmid, sizeof(wargs->shmid));
	if (n < 0) {
		err = -errno;
		homid_log(LOG_ERR, "Failed: write(shmid); err(%d)", err);
		goto failed;
	}

	close(client_fd);
	client_fd = -1;

	err = pthread_create(&thr_id, NULL, worker, wargs);
	if (err) {
		err = -err;
		homid_log(LOG_ERR, "Failed: pthread_create(); err(%d)", err);
		goto failed;
	}

	pthread_detach(thr_id);

	return 0;

failed:
	if (wargs->shm) {
		shmdt(wargs->shm);
	}
	if (wargs->shmid >= 0) {
		shmctl(wargs->shmid, IPC_RMID, NULL);
	}
	free(wargs);

	if (client_fd >= 0) {
		close(client_fd);
	}

	return err;
}
