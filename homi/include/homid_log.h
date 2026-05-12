#ifndef HOMID_LOG_H
#define HOMID_LOG_H

#include <syslog.h>

void
homid_log_set_level(int level);

void
homid_log(int level, const char *fmt, ...);

#endif /* HOMID_LOG_H */
