// О файле: Проверка адреса и запуск xdg-open отдельным процессом без shell. Это проверка допустимого формата, а не подтверждение существования или безопасности сайта.
// Пояснение: Открываем объявления POSIX.1-2008 в системных заголовках до их подключения.
#define _POSIX_C_SOURCE 200809L
// Пояснение: Подключаем browser.h: проверка URL и запуск xdg-open.
#include "browser.h"
// Пояснение: Подключаем ctype.h: проверки символов isalnum/isspace.
#include <ctype.h>
// Пояснение: Подключаем fcntl.h: open и флаги открытия файлов.
#include <fcntl.h>
// Пояснение: Подключаем spawn.h: POSIX-запуск процесса без shell.
#include <spawn.h>
// Пояснение: Подключаем stdio.h: файловые потоки FILE, printf, snprintf и ввод/вывод.
#include <stdio.h>
// Пояснение: Подключаем stdlib.h: выделение и освобождение памяти, exit и другие базовые функции.
#include <stdlib.h>
// Пояснение: Подключаем string.h: strlen, strcmp, memcpy, memset и другие операции строк/байтов.
#include <string.h>
// Пояснение: Подключаем strings.h: POSIX-сравнение строк без учёта регистра.
#include <strings.h>

// Пояснение: Массив окружения процесса предоставлен системой; передадим его xdg-open.
extern char **environ;

// Пояснение: Возвращает выделенный HTTP(S)-адрес либо NULL с сообщением в err.
char *browser_url(const char *domain,char err[ERR_SIZE]) {
    // Пояснение: Измеряем длину строки адреса в байтах.
    size_t len=strlen(domain);
    // Пояснение: Пустой адрес и строку длиннее 8192 байтов отклоняем.
    if(!len || len>8192) {snprintf(err,ERR_SIZE,"Адрес сайта пуст или слишком длинный.");return NULL;}
    // Пояснение: Проверяем каждый байт адреса как unsigned char.
    for(const unsigned char *p=(const unsigned char *)domain;*p;p++) {
        // Пояснение: Запрещаем пробельные и управляющие ASCII-байты, DEL и обратный слеш.
        if(*p<=32 || *p==127 || *p=='\\') {
            // Пояснение: При недопустимом символе не создаём URL, возвращаем ошибку.
            snprintf(err,ERR_SIZE,"Адрес содержит пробелы или недопустимые управляющие символы.");return NULL;
        // Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
        }
    // Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
    }
    // Пояснение: Без учёта регистра определяем, указан ли HTTP либо HTTPS явно.
    bool explicit_http=!strncasecmp(domain,"http://",7),explicit_https=!strncasecmp(domain,"https://",8);
    // Пояснение: Если есть схема ://, отличная от разрешённых, отклоняем её.
    if(!explicit_http && !explicit_https && strstr(domain,"://")) {
        // Пояснение: Сообщаем о разрешённых HTTP/HTTPS и возвращаем NULL.
        snprintf(err,ERR_SIZE,"Открываются только сайты HTTP/HTTPS.");return NULL;
    // Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
    }
    // Пояснение: Пропускаем префикс схемы, чтобы host указывал на начало адресной части.
    const char *host=domain+(explicit_http?7:explicit_https?8:0);
    // Пояснение: Длина host до начала пути, параметров или фрагмента: /, ? или #.
    size_t hostlen=strcspn(host,"/?#");
    // Пояснение: Адресная часть нужна непустая; первый символ — буква/цифра, байт Unicode или [ для IPv6.
    if(!hostlen || !(isalnum((unsigned char)*host) || (unsigned char)*host>=128 || *host=='[')) {
        // Пояснение: Отклоняем строку без допустимого начала host.
        snprintf(err,ERR_SIZE,"Нужен домен или адрес HTTP/HTTPS.");return NULL;
    // Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
    }
    // Пояснение: Проверяем все байты адресной части до пути/параметров.
    for(size_t i=0;i<hostlen;i++) {
        // Пояснение: Берём беззнаковый байт, чтобы корректно передавать его в isalnum.
        unsigned char c=(unsigned char)host[i];
        // Пояснение: Для ASCII разрешены буквы/цифры и .-:[]; прочие байты ASCII запрещены.
        if(c<128 && !isalnum(c) && !strchr(".-:[]",c)) {
            // Пояснение: В частности @ запрещён, поэтому логин и пароль в адресной части не принимаются.
            snprintf(err,ERR_SIZE,"Недопустимый домен. Используйте адрес HTTP/HTTPS без логина и пароля.");return NULL;
        // Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
        }
    // Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
    }
    // Пояснение: Явный HTTP(S) сохраняем без изменения, возвращая независимую копию.
    if(explicit_http || explicit_https)return str_copy(domain);
    // Пояснение: Для адреса без схемы выделяем место на https:// и ноль, собираем и возвращаем URL.
    char *url=mem_alloc(len+9);sprintf(url,"https://%s",domain);return url;
// Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
}
// Пояснение: Запускает xdg-open; pid отдаёт номер дочернего процесса для неблокирующего наблюдения из UI.
bool browser_start(const char *domain,pid_t *pid,char err[ERR_SIZE]) {
    // Пояснение: Сначала нормализуем и проверяем адрес; ошибочный адрес не запускается.
    char *url=browser_url(domain,err);if(!url)return false;
    // Пояснение: Структура действий над дескрипторами нового процесса.
    posix_spawn_file_actions_t actions;
    // Пояснение: Инициализируем список действий; возвращаемое число — код ошибки, а не errno.
    int result=posix_spawn_file_actions_init(&actions);
    // Пояснение: При неудаче освобождаем URL и сообщаем strerror(result).
    if(result) {snprintf(err,ERR_SIZE,"Не удалось подготовить браузер: %s",strerror(result));free(url);return false;}
    // Пояснение: Подменяем stdin дочерней программы на /dev/null, чтобы браузер не читал клавиши приложения.
    result=posix_spawn_file_actions_addopen(&actions,0,"/dev/null",O_RDONLY,0);
    // Пояснение: При успехе предыдущего шага перенаправляем stdout в /dev/null.
    if(!result)result=posix_spawn_file_actions_addopen(&actions,1,"/dev/null",O_WRONLY,0);
    // Пояснение: Аналогично убираем stderr дочерней программы с экрана ncurses.
    if(!result)result=posix_spawn_file_actions_addopen(&actions,2,"/dev/null",O_WRONLY,0);
    // Пояснение: Отдельные аргументы и завершающий NULL; адрес не интерпретируется командной оболочкой.
    char *argv[]={"xdg-open",url,NULL};
    // Пояснение: posix_spawnp ищет xdg-open по PATH и запускает процесс с подготовленными действиями и
    // Пояснение: окружением.
    if(!result)result=posix_spawnp(pid,"xdg-open",&actions,NULL,argv,environ);
    // Пояснение: Удаляем список действий и строку URL: дочернему процессу они уже переданы.
    posix_spawn_file_actions_destroy(&actions);free(url);
    // Пояснение: Неудачный запуск отображаем как ошибку, а не успешное открытие сайта.
    if(result) {snprintf(err,ERR_SIZE,"Не удалось запустить xdg-open: %s",strerror(result));return false;}
    // Пояснение: Процесс xdg-open запущен; фактическое завершение UI проверит позже.
    return true;
// Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
}
