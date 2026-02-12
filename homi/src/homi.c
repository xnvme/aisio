/**
 * Host Orchestrated Multipath I/O
 */
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <syslog.h>
#include <unistd.h>

#include <homi_log.h>


volatile sig_atomic_t stop = 0;

void handle_signal(int sig __attribute__((unused))) {
	stop = 1;
}

static int initialize()
{
	openlog("homi", LOG_PID, LOG_DAEMON);

	return 0;
}

int main()
{
	int err;

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
