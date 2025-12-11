#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <linux/dma-buf.h>
#include <linux/memfd.h>
#include <linux/udmabuf.h>
#include <linux/uio_driver.h>
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

int create_udmabuf(struct buf_udmabuf *b, size_t size) {
  struct udmabuf_create create;
  int memfd, dmabuf_fd;
  void *p;
  int ret, devfd;

  devfd = open("/dev/udmabuf", O_RDWR);
  if (devfd < 0) {
    printf("Failed to open udmabuf dev, %d\n", devfd);
    return devfd;
  }

  memfd = memfd_create("udmabuf-test", MFD_ALLOW_SEALING);
  if (memfd < 0) {
    printf("Failed to create memfd, %d\n", memfd);
    return memfd;
  }

  ret = fcntl(memfd, F_ADD_SEALS, F_SEAL_SHRINK);
  if (ret < 0) {
    printf("Failed to set seals, %d\n", ret);
    return ret;
  }

  ret = ftruncate(memfd, size);
  if (ret == -1) {
    printf("Failed to resize udmabuf, %d\n", ret);
    return ret;
  }

  memset(&create, 0, sizeof(create));
  create.memfd = memfd;
  create.offset = 0;
  create.size = size;
  dmabuf_fd = ioctl(devfd, UDMABUF_CREATE, &create);
  if (dmabuf_fd < 0) {
    printf("Failed to create udmabuf, %d\n", dmabuf_fd);
    return dmabuf_fd;
  }

  p = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, dmabuf_fd, 0);
  if (p == MAP_FAILED) {
    printf("Failed to mmap udmabuf\n");
    return -1;
  }

  close(devfd);
  b->size = size;
  b->dmabuf_fd = dmabuf_fd;
  b->memfd = memfd;
  b->ptr = p;

  return 0;
}

int main(int argc, char *argv[]) {
  struct uio_attach_dma_buf *attach;
  struct uio_get_dma_map *map;
  struct buf_udmabuf dmabuf;
  int uio_fd, ret;
  long buf_size = 8 * 4096;
  long map_size;

  uio_fd = open("/dev/uio0", O_RDWR);
  if (uio_fd < 0) {
    printf("Failed to open /dev/uio0, %d\n", uio_fd);
    return uio_fd;
  }
  printf("UIO FD: %d\n", uio_fd);

  ret = create_udmabuf(&dmabuf, buf_size);
  if (ret) {
    return ret;
  }

  printf("DMABUF FD: %d\n", dmabuf.dmabuf_fd);

  attach = malloc(sizeof(struct uio_attach_dma_buf));
  if (!attach) {
    printf("Failed to alloc attach struct\n");
    return -1;
  }
  attach->fd = dmabuf.dmabuf_fd;

  ret = ioctl(uio_fd, UIO_ATTACH_DMA_BUF, attach);
  if (ret) {
    ret = errno;
    printf("IOCTL UIO_ATTACH_DMA_BUF failed, %d\n", ret);
    return ret;
  }

  printf("dma-buf contains %u addresses\n", attach->count);

  map_size = attach->count * sizeof(struct uio_dma_map);

  map = malloc(sizeof(struct uio_get_dma_map) + map_size);
  if (!map) {
    printf("Failed to alloc map struct\n");
    return -1;
  }
  memset(map->dma_arr, 0, map_size);

  map->fd = dmabuf.dmabuf_fd;
  map->count = attach->count;

  ret = ioctl(uio_fd, UIO_GET_DMA_MAP, map);
  if (ret) {
    ret = errno;
    printf("IOCTL UIO_GET_DMA_MAP failed, %d\n", ret);
    return ret;
  }

  for (int i = 0; i < map->count; i++) {
    printf("addr %d: 0x%x\n", i, map->dma_arr[i].dma_addr);
    printf("len %d: 0x%x\n", i, map->dma_arr[i].dma_len);
  }

  ret = ioctl(uio_fd, UIO_DETACH_DMA_BUF, &dmabuf.dmabuf_fd);
  if (ret) {
    ret = errno;
    printf("IOCTL UIO_DETACH_DMA_BUF failed, %d\n", ret);
    return ret;
  }

  return ret;
}