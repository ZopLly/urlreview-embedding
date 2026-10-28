#include <errno.h>
#include <sys/stat.h>
#include <unistd.h>
int __real_fsync(int fd);
int __wrap_fsync(int fd) {
    static int directory_calls;
    struct stat st;
    if(fstat(fd,&st)==0 && S_ISDIR(st.st_mode) && ++directory_calls==2) {errno=EIO;return -1;}
    return __real_fsync(fd);
}
