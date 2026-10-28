#ifndef URL_REVIEW_BROWSER_H
#define URL_REVIEW_BROWSER_H
#include "core.h"
char *browser_url(const char *domain,char err[ERR_SIZE]);
bool browser_start(const char *domain,pid_t *pid,char err[ERR_SIZE]);
#endif
