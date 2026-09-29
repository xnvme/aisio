// SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
//
// SPDX-License-Identifier: BSD-3-Clause
/*
 * Import a CUDA dma-buf through /dev/dmabuf_import, as uPCIe's misc device and
 * optionally on behalf of a PCI device, and print what each import returns.
 */

#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include <cuda.h>
#include <linux/dmabuf_import.h>

/* cuCtxCreate takes the CUctxCreateParams argument from CUDA 13.0 on, where
 * the alias moved from cuCtxCreate_v2 to cuCtxCreate_v4. 12.5 introduced the v4
 * entry point but kept the alias on v2, so the arity follows the major. */
#if CUDA_VERSION >= 13000
#define CU_CTX_CREATE(pctx, flags, dev) cuCtxCreate((pctx), NULL, (flags), (dev))
#else
#define CU_CTX_CREATE(pctx, flags, dev) cuCtxCreate((pctx), (flags), (dev))
#endif

static const char *
cuda_err_name(CUresult res)
{
	const char *name = "unknown";

	cuGetErrorString(res, &name);
	return name;
}

#define CHECK_CU(expr)                                                         \
	do {                                                                       \
		CUresult _r = (expr);                                                  \
		if (_r != CUDA_SUCCESS) {                                              \
			fprintf(stderr, "FAILED: %s: %s (%d)\n", #expr,                   \
				cuda_err_name(_r), (int)_r);                                   \
			goto out;                                                          \
		}                                                                      \
	} while (0)

static void
fmt_bytes(uint64_t v, char *buf, size_t cap)
{
	static const char *units[] = {"B", "KiB", "MiB", "GiB", "TiB"};
	int u = 0;
	double d = (double)v;

	while (d >= 1024.0 && u < 4) {
		d /= 1024.0;
		u++;
	}

	if (u == 0)
		snprintf(buf, cap, "%" PRIu64 " B", v);
	else
		snprintf(buf, cap, "%.2f %s", d, units[u]);
}

/* Print one check as "ok" or "FAIL" and return nonzero when it failed. */
static int
check(int ok, const char *fmt, ...)
{
	va_list ap;

	printf("%s ", ok ? "ok  " : "FAIL");
	va_start(ap, fmt);
	vprintf(fmt, ap);
	va_end(ap);
	printf("\n");
	return !ok;
}

/* What one import returned, kept for the findings that compare the two. */
struct variant {
	int ok;
	uint32_t count;
	uint64_t first;
	uint64_t smallest;
	uint64_t largest;
};

static int
run_variant(const char *label, int dmabuf_fd, const char *bdf, size_t nbytes,
	    struct variant *res)
{
	struct dmabuf_import_attach_bdf attach_bdf;
	struct dmabuf_import_get_map *map = NULL;
	struct dmabuf_import_describe describe;
	uint32_t count;
	uint64_t total = 0, prev_end = 0;
	uint64_t smallest = UINT64_MAX, largest = 0;
	char len[32], smallest_s[32], largest_s[32], total_s[32], nbytes_s[32];
	int import_fd = -1;
	int contiguous = 1;
	int ret = 1;

	memset(res, 0, sizeof(*res));
	printf("\n== %s ==\n", label);

	import_fd = open(DMABUF_IMPORT_DEVPATH, O_RDWR);
	if (import_fd < 0) {
		fprintf(stderr, "FAILED: open(%s): %s; is the module loaded?\n",
			DMABUF_IMPORT_DEVPATH, strerror(errno));
		goto out;
	}

	memset(&attach_bdf, 0, sizeof(attach_bdf));
	attach_bdf.fd = dmabuf_fd;
	if (bdf)
		snprintf(attach_bdf.bdf, sizeof(attach_bdf.bdf), "%s", bdf);
	/* An empty bdf attaches as the misc device, which is what the upcie-cuda
	 * backend does. ATTACH_BDF owns the import per descriptor, so even a
	 * process killed mid-run cannot leak it into the module's fd table. */
	if (ioctl(import_fd, DMABUF_IMPORT_ATTACH_BDF, &attach_bdf)) {
		fprintf(stderr, "FAILED: DMABUF_IMPORT_ATTACH_BDF(%s): %s\n",
			bdf ? bdf : "", strerror(errno));
		goto out;
	}
	count = attach_bdf.count;
	printf("attach: %u dma segment%s\n", count, count == 1 ? "" : "s");
	if (!count) {
		fprintf(stderr, "FAILED: ATTACH_BDF returned no segments\n");
		goto out;
	}

	map = malloc(sizeof(*map) + (size_t)count * sizeof(map->dma_arr[0]));
	if (!map) {
		fprintf(stderr, "FAILED: malloc(%u segments): %s\n", count,
			strerror(errno));
		goto out;
	}
	memset(map, 0, sizeof(*map));
	map->fd = dmabuf_fd;
	map->count = count;

	if (ioctl(import_fd, DMABUF_IMPORT_GET_MAP, map)) {
		fprintf(stderr, "FAILED: DMABUF_IMPORT_GET_MAP: %s\n", strerror(errno));
		goto out;
	}

	/* GET_MAP fills dma_arr but leaves count as passed in, so it cannot say
	 * how many it filled. DESCRIBE below cross-checks the segment count. */
	for (uint32_t i = 0; i < count; i++) {
		struct dmabuf_import_dma_map *m = &map->dma_arr[i];

		fmt_bytes(m->dma_len, len, sizeof(len));
		printf("  [%2u] dma_addr 0x%016" PRIx64 " len %" PRIu64 " (%s)\n",
			i, (uint64_t)m->dma_addr, (uint64_t)m->dma_len, len);

		total += m->dma_len;
		if (m->dma_len < smallest)
			smallest = m->dma_len;
		if (m->dma_len > largest)
			largest = m->dma_len;
		if (i > 0 && prev_end != m->dma_addr)
			contiguous = 0;
		prev_end = m->dma_addr + m->dma_len;
	}

	fmt_bytes(total, total_s, sizeof(total_s));
	fmt_bytes(smallest, smallest_s, sizeof(smallest_s));
	fmt_bytes(largest, largest_s, sizeof(largest_s));
	printf("map: %u segment%s, %s total (smallest %s, largest %s)\n",
		count, count == 1 ? "" : "s", total_s, smallest_s, largest_s);
	printf("contiguity: %s\n", contiguous ? "every segment abuts the previous"
					       : "segments are disjoint");
	printf("if mapped as 4 KiB pages: %zu entries (computed, not measured)\n",
	       nbytes / 4096);

	memset(&describe, 0, sizeof(describe));
	describe.fd = dmabuf_fd;
	if (ioctl(import_fd, DMABUF_IMPORT_DESCRIBE, &describe)) {
		fprintf(stderr, "FAILED: DMABUF_IMPORT_DESCRIBE: %s\n",
			strerror(errno));
		goto out;
	}
	printf("describe: exporter=%-16s importer=%-16s segments=%u nbus=%u "
	       "nopage=%u npages=%u pinned=%u nbytes=%" PRIu64 "\n",
		describe.exporter, describe.importer, describe.count,
		describe.nbus, describe.nopage, describe.npages,
		describe.pinned, (uint64_t)describe.nbytes);

	/* Every check is printed, and any failure fails this import: the
	 * addresses above only describe the GPU buffer if all of them hold. */
	fmt_bytes(nbytes, nbytes_s, sizeof(nbytes_s));
	ret = 0;
	ret |= check(total == nbytes && describe.nbytes == nbytes,
		     "the import covers the buffer: %s in segments, %" PRIu64
		     " bytes in DESCRIBE, %s allocated",
		     total_s, (uint64_t)describe.nbytes, nbytes_s);
	ret |= check(describe.npages && describe.nopage == describe.npages,
		     "the buffer is device memory: no struct page behind any entry "
		     "(%u without, of %u)",
		     describe.nopage, describe.npages);
	ret |= check(describe.count == count,
		     "DESCRIBE and the import agree on the segment count "
		     "(%u and %u)",
		     describe.count, count);

	res->ok = !ret;
	res->count = count;
	res->first = map->dma_arr[0].dma_addr;
	res->smallest = smallest;
	res->largest = largest;

out:
	free(map);
	if (import_fd >= 0) {
		ioctl(import_fd, DMABUF_IMPORT_DETACH, &dmabuf_fd);
		close(import_fd);
	}
	return ret;
}

static void
print_pieces(const char *label, const struct variant *v, const char *where)
{
	char smallest_s[32], largest_s[32];

	fmt_bytes(v->smallest, smallest_s, sizeof(smallest_s));
	fmt_bytes(v->largest, largest_s, sizeof(largest_s));
	if (v->smallest == v->largest)
		printf("%s: %u x %s %s 0x%" PRIx64 "\n", label, v->count, smallest_s,
		       where, v->first);
	else
		printf("%s: %u segments of %s to %s %s 0x%" PRIx64 "\n", label, v->count,
		       smallest_s, largest_s, where, v->first);
}

/*
 * The misc device is behind no IOMMU, so its first address is the buffer's
 * physical address. The PCI device's first address equals it when nothing
 * translates for that device, and is an IOVA when its IOMMU domain does.
 */
static void
report_findings(const struct variant *misc, const struct variant *peer)
{
	printf("\n== findings: imports ==\n");
	if (!misc->ok || (peer && !peer->ok)) {
		printf("none: an import failed its checks\n");
		return;
	}

	print_pieces("misc device", misc, "from physical");
	if (!peer) {
		printf("translation: unknown, pass --bdf to import for an NVMe\n");
		return;
	}
	print_pieces("PCI device", peer, "at");

	if (peer->first == misc->first)
		printf("translation: none, the device sees physical 0x%" PRIx64
		       " (IOMMU off or passthrough)\n",
		       misc->first);
	else
		printf("translation: the IOMMU maps it, IOVA 0x%" PRIx64
		       " for physical 0x%" PRIx64 "\n",
		       peer->first, misc->first);
	printf("pieces: the exporter cuts the buffer by each importer's DMA max "
	       "segment size\n");
}

int
main(int argc, char *argv[])
{
	const char *bdf = NULL;
	size_t size_mib = 1024;
	int gpu_id = 0;
	CUdevice cu_dev;
	CUcontext ctx = NULL;
	CUdeviceptr vaddr = 0;
	char name[64], bytes_s[32];
	size_t gran_min = 0, gran_rec = 0;
	CUmemAllocationProp prop;
	struct variant misc, peer;
	int dmabuf_fd = -1;
	int ret = 1;

	for (int i = 1; i < argc; i++) {
		if (!strcmp(argv[i], "--size_mib") && i + 1 < argc)
			size_mib = (size_t)atoll(argv[++i]);
		else if (!strcmp(argv[i], "--gpu_id") && i + 1 < argc)
			gpu_id = atoi(argv[++i]);
		else if (!strcmp(argv[i], "--bdf") && i + 1 < argc)
			bdf = argv[++i];
	}

	CHECK_CU(cuInit(0));
	CHECK_CU(cuDeviceGet(&cu_dev, gpu_id));
	CHECK_CU(cuDeviceGetName(name, sizeof(name), cu_dev));
	CHECK_CU(CU_CTX_CREATE(&ctx, 0, cu_dev));

	printf("gpu: %s (device %d)\n", name, gpu_id);

	/* The granularity of cuMemCreate, printed for reference only. The
	 * cuMemAlloc buffer below is not bound to it. */
	memset(&prop, 0, sizeof(prop));
	prop.type = CU_MEM_ALLOCATION_TYPE_PINNED;
	prop.location.type = CU_MEM_LOCATION_TYPE_DEVICE;
	prop.location.id = cu_dev;
	if (cuMemGetAllocationGranularity(&gran_min, &prop,
					  CU_MEM_ALLOC_GRANULARITY_MINIMUM) == CUDA_SUCCESS)
		printf("VMM allocation granularity (minimum):     %zu bytes\n",
		       gran_min);
	if (cuMemGetAllocationGranularity(&gran_rec, &prop,
					  CU_MEM_ALLOC_GRANULARITY_RECOMMENDED) == CUDA_SUCCESS)
		printf("VMM allocation granularity (recommended): %zu bytes\n",
		       gran_rec);

	fmt_bytes((uint64_t)size_mib << 20, bytes_s, sizeof(bytes_s));
	printf("allocating %s (%zu MiB)\n", bytes_s, size_mib);

	CHECK_CU(cuMemAlloc(&vaddr, (size_t)size_mib << 20));

	{
		CUmemGenericAllocationHandle handle;

		CHECK_CU(cuMemGetHandleForAddressRange(
			&handle, vaddr, (size_t)size_mib << 20,
			CU_MEM_RANGE_HANDLE_TYPE_DMA_BUF_FD, 0));
		dmabuf_fd = (int)handle;
	}

	/* Both variants run even when the first one fails, since each is a
	 * separate observation. A failure in either is reported as one. */
	ret = run_variant("misc device (upcie-cuda default)", dmabuf_fd, NULL,
			  (size_t)size_mib << 20, &misc);
	if (bdf && run_variant("PCI device (peer-to-peer path)", dmabuf_fd, bdf,
			       (size_t)size_mib << 20, &peer))
		ret = 1;

	report_findings(&misc, bdf ? &peer : NULL);

out:
	if (dmabuf_fd >= 0)
		close(dmabuf_fd);
	if (vaddr)
		cuMemFree(vaddr);
	if (ctx)
		cuCtxDestroy(ctx);

	return ret;
}
