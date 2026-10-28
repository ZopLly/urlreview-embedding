#include "browser.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(void) {
    char err[ERR_SIZE];char *url=browser_url("example.com",err);
    assert(url && !strcmp(url,"https://example.com"));free(url);
    url=browser_url("https://example.com/path?a=1&b=2",err);
    assert(url && !strcmp(url,"https://example.com/path?a=1&b=2"));free(url);
    url=browser_url("http://пример.рф/test",err);assert(url && !strcmp(url,"http://пример.рф/test"));free(url);
    const char *invalid[]={"","file:///tmp/example","javascript:alert(1)","https://","//example.com","-bad","example.com\nother","https://user@host.example","example.com;touch /tmp/no","https://example.com\\evil"};
    for(size_t i=0;i<sizeof invalid/sizeof *invalid;i++)assert(!browser_url(invalid[i],err));
    puts("Browser URLs: HTTPS default, explicit HTTP(S), Unicode, invalid schemes/controls rejected OK");
}
