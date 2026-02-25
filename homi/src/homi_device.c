#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <syslog.h>

#include <homi_log.h>
#include <homi_opts.h>
#include <homi_device.h>

void
homi_device_set_backend(struct homi_opts *opts)
{

	// TODO: init backend here
	switch (opts->backend)
	{
	case HOMI_BACKEND_AISIO:
	case HOMI_BACKEND_POSIX:
	default:
		break;
	}

	return;
}
