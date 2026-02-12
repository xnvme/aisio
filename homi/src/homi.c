/**
 * Host Orchestrated Multipath I/O
 */
#include <errno.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <syslog.h>
#include <unistd.h>

#include <homi_log.h>


volatile sig_atomic_t stop = 0;

struct homi_cli_args {
	char *config_file;
};

void handle_signal(int sig __attribute__((unused))) {
	stop = 1;
}

static int
parse_args(int argc, char *argv[], struct homi_cli_args *args)
{
	for (int i = 1; i < argc; i++) {
		if (strcmp(argv[i], "--config") == 0) {
			if (i+1 >= argc) {
				homi_log(LOG_CRIT, "Error: Config argument must define a path to a configuration file");
				return -EINVAL;
			}
			args->config_file = argv[++i];
		} else {
			homi_log(LOG_CRIT, "Unexpected argument: %s", argv[i]);
			return -EINVAL;
		}
	}

	return 0;
}


static int initialize()
{
	return 0;
}

int main(int argc, char **argv)
{
	struct homi_cli_args args = {0};
	int err;

	openlog("homi", LOG_PID, LOG_DAEMON);

	err = parse_args(argc, argv, &args);
	if (err) {
		homi_log(LOG_CRIT, "Error while parsing the arguments");
		exit(EXIT_FAILURE);
	}

	err = initialize();
	if (err) {
		homi_log(LOG_CRIT, "Could not initialize the HOMI deamon");
		goto exit;
	}

	homi_log(LOG_NOTICE, "Daemon initialized");

	signal(SIGTERM, handle_signal);
	signal(SIGINT, handle_signal);

	while (!stop)
	{
		//TODO: Insert daemon code here.
		homi_log(LOG_INFO, "We are doing something");
		sleep(20);
	}

	homi_log(LOG_NOTICE, "Daemon terminated");

exit:
	closelog();

	return err;
}
