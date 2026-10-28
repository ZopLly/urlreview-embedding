#define _XOPEN_SOURCE 700
#include "core.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static char error[ERR_SIZE];
static const char *header = "domain;class;label;action;description\r\n";
static void write_file(const char *path, const char *data) {
    FILE *f = fopen(path, "wb"); assert(f);
    assert(fwrite(data, 1, strlen(data), f) == strlen(data)); assert(fclose(f)==0);
}
static void test_csv(void) {
    const char *text="\xef\xbb\xbf" "domain;class;label;action;description;extra\r\n"
        "x.example;shopping;;;\"Русский; текст \"\"кавычки\"\"\r\nпродолжение\";\r\n"
        "x.example;music;;OK;;tail\r\n";
    Table t={0}; assert(table_parse(text,strlen(text),';',&t,error));
    assert(t.count==3 && t.columns==6 && t.bom && strcmp(t.eol,"\r\n")==0);
    assert(strcmp(cell(&t,1,DESCRIPTION),"Русский; текст \"кавычки\"\r\nпродолжение")==0);
    assert(strcmp(t.rows[1].cells[5],"")==0 && reviewed_count(&t)==1);
    size_t n; char *out=table_serialize(&t,&n); Table again={0};
    assert(table_parse(out,n,';',&again,error));
    for(size_t r=0;r<t.count;r++) for(size_t c=0;c<t.columns;c++) assert(strcmp(t.rows[r].cells[c],again.rows[r].cells[c])==0);
    free(out); table_free(&again); table_free(&t);
    const char *bad[]={
        "domain;class;label;action;description\na;b;;;\"unclosed",
        "domain;class;label;action;description\na;b;;;bare\"quote\n",
        "domain;class;label;action;description\na;b;;;\"x\"trailing\n",
        "domain;class;label;action;description\na;b;;OK\n",
        "domain;class;label;action;action\na;b;;;\n",
        "domain;class;label;action;description\na;b;;WRONG;d\n"
    };
    for(size_t i=0;i<sizeof bad/sizeof *bad;i++) assert(!table_parse(bad[i],strlen(bad[i]),';',&t,error));
    char *long_text=mem_alloc(20000); strcpy(long_text,header); strcat(long_text,"a;b;;;");
    size_t start=strlen(long_text); memset(long_text+start,'x',15000); long_text[start+15000]='\0';
    assert(table_parse(long_text,strlen(long_text),';',&t,error)); assert(strlen(cell(&t,1,DESCRIPTION))==15000);
    table_free(&t); free(long_text);
    const char *reordered="extra\tdescription\taction\tlabel\tclass\tdomain\n\tтекст\t\t\tmusic\tx.example";
    assert(table_parse(reordered,strlen(reordered),'\t',&t,error)); assert(strcmp(cell(&t,1,DOMAIN),"x.example")==0); table_free(&t);
    puts("CSV: quoted/multiline/long/BOM/schema/status/reordered/trailing fields OK");
}
static void test_encoding(void) {
    const char *text="Инструменты; Ёжик"; size_t n,m;
    char *cp=convert_text(text,strlen(text),"UTF-8","WINDOWS-1251",&n,error); assert(cp);
    char *utf=convert_text(cp,n,"WINDOWS-1251","UTF-8",&m,error); assert(utf && strcmp(utf,text)==0);
    free(cp); free(utf);
    assert(!convert_text("😀",strlen("😀"),"UTF-8","WINDOWS-1251",&n,error));
    assert(!convert_text("\xff",1,"UTF-8","UTF-8",&n,error));
    puts("Encoding: exact CP1251 roundtrip; unrepresentable/invalid bytes rejected OK");
}
static void test_store(void) {
    char dir[]="/tmp/url-review-core-XXXXXX"; assert(mkdtemp(dir));
    char input[512],output[512],linkname[512],lock[520];
    snprintf(input,sizeof input,"%s/input.csv",dir); snprintf(output,sizeof output,"%s/work.csv",dir);
    snprintf(linkname,sizeof linkname,"%s/alias.csv",dir); snprintf(lock,sizeof lock,"%s.lock",output);
    const char *original="domain;class;label;action;description\nx.example;shopping;;;\"продажа; инструментов\"\nx.example;music;;;\n";
    write_file(input,original); Store s, other;
    assert(!store_open(&s,input,input,"UTF-8",';',error));
    assert(link(input,linkname)==0); assert(!store_open(&s,input,linkname,"UTF-8",';',error)); unlink(linkname);
    assert(store_open(&s,input,output,"UTF-8",';',error));
    assert(!store_open(&other,input,output,"UTF-8",';',error));
    assert(store_commit(&s,1,"ERROR","shopping,music",error));
    assert(strcmp(cell(&s.table,1,ACTION),"ERROR")==0 && strcmp(cell(&s.table,2,ACTION),"")==0);
    assert(!store_commit(&s,2,"nonsense","",error));
    assert(!store_commit(&s,0,"OK","",error));
    size_t n; char *saved=read_bytes(output,&n,error); assert(saved);
    assert(store_commit(&s,1,"OK","",error)); assert(reviewed_count(&s.table)==1);
    write_file(output,"external edit\n");
    assert(!store_commit(&s,2,"OK","",error)); assert(strcmp(cell(&s.table,2,ACTION),"")==0);
    store_close(&s);
    write_file(output,saved); free(saved);
    assert(store_open(&s,input,output,"UTF-8",';',error)); assert(reviewed_count(&s.table)==1); store_close(&s);
    write_file(output,"domain;class;label;action;description\ny.example;shopping;;;changed\n");
    assert(!store_open(&s,input,output,"UTF-8",';',error));
    char *unchanged=read_bytes(input,&n,error); assert(strcmp(unchanged,original)==0); free(unchanged);
    unlink(output); unlink(lock); unlink(input); rmdir(dir);
    puts("Store: immutable input/lock/resume/rollback/external edits/duplicate domains OK");
}
int main(void) {test_csv();test_encoding();test_store();puts("core: all checks passed");return 0;}
