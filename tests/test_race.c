// О файле: Проверка гонки внешнего редактирования: обёртка fopen меняет вымышленную рабочую копию между чтениями. Хранилище не должно затереть это решение.
// Пояснение: Подключаем core.h: общие типы Table/Store и функции CSV, памяти и сохранения.
#include "core.h"
// Пояснение: Подключаем assert.h: assert: немедленный провал теста, если условие ложно.
#include <assert.h>
// Пояснение: Подключаем fcntl.h: open и флаги открытия файлов.
#include <fcntl.h>
// Пояснение: Подключаем stdio.h: файловые потоки FILE, printf, snprintf и ввод/вывод.
#include <stdio.h>
// Пояснение: Подключаем stdlib.h: выделение и освобождение памяти, exit и другие базовые функции.
#include <stdlib.h>
// Пояснение: Подключаем string.h: strlen, strcmp, memcpy, memset и другие операции строк/байтов.
#include <string.h>
// Пояснение: Подключаем unistd.h: POSIX-вызовы read/write/close/fsync и работу с процессами.
#include <unistd.h>

/* Linker interposition injects one real external write between production reads.
   Only this test binary is wrapped. No test hooks are present in production. */
// Пояснение: Настоящая fopen доступна по этому имени благодаря --wrap=fopen.
FILE *__real_fopen(const char *,const char *);
// Пояснение: Путь, для которого подмешивается изменение; NULL выключает подмену.
static const char *watched;
// Пояснение: Счётчик чтений наблюдаемого файла.
static int reads;
// Пояснение: Синтетическое внешнее изменение: первый сайт получил OK.
static const char *updated="domain;class;label;action;description\nx.example;shopping;;OK;first\ny.example;music;;;second\n";
// Пояснение: Тестовая обёртка открытия файлов.
FILE *__wrap_fopen(const char *path,const char *mode) {
    // Пояснение: Только второе открытие наблюдаемого пути для чтения вызывает подмену.
    if(watched && !strcmp(path,watched) && mode[0]=='r' && ++reads==2) {
        // Пояснение: Открываем его напрямую через open, очищая прежнее содержимое; требуем успешный fd.
        int fd=open(path,O_WRONLY|O_TRUNC);assert(fd>=0);
        // Пояснение: Пишем внешнюю версию целиком и проверяем закрытие.
        size_t n=strlen(updated);assert(write(fd,updated,n)==(ssize_t)n);assert(close(fd)==0);
    // Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
    }
    // Пояснение: После возможного изменения выполняем настоящее fopen.
    return __real_fopen(path,mode);
// Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
}
// Пояснение: Вспомогательная запись тестовых файлов без увеличения счётчика обёртки.
static void put(const char *path,const char *text) {
    // Пояснение: Через настоящую fopen пишем текст и проверяем все операции.
    FILE *f=__real_fopen(path,"w");assert(f);assert(fputs(text,f)>=0);assert(fclose(f)==0);
// Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
}
// Пояснение: Начало сценария гонки.
int main(void) {
    // Пояснение: Новый временный каталог изолирует файлы от других тестов.
    char dir[]="/tmp/url-review-race-XXXXXX";assert(mkdtemp(dir));
    // Пояснение: Буферы трёх путей.
    char input[512],output[512],lock[520];
    // Пояснение: Формируем пути исходника, копии и lock.
    snprintf(input,sizeof input,"%s/input.csv",dir);snprintf(output,sizeof output,"%s/work.csv",dir);snprintf(lock,sizeof lock,"%s.lock",output);
    // Пояснение: Исходно оба вымышленных сайта не проверены.
    const char *original="domain;class;label;action;description\nx.example;shopping;;;first\ny.example;music;;;second\n";
    // Пояснение: Создаём одинаковые исходник и рабочую копию.
    put(input,original);put(output,original);
    // Пояснение: Включаем наблюдение за копией и обнуляем счётчик.
    watched=output;reads=0;
    // Пояснение: Открываем Store, считывая первоначальную рабочую копию.
    Store s;char err[ERR_SIZE];assert(store_open(&s,input,output,"UTF-8",';',err));
    // Пояснение: Пробуем разметить второй сайт; подмена вставит чужое решение во время последующих чтений.
    (void)store_commit(&s,2,"ERROR","music",err);
    // Пояснение: Выключаем подмену перед независимой проверкой диска.
    watched=NULL;
    // Пояснение: Читаем фактическую рабочую копию стандартным путём C.
    Table actual;assert(table_read(output,"UTF-8",';',&actual,err));
    // Пояснение: Внешний OK первого сайта должен сохраниться, а не потеряться при записи второго решения.
    assert(!strcmp(cell(&actual,1,ACTION),"OK") && "external decision must not be lost");
    // Пояснение: Освобождаем таблицу, закрываем Store и удаляем временные данные.
    table_free(&actual);store_close(&s);unlink(output);unlink(lock);unlink(input);rmdir(dir);
    // Пояснение: Печатаем успех только после проверки сохранности внешнего решения.
    puts("Store race: a concurrent external decision cannot become an unread baseline OK");
// Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
}
