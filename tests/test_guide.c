#include "guide.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
int main(void) {
    Guide g={0}; char err[ERR_SIZE];
    assert(guide_read("data/categories.tsv",&g,err)); assert(g.count>40);
    assert(!strcmp(g.items[0].code,"porno_and_erotics"));
    bool shopping=false,c2=false;
    for(size_t i=0;i<g.count;i++) {
        if(!strcmp(g.items[i].code,"shopping")) { shopping=true; assert(strstr(g.items[i].includes,"продаж")); }
        if(!strcmp(g.items[i].code,"c2")) c2=true;
    }
    assert(shopping && c2); guide_free(&g);
    char path[]="/tmp/url-review-guide-XXXXXX"; int fd=mkstemp(path); assert(fd>=0);
    FILE *f=fdopen(fd,"w"); assert(f); fputs("shopping\tПокупки\tТовары\t\nshopping\tДубль\tТовары\t\n",f); fclose(f);
    assert(!guide_read(path,&g,err)); unlink(path);
    puts("Guide: actual rules/stable order/c2/duplicate detection OK");
}
