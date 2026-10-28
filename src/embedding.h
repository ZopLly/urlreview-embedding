#ifndef URL_REVIEW_EMBEDDING_H
#define URL_REVIEW_EMBEDDING_H
#include "core.h"
#include <stdint.h>
#define EMBEDDING_DIM 384
typedef struct { float *vectors; size_t count; } Embedding;
typedef struct { size_t row; float score; } EmbeddingHit;
bool embedding_read(const char *path,const Table *table,Embedding *index,char err[ERR_SIZE]);
size_t embedding_search(const Embedding *index,const Table *table,size_t row,EmbeddingHit *hits,size_t capacity);
void embedding_free(Embedding *index);
#endif
