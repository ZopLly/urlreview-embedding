#include "guide.h"
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void guide_free(Guide *g) {
    for(size_t i=0;i<g->count;i++) {
        free(g->items[i].code); free(g->items[i].title);
        free(g->items[i].includes); free(g->items[i].excludes);
    }
    free(g->items); memset(g,0,sizeof *g);
}
bool guide_read(const char *path,Guide *g,char err[ERR_SIZE]) {
    memset(g,0,sizeof *g); size_t n,m;
    char *raw=read_bytes(path,&n,err); if(!raw) return false;
    if(memchr(raw,0,n)) { free(raw); snprintf(err,ERR_SIZE,"Справочник содержит нулевой байт."); return false; }
    char *data=convert_text(raw,n,"UTF-8","UTF-8",&m,err); free(raw); if(!data) return false;
    char *line=data;
    while(*line) {
        char *end=strchr(line,'\n'); if(end) *end=0;
        size_t len=strlen(line); if(len && line[len-1]=='\r') line[len-1]=0;
        if(*line) {
            char *parts[4]; parts[0]=line;
            for(size_t i=1;i<4;i++) {
                char *tab=strchr(parts[i-1],'\t');
                if(!tab) goto invalid;
                *tab=0;parts[i]=tab+1;
            }
            if(strchr(parts[3],'\t') || !*parts[0] || !*parts[1] || !*parts[2]) goto invalid;
            for(const char *p=parts[0];*p;p++) if(!(*p>='a'&&*p<='z') && !(*p>='0'&&*p<='9') && *p!='_') goto invalid;
            for(size_t i=0;i<g->count;i++) if(!strcmp(g->items[i].code,parts[0])) goto invalid;
            g->items=mem_resize(g->items,(g->count+1)*sizeof *g->items);
            Category *c=&g->items[g->count++];
            c->code=str_copy(parts[0]);c->title=str_copy(parts[1]);c->includes=str_copy(parts[2]);c->excludes=str_copy(parts[3]);
        }
        if(!end) break;
        line=end+1;
    }
    free(data);
    if(g->count) return true;
    snprintf(err,ERR_SIZE,"Справочник пуст.");return false;
invalid:
    snprintf(err,ERR_SIZE,"Неверная или повторяющаяся категория в строке %zu справочника.",g->count+1);
    free(data);guide_free(g);return false;
}
