/**
 * Host Orchestrated Multipath I/O
 */
#include <errno.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <libxal.h>

#include <homid.h>
#include <homid_ipc.h>
#include <homid_log.h>
#include <homid_xal.h>
#include <homid_opts.h>

volatile sig_atomic_t stop = 0;

struct homid_cli_args {
	char *config_file;
};

static int
homid_close(struct homid *homid);

static void
handle_signal(int sig __attribute__((unused)))
{
	stop = 1;
}

static int
parse_args(int argc, char *argv[], struct homid_cli_args *args)
{
	for (int i = 1; i < argc; i++) {
		if (strcmp(argv[i], "--config") == 0) {
			if (i+1 >= argc) {
				homid_log(LOG_CRIT, "Error: Config argument must define a path to a configuration file");
				return -EINVAL;
			}
			args->config_file = argv[++i];
		} else {
			homid_log(LOG_CRIT, "Unexpected argument: %s", argv[i]);
			return -EINVAL;
		}
	}

	return 0;
}

static int
homid_initialize(struct homid_opts *opts, struct homid **homid)
{
	struct homid *cand;
	int err;

	homid_log_set_level(opts->log_level);

	cand = calloc(1, sizeof(*cand));
	if (!cand) {
		homid_log(LOG_CRIT, "FAILED: calloc(); errno(%d)", errno);
		return -errno;
	}

	err = homid_ipc_open(opts->ipc_socket, &cand->conn);
	if (err) {
		homid_log(LOG_ERR, "Failed: homid_ipc_open()");
		goto failed;
	}

	cand->ndevs = opts->ndevs;
	err = homid_device_setup(opts, &cand->dev);
	if (err) {
		homid_log(LOG_ERR, "Failed: homid_device_setup()");
		goto failed;
	}

	*homid = cand;

	return 0;

failed:
	homid_close(cand);
	return err;
}

static int
homid_close(struct homid *homid) {
	if (!homid) {
		homid_log(LOG_INFO, "No homid given; skipping homid_close()");
		return 0;
	}

	homid_device_close(homid->ndevs, homid->dev);
	homid_ipc_close(homid->conn);

	return 0;
}

int main(int argc, char **argv)
{
	struct homid_cli_args args = {0};
	struct homid_opts opts = {0};
	struct homid *homid = NULL;
	int err;

	openlog("homi", LOG_PID, LOG_DAEMON);

	err = parse_args(argc, argv, &args);
	if (err) {
		homid_log(LOG_CRIT, "Error while parsing the arguments");
		exit(EXIT_FAILURE);
	}

	err = homid_opts_from_toml(args.config_file, &opts);
	if (err) {
		homid_log(LOG_CRIT, "Error while parsing the configuration file");
		goto exit;
	}

	err = homid_initialize(&opts, &homid);
	if (err) {
		homid_log(LOG_CRIT, "Could not initialize the HOMI deamon");
		goto exit;
	}

	homid_log(LOG_NOTICE, "Daemon initialized");

	struct sigaction sa = {
		.sa_handler = handle_signal,
		.sa_flags   = 0,
	};
	sigemptyset(&sa.sa_mask);
	sigaction(SIGTERM, &sa, NULL);
	sigaction(SIGINT, &sa, NULL);

	while (!stop) {
		err = homid_ipc_accept(homid);
		if (err) {
			homid_log(LOG_ERR, "Failed: homid_ipc_accept(); err(%d)", err);
			continue;
		}
	}

	homid_log(LOG_NOTICE, "Daemon terminated");

exit:
	homid_close(homid);
	free(homid);
	closelog();
	free(opts.dev_uris);

	return err;
}
