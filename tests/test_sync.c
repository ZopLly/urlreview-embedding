// О файле: Подмена fsync через линкер воспроизводит ошибку синхронизации каталога после rename. Проверяем специальный статус, совпадение памяти с диском и повторную запись.
// Пояснение: Подключаем core.h: общие типы Table/Store и функции CSV, памяти и сохранения.
#include "core.h"
// Пояснение: Подключаем assert.h: assert: немедленный провал теста, если условие ложно.
#include <assert.h>
// Пояснение: Подключаем errno.h: errno и коды системных ошибок.
#include <errno.h>
// Пояснение: Подключаем stdio.h: файловые потоки FILE, printf, snprintf и ввод/вывод.
#include <stdio.h>
// Пояснение: Подключаем stdlib.h: выделение и освобождение памяти, exit и другие базовые функции.
#include <stdlib.h>
// Пояснение: Подключаем string.h: strlen, strcmp, memcpy, memset и другие операции строк/байтов.
#include <string.h>
// Пояснение: Подключаем sys/stat.h: метаданные файла и проверки его типа.
#include <sys/stat.h>
// Пояснение: Подключаем unistd.h: POSIX-вызовы read/write/close/fsync и работу с процессами.
#include <unistd.h>

// Пояснение: Линкер предоставит имя настоящей fsync, обходя __wrap_fsync.
int __real_fsync(int fd);
// Пояснение: Нулевой статический флаг: по умолчанию ошибки не подмешиваем.
static bool fail_directory_sync;
// Пояснение: Обёртка получает все fsync только внутри этого тестового бинарника.
int __wrap_fsync(int fd) {
    // Пояснение: Определяем тип объекта по дескриптору и требуем успешный fstat.
    struct stat st;assert(fstat(fd,&st)==0);
    // Пояснение: При включённой подмене только каталог получает EIO/-1; обычный файл синхронизируется
    // Пояснение: нормально.
    if(fail_directory_sync && S_ISDIR(st.st_mode)){errno=EIO;return -1;}
    // Пояснение: Все прочие вызовы передаём настоящей fsync.
    return __real_fsync(fd);
// Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
}
// Пояснение: Точка входа сценария сохранения.
int main(void) {
    // Пояснение: Создаём уникальный временный каталог.
    char dir[]="/tmp/url-review-sync-XXXXXX";assert(mkdtemp(dir));
    // Пояснение: Буферы путей исходника, копии и блокировки.
    char input[512],output[512],lock[520];
    // Пояснение: Формируем все три пути.
    snprintf(input,sizeof input,"%s/input.csv",dir);snprintf(output,sizeof output,"%s/work.csv",dir);snprintf(lock,sizeof lock,"%s.lock",output);
    // Пояснение: Пишем минимальный синтетический исходник и проверяем закрытие.
    FILE *f=fopen(input,"w");assert(f);fputs("domain;class;label;action;description\nx.example;shopping;;;test\n",f);assert(fclose(f)==0);
    // Пояснение: Открываем Store до включения ошибки, чтобы первая копия создалась нормально.
    Store s;char err[ERR_SIZE];assert(store_open(&s,input,output,"UTF-8",';',err));
    // Пояснение: Включаем ошибку fsync каталога для следующего сохранения.
    fail_directory_sync=true;
    // Пояснение: Сохранение после rename обязано вернуть SAVE_UNCERTAIN, а не обычный успех или откат.
    assert(store_commit(&s,1,"ERROR","shopping",err)==SAVE_UNCERTAIN && "uncertain durability is not ordinary success");
    // Пояснение: Ошибка должна быть объяснена, а память уже должна содержать новое действие.
    assert(*err && !strcmp(cell(&s.table,1,ACTION),"ERROR"));
    // Пояснение: Читаем диск независимо: новый ERROR должен присутствовать и там; освобождаем временную
    // Пояснение: таблицу.
    Table actual;assert(table_read(output,"UTF-8",';',&actual,err));assert(!strcmp(cell(&actual,1,ACTION),"ERROR"));table_free(&actual);
    // Пояснение: Выключаем подмену; повторное сохранение должно вернуть SAVE_OK=1.
    fail_directory_sync=false;assert(store_commit(&s,1,"ERROR","shopping",err)==1);
    // Пояснение: Закрываем Store до удаления файлов и каталога.
    store_close(&s);unlink(output);unlink(lock);unlink(input);rmdir(dir);
    // Пояснение: Печатаем итог сценария.
    puts("Store sync: replaced-but-uncertain is explicit; memory matches disk; retry succeeds OK");
// Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
}
