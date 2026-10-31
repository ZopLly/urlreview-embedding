// XLSX backend отделён от CSV-парсера и использует только стандартный Python 3.
#ifndef URL_REVIEW_WORKBOOK_H
#define URL_REVIEW_WORKBOOK_H
#include "core.h"
// Проверяет расширение без учёта регистра; преобразование XLSX↔CSV не подразумевается.
bool workbook_path(const char *path);
// Разбирает байты книги и заполняет Table, имя листа и физические номера строк.
bool workbook_read(const char *raw,size_t len,const char *sheet,Table *table,char err[ERR_SIZE]);
// Возвращает новые байты книги, меняя лишь action/label относительно последнего снимка.
char *workbook_write(const char *raw,size_t len,const Table *table,size_t *out_len,char err[ERR_SIZE]);
#endif
