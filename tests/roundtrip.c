#include "core.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc,char **argv) {
    if(argc!=5)return 2;
    char err[ERR_SIZE];Table t;
    char sep=!strcmp(argv[4],"tab")?'\t':argv[4][0];
    if(!table_read(argv[1],argv[3],sep,&t,err)){fprintf(stderr,"%s\n",err);return 1;}
    size_t n,m;char *utf=table_serialize(&t,&n);
    char *out=convert_text(utf,n,"UTF-8",argv[3],&m,err);free(utf);table_free(&t);
    if(!out)return 1;
    FILE *f=fopen(argv[2],"wb");if(!f){free(out);return 1;}
    bool ok=fwrite(out,1,m,f)==m;free(out);
    if(fclose(f))ok=false;
    return ok?0:1;
}
