#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <syslog.h>
#include <tomlc17.h>

#include <homi_log.h>
#include <homi_opts.h>
#include <homi_device.h>

static int
get_default_opts(struct homi_opts *opts)
{
	opts->log_level = LOG_NOTICE;

	return 0;
}

int
homi_opts_from_toml(char *config_file, struct homi_opts *opts)
{
	toml_result_t result;
	toml_datum_t log_level, devices;
	toml_datum_t backend, gpu_nqueues, gpu_tbsize;
	int err = 0;

	result = toml_parse_file_ex(config_file);

	if (!result.ok) {
		homi_log(LOG_INFO, "Configuration file did not exit. Returning to defaults");
		err = get_default_opts(opts);
		if (err) {
			homi_log(LOG_CRIT, "Error while getting default options");
		}
		goto exit;
	}

	log_level = toml_seek(result.toptab, "log_level");

	if (log_level.type != TOML_INT64) {
		homi_log(LOG_WARNING, "Missing or invalid 'log_level' property in config, defaulting to LOG_NOTICE");
	}

	switch (log_level.u.int64)
	{
	case 0:
		opts->log_level = LOG_CRIT;
		break;
	case 1:
		opts->log_level = LOG_WARNING;
		break;
	case 2:
		opts->log_level = LOG_NOTICE;
		break;
	case 3:
		opts->log_level = LOG_INFO;
		break;
	case 4:
		opts->log_level = LOG_DEBUG;
		break;
	default:
		homi_log(LOG_WARNING, "Missing or invalid 'log_level' property in config, defaulting to LOG_NOTICE");
		opts->log_level = LOG_NOTICE;
		break;
	}

	devices = toml_seek(result.toptab, "devices");

	if (devices.type != TOML_ARRAY) {
		homi_log(LOG_ERR, "Missing or invalid 'devices' property in config");
		err = -EINVAL;
		goto exit;
	}

	opts->ndevs = devices.u.arr.size;
	opts->dev_uris = malloc(devices.u.arr.size * sizeof(*opts->dev_uris));
	if (!opts->dev_uris) {
		err = -errno;
		homi_log(LOG_ERR, "Faied: malloc(); errno(%d)", errno);
		goto exit;
	}

	for (int i = 0; i < devices.u.arr.size; i++) {
		toml_datum_t elem = devices.u.arr.elem[i];

		if (elem.type != TOML_STRING) {
			homi_log(LOG_ERR, "Invalid device URI: not a string");
			err = -EINVAL;
			goto exit;
		}

		strcpy(opts->dev_uris[i], elem.u.s);
	}

	backend = toml_seek(result.toptab, "backend");

	if (backend.type != TOML_STRING) {
		homi_log(LOG_ERR, "Missing or invalid 'backend' property in config");
		err = -EINVAL;
		goto exit;
	}

	if (strcmp(backend.u.s, "aisio") == 0) {
		opts->backend = HOMI_BACKEND_AISIO;

		// Parse gpu_nqueues for aisio
		gpu_nqueues = toml_seek(result.toptab, "gpu_nqueues");
		if (gpu_nqueues.type != TOML_INT64) {
			homi_log(LOG_WARNING, "Missing or invalid 'gpu_nqueues' in config, defaulting to 128.");
			opts->gpu_nqueues = 128;
		} else {
			opts->gpu_nqueues = gpu_nqueues.u.int64;
		}

		// Parse gpu_tbsize for aisio
		gpu_tbsize = toml_seek(result.toptab, "gpu_tbsize");
		if (gpu_tbsize.type != TOML_INT64) {
			homi_log(LOG_WARNING, "Missing or invalid 'gpu_tbsize' in config, defaulting to 64.");
			opts->gpu_tbsize = 64;
		} else {
			opts->gpu_tbsize = gpu_tbsize.u.int64;
		}
	} else if (strcmp(backend.u.s, "posix") == 0) {
		opts->backend = HOMI_BACKEND_POSIX;
	} else {
		homi_log(LOG_ERR, "Invalid backend: %s", backend.u.s);
		goto exit;
	}

	homi_log(LOG_NOTICE, "homi backend set to %d, gpu_nqueues %d, gpu_tbsize %d",
			opts->backend, opts->gpu_nqueues, opts->gpu_tbsize);

exit:
	toml_free(result);

	return err;
}
