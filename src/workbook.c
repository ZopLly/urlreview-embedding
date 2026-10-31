// C-мост к OOXML backend: временные дескрипторы вместо shell и двунаправленных pipe.
#define _POSIX_C_SOURCE 200809L
#include "workbook.h"
#include <errno.h>
#include <fcntl.h>
#include <spawn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

// Окружение наследуется Python-процессом; содержимое книги в argv не попадает.
extern char **environ;
// Лимит протокола чуть больше исходника: ответ чтения содержит таблицу и номера строк.
#define BRIDGE_LIMIT ((size_t)256*1024*1024+8*1024*1024)

bool workbook_path(const char *path) {
    // Поддерживается также .XLSX; строка должна иметь хотя бы пять последних байтов.
    size_t n=strlen(path);
    return n>=5&&!strcasecmp(path+n-5,".xlsx");
}

static bool helper_path(char path[8192],char err[ERR_SIZE]) {
    // /proc/self/exe не зависит от текущего каталога пользователя.
    char executable[4096];ssize_t n=readlink("/proc/self/exe",executable,sizeof executable-1);
    if(n<=0)goto fail;
    executable[n]=0;
    char *slash=strrchr(executable,'/');if(!slash)goto fail;*slash=0;
    // Обычное приложение лежит в корне, тестовые бинарники — в build.
    snprintf(path,8192,"%s/scripts/xlsx_io.py",executable);
    if(access(path,R_OK)==0)return true;
    snprintf(path,8192,"%s/../scripts/xlsx_io.py",executable);
    if(access(path,R_OK)==0)return true;
fail:
    snprintf(err,ERR_SIZE,"Не найден scripts/xlsx_io.py рядом с приложением. Перенесите весь проект, а не только бинарник.");
    return false;
}

static char *run_helper(const char *mode,const char *sheet,const char *raw,size_t n,const char *extra,size_t extra_len,size_t *out_len,char err[ERR_SIZE]) {
    // Отдельные временные потоки не могут взаимно заблокироваться на полном pipe.
    char path[8192];if(!helper_path(path,err))return NULL;
    FILE *input=tmpfile(),*output=tmpfile();char *result=NULL;
    if(!input||!output){snprintf(err,ERR_SIZE,"Не удалось создать временный поток XLSX: %s",strerror(errno));goto finish;}
    if(extra) {
        // При записи передаём uint64 длину шаблона, сам XLSX, затем новый CSV.
        unsigned char length[8];
        for(unsigned i=0;i<8;i++)length[i]=(unsigned char)((uint64_t)n>>(8*i));
        if(fwrite(length,1,8,input)!=8)goto io_error;
    }
    if(fwrite(raw,1,n,input)!=n||(extra&&fwrite(extra,1,extra_len,input)!=extra_len)||fflush(input)||fseek(input,0,SEEK_SET))goto io_error;
    // posix_spawn получает каждый аргумент отдельно; имена листов не исполняются как команды.
    char *argv[]={"python3",path,(char *)mode,(char *)(sheet?sheet:""),NULL};
    posix_spawn_file_actions_t actions;int code=posix_spawn_file_actions_init(&actions);
    if(code){snprintf(err,ERR_SIZE,"Не удалось подготовить XLSX backend: %s",strerror(code));goto finish;}
    code=posix_spawn_file_actions_adddup2(&actions,fileno(input),STDIN_FILENO);
    if(!code)code=posix_spawn_file_actions_adddup2(&actions,fileno(output),STDOUT_FILENO);
    // Диагностика Python идёт через ERR-протокол; traceback не должен разрушать экран ncurses.
    if(!code)code=posix_spawn_file_actions_addopen(&actions,STDERR_FILENO,"/dev/null",O_WRONLY,0);
    // После dup2 закрываем исходные номера в дочернем процессе.
    if(!code)code=posix_spawn_file_actions_addclose(&actions,fileno(input));
    if(!code)code=posix_spawn_file_actions_addclose(&actions,fileno(output));
    pid_t pid=0;
    if(!code)code=posix_spawnp(&pid,"python3",&actions,NULL,argv,environ);
    posix_spawn_file_actions_destroy(&actions);
    if(code){snprintf(err,ERR_SIZE,"Для XLSX нужен Python 3 и scripts/xlsx_io.py: %s",strerror(code));goto finish;}
    int status;pid_t waited;
    // Прерывание waitpid сигналом не означает, что Python уже завершился.
    do{waited=waitpid(pid,&status,0);}while(waited<0&&errno==EINTR);
    if(waited<0){snprintf(err,ERR_SIZE,"Не удалось дождаться XLSX backend.");goto finish;}
    struct stat st;
    if(fstat(fileno(output),&st)||st.st_size<3||(size_t)st.st_size>BRIDGE_LIMIT||fseek(output,0,SEEK_SET))goto io_error;
    size_t size=(size_t)st.st_size;
    char *response=mem_alloc(size+1);
    if(fread(response,1,size,output)!=size){free(response);goto io_error;}
    if(size>=4&&!memcmp(response,"ERR\n",4)) {
        snprintf(err,ERR_SIZE,"XLSX: %s",response+4);free(response);goto finish;
    }
    if(memcmp(response,"OK\n",3)||!WIFEXITED(status)||WEXITSTATUS(status)!=0) {
        snprintf(err,ERR_SIZE,"XLSX backend завершился с ошибкой; рабочая копия не заменена.");free(response);goto finish;
    }
    // Убираем служебный префикс, сохраняя бинарные нули внутри ZIP.
    memmove(response,response+3,size-3);response[size-3]=0;*out_len=size-3;result=response;
    goto finish;
io_error:
    snprintf(err,ERR_SIZE,"Ошибка обмена с XLSX backend; рабочая копия не заменена.");
finish:
    if(input)fclose(input);
    if(output)fclose(output);
    return result;
}

static uint32_t little32(const unsigned char *p) {
    // Четыре байта протокола независимо от машинного порядка байтов.
    return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;
}

bool workbook_read(const char *raw,size_t len,const char *sheet,Table *table,char err[ERR_SIZE]) {
    // Тело ответа: длина имени, число строк, имя UTF-8, uint32 номера строк, CSV UTF-8.
    size_t n;char *reply=run_helper("read",sheet,raw,len,NULL,0,&n,err);if(!reply)return false;
    bool ok=false;
    if(n<8)goto invalid;
    const unsigned char *p=(const unsigned char *)reply;
    size_t name_len=little32(p),count=little32(p+4);
    if(name_len>n-8||count>(n-8-name_len)/4||!count)goto invalid;
    size_t offset=8+name_len+4*count;
    if(memchr(reply+8,0,name_len)||!table_parse(reply+offset,n-offset,';',table,err))goto finish;
    if(table->count!=count){table_free(table);goto invalid;}
    table->sheet=mem_alloc(name_len+1);memcpy(table->sheet,reply+8,name_len);
    table->source_rows=mem_alloc(count*sizeof *table->source_rows);
    for(size_t r=0;r<count;r++)table->source_rows[r]=little32(p+8+name_len+4*r);
    ok=true;goto finish;
invalid:
    snprintf(err,ERR_SIZE,"Неверный ответ XLSX backend.");
finish:
    free(reply);return ok;
}

char *workbook_write(const char *raw,size_t len,const Table *table,size_t *out_len,char err[ERR_SIZE]) {
    // Сериализатор C отдаёт значения, Python проверит неизменяемые ячейки перед заменой action/label.
    size_t csv_len;char *csv=table_serialize(table,&csv_len);
    char *result=run_helper("write",table->sheet,raw,len,csv,csv_len,out_len,err);
    free(csv);return result;
}
