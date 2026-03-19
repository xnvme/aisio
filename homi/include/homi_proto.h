#ifndef HOMI_PROTO_H
#define HOMI_PROTO_H

#include <semaphore.h>
#include <stdint.h>

#define HOMI_MAX_CONNECTS   8
#define HOMI_SHM_MAX_PAYLOAD 4096

enum homi_msg_type {
	/* TODO: add message types as daemon functionality is extended */
	HOMI_MSG_TYPE_HELLOWORLD = 0, ///< Test type, as an example of what is needed
};

struct homi_req_helloworld {
	int32_t value;
};

struct homi_msg_header {
	enum homi_msg_type type;
	size_t payload_len;
};

/*
 * Layout of the shared memory segment.
 *
 * The server initializes both semaphores to 0 on startup.
 * To issue a request:
 *   1. Write header + payload with homi_proto_shm_write().
 *   2. sem_post(req_ready)  — signals the server.
 *   3. sem_wait(res_ready)  — blocks until the server replies.
 *   4. Read response with homi_proto_shm_read().
 *
 * Before disconnecting, client sets done = 1 and posts req_ready
 */
struct homi_shm {
	sem_t req_ready;
	sem_t res_ready;
	uint8_t done;
	struct homi_msg_header hdr;
	char payload[HOMI_SHM_MAX_PAYLOAD];
};

/**
 * Read the header and payload from the shared memory segment.
 *
 * *buf points directly into the shared memory segment and is valid only until
 * the next sem_post. Callers that need to retain the payload must copy it.
 * *buf is set to NULL when payload_len is zero.
 *
 * @param shm  Attached shared memory segment.
 * @param hdr  Output: populated with the message header.
 * @param buf  Output: pointer into shm->payload, or NULL.
 * @return     0 on success, negative errno on failure.
 */
int
homi_proto_shm_read(struct homi_shm *shm, struct homi_msg_header *hdr, void **buf);

/**
 * Copy hdr and buf into the shared memory segment.
 *
 * Sets hdr->payload_len to buf_len and copies both into shm. The caller is
 * responsible for signalling the appropriate semaphore afterwards.
 *
 * @param shm      Attached shared memory segment.
 * @param hdr      Message header; payload_len is overwritten with buf_len.
 * @param buf      Payload to copy in.
 * @param buf_len  Length of buf in bytes. Must be <= HOMI_SHM_MAX_PAYLOAD.
 * @return         0 on success, -EMSGSIZE if buf_len exceeds the limit.
 */
int
homi_proto_shm_write(struct homi_shm *shm, struct homi_msg_header *hdr,
                     void *buf, size_t buf_len);

/**
 * Read a message from a socket.
 *
 * Reads a homi_msg_header followed by its payload from sock_fd. The payload
 * is heap-allocated and returned via *buf; the caller is responsible for
 * freeing it. *buf is set to NULL if payload_len is zero.
 *
 * @param sock_fd  File descriptor of the connected socket.
 * @param hdr      Output: populated with the received message header.
 * @param buf      Output: allocated buffer containing the payload, or NULL.
 * @return         0 on success, negative errno on failure.
 */
int
homi_proto_socket_read(int sock_fd, struct homi_msg_header *hdr, char **buf);

/**
 * Write a message to a socket.
 *
 * Sends hdr followed by buf as a single framed message. Sets hdr->payload_len
 * to buf_len before writing.
 *
 * @param sock_fd   File descriptor of the connected socket.
 * @param hdr       Message header; payload_len will be overwritten with buf_len.
 * @param buf       Payload to send.
 * @param buf_len   Length of the payload in bytes.
 * @return          0 on success, negative errno on failure.
 */
int
homi_proto_socket_write(int sock_fd, struct homi_msg_header *hdr, void *buf, size_t buf_len);

#endif /* HOMI_PROTO_H */
