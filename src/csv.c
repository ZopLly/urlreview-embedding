#define _POSIX_C_SOURCE 200809L
#include "core.h"
#include <errno.h>
#include <iconv.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#define INPUT_LIMIT ((size_t)256 * 1024 * 1024)
typedef struct { char *data; size_t len, cap; } Buffer;

void *mem_alloc(size_t n) {
    void *p = calloc(n ? n : 1, 1);
    if (!p) { fputs("Недостаточно памяти.\n", stderr); exit(2); }
    return p;
}
void *mem_resize(void *p, size_t n) {
    void *q = realloc(p, n ? n : 1);
    if (!q) { fputs("Недостаточно памяти.\n", stderr); exit(2); }
    return q;
}
char *str_copy(const char *s) {
    size_t n = strlen(s) + 1; char *p = mem_alloc(n); memcpy(p, s, n); return p;
}
static void append(Buffer *b, const char *s, size_t n) {
    if (b->len + n + 1 > b->cap) {
        b->cap = (b->len + n + 1) * 2;
        b->data = mem_resize(b->data, b->cap);
    }
    memcpy(b->data + b->len, s, n); b->len += n; b->data[b->len] = 0;
}
static void put(Buffer *b, char ch) { append(b, &ch, 1); }
char *read_bytes(const char *path, size_t *len, char err[ERR_SIZE]) {
    FILE *f = fopen(path, "rb");
    if (!f) { snprintf(err, ERR_SIZE, "Не удалось открыть файл: %s", strerror(errno)); return NULL; }
    struct stat st;
    if (fstat(fileno(f), &st) || !S_ISREG(st.st_mode) || st.st_size < 0 || (size_t)st.st_size > INPUT_LIMIT) {
        snprintf(err, ERR_SIZE, "Нужен обычный файл размером не более 256 МиБ."); fclose(f); return NULL;
    }
    Buffer b = {0}; char block[65536]; size_t n;
    while ((n = fread(block, 1, sizeof block, f)) != 0) {
        if (b.len + n > INPUT_LIMIT) { snprintf(err, ERR_SIZE, "Файл превышает 256 МиБ."); free(b.data); fclose(f); return NULL; }
        append(&b, block, n);
    }
    bool failed = ferror(f) != 0;
    if (fclose(f) != 0) failed = true;
    if (failed) { snprintf(err, ERR_SIZE, "Ошибка чтения файла."); free(b.data); return NULL; }
    if (!b.data) b.data = str_copy("");
    *len = b.len; return b.data;
}
char *convert_text(const char *data, size_t len, const char *from, const char *to, size_t *out_len, char err[ERR_SIZE]) {
    iconv_t cd = iconv_open(to, from);
    if (cd == (iconv_t)-1) { snprintf(err, ERR_SIZE, "Неизвестная кодировка: %s → %s", from, to); return NULL; }
    size_t capacity = len * 4 + 16, left = capacity - 1, inleft = len;
    char *result = mem_alloc(capacity), *out = result, *in = (char *)data;
    bool ok = iconv(cd, &in, &inleft, &out, &left) != (size_t)-1;
    if (ok) ok = iconv(cd, NULL, NULL, &out, &left) != (size_t)-1;
    iconv_close(cd);
    if (!ok) {
        snprintf(err, ERR_SIZE, "Ошибка кодировки %s → %s: неверный или непредставимый символ (байт %zu).", from, to, len-inleft);
        free(result); return NULL;
    }
    *out_len = (size_t)(out - result); *out = 0; return result;
}
void table_free(Table *t) {
    for (size_t r = 0; r < t->count; r++) {
        for (size_t c = 0; c < t->rows[r].count; c++) free(t->rows[r].cells[c]);
        free(t->rows[r].cells);
    }
    free(t->rows); memset(t, 0, sizeof *t);
}
static void finish_field(Row *row, Buffer *b) {
    row->cells = mem_resize(row->cells, (row->count + 1) * sizeof *row->cells);
    row->cells[row->count++] = b->data ? b->data : str_copy(""); memset(b, 0, sizeof *b);
}
static void finish_row(Table *t, Row *row) {
    t->rows = mem_resize(t->rows, (t->count + 1) * sizeof *t->rows);
    t->rows[t->count++] = *row; memset(row, 0, sizeof *row);
}
static bool schema(Table *t, char err[ERR_SIZE]) {
    static const char *names[] = {"domain", "class", "label", "action", "description"};
    if (!t->count) { snprintf(err, ERR_SIZE, "CSV пуст: отсутствует заголовок."); return false; }
    t->columns = t->rows[0].count;
    for (size_t k = 0; k < COLUMN_COUNT; k++) {
        size_t found = 0;
        for (size_t c = 0; c < t->columns; c++) if (!strcmp(t->rows[0].cells[c], names[k])) { t->col[k] = c; found++; }
        if (found != 1) { snprintf(err, ERR_SIZE, "Нужен ровно один столбец '%s'. Проверьте разделитель и кодировку.", names[k]); return false; }
    }
    for (size_t r = 1; r < t->count; r++) {
        if (t->rows[r].count != t->columns) {
            snprintf(err, ERR_SIZE, "Запись %zu: %zu полей вместо %zu.", r, t->rows[r].count, t->columns); return false;
        }
        const char *a = cell(t, r, ACTION);
        if (*a && strcmp(a,"OK") && strcmp(a,"ERROR") && strcmp(a,"NOT_DESC")) {
            snprintf(err, ERR_SIZE, "Запись %zu: неизвестное значение action. Ожидается OK, ERROR, NOT_DESC или пусто.", r); return false;
        }
    }
    return true;
}
bool table_parse(const char *text, size_t len, char delimiter, Table *t, char err[ERR_SIZE]) {
    memset(t, 0, sizeof *t); t->delimiter = delimiter; strcpy(t->eol, "\n");
    enum { START, PLAIN, QUOTED, CLOSED } state = START;
    Buffer field = {0}; Row row = {0}; bool pending = false, eol_seen = false;
    size_t i = 0;
    if (len >= 3 && !memcmp(text, "\xef\xbb\xbf", 3)) { t->bom = true; i = 3; }
    for (; i < len; i++) {
        char ch = text[i];
        if (!ch) { snprintf(err, ERR_SIZE, "CSV содержит нулевой байт."); goto fail; }
        pending = true;
        if (state == QUOTED) {
            if (ch == '"') state = CLOSED;
            else put(&field, ch);
            continue;
        }
        if (state == CLOSED && ch == '"') { put(&field, '"'); state = QUOTED; continue; }
        if (ch == delimiter) { finish_field(&row, &field); state = START; continue; }
        if (ch == '\n' || ch == '\r') {
            bool crlf = ch == '\r' && i+1 < len && text[i+1] == '\n';
            if (!eol_seen) { strcpy(t->eol, crlf ? "\r\n" : ch == '\r' ? "\r" : "\n"); eol_seen = true; }
            if (crlf) i++;
            finish_field(&row, &field); finish_row(t, &row); state = START; pending = false; continue;
        }
        if (state == CLOSED) { snprintf(err, ERR_SIZE, "Запись %zu: символ после закрывающей кавычки.", t->count+1); goto fail; }
        if (ch == '"') {
            if (state != START) { snprintf(err, ERR_SIZE, "Запись %zu: кавычка внутри незакавыченного поля.", t->count+1); goto fail; }
            state = QUOTED;
        } else { put(&field, ch); state = PLAIN; }
    }
    if (state == QUOTED) { snprintf(err, ERR_SIZE, "CSV: незакрытая кавычка."); goto fail; }
    if (pending) { finish_field(&row, &field); finish_row(t, &row); }
    if (!schema(t, err)) goto fail;
    return true;
fail:
    free(field.data);
    for (size_t c = 0; c < row.count; c++) free(row.cells[c]);
    free(row.cells); table_free(t); return false;
}
bool table_read(const char *path, const char *encoding, char delimiter, Table *t, char err[ERR_SIZE]) {
    size_t n, m; char *raw = read_bytes(path, &n, err); if (!raw) return false;
    char *utf = convert_text(raw, n, encoding, "UTF-8", &m, err); free(raw);
    if (!utf) return false;
    bool ok = table_parse(utf, m, delimiter, t, err); free(utf); return ok;
}
char *table_serialize(const Table *t, size_t *len) {
    Buffer out = {0};
    if (t->bom) append(&out, "\xef\xbb\xbf", 3);
    for (size_t r = 0; r < t->count; r++) {
        for (size_t c = 0; c < t->columns; c++) {
            if (c) put(&out, t->delimiter);
            const char *s = t->rows[r].cells[c]; bool quote = false;
            for (const char *p = s; *p; p++) if (*p == t->delimiter || *p == '"' || *p == '\n' || *p == '\r') quote = true;
            if (quote) put(&out, '"');
            for (; *s; s++) { if (*s == '"') put(&out, '"'); put(&out, *s); }
            if (quote) put(&out, '"');
        }
        append(&out, t->eol, strlen(t->eol));
    }
    *len = out.len; return out.data ? out.data : str_copy("");
}
const char *cell(const Table *t, size_t row, int column) { return t->rows[row].cells[t->col[column]]; }
size_t reviewed_count(const Table *t) {
    size_t count = 0;
    for (size_t r = 1; r < t->count; r++) if (*cell(t,r,ACTION)) count++;
    return count;
}
