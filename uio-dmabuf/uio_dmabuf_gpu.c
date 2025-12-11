#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <linux/dma-buf.h>
#include <linux/uio_driver.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>

#include <cuda.h>

struct gpu_dmabuf_info {
  CUmemGenericAllocationHandle dmabuf_fd;
  CUdeviceptr vaddr;
  CUcontext ctx;
};

int create_nvidia_dmabuf_fd(struct gpu_dmabuf_info *gdi, size_t buf_size) {
  CUmemGenericAllocationHandle dmabuf_fd;
  CUdeviceptr vaddr;
  CUdevice dev;
  CUcontext ctx;
  CUresult res;
  int gpu_id = 0;

  res = cuInit(0);
  if (res != CUDA_SUCCESS) {
    printf("cuInit failed with error code %d\n", res);
    return 1;
  }

  res = cuDeviceGet(&dev, gpu_id);
  if (res != CUDA_SUCCESS) {
    printf("cuDeviceGet failed with error code %d\n", res);
    return 1;
  }

  res = cuCtxCreate(&ctx, 0, dev);
  if (res != CUDA_SUCCESS) {
    printf("cuCtxCreate failed with error code %d\n", res);
    return 1;
  }

  res = cuMemAlloc(&vaddr, buf_size);
  if (res != CUDA_SUCCESS) {
    printf("cuMemAlloc failed with error code %d\n", res);
    return 1;
  }

  res = cuMemGetHandleForAddressRange(&dmabuf_fd, vaddr, buf_size,
                                      CU_MEM_RANGE_HANDLE_TYPE_DMA_BUF_FD, 0);
  if (res != CUDA_SUCCESS) {
    printf("cuMemGetHandleForAddressRange failed with error code %d\n", res);
    return 1;
  }

  gdi->dmabuf_fd = dmabuf_fd;
  gdi->vaddr = vaddr;
  gdi->ctx = ctx;

  return 0;
}

int destroy_nvidia_dmabuf_fd(struct gpu_dmabuf_info *gdi) {
  cuCtxDestroy(gdi->ctx);
  cuMemFree(gdi->vaddr);
  return 0;
}

int main(int argc, char *argv[]) {
  struct uio_attach_dma_buf *attach;
  struct uio_get_dma_map *map;
  struct gpu_dmabuf_info gpu_dmabuf_info;
  int uio_fd, dmabuf_fd, ret;
  size_t buf_size = 8 * 65536; // 8 GPU pages
  long map_size;

  uio_fd = open("/dev/uio0", O_RDWR);
  if (uio_fd < 0) {
    printf("Failed to open /dev/uio0, %d\n", uio_fd);
    return uio_fd;
  }
  printf("UIO FD: %d\n", uio_fd);
  ret = create_nvidia_dmabuf_fd(&gpu_dmabuf_info, buf_size);
  if (ret) {
    fprintf(stderr, "DMABUF setup failed: %d\n", ret);
    return 1;
  }

  dmabuf_fd = (int)gpu_dmabuf_info.dmabuf_fd;

  printf("DMABUF FD: %d\n", dmabuf_fd);

  attach = malloc(sizeof(struct uio_attach_dma_buf));
  if (!attach) {
    printf("Failed to alloc attach struct\n");
    return -1;
  }
  attach->fd = dmabuf_fd;

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

  map->fd = dmabuf_fd;
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

  ret = ioctl(uio_fd, UIO_DETACH_DMA_BUF, &dmabuf_fd);
  if (ret) {
    ret = errno;
    printf("IOCTL UIO_DETACH_DMA_BUF failed, %d\n", ret);
    return ret;
  }

  destroy_nvidia_dmabuf_fd(&gpu_dmabuf_info);

  return ret;
}