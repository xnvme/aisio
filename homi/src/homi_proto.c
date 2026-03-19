#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <homi_proto.h>

int
homi_proto_shm_read(struct homi_shm *shm, struct homi_msg_header *hdr, void **buf)
{
	*hdr = shm->hdr;
	*buf = hdr->payload_len > 0 ? shm->payload : NULL;

	return 0;
}

int
homi_proto_shm_write(struct homi_shm *shm, struct homi_msg_header *hdr,
                     void *buf, size_t buf_len)
{
	if (buf_len > HOMI_SHM_MAX_PAYLOAD) {
		return -EMSGSIZE;
	}

	hdr->payload_len = buf_len;
	shm->hdr = *hdr;

	if (buf && buf_len > 0) {
		memcpy(shm->payload, buf, buf_len);
	}

	return 0;
}
