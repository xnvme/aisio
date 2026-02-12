#define HOMI_DEVURI_MAXLEN 256

struct homi_opts {
	int log_level;
	int ndevs;
	char (*dev_uris)[HOMI_DEVURI_MAXLEN];
};

/**
 * Parse the TOML configuration file
 *
 * We expect the configuration file to have keys:
 * - log_level (int)
 * - devices (array of strings)
 *
 * @param path Path to the configuration file
 * @param opts homi_opts struct that the configuration will be loaded into
 */
int
homi_opts_from_toml(char *path, struct homi_opts *opts);
