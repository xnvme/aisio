#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <linux/dma-buf.h>
#include <linux/memfd.h>
#include <linux/udmabuf.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

struct buf_udmabuf {
  void *ptr;
  size_t size;
  int dmabuf_fd;
  int memfd;
};

int create_udmabuf(int udmabuf_fd, struct buf_udmabuf *b, size_t size) {
  struct udmabuf_create create;
  int memfd, dmabuf_fd;
  void *p;
  int err;

  memfd = memfd_create("udmabuf-test", MFD_ALLOW_SEALING);
  if (memfd < 0) {
    err = errno;
    printf("Failed to create memfd, errno: %d\n", err);
    return err;
  }

  err = fcntl(memfd, F_ADD_SEALS, F_SEAL_SHRINK);
  if (err) {
    err = errno;
    printf("Failed to set seals, errno: %d\n", err);
    return err;
  }

  err = ftruncate(memfd, size);
  if (err) {
    err = errno;
    printf("Failed to resize udmabuf, errno: %d\n", err);
    return err;
  }

  memset(&create, 0, sizeof(create));
  create.memfd = memfd;
  create.offset = 0;
  create.size = size;
  dmabuf_fd = ioctl(udmabuf_fd, UDMABUF_CREATE, &create);
  if (dmabuf_fd < 0) {
    err = errno;
    printf("Failed to create udmabuf, errno: %d\n", err);
    return err;
  }

  p = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, dmabuf_fd, 0);
  if (p == MAP_FAILED) {
    err = errno;
    printf("Failed to mmap udmabuf, errno: %d\n", err);
    return err;
  }

  b->size = size;
  b->dmabuf_fd = dmabuf_fd;
  b->memfd = memfd;
  b->ptr = p;

  return 0;
}

int main(int argc, char *argv[]) {
  struct udmabuf_attach *attach;
  struct udmabuf_get_map *map;
  struct buf_udmabuf dmabuf;
  int udmabuf_fd, dmabuf_fd, err;
  long buf_size = 8 * 4096;
  long map_size;

  udmabuf_fd = open("/dev/udmabuf", O_RDWR);
  if (udmabuf_fd < 0) {
    err = errno;
    printf("Failed to open udmabuf dev, errno: %d\n", err);
    return err;
  }

  err = create_udmabuf(udmabuf_fd, &dmabuf, buf_size);
  if (err) {
    return err;
  }

  dmabuf_fd = dmabuf.dmabuf_fd;

  printf("DMABUF FD: %d\n", dmabuf_fd);

  attach = malloc(sizeof(struct udmabuf_attach));
  if (!attach) {
    err = errno;
    printf("Failed to alloc attach struct, errno: %d\n", err);
    return err;
  }
  memset(attach, 0, sizeof(*attach));
  attach->fd = dmabuf_fd;

  err = ioctl(udmabuf_fd, UDMABUF_ATTACH, attach);
  if (err) {
    err = errno;
    printf("IOCTL UDMABUF_ATTACH failed, errno: %d\n", err);
    return err;
  }

  printf("dma-buf contains %u addresses\n", attach->count);

  map_size = attach->count * sizeof(struct udmabuf_dma_map);

  map = malloc(sizeof(struct udmabuf_get_map) + map_size);
  if (!map) {
    err = errno;
    printf("Failed to alloc map struct, errno: %d\n", err);
    return err;
  }
  memset(map, 0, sizeof(*map));

  map->fd = dmabuf_fd;
  map->count = attach->count;

  err = ioctl(udmabuf_fd, UDMABUF_GET_MAP, map);
  if (err) {
    err = errno;
    printf("IOCTL UDMABUF_GET_MAP failed, errno: %d\n", err);
    return err;
  }

  for (int i = 0; i < map->count; i++) {
    printf("addr %d: 0x%llx\n", i, map->dma_arr[i].dma_addr);
    printf("len %d: %lld\n", i, map->dma_arr[i].dma_len);
  }

  err = ioctl(udmabuf_fd, UDMABUF_DETACH, &dmabuf_fd);
  if (err) {
    err = errno;
    printf("IOCTL UDMABUF_DETACH failed, errno: %d\n", err);
    return err;
  }

  close(udmabuf_fd);
  free(attach);
  free(map);

  return err;
}