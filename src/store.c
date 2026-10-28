#define _XOPEN_SOURCE 700
#include "core.h"
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>

static char *canonical_output(const char *path, char err[ERR_SIZE]) {
    char *copy = str_copy(path), *slash = strrchr(copy,'/');
    const char *name = slash ? slash+1 : copy;
    if (!*name || !strcmp(name,".") || !strcmp(name,"..")) { snprintf(err,ERR_SIZE,"Нужно имя файла рабочей копии."); free(copy); return NULL; }
    char *base = str_copy(name);
    if (slash) { if (slash==copy) slash[1]=0; else *slash=0; }
    char *dir = realpath(slash ? copy : ".", NULL);
    if (!dir) { snprintf(err,ERR_SIZE,"Каталог рабочей копии недоступен: %s",strerror(errno)); free(base); free(copy); return NULL; }
    char *result = mem_alloc(strlen(dir)+strlen(base)+2);
    sprintf(result,"%s/%s",dir,base); free(dir); free(base); free(copy); return result;
}
static bool protected_path(Store *s, char err[ERR_SIZE]) {
    struct stat st;
    if (!strcmp(s->input,s->output)) { snprintf(err,ERR_SIZE,"Исходник и рабочая копия должны быть разными файлами."); return false; }
    if (lstat(s->output,&st)==0) {
        if (!S_ISREG(st.st_mode) || (st.st_dev==s->input_dev && st.st_ino==s->input_ino)) {
            snprintf(err,ERR_SIZE,"Рабочая копия должна быть отдельным обычным файлом, не ссылкой на исходник."); return false;
        }
    } else if (errno!=ENOENT) { snprintf(err,ERR_SIZE,"Не удалось проверить рабочую копию: %s",strerror(errno)); return false; }
    return true;
}
static bool unchanged(Store *s, char err[ERR_SIZE]) {
    if (!protected_path(s,err)) return false;
    if (!s->snapshot) {
        struct stat st;
        if (lstat(s->output,&st)==0 || errno!=ENOENT) { snprintf(err,ERR_SIZE,"Рабочая копия появилась извне. Перезапустите приложение."); return false; }
        return true;
    }
    size_t n; char *data=read_bytes(s->output,&n,err); if (!data) return false;
    bool ok=n==s->snapshot_len && !memcmp(data,s->snapshot,n); free(data);
    if (!ok) snprintf(err,ERR_SIZE,"Рабочая копия изменена другой программой. Запись отменена; перезапустите приложение.");
    return ok;
}
static bool atomic_write(Store *s, const char *data, size_t n, char err[ERR_SIZE]) {
    if (!unchanged(s,err)) return false;
    char *temp=mem_alloc(strlen(s->output)+16); sprintf(temp,"%s.tmp.XXXXXX",s->output);
    int fd=mkstemp(temp);
    if (fd<0) { snprintf(err,ERR_SIZE,"Не удалось создать временный файл: %s",strerror(errno)); free(temp); return false; }
    size_t pos=0; bool ok=true;
    while (pos<n) {
        ssize_t k=write(fd,data+pos,n-pos);
        if (k<0 && errno==EINTR) continue;
        if (k<=0) { ok=false; break; }
        pos+=(size_t)k;
    }
    if (ok && fsync(fd)!=0) ok=false;
    if (close(fd)!=0) ok=false;
    if (!ok) snprintf(err,ERR_SIZE,"Ошибка записи: %s",strerror(errno));
    if (ok) ok=unchanged(s,err);
    if (ok && rename(temp,s->output)!=0) { snprintf(err,ERR_SIZE,"Не удалось заменить рабочую копию: %s",strerror(errno)); ok=false; }
    if (!ok) unlink(temp);
    else {
        free(s->snapshot); s->snapshot=mem_alloc(n+1); memcpy(s->snapshot,data,n); s->snapshot_len=n;
        char *dir=str_copy(s->output), *slash=strrchr(dir,'/'); *slash=0;
        int dirfd=open(*dir?dir:"/",O_RDONLY|O_DIRECTORY);
        if (dirfd>=0) { if (fsync(dirfd)!=0) snprintf(err,ERR_SIZE,"Данные сохранены, но fsync каталога недоступен."); close(dirfd); }
        free(dir);
    }
    free(temp); return ok;
}
static bool compatible(const Table *a,const Table *b) {
    if(a->count!=b->count || a->columns!=b->columns) return false;
    for(size_t r=0;r<a->count;r++) for(size_t c=0;c<a->columns;c++) {
        if(r && (c==a->col[ACTION] || c==a->col[LABEL])) continue;
        if(strcmp(a->rows[r].cells[c],b->rows[r].cells[c])) return false;
    }
    return true;
}
bool store_open(Store *s,const char *input,const char *output,const char *encoding,char delimiter,char err[ERR_SIZE]) {
    memset(s,0,sizeof *s); s->lock_fd=-1; err[0]=0;
    s->input=realpath(input,NULL);
    if(!s->input) { snprintf(err,ERR_SIZE,"Исходник недоступен: %s",strerror(errno)); goto fail; }
    struct stat st;
    if(stat(s->input,&st)!=0) { snprintf(err,ERR_SIZE,"Не удалось проверить исходник."); goto fail; }
    s->input_dev=st.st_dev; s->input_ino=st.st_ino;
    s->output=canonical_output(output,err); if(!s->output) goto fail;
    s->encoding=str_copy(encoding);
    if(!protected_path(s,err)) goto fail;
    char *lock=mem_alloc(strlen(s->output)+6); sprintf(lock,"%s.lock",s->output);
    s->lock_fd=open(lock,O_CREAT|O_RDWR|O_CLOEXEC|O_NOFOLLOW,0600); free(lock);
    if(s->lock_fd<0 || flock(s->lock_fd,LOCK_EX|LOCK_NB)!=0) { snprintf(err,ERR_SIZE,"Рабочая копия занята другим экземпляром или блокировка недоступна."); goto fail; }
    if(!table_read(s->input,encoding,delimiter,&s->table,err)) goto fail;
    if(lstat(s->output,&st)==0) {
        if(!protected_path(s,err)) goto fail;
        Table resumed={0};
        if(!table_read(s->output,encoding,delimiter,&resumed,err)) goto fail;
        if(!compatible(&s->table,&resumed)) { table_free(&resumed); snprintf(err,ERR_SIZE,"Рабочая копия не соответствует исходнику: записи или неизменяемые столбцы отличаются."); goto fail; }
        table_free(&s->table); s->table=resumed;
        s->snapshot=read_bytes(s->output,&s->snapshot_len,err); if(!s->snapshot) goto fail;
    } else {
        size_t n; char *raw=read_bytes(s->input,&n,err); if(!raw) goto fail;
        bool ok=atomic_write(s,raw,n,err); free(raw); if(!ok) goto fail;
    }
    return true;
fail: store_close(s); return false;
}
bool store_commit(Store *s,size_t row,const char *action,const char *label,char err[ERR_SIZE]) {
    err[0]=0;
    if(!row || row>=s->table.count || (strcmp(action,"OK") && strcmp(action,"ERROR") && strcmp(action,"NOT_DESC"))) {
        snprintf(err,ERR_SIZE,"Недопустимая запись или действие."); return false;
    }
    char **a=&s->table.rows[row].cells[s->table.col[ACTION]], **l=&s->table.rows[row].cells[s->table.col[LABEL]];
    char *old_a=*a,*old_l=*l;
    *a=str_copy(action); *l=str_copy(label);
    size_t n,m; char *utf=table_serialize(&s->table,&n);
    char *raw=convert_text(utf,n,"UTF-8",s->encoding,&m,err); free(utf);
    bool ok=raw && atomic_write(s,raw,m,err); free(raw);
    if(ok) { free(old_a); free(old_l); }
    else { free(*a); free(*l); *a=old_a; *l=old_l; }
    return ok;
}
void store_close(Store *s) {
    table_free(&s->table); free(s->input);free(s->output);free(s->encoding);free(s->snapshot);
    if(s->lock_fd>=0) close(s->lock_fd);
    memset(s,0,sizeof *s);s->lock_fd=-1;
}
