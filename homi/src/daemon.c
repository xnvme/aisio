/**
 * Host Orchestrated Multipath I/O
 *
 * Compile with
 *   gcc daemon.c -o daemon.o
 */
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <syslog.h>
#include <unistd.h>

#include <homi_log.h>

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
		exit(EXIT_FAILURE);
	}
	homi_log(LOG_NOTICE, "Daemon initialized");

	while (1)
	{
		//TODO: Insert daemon code here.
		homi_log(LOG_INFO, "We are doing something");
		sleep(20);
	}

	homi_log(LOG_NOTICE, "Daemon terminated");
	closelog();

	return EXIT_SUCCESS;
}
