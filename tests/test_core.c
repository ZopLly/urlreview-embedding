// О файле: Прямые C-тесты ядра: assert прерывает тест при нарушении условия. Все создаваемые файлы вымышлены и находятся в уникальном временном каталоге.
// Пояснение: Запрашиваем API X/Open Issue 7, включая нужные POSIX-функции; макрос задаётся до заголовков.
#define _XOPEN_SOURCE 700
// Пояснение: Подключаем core.h: общие типы Table/Store и функции CSV, памяти и сохранения.
#include "core.h"
// Пояснение: Подключаем assert.h: assert: немедленный провал теста, если условие ложно.
#include <assert.h>
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

// Пояснение: Общий буфер подробной ошибки для вызовов модулей.
static char error[ERR_SIZE];
// Пояснение: Повторно используемый заголовок CSV с CRLF.
static const char *header = "domain;class;label;action;description\r\n";
// Пояснение: Вспомогательная запись заданного тестового текста в файл.
static void write_file(const char *path, const char *data) {
    // Пояснение: Открываем файл бинарно и assert проверяет успешность.
    FILE *f = fopen(path, "wb"); assert(f);
    // Пояснение: Требуем запись всех байтов и успешное закрытие.
    assert(fwrite(data, 1, strlen(data), f) == strlen(data)); assert(fclose(f)==0);
// Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
}
// Пояснение: Проверяет CSV-парсер и сериализатор на корректных и некорректных данных.
static void test_csv(void) {
    // Пояснение: Начало синтетического текста: UTF-8 BOM, обязательные столбцы и extra.
    const char *text="\xef\xbb\xbf" "domain;class;label;action;description;extra\r\n"
        // Пояснение: Поле содержит разделитель, экранированные кавычки и настоящий перенос внутри
        // Пояснение: quoted-текста.
        "x.example;shopping;;;\"Русский; текст \"\"кавычки\"\"\r\nпродолжение\";\r\n"
        // Пояснение: Повторный домен разрешён; вторая запись уже проверена и содержит дополнительное поле.
        "x.example;music;;OK;;tail\r\n";
    // Пояснение: Разбираем текст в пустую таблицу и требуем успех.
    Table t={0}; assert(table_parse(text,strlen(text),';',&t,error));
    // Пояснение: Проверяем две записи данных плюс заголовок, шесть столбцов, BOM и стиль CRLF.
    assert(t.count==3 && t.columns==6 && t.bom && strcmp(t.eol,"\r\n")==0);
    // Пояснение: Содержимое описания должно восстановить кавычки и внутренний CRLF без изменений.
    assert(strcmp(cell(&t,1,DESCRIPTION),"Русский; текст \"кавычки\"\r\nпродолжение")==0);
    // Пояснение: Пустое хвостовое поле должно сохраниться, проверенный action должен учитываться ровно один.
    assert(strcmp(t.rows[1].cells[5],"")==0 && reviewed_count(&t)==1);
    // Пояснение: Сериализуем таблицу и готовим вторую Table для обратного разбора.
    size_t n; char *out=table_serialize(&t,&n); Table again={0};
    // Пояснение: Результат сериализации тоже должен успешно разбираться.
    assert(table_parse(out,n,';',&again,error));
    // Пояснение: Сравниваем все значения обеих таблиц по ячейкам.
    for(size_t r=0;r<t.count;r++) for(size_t c=0;c<t.columns;c++) assert(strcmp(t.rows[r].cells[c],again.rows[r].cells[c])==0);
    // Пояснение: Освобождаем сериализованный текст и обе таблицы.
    free(out); table_free(&again); table_free(&t);
    // Пояснение: Массив намеренно неверных CSV.
    const char *bad[]={
        // Пояснение: Ошибка: quoted-поле не закрыто.
        "domain;class;label;action;description\na;b;;;\"unclosed",
        // Пояснение: Ошибка: кавычка внутри обычного поля.
        "domain;class;label;action;description\na;b;;;bare\"quote\n",
        // Пояснение: Ошибка: текст после закрывающей кавычки.
        "domain;class;label;action;description\na;b;;;\"x\"trailing\n",
        // Пояснение: Ошибка: недостаточно столбцов.
        "domain;class;label;action;description\na;b;;OK\n",
        // Пояснение: Ошибка: повтор action и отсутствие description.
        "domain;class;label;action;action\na;b;;;\n",
        // Пояснение: Ошибка: неизвестный статус WRONG.
        "domain;class;label;action;description\na;b;;WRONG;d\n"
    // Пояснение: Закрываем массив ошибочных примеров.
    };
    // Пояснение: Каждый пример должен быть отвергнут парсером.
    for(size_t i=0;i<sizeof bad/sizeof *bad;i++) assert(!table_parse(bad[i],strlen(bad[i]),';',&t,error));
    // Пояснение: Выделяем большой буфер и начинаем валидную запись с пустым action.
    char *long_text=mem_alloc(20000); strcpy(long_text,header); strcat(long_text,"a;b;;;");
    // Пояснение: Добавляем 15000 символов описания и вручную ставим завершающий ноль.
    size_t start=strlen(long_text); memset(long_text+start,'x',15000); long_text[start+15000]='\0';
    // Пояснение: Парсер должен принять длинное поле без обрезания.
    assert(table_parse(long_text,strlen(long_text),';',&t,error)); assert(strlen(cell(&t,1,DESCRIPTION))==15000);
    // Пояснение: Освобождаем длинный тестовый текст и таблицу.
    table_free(&t); free(long_text);
    // Пояснение: Новый пример переставляет столбцы, использует табуляцию и не имеет финального LF.
    const char *reordered="extra\tdescription\taction\tlabel\tclass\tdomain\n\tтекст\t\t\tmusic\tx.example";
    // Пояснение: Проверяем логический доступ DOMAIN независимо от позиции, затем освобождаем таблицу.
    assert(table_parse(reordered,strlen(reordered),'\t',&t,error)); assert(strcmp(cell(&t,1,DOMAIN),"x.example")==0); table_free(&t);
    // Пояснение: Печатаем итог только после всех assert.
    puts("CSV: quoted/multiline/long/BOM/schema/status/reordered/trailing fields OK");
// Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
}
// Пояснение: Проверяет точность кодировок и отклонение неверных последовательностей.
static void test_encoding(void) {
    // Пояснение: Кириллица с Ё позволяет проверить нетривиальные байты CP1251; n/m — длины результатов.
    const char *text="Инструменты; Ёжик"; size_t n,m;
    // Пояснение: Переводим UTF-8 в Windows-1251 и требуем успешный результат.
    char *cp=convert_text(text,strlen(text),"UTF-8","WINDOWS-1251",&n,error); assert(cp);
    // Пояснение: Переводим обратно и требуем точное совпадение с исходным UTF-8.
    char *utf=convert_text(cp,n,"WINDOWS-1251","UTF-8",&m,error); assert(utf && strcmp(utf,text)==0);
    // Пояснение: Освобождаем обе выделенные строки.
    free(cp); free(utf);
    // Пояснение: Emoji не представим в CP1251: преобразование должно вернуть NULL.
    assert(!convert_text("😀",strlen("😀"),"UTF-8","WINDOWS-1251",&n,error));
    // Пояснение: Байт FF невалиден в UTF-8: даже UTF-8 → UTF-8 должен обнаружить ошибку.
    assert(!convert_text("\xff",1,"UTF-8","UTF-8",&n,error));
    // Пояснение: Печатаем успешный результат проверок кодировки.
    puts("Encoding: exact CP1251 roundtrip; unrepresentable/invalid bytes rejected OK");
// Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
}
// Пояснение: Проверяет рабочую копию, блокировку, откат и восстановление сеанса.
static void test_store(void) {
    // Пояснение: Создаём уникальный временный каталог из шаблона XXXXXX.
    char dir[]="/tmp/url-review-core-XXXXXX"; assert(mkdtemp(dir));
    // Пояснение: Буферы путей исходника, копии, ссылки и lock.
    char input[512],output[512],linkname[512],lock[520];
    // Пояснение: Формируем пути входного и рабочего CSV.
    snprintf(input,sizeof input,"%s/input.csv",dir); snprintf(output,sizeof output,"%s/work.csv",dir);
    // Пояснение: Формируем имя жёсткой ссылки и файла блокировки.
    snprintf(linkname,sizeof linkname,"%s/alias.csv",dir); snprintf(lock,sizeof lock,"%s.lock",output);
    // Пояснение: Синтетический CSV содержит два одинаковых домена и quoted-описание с разделителем.
    const char *original="domain;class;label;action;description\nx.example;shopping;;;\"продажа; инструментов\"\nx.example;music;;;\n";
    // Пояснение: Пишем исходник; готовим два Store для проверки конфликта блокировки.
    write_file(input,original); Store s, other;
    // Пояснение: Совпадение исходного и выходного пути должно быть запрещено.
    assert(!store_open(&s,input,input,"UTF-8",';',error));
    // Пояснение: Жёсткая ссылка на исходник тоже запрещена; после проверки удаляем только ссылку.
    assert(link(input,linkname)==0); assert(!store_open(&s,input,linkname,"UTF-8",';',error)); unlink(linkname);
    // Пояснение: Обычная отдельная рабочая копия должна успешно открыться.
    assert(store_open(&s,input,output,"UTF-8",';',error));
    // Пояснение: Второй Store не может захватить ту же рабочую копию одновременно.
    assert(!store_open(&other,input,output,"UTF-8",';',error));
    // Пояснение: Сохраняем ERROR с двумя английскими кодами label.
    assert(store_commit(&s,1,"ERROR","shopping,music",error));
    // Пояснение: Только первая запись меняет action; одинаковый домен не объединяет записи.
    assert(strcmp(cell(&s.table,1,ACTION),"ERROR")==0 && strcmp(cell(&s.table,2,ACTION),"")==0);
    // Пояснение: Неизвестное действие не должно приниматься.
    assert(!store_commit(&s,2,"nonsense","",error));
    // Пояснение: Изменять строку заголовка с индексом 0 запрещено.
    assert(!store_commit(&s,0,"OK","",error));
    // Пояснение: Сохраняем байты рабочей копии для последующего теста восстановления.
    size_t n; char *saved=read_bytes(output,&n,error); assert(saved);
    // Пояснение: Повторное решение той же записи не должно увеличивать reviewed_count до двух.
    assert(store_commit(&s,1,"OK","",error)); assert(reviewed_count(&s.table)==1);
    // Пояснение: Проверку файловых прав выполняем не от root, который может обходить эти ограничения.
    if(geteuid()!=0) {
        // Пояснение: Убираем право записи в каталог, сохраняя чтение и проход.
        assert(chmod(dir,0500)==0);
        // Пояснение: Новое сохранение должно отказать при создании/замене файла.
        assert(!store_commit(&s,2,"OK","",error));
        // Пояснение: Неудачная запись должна откатить action в памяти к пустому.
        assert(strcmp(cell(&s.table,2,ACTION),"")==0);
        // Пояснение: Возвращаем права каталога для последующей очистки и работы.
        assert(chmod(dir,0700)==0);
    // Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
    }
    // Пояснение: Имитируем чужое изменение рабочей копии вне Store.
    write_file(output,"external edit\n");
    // Пояснение: Сохранение должно отказать и оставить второй action в памяти пустым.
    assert(!store_commit(&s,2,"OK","",error)); assert(strcmp(cell(&s.table,2,ACTION),"")==0);
    // Пояснение: Закрываем первый сеанс и его блокировку.
    store_close(&s);
    // Пояснение: Восстанавливаем ранее сохранённую валидную копию и освобождаем снимок.
    write_file(output,saved); free(saved);
    // Пояснение: Возобновляем сеанс: одно прежнее решение должно восстановиться; затем закрываем Store.
    assert(store_open(&s,input,output,"UTF-8",';',error)); assert(reviewed_count(&s.table)==1); store_close(&s);
    // Пояснение: Создаём несовместимую копию с другим сайтом и описанием.
    write_file(output,"domain;class;label;action;description\ny.example;shopping;;;changed\n");
    // Пояснение: Возобновление с несовместимой копией должно быть отклонено.
    assert(!store_open(&s,input,output,"UTF-8",';',error));
    // Пояснение: Проверяем побайтовую неизменность исходника за все операции.
    char *unchanged=read_bytes(input,&n,error); assert(strcmp(unchanged,original)==0); free(unchanged);
    // Пояснение: Удаляем временные файлы и каталог после закрытия Store.
    unlink(output); unlink(lock); unlink(input); rmdir(dir);
    // Пояснение: Сообщаем об успехе проверок хранилища.
    puts("Store: immutable input/lock/resume/rollback/external edits/duplicate domains OK");
// Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
}
// Пояснение: Запускаем три группы последовательно; любой assert остановит тест раньше итогового успеха.
int main(void) {test_csv();test_encoding();test_store();puts("core: all checks passed");return 0;}
