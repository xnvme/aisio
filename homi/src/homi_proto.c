#include <errno.h>
#include <stdlib.h>
#include <unistd.h>

#include <homi_proto.h>

static int
_read_from_buffer(int sock_fd, void *buf, size_t len)
{
	size_t done = 0;
	ssize_t n;

	while (done < len) {
		n = read(sock_fd, (char *)buf + done, len - done);
		if (n < 0) {
			return -errno;
		}
		if (n == 0) {
			return -EIO;
		}
		done += n;
	}

	return 0;
}

static int
_write_to_buffer(int sock_fd, void *buf, size_t len)
{
	size_t done = 0;
	ssize_t n;

	while (done < len) {
		n = write(sock_fd, (const char *)buf + done, len - done);
		if (n < 0) {
			return -errno;
		}
		done += n;
	}

	return 0;
}

int
homi_proto_socket_read(int sock_fd, struct homi_msg_header *hdr, char **buf)
{
	char *payload = NULL;
	int err;

	err = _read_from_buffer(sock_fd, hdr, sizeof(*hdr));
	if (err) {
		return err;
	}

	if (hdr->payload_len > 0) {
		payload = malloc(hdr->payload_len);
		if (!payload) {
			err = -errno;
			return err;
		}

		err = _read_from_buffer(sock_fd, payload, hdr->payload_len);
		if (err) {
			free(payload);
			return err;
		}
	}

	*buf = payload;

	return 0;
}

int
homi_proto_socket_write(int sock_fd, struct homi_msg_header *hdr, void *buf, size_t buf_len)
{
	int err;

	hdr->payload_len = (uint32_t)buf_len;

	err = _write_to_buffer(sock_fd, hdr, sizeof(*hdr));
	if (err) {
		return err;
	}

	err = _write_to_buffer(sock_fd, buf, buf_len);
	if (err) {
		return err;
	}

	return 0;
}
