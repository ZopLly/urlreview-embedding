// О файле: Проверяет чтение поставляемого TSV, стабильный порядок и отказ при дублирующихся кодах.
// Пояснение: Подключаем guide.h: типы и функции справочника категорий.
#include "guide.h"
// Пояснение: Подключаем assert.h: assert: немедленный провал теста, если условие ложно.
#include <assert.h>
// Пояснение: Подключаем stdio.h: файловые потоки FILE, printf, snprintf и ввод/вывод.
#include <stdio.h>
// Пояснение: Подключаем stdlib.h: выделение и освобождение памяти, exit и другие базовые функции.
#include <stdlib.h>
// Пояснение: Подключаем string.h: strlen, strcmp, memcpy, memset и другие операции строк/байтов.
#include <string.h>
// Пояснение: Подключаем unistd.h: POSIX-вызовы read/write/close/fsync и работу с процессами.
#include <unistd.h>
// Пояснение: Начало проверки справочника.
int main(void) {
    // Пояснение: Пустая структура Guide и буфер ошибки.
    Guide g={0}; char err[ERR_SIZE];
    // Пояснение: Поставляемый справочник должен читаться и содержать больше сорока категорий.
    assert(guide_read("data/categories.tsv",&g,err)); assert(g.count>40);
    // Пояснение: Первый код фиксирует сохранение исходного порядка.
    assert(!strcmp(g.items[0].code,"porno_and_erotics"));
    // Новые коды берём именно из DOCX; Travel сохраняет заглавную T.
    const char *new_codes[]={"Travel","health_and_medicine","catalog_sales","services","corporate","education"};
    // Критерии должны быть доступны вызывающему коду, а не только существовать в TSV.
    for(size_t k=0;k<sizeof new_codes/sizeof *new_codes;k++) {
        // Ищем категорию по точному коду, без приведения регистра.
        const Category *found=NULL;
        // guide_read обязан сохранить все поля каждой новой категории.
        for(size_t i=0;i<g.count;i++)if(!strcmp(g.items[i].code,new_codes[k]))found=&g.items[i];
        // Отсутствующий код или потерянные критерии означают непригодный справочник.
        assert(found && *found->title && *found->includes && *found->excludes);
    }
    // Пояснение: Флаги найденных важных категорий.
    bool shopping=false,c2=false;
    // Пояснение: Перебираем весь загруженный справочник.
    for(size_t i=0;i<g.count;i++) {
        // Пояснение: shopping должна существовать и содержать критерий о продаже.
        if(!strcmp(g.items[i].code,"shopping")) { shopping=true; assert(strstr(g.items[i].includes,"продаж")); }
        // Пояснение: Код c2 тоже должен присутствовать, даже если он короткий.
        if(!strcmp(g.items[i].code,"c2")) c2=true;
    // Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
    }
    // Пояснение: Требуем обе категории, затем освобождаем справочник.
    assert(shopping && c2); guide_free(&g);
    // Пояснение: Создаём временный файл для ошибочного TSV.
    char path[]="/tmp/url-review-guide-XXXXXX"; int fd=mkstemp(path); assert(fd>=0);
    // Пояснение: Две строки имеют один код shopping: это намеренный дубликат; закрываем поток после записи.
    FILE *f=fdopen(fd,"w"); assert(f); fputs("shopping\tПокупки\tТовары\t\nshopping\tДубль\tТовары\t\n",f); fclose(f);
    // Пояснение: Чтение дубликата должно отказать; удаляем временный файл.
    assert(!guide_read(path,&g,err)); unlink(path);
    // Пояснение: Сообщаем об успехе.
    puts("Guide: actual rules/stable order/c2/duplicate detection OK");
// Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
}
