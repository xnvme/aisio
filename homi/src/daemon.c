/**
 * Host Orchestrated Multipath I/O
 *
 * Compile with
 *   gcc daemon.c -o daemon.o
 */
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <syslog.h>
#include <unistd.h>

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
		syslog(LOG_CRIT, "Failed: Could not initialize the HOMI deamon");
		exit(EXIT_FAILURE);
	}
	syslog(LOG_NOTICE, "Daemon initialized");

	while (1)
	{
		//TODO: Insert daemon code here.
		syslog(LOG_NOTICE, "Info: we are doing something");
		sleep(20);
	}

	syslog (LOG_NOTICE, "Daemon terminated");
	closelog();

	return EXIT_SUCCESS;
}
