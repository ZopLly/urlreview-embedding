#include "embedding.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static void u32(FILE *f,unsigned n){for(int i=0;i<4;i++)fputc((n>>(8*i))&255,f);}
static void u64(FILE *f,uint64_t n){for(int i=0;i<8;i++)fputc((int)((n>>(8*i))&255),f);}
static void fixture(const char *path,const uint64_t *hashes,bool broken){
 FILE *f=fopen(path,"wb");assert(f);fwrite("UREMB01\n",1,8,f);u32(f,4);u32(f,384);
 for(int r=0;r<4;r++){
  u64(f,hashes[r]);for(int d=0;d<384;d++){
   float v=d==0?(r==2?0:1):d==1&&r==2?1:0;
   if(broken&&r==0&&d==0)v=NAN;
   uint32_t bits;memcpy(&bits,&v,4);u32(f,bits);
  }
 }fclose(f);
}
int main(void){
 const char *csv="domain;class;label;action;description\none.example;shopping;;;Инструменты\ntwo.example;shopping;;OK;Магазин\nthree.example;music;;ERROR;Музыка\nfour.example;shopping;;;Пусто\n";
 Table t={0};Embedding e={0};EmbeddingHit hits[5];char err[ERR_SIZE];
 assert(table_parse(csv,strlen(csv),';',&t,err));
 const uint64_t hashes[]={UINT64_C(0x1952e5c4f4004a9),UINT64_C(0x8770eac1df2d82fc),UINT64_C(0x40326ad3f533a71a),UINT64_C(0xf6fc2ed5b0c1884d)};
 char path[]="/tmp/embedding-XXXXXX";int fd=mkstemp(path);assert(fd>=0);close(fd);
 fixture(path,hashes,false);
 assert(embedding_read(path,&t,&e,err));
 assert(embedding_search(&e,&t,1,hits,5)==2);
 assert(hits[0].row==2&&fabsf(hits[0].score-1)<.001f);assert(hits[1].row==3);
 free(t.rows[4].cells[t.col[ACTION]]);t.rows[4].cells[t.col[ACTION]]=str_copy("NOT_DESC");
 assert(embedding_search(&e,&t,1,hits,5)==3);
 embedding_free(&e);assert(embedding_read(path,&t,&e,err));embedding_free(&e);
 free(t.rows[2].cells[t.col[DESCRIPTION]]);t.rows[2].cells[t.col[DESCRIPTION]]=str_copy("Изменено");
 assert(!embedding_read(path,&t,&e,err));
 table_free(&t);assert(table_parse(csv,strlen(csv),';',&t,err));fixture(path,hashes,true);
 assert(!embedding_read(path,&t,&e,err));
 FILE *f=fopen(path,"wb");assert(f);fputs("UREMB01\n",f);u32(f,999999999);u32(f,384);fclose(f);
 assert(!embedding_read(path,&t,&e,err));
 unlink(path);table_free(&t);puts("Embeddings: ranking/live labels/stale index/NaN/size guards OK");
}
