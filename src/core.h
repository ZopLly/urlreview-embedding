// О файле: Общий контракт модулей C: структуры данных, владение памятью и объявления функций. Реализации чтения находятся в csv.c, хранения — в store.c.
// Пояснение: Защита заголовка: читаем содержимое только если его уникальный макрос ещё не определён.
#ifndef URL_REVIEW_CORE_H
// Пояснение: Отмечаем заголовок как подключённый, чтобы повторный #include не дублировал определения.
#define URL_REVIEW_CORE_H
// Пояснение: Подключаем stdbool.h: логический тип bool и значения true/false.
#include <stdbool.h>
// Пояснение: Подключаем stddef.h: size_t для размеров и NULL для пустого указателя.
#include <stddef.h>
// Пояснение: Подключаем sys/types.h: системные типы pid_t, dev_t и ino_t.
#include <sys/types.h>

// Пояснение: Размер буфера сообщений об ошибках — 512 байтов вместе с завершающим нулём.
#define ERR_SIZE 512
// Пояснение: Логические имена столбцов: от DOMAIN=0 до DESCRIPTION=4; COLUMN_COUNT=5 задаёт длину массива col.
enum { DOMAIN, CLASS, LABEL, ACTION, DESCRIPTION, COLUMN_COUNT };
// Пояснение: Одна CSV-запись: cells — массив указателей на динамические строки; count — количество ячеек.
typedef struct { char **cells; size_t count; } Row;
// Пояснение: Начало определения структуры всей таблицы.
typedef struct {
    // Пояснение: Динамический массив Row; элемент 0 содержит заголовок, сайты начинаются с 1.
    Row *rows;
    // Пояснение: count включает заголовок; columns — число столбцов из заголовка.
    size_t count, columns;
    // Пояснение: Отображение логического имени столбца на его фактическую позицию в CSV.
    size_t col[COLUMN_COUNT];
    // Пояснение: Разделитель CSV и строка перевода строки: до двух байтов CRLF плюс завершающий ноль.
    char delimiter, eol[3];
    // Пояснение: Запоминает наличие UTF-8 BOM у загруженного файла.
    bool bom;
    // Для XLSX запоминаем выбранный лист; NULL обозначает обычную CSV-таблицу.
    char *sheet;
    // Физические номера строк Excel, включая строку заголовка; CSV использует индекс+1.
    size_t *source_rows;
// Пояснение: Завершение структуры и имя типа Table.
} Table;
// Пояснение: Начало состояния открытого рабочего сеанса.
typedef struct {
    // Пояснение: Таблица с текущими решениями в памяти; Store отвечает за её освобождение.
    Table table;
    // Пояснение: Собственные динамические строки путей, имени кодировки и последнего снимка байтов файла.
    char *input, *output, *encoding, *snapshot;
    // Пояснение: Число действительных байтов snapshot; сравнение не зависит от нулевого завершения.
    size_t snapshot_len;
    // Пояснение: Дескриптор файла блокировки; -1 обозначает отсутствие открытого дескриптора.
    int lock_fd;
    // Пояснение: Устройство исходного файла для проверки тождества файлов.
    dev_t input_dev;
    // Пояснение: Номер inode исходника; пара device+inode обнаруживает жёсткую ссылку на тот же файл.
    ino_t input_ino;
    // Формат рабочей копии; протокол атомарного сохранения одинаков для CSV и XLSX.
    bool xlsx;
// Пояснение: Завершение структуры Store.
} Store;
// Пояснение: Три результата сохранения: не заменён, заменён и синхронизирован, заменён с неопределённой
// Пояснение: надёжностью.
typedef enum { SAVE_FAILED=0, SAVE_OK=1, SAVE_UNCERTAIN=2 } SaveResult;

// Пояснение: Объявление CSV-парсера: текст+длина → Table; false сопровождается сообщением в err.
bool table_parse(const char *text, size_t len, char delimiter, Table *t, char err[ERR_SIZE]);
// Пояснение: Объявление чтения CSV из файла с явной кодировкой и разделителем.
bool table_read(const char *path, const char *encoding, char delimiter, Table *t, char err[ERR_SIZE]);
// Вариант чтения с явным выбором листа XLSX; прежняя функция вызывает его с NULL.
bool table_read_sheet(const char *path,const char *encoding,char delimiter,const char *sheet,Table *t,char err[ERR_SIZE]);
// Пояснение: Возвращает выделенную строку CSV и её длину; вызывающий код освобождает строку.
char *table_serialize(const Table *t, size_t *len);
// Пояснение: Освобождает таблицу и все вложенные строки.
void table_free(Table *t);
// Пояснение: Преобразует байты между кодировками; возвращает выделенную строку либо NULL и ошибку.
char *convert_text(const char *data, size_t len, const char *from, const char *to, size_t *out_len, char err[ERR_SIZE]);
// Пояснение: Читает ограниченный по размеру обычный файл; результат принадлежит вызывающему коду.
char *read_bytes(const char *path, size_t *len, char err[ERR_SIZE]);
// Пояснение: Выделяет обнулённую память или завершает программу при её нехватке.
void *mem_alloc(size_t size);
// Пояснение: Меняет размер блока; результат нужно присвоить обратно, так как адрес может измениться.
void *mem_resize(void *p, size_t size);
// Пояснение: Возвращает динамическую копию строки с завершающим нулём.
char *str_copy(const char *s);
// Пояснение: Возвращает заимствованный указатель на ячейку: освобождать его отдельно нельзя.
const char *cell(const Table *t, size_t row, int column);
// Пояснение: Считает непустые action; предполагает таблицу с уже проверенной схемой.
size_t reviewed_count(const Table *t);
// Пояснение: Открывает сеанс и блокировку, создаёт либо восстанавливает отдельную рабочую копию.
bool store_open(Store *s, const char *input, const char *output, const char *encoding, char delimiter, char err[ERR_SIZE]);
// Выбор листа сохраняется в Table для возобновления и каждой последующей записи книги.
bool store_open_sheet(Store *s,const char *input,const char *output,const char *encoding,char delimiter,const char *sheet,char err[ERR_SIZE]);
// Пояснение: Применяет решение к записи и сохраняет; точный SaveResult определяет поведение интерфейса.
SaveResult store_commit(Store *s, size_t row, const char *action, const char *label, char err[ERR_SIZE]);
// Пояснение: Закрывает блокировку и освобождает всё, чем владеет Store.
void store_close(Store *s);
// Пояснение: Конец условного включения заголовка.
#endif
