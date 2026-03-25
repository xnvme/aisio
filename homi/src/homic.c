#include <errno.h>
#include <fcntl.h>
#include <semaphore.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/shm.h>
#include <sys/stat.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#include <libxal.h>

#include <homic.h>
#include <homi_proto.h>

struct homic_shm_xal {
	size_t inodes_size;
	void *inodes_mem;
	size_t extents_size;
	void *extents_mem;
};

struct homic_client {
	int shmid;
	struct homi_shm *shm;
	size_t shm_xal_count;
	struct homi_shm_xal *shm_xal;
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
	void *response = NULL;
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

static int
retrieve_mountpoint(const char *dev_uri, char *mountpoint)
{
	FILE *f;
	char d[XAL_PATH_MAXLEN + 1], m[XAL_PATH_MAXLEN + 1];
	bool found = false;

	f = fopen("/proc/mounts", "r");
	if (!f) {
		return -errno;
	}

	while (fscanf(f, "%s %s%*[^\n]\n", d, m) == 2) {
		if (strcmp(d, dev_uri) == 0) {
			strcpy(mountpoint, m);
			found = true;
			break;
		}
	}

	fclose(f);

	return found ? 0 : -ENOENT;
}

int
homic_connect_xal(char *dev_uri, struct xal **out)
{
	struct homi_msg_header hdr = {0};
	struct homi_req_xal_connect req = {0};
	struct homi_res_xal_connect *res;
	struct xal_sb sb;
	struct stat st;
	char shm_name[64], shm_name_inodes[80], shm_name_extents[80];
	char mountpoint_buf[XAL_PATH_MAXLEN + 1];
	const char *mountpoint = NULL;
	struct homic_shm_xal shm_xal = {0};
	size_t inodes_size, extents_size;
	void *inodes_mem, *extents_mem;
	int fd, err;

	if (!g_homic_client) {
		err = -ENOTCONN;
		fprintf(stderr, "Failed: No connection, please call homic_connect(); err(%d)\n", err);
		return err;
	}

	strncpy(req.dev_uri, dev_uri, sizeof(req.dev_uri) - 1);
	hdr.type = HOMI_MSG_TYPE_XAL_CONNECT;

	err = homi_proto_shm_write(g_homic_client->shm, &hdr, &req, sizeof(req));
	if (err) {
		fprintf(stderr, "Failed: homi_proto_shm_write(); err(%d)\n", err);
		return err;
	}

	sem_post(&g_homic_client->shm->req_ready);
	sem_wait(&g_homic_client->shm->res_ready);

	err = homi_proto_shm_read(g_homic_client->shm, &hdr, (void **)&res);
	if (err) {
		fprintf(stderr, "Failed: homi_proto_shm_read(); err(%d)\n", err);
		return err;
	}
	if (res->err) {
		return res->err;
	}

	/* Copy out of shm before any further operations touch the segment. */
	sb = res->sb;
	memcpy(shm_name, res->shm_name, sizeof(shm_name));

	if (!retrieve_mountpoint(dev_uri, mountpoint_buf)) {
		mountpoint = mountpoint_buf;
	}

	snprintf(shm_name_inodes, sizeof(shm_name_inodes), "%s_inodes", shm_name);
	snprintf(shm_name_extents, sizeof(shm_name_extents), "%s_extents", shm_name);

	fd = shm_open(shm_name_inodes, O_RDONLY, 0);
	if (fd < 0) {
		err = -errno;
		fprintf(stderr, "Failed: shm_open(inodes); err(%d)\n", err);
		goto failed;
	}

	err = fstat(fd, &st);
	if (err) {
		err = -errno;
		fprintf(stderr, "Failed: fstat(inodes); err(%d)\n", err);
		goto failed;
	}

	inodes_size = st.st_size;
	inodes_mem = mmap(NULL, st.st_size, PROT_READ, MAP_SHARED, fd, 0);

	close(fd);
	fd = -1;

	if (inodes_mem == MAP_FAILED) {
		err = -errno;
		fprintf(stderr, "Failed: mmap(inodes); err(%d)\n", err);
		goto failed;
	}

	fd = shm_open(shm_name_extents, O_RDONLY, 0);
	if (fd < 0) {
		err = -errno;
		fprintf(stderr, "Failed: shm_open(extents); err(%d)\n", err);
		goto unmap_inodes;
	}

	err = fstat(fd, &st);
	if (err) {
		err = -errno;
		fprintf(stderr, "Failed: fstat(extents); err(%d)\n", err);
		goto unmap_inodes;
	}

	extents_size = st.st_size;
	extents_mem = mmap(NULL, extents_size, PROT_READ, MAP_SHARED, fd, 0);

	close(fd);
	fd = -1;

	if (extents_mem == MAP_FAILED) {
		err = -errno;
		fprintf(stderr, "Failed: mmap(extents); err(%d)\n", err);
		goto unmap_inodes;
	}

	err = xal_from_pools(&sb, mountpoint, inodes_mem, extents_mem, out);
	if (err) {
		fprintf(stderr, "Failed: xal_from_pools(); err(%d)\n", err);
		goto unmap_extents;
	}

	return err;

unmap_extents:
	munmap(extents_mem, extents_size);
unmap_inodes:
	munmap(inodes_mem, inodes_size);
failed:
	if (fd >= 0) {
		close(fd);
	}

	return err;
}
