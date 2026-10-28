#ifndef URL_REVIEW_GUIDE_H
#define URL_REVIEW_GUIDE_H
#include "core.h"
typedef struct { char *code, *title, *includes, *excludes; } Category;
typedef struct { Category *items; size_t count; } Guide;
bool guide_read(const char *path, Guide *guide, char err[ERR_SIZE]);
void guide_free(Guide *guide);
#endif
