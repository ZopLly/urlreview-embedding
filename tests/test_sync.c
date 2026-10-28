#include "core.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

int __real_fsync(int fd);
static bool fail_directory_sync;
int __wrap_fsync(int fd) {
    struct stat st;assert(fstat(fd,&st)==0);
    if(fail_directory_sync && S_ISDIR(st.st_mode)){errno=EIO;return -1;}
    return __real_fsync(fd);
}
int main(void) {
    char dir[]="/tmp/url-review-sync-XXXXXX";assert(mkdtemp(dir));
    char input[512],output[512],lock[520];
    snprintf(input,sizeof input,"%s/input.csv",dir);snprintf(output,sizeof output,"%s/work.csv",dir);snprintf(lock,sizeof lock,"%s.lock",output);
    FILE *f=fopen(input,"w");assert(f);fputs("domain;class;label;action;description\nx.example;shopping;;;test\n",f);assert(fclose(f)==0);
    Store s;char err[ERR_SIZE];assert(store_open(&s,input,output,"UTF-8",';',err));
    fail_directory_sync=true;
    assert(store_commit(&s,1,"ERROR","shopping",err)==SAVE_UNCERTAIN && "uncertain durability is not ordinary success");
    assert(*err && !strcmp(cell(&s.table,1,ACTION),"ERROR"));
    Table actual;assert(table_read(output,"UTF-8",';',&actual,err));assert(!strcmp(cell(&actual,1,ACTION),"ERROR"));table_free(&actual);
    fail_directory_sync=false;assert(store_commit(&s,1,"ERROR","shopping",err)==1);
    store_close(&s);unlink(output);unlink(lock);unlink(input);rmdir(dir);
    puts("Store sync: replaced-but-uncertain is explicit; memory matches disk; retry succeeds OK");
}
