#include <errno.h>
#include <semaphore.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/shm.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#include <homic.h>
#include <homi_proto.h>

struct homic_client {
	int shmid;
	struct homi_shm *shm;
};

static struct homic_client *g_homic_client = NULL;

int
homic_connect(char *socket_path)
{
	struct homic_client *cand;
	struct sockaddr_un saddr;
	ssize_t n;
	int fd, shmid, err;

	cand = calloc(1, sizeof(*cand));
	if (!cand) {
		err = -errno;
		fprintf(stderr, "Failed: calloc(); err(%d)\n", err);
		return err;
	}

	fd = socket(AF_LOCAL, SOCK_STREAM, 0);
	if (fd < 0) {
		err = -errno;
		fprintf(stderr, "Failed: socket(); err(%d)\n", err);
		goto failed;
	}

	saddr.sun_family = AF_LOCAL;
	strncpy(saddr.sun_path, socket_path, sizeof(saddr.sun_path));
	saddr.sun_path[sizeof(saddr.sun_path) - 1] = '\0';

	err = connect(fd, (struct sockaddr *)&saddr, sizeof(saddr));
	if (err) {
		err = -errno;
		fprintf(stderr, "Failed: connect(); err(%d)\n", err);
		close(fd);
		goto failed;
	}

	n = read(fd, &shmid, sizeof(shmid));
	if (n != (ssize_t)sizeof(shmid)) {
		err = -EIO;
		fprintf(stderr, "Failed: read(shmid); err(%d)\n", err);
		close(fd);
		goto failed;
	}

	close(fd);

	cand->shm = shmat(shmid, NULL, 0);
	if (cand->shm == (void *)-1) {
		err = -errno;
		fprintf(stderr, "Failed: shmat(); err(%d)\n", err);
		cand->shm = NULL;
		goto failed;
	}

	cand->shmid = shmid;
	g_homic_client = cand;

	return 0;

failed:
	free(cand);
	return err;
}

void
homic_disconnect()
{
	if (!g_homic_client) {
		return;
	}

	if (g_homic_client->shm) {
		g_homic_client->shm->done = 1;
		sem_post(&g_homic_client->shm->req_ready);
		shmdt(g_homic_client->shm);
	}

	free(g_homic_client);
	g_homic_client = NULL;
}

int
homic_helloworld(int32_t value, char **out)
{
	struct homi_msg_header hdr = {0};
	struct homi_req_helloworld req = {0};
	enum homi_msg_type msg_type = HOMI_MSG_TYPE_HELLOWORLD;
	char *response = NULL;
	int err;

	if (!g_homic_client) {
		err = -ENOTCONN;
		fprintf(stderr, "Failed: No connection, please call homic_connect(); err(%d)\n", err);
		return err;
	}

	req.value = value;
	hdr.type = msg_type;

	err = homi_proto_shm_write(g_homic_client->shm, &hdr, &req, sizeof(req));
	if (err) {
		fprintf(stderr, "Failed: homi_proto_shm_write(); err(%d)\n", err);
		return err;
	}

	sem_post(&g_homic_client->shm->req_ready);
	sem_wait(&g_homic_client->shm->res_ready);

	err = homi_proto_shm_read(g_homic_client->shm, &hdr, &response);
	if (err) {
		fprintf(stderr, "Failed: homi_proto_shm_read(); err(%d)\n", err);
		return err;
	}

	*out = strdup(response);
	if (!*out) {
		return -ENOMEM;
	}

	return 0;
}
