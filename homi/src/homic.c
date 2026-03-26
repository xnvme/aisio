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
	char *socket_path;
	size_t shm_xal_count;
	struct homic_shm_xal *shm_xal;
};

static struct homic_client *g_homic_client = NULL;

static int
_connect(char *socket_path)
{
	struct sockaddr_un saddr;
	int sock_fd, err;

	sock_fd = socket(AF_LOCAL, SOCK_STREAM, 0);
	if (sock_fd < 0) {
		err = -errno;
		fprintf(stderr, "Failed: socket(); err(%d)\n", err);
		return err;
	}

	saddr.sun_family = AF_LOCAL;
	strncpy(saddr.sun_path, socket_path, sizeof(saddr.sun_path));
	saddr.sun_path[sizeof(saddr.sun_path) - 1] = '\0';

	err = connect(sock_fd, (struct sockaddr *)&saddr, sizeof(saddr));
	if (err) {
		err = -errno;
		fprintf(stderr, "Failed: connect(); err(%d)\n", err);
		close(sock_fd);
		return err;
	}

	return sock_fd;
}

int
homic_connect(char *socket_path)
{
	struct homic_client *cand;
	int sock_fd, err;

	cand = calloc(1, sizeof(*cand));
	if (!cand) {
		err = -errno;
		fprintf(stderr, "Failed: calloc(); err(%d)\n", err);
		return err;
	}

	sock_fd = _connect(socket_path);
	if (sock_fd < 0) {
		err = sock_fd;
		goto failed;
	}
	close(sock_fd);

	cand->socket_path = strdup(socket_path);
	if (!cand->socket_path) {
		err = -ENOMEM;
		goto failed;
	}

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

	free(g_homic_client->socket_path);

	for (size_t i = 0; i < g_homic_client->shm_xal_count; i++) {
		struct homic_shm_xal *xal = &g_homic_client->shm_xal[i];

		munmap(xal->inodes_mem, xal->inodes_size);
		munmap(xal->extents_mem, xal->extents_size);
	}
	free(g_homic_client->shm_xal);

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
	int sock_fd = -1, err;

	if (!g_homic_client) {
		err = -ENOTCONN;
		fprintf(stderr, "Failed: No connection, please call homic_client_connect(); err(%d)\n", err);
		return err;
	}

	sock_fd = _connect(g_homic_client->socket_path);
	if (sock_fd < 0) {
		err = sock_fd;
		fprintf(stderr, "Failed: _connect(%s); err(%d)\n", g_homic_client->socket_path, err);
		goto failed;
	}

	req.value = value;
	hdr.type = msg_type;
	hdr.payload_len = sizeof(req);

	err = homi_proto_socket_write(sock_fd, &hdr, &req, sizeof(req));
	if (err) {
		fprintf(stderr, "Failed: homi_proto_socket_write(hdr); err(%d)\n", err);
		goto failed;
	}

	err = homi_proto_socket_read(sock_fd, &hdr, (void **)&response);
	if (err) {
		fprintf(stderr, "Failed: homi_proto_socket_read(hdr); err(%d)\n", err);
		goto failed;
	}

	close(sock_fd);
	*out = response;
	return 0;

failed:
	if (sock_fd >= 0) {
		close(sock_fd);
	}
	return err;
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
	struct homic_shm_xal *shm_xal;
	struct xal_sb sb;
	struct stat st;
	char shm_name[64], shm_name_inodes[80], shm_name_extents[80];
	char mountpoint_buf[XAL_PATH_MAXLEN + 1];
	const char *mountpoint = NULL;
	size_t inodes_size, extents_size, new_count;
	void *inodes_mem, *extents_mem;
	int sock_fd = -1, shm_fd = -1, err;

	if (!g_homic_client) {
		err = -ENOTCONN;
		fprintf(stderr, "Failed: No connection, please call homic_connect(); err(%d)\n", err);
		return err;
	}

	sock_fd = _connect(g_homic_client->socket_path);
	if (sock_fd < 0) {
		err = sock_fd;
		fprintf(stderr, "Failed: _connect(%s); err(%d)\n", g_homic_client->socket_path, err);
		goto failed;
	}

	strncpy(req.dev_uri, dev_uri, sizeof(req.dev_uri) - 1);
	hdr.type = HOMI_MSG_TYPE_XAL_CONNECT;

	err = homi_proto_socket_write(sock_fd, &hdr, &req, sizeof(req));
	if (err) {
		fprintf(stderr, "Failed: homi_proto_socket_write(); err(%d)\n", err);
		goto failed;
	}

	err = homi_proto_socket_read(sock_fd, &hdr, (void **)&res);
	if (err) {
		fprintf(stderr, "Failed: homi_proto_socket_read(); err(%d)\n", err);
		goto failed;
	}
	if (res->err) {
		fprintf(stderr, "Failed: homi_proto_socket_read(); err(%d)\n", res->err);
		goto failed;
	}

	close(sock_fd);
	sock_fd = -1;

	/* Copy out of shm before any further operations touch the segment. */
	sb = res->sb;
	memcpy(shm_name, res->shm_name, sizeof(shm_name));

	if (!retrieve_mountpoint(dev_uri, mountpoint_buf)) {
		mountpoint = mountpoint_buf;
	}

	snprintf(shm_name_inodes, sizeof(shm_name_inodes), "%s_inodes", shm_name);
	snprintf(shm_name_extents, sizeof(shm_name_extents), "%s_extents", shm_name);

	shm_fd = shm_open(shm_name_inodes, O_RDONLY, 0);
	if (shm_fd < 0) {
		err = -errno;
		fprintf(stderr, "Failed: shm_open(inodes); err(%d)\n", err);
		goto failed;
	}

	err = fstat(shm_fd, &st);
	if (err) {
		err = -errno;
		fprintf(stderr, "Failed: fstat(inodes); err(%d)\n", err);
		goto failed;
	}

	inodes_size = st.st_size;
	inodes_mem = mmap(NULL, st.st_size, PROT_READ, MAP_SHARED, shm_fd, 0);

	close(shm_fd);
	shm_fd = -1;

	if (inodes_mem == MAP_FAILED) {
		err = -errno;
		fprintf(stderr, "Failed: mmap(inodes); err(%d)\n", err);
		goto failed;
	}

	shm_fd = shm_open(shm_name_extents, O_RDONLY, 0);
	if (shm_fd < 0) {
		err = -errno;
		fprintf(stderr, "Failed: shm_open(extents); err(%d)\n", err);
		goto unmap_inodes;
	}

	err = fstat(shm_fd, &st);
	if (err) {
		err = -errno;
		fprintf(stderr, "Failed: fstat(extents); err(%d)\n", err);
		goto unmap_inodes;
	}

	extents_size = st.st_size;
	extents_mem = mmap(NULL, extents_size, PROT_READ, MAP_SHARED, shm_fd, 0);

	close(shm_fd);
	shm_fd = -1;

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

	new_count = g_homic_client->shm_xal_count + 1;

	if (g_homic_client->shm_xal) {
		shm_xal = realloc(g_homic_client->shm_xal, new_count * sizeof(*shm_xal));
	} else {
		shm_xal = malloc(new_count * sizeof(*shm_xal));
	}
	if (!shm_xal) {
		err = -ENOMEM;
		goto unmap_extents;
	}

	shm_xal[new_count - 1].inodes_mem = inodes_mem;
	shm_xal[new_count - 1].inodes_size = inodes_size;
	shm_xal[new_count - 1].extents_mem = extents_mem;
	shm_xal[new_count - 1].extents_size = extents_size;
	g_homic_client->shm_xal = shm_xal;
	g_homic_client->shm_xal_count = new_count;

	return 0;

unmap_extents:
	munmap(extents_mem, extents_size);
unmap_inodes:
	munmap(inodes_mem, inodes_size);
failed:
	if (shm_fd >= 0) {
		close(shm_fd);
	}
	if (sock_fd >= 0) {
		close(sock_fd);
	}

	return err;
}
