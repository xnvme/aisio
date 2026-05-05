#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <syslog.h>

#include <libxal.h>
#include <libxnvme.h>

#include <homid.h>
#include <homid_log.h>
#include <homid_xal.h>
#include <homid_opts.h>

static void
on_xal_dirty(struct xal *xal, void *cb_args)
{
	struct homi_xal_state *state = cb_args;

	(void)xal;
	atomic_store(&state->dirty, true);
}

static void
on_xal_seq_lock(struct xal *xal, int seq, void *cb_args)
{
	struct homi_xal_state *state = cb_args;

	(void)xal;
	atomic_store_explicit(&state->seq_lock, seq, memory_order_release);
}

int
homid_xal_setup(struct xal_opts *opts, struct homid_device *device)
{
	char shm_state_name[80];
	struct homi_xal_state *state;
	struct xal *xal;
	int shm_fd, err;

	if (!device) {
		err = -EINVAL;
		homid_log(LOG_ERR, "No homid_device for xal setup: %d", err);
		return err;
	}

	err = xal_open(device->dev, &xal, opts);
	if (err) {
		homid_log(LOG_ERR, "xal_open(): %d", err);
		return err;
	}

	err = xal_dinodes_retrieve(xal);
	if (err) {
		homid_log(LOG_ERR, "xal_dinodes_retrieve(): %d", err);
		goto close_xal;
	}

	err = xal_index(xal);
	if (err) {
		homid_log(LOG_ERR, "xal_index(): %d", err);
		goto close_xal;
	}

	snprintf(shm_state_name, sizeof(shm_state_name), "%s_state", device->shm_name);

	shm_fd = shm_open(shm_state_name, O_CREAT | O_RDWR, 0666);
	if (shm_fd < 0) {
		err = -errno;
		homid_log(LOG_ERR, "shm_open(%s): %d", shm_state_name, err);
		goto close_xal;
	}

	err = ftruncate(shm_fd, sizeof(struct homi_xal_state));
	if (err) {
		err = -errno;
		homid_log(LOG_ERR, "ftruncate(%s): %d", shm_state_name, err);
		close(shm_fd);
		goto unlink_state;
	}

	state = mmap(NULL, sizeof(struct homi_xal_state), PROT_READ | PROT_WRITE, MAP_SHARED, shm_fd, 0);
	close(shm_fd);
	if (state == MAP_FAILED) {
		err = -errno;
		homid_log(LOG_ERR, "mmap(%s): %d", shm_state_name, err);
		goto unlink_state;
	}

	atomic_store(&state->dirty, false);
	atomic_store(&state->seq_lock, 0);

	if (opts->file_lookupmode) {
		err = xal_watch_filesystem(xal, on_xal_dirty, state);
		if (err) {
			homid_log(LOG_WARNING, "xal_watch_filesystem(): %d; dirty detection unavailable", err);
		}
	}

	xal_set_seq_lock_cb(xal, on_xal_seq_lock, state);

	device->xal = xal;
	device->state = state;
	device->watching = (err == 0);

	return 0;

unlink_state:
	shm_unlink(shm_state_name);
close_xal:
	xal_close(xal);
	return err;
}

int
homid_xnvme_setup(char *uri, struct xnvme_dev **device)
{
	struct xnvme_opts opts = xnvme_opts_default();
	struct xnvme_dev *dev;
	int err;

	opts.be = "linux";
	dev = xnvme_dev_open(uri, &opts);
	if (!dev) {
		err = -errno;
		homid_log(LOG_ERR, "xnvme_dev_open(): %d", err);
		return err;
	}

	*device = dev;
	return 0;
}

void
homid_device_close(unsigned int ndevs, struct homid_device *devices)
{
	if (!devices) {
		return;
	}

	for (unsigned int i = 0; i < ndevs; i++) {
		struct homid_device *dev = &devices[i];

		if (!dev) {
			continue;
		}

		if (dev->watching) {
			xal_stop_watching_filesystem(dev->xal);
		}

		if (dev->state) {
			char shm_state_name[80];

			snprintf(shm_state_name, sizeof(shm_state_name), "%s_state", dev->shm_name);
			munmap(dev->state, sizeof(struct homi_xal_state));
			shm_unlink(shm_state_name);
		}

		xal_close(dev->xal);

		xnvme_dev_close(dev->dev);
	}

	free(devices);
}

int
homid_device_setup(struct homid_opts *opts, struct homid_device **devices)
{
	struct xal_opts *xal_opts = &opts->xal_opts;
	struct homid_device *devs;
	unsigned int ndevs = opts->ndevs;
	int err;

	devs = calloc(ndevs, sizeof(struct homid_device));
	if (!devs) {
		err = -errno;
		homid_log(LOG_ERR, "Failed to allocate devices: %d", err);
		return err;
	}

	for (unsigned int i = 0; i < ndevs; i++) {
		char *uri = opts->dev_uris[i];

		strncpy(devs[i].uri, uri, sizeof(devs[i].uri) - 1);
		snprintf(devs[i].shm_name, sizeof(devs[i].shm_name), "/homid_dev%u", i);
		xal_opts->shm_name = devs[i].shm_name;

		err = homid_xnvme_setup(uri, &devs[i].dev);
		if (err) {
			homid_log(LOG_ERR, "Failed to setup xNVMe for %s: %d", uri, err);
			goto failed;
		}

		err = homid_xal_setup(xal_opts, &devs[i]);
		if (err) {
			homid_log(LOG_ERR, "Failed to setup XAL for %s: %d", uri, err);
			goto failed;
		}
	}

	*devices = devs;
	return 0;

failed:
	homid_device_close(ndevs, devs);
	return err;
}

struct homid_device *
homid_device_get(struct homid *homid, char *uri)
{
	struct homid_device *found = NULL;

	for (uint32_t i = 0; i < homid->ndevs; i++) {
		if (!strcmp(homid->dev[i].uri, uri)) {
			found = &homid->dev[i];
			break;
		}
	}

	return found;
}
