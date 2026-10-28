#define _XOPEN_SOURCE 700
#include "core.h"
#include "guide.h"
#include "ui.h"
#include "embedding.h"
#include <locale.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static void usage(void) {
    puts("URL Review — локальная ручная разметка сайтов\n\n"
         "  url-review INPUT.csv WORK.csv [параметры]\n"
         "  url-review --check INPUT.csv [параметры]\n\n"
         "  --encoding UTF-8|windows-1251   Кодировка входа и рабочей копии\n"
         "  --delimiter ';'|','|tab         Разделитель (по умолчанию ;)\n"
         "  --guide ПУТЬ                   Справочник категорий TSV\n"
         "  --embeddings ПУТЬ              Локальный индекс похожих записей (.uremb)\n"
         "  --check                        Проверить CSV без записи и без интерфейса\n"
         "  --help                         Эта справка\n\n"
         "WORK.csv — отдельная рабочая копия. Если она существует, работа\n"
         "продолжится из неё после проверки совместимости с исходником.\n"
         "Не открывайте рабочую копию одновременно в офисном редакторе.\n"
         "Демо: ./scripts/run-demo.sh");
}
static char *default_guide(const char *arg0) {
    char executable[4096]; ssize_t n=readlink("/proc/self/exe",executable,sizeof executable-1);
    char *path;
    if(n>0) { executable[n]=0;path=str_copy(executable); }
    else { path=realpath(arg0,NULL); if(!path) return str_copy("data/categories.tsv"); }
    char *slash=strrchr(path,'/');if(slash) *slash=0;
    char *result=mem_alloc(strlen(path)+32);sprintf(result,"%s/data/categories.tsv",path);free(path);return result;
}
int main(int argc,char **argv) {
    if(!setlocale(LC_ALL,"")) setlocale(LC_ALL,"C.UTF-8");
    if(MB_CUR_MAX==1 && !setlocale(LC_CTYPE,"C.UTF-8")) {
        fputs("Для интерфейса нужна UTF-8 locale (например C.UTF-8).\n",stderr);return 1;
    }
    const char *input=NULL,*output=NULL,*encoding="UTF-8",*guide_path=NULL,*embedding_path=NULL;
    char delimiter=';';bool check=false;
    for(int i=1;i<argc;i++) {
        if(!strcmp(argv[i],"--help") || !strcmp(argv[i],"-h")) { usage();return 0; }
        if(!strcmp(argv[i],"--check")) { check=true;continue; }
        if(!strcmp(argv[i],"--encoding") || !strcmp(argv[i],"--delimiter") || !strcmp(argv[i],"--guide") || !strcmp(argv[i],"--embeddings")) {
            const char *option=argv[i];
            if(++i>=argc) { fprintf(stderr,"Нужно значение для %s\n",option);return 1; }
            if(!strcmp(option,"--encoding")) {
                if(!strcasecmp(argv[i],"utf-8")) encoding="UTF-8";
                else if(!strcasecmp(argv[i],"windows-1251") || !strcasecmp(argv[i],"cp1251")) encoding="WINDOWS-1251";
                else { fputs("Кодировка: UTF-8 или windows-1251.\n",stderr);return 1; }
            } else if(!strcmp(option,"--guide")) guide_path=argv[i];
            else if(!strcmp(option,"--embeddings")) embedding_path=argv[i];
            else if(!strcmp(argv[i],"tab") || !strcmp(argv[i],"\\t")) delimiter='\t';
            else if(!strcmp(argv[i],";") || !strcmp(argv[i],",")) delimiter=argv[i][0];
            else { fputs("Разделитель: ; , или tab.\n",stderr);return 1; }
        } else if(argv[i][0]=='-') { fprintf(stderr,"Неизвестный параметр: %s\n",argv[i]);return 1; }
        else if(!input) input=argv[i];
        else if(!output) output=argv[i];
        else { fputs("Лишний путь в аргументах.\n",stderr);return 1; }
    }
    if(!input || (!check&&!output) || (check&&output)) { usage();return 1; }
    char err[ERR_SIZE];
    if(check) {
        Table t={0};
        if(!table_read(input,encoding,delimiter,&t,err)) { fprintf(stderr,"%s\n",err);return 1; }
        printf("CSV корректен. Записей: %zu; проверено: %zu; столбцов: %zu.\n",t.count-1,reviewed_count(&t),t.columns);
        Embedding index={0};
        if(embedding_path&&!embedding_read(embedding_path,&t,&index,err)) {
            fprintf(stderr,"%s\n",err);table_free(&t);return 1;
        }
        if(embedding_path)puts("Индекс совместим с CSV.");
        embedding_free(&index);table_free(&t);return 0;
    }
    if(!isatty(STDIN_FILENO) || !isatty(STDOUT_FILENO)) { fputs("Запустите приложение в терминале. Для проверки без интерфейса используйте --check.\n",stderr);return 1; }
    char *guide_default=default_guide(argv[0]); Guide guide;
    if(!guide_read(guide_path?guide_path:guide_default,&guide,err)) { fprintf(stderr,"Справочник: %s\n",err);free(guide_default);return 1; }
    free(guide_default);
    Store store;
    if(!store_open(&store,input,output,encoding,delimiter,err)) { fprintf(stderr,"%s\n",err);guide_free(&guide);return 1; }
    Embedding index={0};
    if(embedding_path&&!embedding_read(embedding_path,&store.table,&index,err)) {
        fprintf(stderr,"%s\n",err);store_close(&store);guide_free(&guide);return 1;
    }
    int result=ui_run(&store,&guide,&index);
    embedding_free(&index);
    store_close(&store);guide_free(&guide);return result;
}
