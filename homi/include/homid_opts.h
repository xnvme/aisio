#define HOMID_DEVURI_MAXLEN 256

struct homid_opts {
	int log_level;
	int ndevs;
	char (*dev_uris)[HOMID_DEVURI_MAXLEN];
};

/**
 * Parse the TOML configuration file
 *
 * We expect the configuration file to have keys:
 * - log_level (int)
 * - devices (array of strings)
 *
 * @param path Path to the configuration file
 * @param opts homid_opts struct that the configuration will be loaded into
 */
int
homid_opts_from_toml(char *path, struct homid_opts *opts);
