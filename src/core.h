#ifndef URL_REVIEW_CORE_H
#define URL_REVIEW_CORE_H
#include <stdbool.h>
#include <stddef.h>
#include <sys/types.h>

#define ERR_SIZE 512
enum { DOMAIN, CLASS, LABEL, ACTION, DESCRIPTION, COLUMN_COUNT };
typedef struct { char **cells; size_t count; } Row;
typedef struct {
    Row *rows;
    size_t count, columns;
    size_t col[COLUMN_COUNT];
    char delimiter, eol[3];
    bool bom;
} Table;
typedef struct {
    Table table;
    char *input, *output, *encoding, *snapshot;
    size_t snapshot_len;
    int lock_fd;
    dev_t input_dev;
    ino_t input_ino;
} Store;
typedef enum { SAVE_FAILED=0, SAVE_OK=1, SAVE_UNCERTAIN=2 } SaveResult;

bool table_parse(const char *text, size_t len, char delimiter, Table *t, char err[ERR_SIZE]);
bool table_read(const char *path, const char *encoding, char delimiter, Table *t, char err[ERR_SIZE]);
char *table_serialize(const Table *t, size_t *len);
void table_free(Table *t);
char *convert_text(const char *data, size_t len, const char *from, const char *to, size_t *out_len, char err[ERR_SIZE]);
char *read_bytes(const char *path, size_t *len, char err[ERR_SIZE]);
void *mem_alloc(size_t size);
void *mem_resize(void *p, size_t size);
char *str_copy(const char *s);
const char *cell(const Table *t, size_t row, int column);
size_t reviewed_count(const Table *t);
bool store_open(Store *s, const char *input, const char *output, const char *encoding, char delimiter, char err[ERR_SIZE]);
SaveResult store_commit(Store *s, size_t row, const char *action, const char *label, char err[ERR_SIZE]);
void store_close(Store *s);
#endif
