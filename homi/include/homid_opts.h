#ifndef HOMID_OPTS_H
#define HOMID_OPTS_H

#include <libxal.h>

#define HOMID_DEVURI_MAXLEN 256

struct homid_opts {
	int log_level;
	unsigned int ndevs;
	char (*dev_uris)[HOMID_DEVURI_MAXLEN];
	char *ipc_socket;
	struct xal_opts xal_opts;
};

/**
 * Parse the TOML configuration file
 *
 * We expect the configuration file to have keys:
 * - log_level (int)
 * - devices (array of strings)
 * - ipc_socket (string)
 * - xal.backend (int)
 * - xal.watchmode (int)
 * - xal.file_lookupmode (int)
 *
 * @param path Path to the configuration file
 * @param opts homid_opts struct that the configuration will be loaded into
 */
int
homid_opts_from_toml(char *path, struct homid_opts *opts);

#endif /* HOMID_OPTS_H */
