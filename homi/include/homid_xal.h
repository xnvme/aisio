struct homid_opts;

struct homid_device {
	struct xnvme_dev *dev;
	struct xal *xal;
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
