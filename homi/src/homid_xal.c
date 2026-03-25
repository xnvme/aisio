#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <syslog.h>

#include <libxal.h>
#include <libxnvme.h>

#include <homid.h>
#include <homid_log.h>
#include <homid_xal.h>
#include <homid_opts.h>

int
homid_xal_setup(struct xal_opts *opts, struct homid_device *device)
{
	struct xal *xal;
	int err;

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
		goto close;
	}

	err = xal_index(xal);
	if (err) {
		homid_log(LOG_ERR, "xal_index(): %d", err);
		goto close;
	}

	device->xal = xal;

	return 0;

close:
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
