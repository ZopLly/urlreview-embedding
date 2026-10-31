// О файле: Проверяет преобразование и фильтрацию URL, не запуская настоящий браузер.
// Пояснение: Подключаем browser.h: проверка URL и запуск xdg-open.
#include "browser.h"
// Пояснение: Подключаем assert.h: assert: немедленный провал теста, если условие ложно.
#include <assert.h>
// Пояснение: Подключаем stdio.h: файловые потоки FILE, printf, snprintf и ввод/вывод.
#include <stdio.h>
// Пояснение: Подключаем stdlib.h: выделение и освобождение памяти, exit и другие базовые функции.
#include <stdlib.h>
// Пояснение: Подключаем string.h: strlen, strcmp, memcpy, memset и другие операции строк/байтов.
#include <string.h>
// Пояснение: Точка входа проверок URL.
int main(void) {
    // Пояснение: Создаём буфер ошибки и нормализуем адрес без схемы.
    char err[ERR_SIZE];char *url=browser_url("example.com",err);
    // Пояснение: Проверяем добавление https://, затем освобождаем возвращённую строку.
    assert(url && !strcmp(url,"https://example.com"));free(url);
    // Пояснение: Подготавливаем явный HTTPS-адрес с путём и query-параметрами.
    url=browser_url("https://example.com/path?a=1&b=2",err);
    // Пояснение: Явный HTTPS не должен изменяться; освобождаем результат.
    assert(url && !strcmp(url,"https://example.com/path?a=1&b=2"));free(url);
    // Пояснение: Явный HTTP и Unicode-домен должны сохраняться; возвращённую копию освобождаем.
    url=browser_url("http://пример.рф/test",err);assert(url && !strcmp(url,"http://пример.рф/test"));free(url);
    // Пояснение: Набор запрещённых форматов: пустота, другие схемы, неверный host, управляющие символы и логин.
    const char *invalid[]={"","file:///tmp/example","javascript:alert(1)","https://","//example.com","-bad","example.com\nother","https://user@host.example","example.com;touch /tmp/no","https://example.com\\evil"};
    // Пояснение: Каждый недопустимый адрес должен дать NULL без запуска внешней программы.
    for(size_t i=0;i<sizeof invalid/sizeof *invalid;i++)assert(!browser_url(invalid[i],err));
    // Пояснение: Печатаем итог после всех успешных assert.
    puts("Browser URLs: HTTPS default, explicit HTTP(S), Unicode, invalid schemes/controls rejected OK");
// Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
}
