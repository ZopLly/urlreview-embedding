#include "embedding.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static uint32_t little32(const unsigned char *p) {
    return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;
}
static uint64_t fingerprint(const char *domain,const char *description) {
    uint64_t h=UINT64_C(14695981039346656037);
    const unsigned char *p=(const unsigned char *)domain;
    do {h=(h^*p)*UINT64_C(1099511628211);}while(*p++);
    for(p=(const unsigned char *)description;*p;p++)h=(h^*p)*UINT64_C(1099511628211);
    return h;
}
void embedding_free(Embedding *e) {free(e->vectors);memset(e,0,sizeof *e);}
bool embedding_read(const char *path,const Table *t,Embedding *e,char err[ERR_SIZE]) {
    memset(e,0,sizeof *e);size_t n;char *raw=read_bytes(path,&n,err);if(!raw)return false;
    const unsigned char *p=(const unsigned char *)raw;
    const size_t record=8+4*EMBEDDING_DIM;
    if(n<16||memcmp(p,"UREMB01\n",8)||little32(p+12)!=EMBEDDING_DIM||
       !t->count||little32(p+8)!=t->count-1||t->count-1>(SIZE_MAX-16)/record||n!=16+(t->count-1)*record) {
        snprintf(err,ERR_SIZE,"Неверный формат индекса или число записей. Пересоздайте индекс для этой таблицы.");free(raw);return false;
    }
    e->count=t->count;e->vectors=mem_alloc(t->count*EMBEDDING_DIM*sizeof(float));
    p+=16;
    for(size_t r=1;r<t->count;r++,p+=record) {
        uint64_t hash=(uint64_t)little32(p)|(uint64_t)little32(p+4)<<32;
        if(hash!=fingerprint(cell(t,r,DOMAIN),cell(t,r,DESCRIPTION))) {
            snprintf(err,ERR_SIZE,"Индекс устарел: домен или описание записи %zu изменены. Пересоздайте индекс.",r);goto fail;
        }
        float *v=e->vectors+r*EMBEDDING_DIM;double norm=0;
        for(size_t d=0;d<EMBEDDING_DIM;d++) {
            uint32_t bits=little32(p+8+d*4);memcpy(v+d,&bits,4);
            if(!isfinite(v[d])||fabsf(v[d])>1.001f)goto invalid_vector;
            norm+=(double)v[d]*v[d];
        }
        if(norm!=0&&fabs(norm-1)>.02)goto invalid_vector;
    }
    free(raw);return true;
invalid_vector:
    snprintf(err,ERR_SIZE,"Индекс повреждён: неверный вектор.");
fail:
    free(raw);embedding_free(e);return false;
}
size_t embedding_search(const Embedding *e,const Table *t,size_t row,EmbeddingHit *hits,size_t capacity) {
    if(!e||!e->vectors||e->count!=t->count||!row||row>=t->count||!capacity)return 0;
    const float *q=e->vectors+row*EMBEDDING_DIM;float norm=0;
    for(size_t d=0;d<EMBEDDING_DIM;d++)norm+=q[d]*q[d];
    if(norm==0)return 0;
    size_t count=0;
    for(size_t r=1;r<t->count;r++) {
        const char *a=cell(t,r,ACTION);
        if(r==row||(strcmp(a,"OK")&&strcmp(a,"ERROR")&&strcmp(a,"NOT_DESC")))continue;
        const float *v=e->vectors+r*EMBEDDING_DIM;float dot=0,vnorm=0;
        for(size_t d=0;d<EMBEDDING_DIM;d++){dot+=q[d]*v[d];vnorm+=v[d]*v[d];}
        if(vnorm==0)continue;
        float score=fmaxf(-1,fminf(1,dot/sqrtf(norm*vnorm)));
        size_t pos=0;while(pos<count&&hits[pos].score>=score)pos++;
        if(pos>=capacity)continue;
        if(count<capacity)count++;
        for(size_t i=count-1;i>pos;i--)hits[i]=hits[i-1];
        hits[pos]=(EmbeddingHit){r,score};
    }
    return count;
}
