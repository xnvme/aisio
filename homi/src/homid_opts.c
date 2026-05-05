#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <tomlc17.h>

#include <libxal.h>

#include <homid_log.h>
#include <homid_xal.h>
#include <homid_opts.h>

static int
get_default_opts(struct homid_opts *opts)
{
	opts->log_level = LOG_NOTICE;

	return 0;
}

int
homid_opts_from_toml(char *config_file, struct homid_opts *opts)
{
	toml_result_t result;
	toml_datum_t log_level, devices, ipc_socket;
	toml_datum_t xal_backend, xal_watchmode, xal_file_lookupmode;
	int err = 0;

	result = toml_parse_file_ex(config_file);

	if (!result.ok) {
		homid_log(LOG_INFO, "Configuration file did not exit. Returning to defaults");
		err = get_default_opts(opts);
		if (err) {
			homid_log(LOG_CRIT, "Error while getting default options");
		}
		goto exit;
	}

	log_level = toml_seek(result.toptab, "log_level");

	if (log_level.type != TOML_INT64) {
		homid_log(LOG_WARNING, "Missing or invalid 'log_level' property in config, defaulting to LOG_NOTICE");
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
		homid_log(LOG_WARNING, "Missing or invalid 'log_level' property in config, defaulting to LOG_NOTICE");
		opts->log_level = LOG_NOTICE;
		break;
	}

	devices = toml_seek(result.toptab, "devices");

	if (devices.type != TOML_ARRAY) {
		homid_log(LOG_ERR, "Missing or invalid 'devices' property in config");
		err = -EINVAL;
		goto exit;
	}

	opts->ndevs = devices.u.arr.size;
	opts->dev_uris = malloc(devices.u.arr.size * sizeof(*opts->dev_uris));
	if (!opts->dev_uris) {
		err = -errno;
		homid_log(LOG_ERR, "Failed: malloc(); errno(%d)", errno);
		goto exit;
	}

	for (int i = 0; i < devices.u.arr.size; i++) {
		toml_datum_t elem = devices.u.arr.elem[i];

		if (elem.type != TOML_STRING) {
			homid_log(LOG_ERR, "Invalid device URI: not a string");
			err = -EINVAL;
			goto exit;
		}

		strcpy(opts->dev_uris[i], elem.u.s);
	}

	ipc_socket = toml_seek(result.toptab, "ipc_socket");

	if (ipc_socket.type != TOML_STRING) {
		homid_log(LOG_ERR, "Missing or invalid 'ipc_socket' property in config");
		err = -EINVAL;
		goto exit;
	}

	opts->ipc_socket = malloc(strlen(ipc_socket.u.s) + 1);
	if (!opts->ipc_socket) {
		err = -errno;
		homid_log(LOG_ERR, "Failed: malloc(); errno(%d)", errno);
		goto exit;
	}
	strcpy(opts->ipc_socket, ipc_socket.u.s);

	xal_backend = toml_seek(result.toptab, "xal.backend");
	if (xal_backend.type != TOML_INT64) {
		homid_log(LOG_ERR, "Missing or invalid 'xal.backend' property in config");
		err = -EINVAL;
		goto exit;
	}

	switch (xal_backend.u.int64)
	{
	case XAL_BACKEND_XFS:
	case XAL_BACKEND_FIEMAP:
		opts->xal_opts.be = xal_backend.u.int64;
		break;
	default:
		homid_log(LOG_ERR, "Missing or invalid 'xal.backend' property in config");
		err = -EINVAL;
		goto exit;
	}

	xal_watchmode = toml_seek(result.toptab, "xal.watchmode");
	if (xal_watchmode.type != TOML_INT64) {
		homid_log(LOG_WARNING, "Missing or invalid 'xal.watchmode' property in config");
	}

	switch (xal_watchmode.u.int64)
	{
	case XAL_WATCHMODE_NONE:
	case XAL_WATCHMODE_DIRTY_DETECTION:
	case XAL_WATCHMODE_EXTENT_UPDATE:
		opts->xal_opts.watch_mode = xal_watchmode.u.int64;
		break;
	default:
		homid_log(LOG_WARNING, "'xal.watchmode' defaulting to 'none'");
		opts->xal_opts.watch_mode = XAL_WATCHMODE_NONE;
		break;
	}

	xal_file_lookupmode = toml_seek(result.toptab, "xal.file_lookupmode");
	if (xal_file_lookupmode.type != TOML_INT64) {
		homid_log(LOG_WARNING, "Missing or invalid 'xal.file_lookupmode' property in config");
	}

	switch (xal_file_lookupmode.u.int64)
	{
	case XAL_FILE_LOOKUPMODE_TRAVERSE:
	case XAL_FILE_LOOKUPMODE_HASHMAP:
		opts->xal_opts.file_lookupmode = xal_file_lookupmode.u.int64;
		break;
	default:
		homid_log(LOG_WARNING, "'xal.file_lookupmode' defaulting to 'traverse'");
		opts->xal_opts.file_lookupmode = XAL_FILE_LOOKUPMODE_TRAVERSE;
		break;
	}

exit:
	toml_free(result);

	return err;
}
