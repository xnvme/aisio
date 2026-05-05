#ifndef HOMID_XAL_H
#define HOMID_XAL_H

#include <stdbool.h>

#include <homid_opts.h>
#include <homi_proto.h>

struct homid;

struct homid_device {
	struct xnvme_dev *dev;
	struct xal *xal;
	struct homi_xal_state *state;
	bool watching;
	char uri[HOMID_DEVURI_MAXLEN];
	char shm_name[64];
};

/**
 * Setup xal for the homid_device
 *
 * For the given homid_device, open xal and retrieve extents through a full scan.
 * xnvme device must be initialized first.
 *
 * @param opts		xal_opts parsed from config file.
 * @param device	Output: device to setup.
 * @return			0 on success, negative errno on failure.
 */
int
homid_xal_setup(struct xal_opts *opts, struct homid_device *device);

/**
 * Setup xnvme for the homid_device
 *
 * For the given homid_device, initialize xnvme.
 * Uses default xnvme_opts with "linux" as backend.
 *
 * @param uri		URI of the device.
 * @param device	Output: device to setup.
 * @return			0 on success, negative errno on failure.
 */
int
homid_xnvme_setup(char *uri, struct xnvme_dev **device);

/**
 * Cleans up array of homid_device
 *
 * For the given number of devices, clean each homid_device's xal and xvnme setups.
 * Checks before freeing.
 *
 * @param ndevs		Number of devices to clean.
 * @param devices	Array of homid_device to clean.
 */
void
homid_device_close(unsigned int ndevs, struct homid_device *devices);

/**
 * Setup array of homid_device
 *
 * Allocates array of homid_device and initializes xnvme and xal for each of them.
 * Uses device uri, ndevs, and xal_opts from user config options.
 *
 * @param opts		config options parsed from user config file.
 * @param devices	Output: array of homid_device to setup.
 * @return			0 on success, negative errno on failure.
 */
int
homid_device_setup(struct homid_opts *opts, struct homid_device **devices);

/**
 * Get a pointer to the homid_device from a given device URI
 *
 * @param homid   Daemon state
 * @param uri     Device URI
 * @return        A pointer to the first homid_device with a matching URI, NULL if
 *                none is found.
 */
struct homid_device *
homid_device_get(struct homid *homid, char *uri);

#endif /* HOMID_XAL_H */
