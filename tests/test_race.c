#include "core.h"
#include <assert.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Linker interposition injects one real external write between production reads.
   Only this test binary is wrapped. No test hooks are present in production. */
FILE *__real_fopen(const char *,const char *);
static const char *watched;
static int reads;
static const char *updated="domain;class;label;action;description\nx.example;shopping;;OK;first\ny.example;music;;;second\n";
FILE *__wrap_fopen(const char *path,const char *mode) {
    if(watched && !strcmp(path,watched) && mode[0]=='r' && ++reads==2) {
        int fd=open(path,O_WRONLY|O_TRUNC);assert(fd>=0);
        size_t n=strlen(updated);assert(write(fd,updated,n)==(ssize_t)n);assert(close(fd)==0);
    }
    return __real_fopen(path,mode);
}
static void put(const char *path,const char *text) {
    FILE *f=__real_fopen(path,"w");assert(f);assert(fputs(text,f)>=0);assert(fclose(f)==0);
}
int main(void) {
    char dir[]="/tmp/url-review-race-XXXXXX";assert(mkdtemp(dir));
    char input[512],output[512],lock[520];
    snprintf(input,sizeof input,"%s/input.csv",dir);snprintf(output,sizeof output,"%s/work.csv",dir);snprintf(lock,sizeof lock,"%s.lock",output);
    const char *original="domain;class;label;action;description\nx.example;shopping;;;first\ny.example;music;;;second\n";
    put(input,original);put(output,original);
    watched=output;reads=0;
    Store s;char err[ERR_SIZE];assert(store_open(&s,input,output,"UTF-8",';',err));
    (void)store_commit(&s,2,"ERROR","music",err);
    watched=NULL;
    Table actual;assert(table_read(output,"UTF-8",';',&actual,err));
    assert(!strcmp(cell(&actual,1,ACTION),"OK") && "external decision must not be lost");
    table_free(&actual);store_close(&s);unlink(output);unlink(lock);unlink(input);rmdir(dir);
    puts("Store race: a concurrent external decision cannot become an unread baseline OK");
}
