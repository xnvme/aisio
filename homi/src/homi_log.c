#include <stdarg.h>
#include <stdio.h>
#include <syslog.h>

static int g_homi_log_level = LOG_NOTICE;

void
homi_log_set_level(int level)
{
	switch (level)
	{
	case LOG_DEBUG:
	case LOG_INFO:
		syslog(LOG_INFO, "INFO: Setting log level(%d)", level);
		__attribute__ ((fallthrough));
	case LOG_NOTICE:
	case LOG_WARNING:
	case LOG_ERR:
	case LOG_CRIT:
		g_homi_log_level = level;
		break;

	default:
		syslog(LOG_WARNING, "WARN: Unknown log level, defaulting to LOG_NOTICE");
		g_homi_log_level = LOG_NOTICE;
		break;
	}
}

void
homi_log(int level, const char *fmt, ...)
{
	va_list args;
	const char *prefix;
	char prefixed_fmt[256];

	if (level > g_homi_log_level) {
		return;
	}

	switch (level) {
	case LOG_DEBUG:
		prefix = "DEBUG: ";
		break;
	case LOG_INFO:
		prefix = "INFO: ";
		break;
	case LOG_NOTICE:
		prefix = "NOTICE: ";
		break;
	case LOG_WARNING:
		prefix = "WARN: ";
		break;
	case LOG_ERR:
		prefix = "ERROR: ";
		break;
	case LOG_CRIT:
		prefix = "CRITICAL: ";
		break;
	default:
		prefix = "";
		break;
	}

	snprintf(prefixed_fmt, sizeof(prefixed_fmt), "%s%s", prefix, fmt);

	va_start(args, fmt);
	vsyslog(level, prefixed_fmt, args);
	va_end(args);
}
