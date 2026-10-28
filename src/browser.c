#define _POSIX_C_SOURCE 200809L
#include "browser.h"
#include <ctype.h>
#include <fcntl.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>

extern char **environ;

char *browser_url(const char *domain,char err[ERR_SIZE]) {
    size_t len=strlen(domain);
    if(!len || len>8192) {snprintf(err,ERR_SIZE,"Адрес сайта пуст или слишком длинный.");return NULL;}
    for(const unsigned char *p=(const unsigned char *)domain;*p;p++) {
        if(*p<=32 || *p==127 || *p=='\\') {
            snprintf(err,ERR_SIZE,"Адрес содержит пробелы или недопустимые управляющие символы.");return NULL;
        }
    }
    bool explicit_http=!strncasecmp(domain,"http://",7),explicit_https=!strncasecmp(domain,"https://",8);
    if(!explicit_http && !explicit_https && strstr(domain,"://")) {
        snprintf(err,ERR_SIZE,"Открываются только сайты HTTP/HTTPS.");return NULL;
    }
    const char *host=domain+(explicit_http?7:explicit_https?8:0);
    size_t hostlen=strcspn(host,"/?#");
    if(!hostlen || !(isalnum((unsigned char)*host) || (unsigned char)*host>=128 || *host=='[')) {
        snprintf(err,ERR_SIZE,"Нужен домен или адрес HTTP/HTTPS.");return NULL;
    }
    for(size_t i=0;i<hostlen;i++) {
        unsigned char c=(unsigned char)host[i];
        if(c<128 && !isalnum(c) && !strchr(".-:[]",c)) {
            snprintf(err,ERR_SIZE,"Недопустимый домен. Используйте адрес HTTP/HTTPS без логина и пароля.");return NULL;
        }
    }
    if(explicit_http || explicit_https)return str_copy(domain);
    char *url=mem_alloc(len+9);sprintf(url,"https://%s",domain);return url;
}
bool browser_start(const char *domain,pid_t *pid,char err[ERR_SIZE]) {
    char *url=browser_url(domain,err);if(!url)return false;
    posix_spawn_file_actions_t actions;
    int result=posix_spawn_file_actions_init(&actions);
    if(result) {snprintf(err,ERR_SIZE,"Не удалось подготовить браузер: %s",strerror(result));free(url);return false;}
    result=posix_spawn_file_actions_addopen(&actions,0,"/dev/null",O_RDONLY,0);
    if(!result)result=posix_spawn_file_actions_addopen(&actions,1,"/dev/null",O_WRONLY,0);
    if(!result)result=posix_spawn_file_actions_addopen(&actions,2,"/dev/null",O_WRONLY,0);
    char *argv[]={"xdg-open",url,NULL};
    if(!result)result=posix_spawnp(pid,"xdg-open",&actions,NULL,argv,environ);
    posix_spawn_file_actions_destroy(&actions);free(url);
    if(result) {snprintf(err,ERR_SIZE,"Не удалось запустить xdg-open: %s",strerror(result));return false;}
    return true;
}
