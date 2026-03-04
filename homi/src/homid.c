/**
 * Host Orchestrated Multipath I/O
 */
#include <errno.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <homid_log.h>
#include <homid_opts.h>


volatile sig_atomic_t stop = 0;

struct homid_cli_args {
	char *config_file;
};

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
initialize(struct homid_opts *opts)
{
	homid_log_set_level(opts->log_level);

	// For now, we just log the devices given in the configuration file.
	for (int i = 0; i < opts->ndevs; i++) {
		homid_log(LOG_NOTICE, "Device: %s", opts->dev_uris[i]);
	}

	return 0;
}

int main(int argc, char **argv)
{
	struct homid_cli_args args = {0};
	struct homid_opts opts = {0};
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

	err = initialize(&opts);
	if (err) {
		homid_log(LOG_CRIT, "Could not initialize the HOMI deamon");
		goto exit;
	}

	homid_log(LOG_NOTICE, "Daemon initialized");

	signal(SIGTERM, handle_signal);
	signal(SIGINT, handle_signal);

	while (!stop)
	{
		//TODO: Insert daemon code here.
		homid_log(LOG_INFO, "We are doing something");
		sleep(10);
	}

	homid_log(LOG_NOTICE, "Daemon terminated");

exit:
	closelog();
	free(opts.dev_uris);

	return err;
}
