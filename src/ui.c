#define _XOPEN_SOURCE_EXTENDED 1
#include "ui.h"
#include <ctype.h>
#include <curses.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

typedef struct { wchar_t **items; size_t count; int width; } Lines;
typedef struct {
    Store *store;
    const Guide *guide;
    bool *deferred;
    size_t *history, history_count, history_pos;
    size_t row, scroll;
    Lines description;
    char message[ERR_SIZE];
} UI;
static volatile sig_atomic_t stopped=0;
static void interrupted(int signo) { (void)signo; stopped=1; }
static wchar_t *wide_text(const char *s) {
    size_t n=strlen(s); wchar_t *w=mem_alloc((n+1)*sizeof *w);
    mbstate_t state={0};size_t i=0,pos=0;
    while(pos<n) {
        wchar_t ch;size_t k=mbrtowc(&ch,s+pos,n-pos,&state);
        if(k==(size_t)-1 || k==(size_t)-2) { ch=L'�';k=1;memset(&state,0,sizeof state); }
        if(!k) break;
        w[i++]=ch;pos+=k;
    }
    w[i]=0;return w;
}
static void text(int y,int x,const char *s,int width) {
    if(y<0 || y>=LINES || x<0 || x>=COLS || width<=0) return;
    if(width>COLS-x) width=COLS-x;
    wchar_t *w=wide_text(s);int cells=0;size_t n=0;
    while(w[n]) {
        int size=wcwidth(w[n]);
        if(size<0) { w[n]=L' ';size=1; }
        if(cells+size>width) break;
        cells+=size;n++;
    }
    mvaddnwstr(y,x,w,(int)n);free(w);
}
static void lines_free(Lines *l) {
    for(size_t i=0;i<l->count;i++) free(l->items[i]);
    free(l->items);memset(l,0,sizeof *l);
}
static void line_add(Lines *l,const wchar_t *w,size_t n) {
    l->items=mem_resize(l->items,(l->count+1)*sizeof *l->items);
    wchar_t *copy=mem_alloc((n+1)*sizeof *copy);memcpy(copy,w,n*sizeof *copy);
    l->items[l->count++]=copy;
}
static void lines_make(Lines *l,const char *s,int width) {
    lines_free(l);if(width<1) width=1;l->width=width;
    wchar_t *w=wide_text(s), *line=mem_alloc((strlen(s)+2)*sizeof *line);
    size_t len=0;int cells=0;
    for(size_t i=0;w[i];i++) {
        wchar_t ch=w[i];if(ch==L'\r') continue;
        if(ch==L'\n') {line_add(l,line,len);len=0;cells=0;continue;}
        int size=wcwidth(ch);
        if(size<0 || ch==L'\t') {ch=L' ';size=1;}
        if(size>width) {ch=L'?';size=1;}
        if(cells+size>width && len) {line_add(l,line,len);len=0;cells=0;}
        line[len++]=ch;cells+=size;
    }
    if(len || !l->count) line_add(l,line,len);
    free(w);free(line);
}
static void draw_lines(const Lines *l,int top,int height,size_t scroll) {
    for(int i=0;i<height && scroll+(size_t)i<l->count;i++) mvaddnwstr(top+i,2,l->items[scroll+(size_t)i],-1);
}
static void header(const char *title) {
    erase();attron(COLOR_PAIR(1)|A_BOLD);text(0,2,title,COLS-4);attroff(COLOR_PAIR(1)|A_BOLD);
    if(LINES>1) mvhline(1,1,ACS_HLINE,COLS>2?COLS-2:1);
}
static bool small_screen(void) {
    if(COLS>=65 && LINES>=18) return false;
    erase();text(0,0,"Увеличьте окно терминала: минимум 65×18.",COLS);
    text(2,0,"Q — выход; Escape — назад",COLS);refresh();return true;
}
static void scroll_key(int key,size_t *scroll,size_t count,int height) {
    size_t max=count>(size_t)height?count-(size_t)height:0;
    if(key==KEY_DOWN || key=='j') {if(*scroll<max) (*scroll)++;}
    if(key==KEY_UP || key=='k') {if(*scroll) (*scroll)--;}
    if(key==KEY_NPAGE || key==' ') *scroll=(*scroll+(size_t)height>max)?max:*scroll+(size_t)height;
    if(key==KEY_PPAGE) *scroll=*scroll>(size_t)height?*scroll-(size_t)height:0;
    if(key==KEY_HOME || key=='g') *scroll=0;
    if(key==KEY_END || key=='G') *scroll=max;
    if(*scroll>max) *scroll=max;
}
static int read_key(void) { return stopped?'q':getch(); }
static void viewer(const char *title,const char *body) {
    Lines lines={0};size_t scroll=0;
    while(!stopped) {
        if(!small_screen()) {
            if(lines.width!=COLS-4) lines_make(&lines,body,COLS-4);
            scroll_key(0,&scroll,lines.count,LINES-5);header(title);
            draw_lines(&lines,3,LINES-5,scroll);
            text(LINES-1,2,"↑↓ / PgUp PgDn — прокрутка    Escape / Q — назад",COLS-4);refresh();
        }
        int key=read_key();if(key=='q'||key=='Q'||key==27) break;
        scroll_key(key,&scroll,lines.count,LINES>5?LINES-5:1);
    }
    lines_free(&lines);
}
static void category_help(const Guide *g,size_t index) {
    const Category *c=&g->items[index];
    size_t n=strlen(c->includes)+strlen(c->excludes)+strlen(c->title)+strlen(c->code)+200;
    char *body=mem_alloc(n);
    snprintf(body,n,"%s — %s\n\nВключает:\n%s\n\nНе включает:\n%s",c->code,c->title,c->includes,*c->excludes?c->excludes:"Отдельные исключения в справочнике не указаны.");
    viewer("Справка по категории",body);free(body);
}
static int exit_draft(bool uncertain) {
    while(!stopped) {
        bool too_small=small_screen();
        if(!too_small) {
            header(uncertain?"Запись требует проверки":"Несохранённое решение");
            text(4,2,"S — перейти к сохранению",COLS-4);
            text(6,2,uncertain?"D — выйти без новой попытки записи":"D — выйти без этого решения",COLS-4);
            text(8,2,"C / Escape — продолжить редактирование",COLS-4);refresh();
        }
        int key=read_key();if(!too_small && (key=='s'||key=='S')) return 1;
        if(key=='d'||key=='D') return 2;
        if(key=='c'||key=='C'||key==27) return 0;
    }
    return 2;
}
static char *selected_label(const Guide *g,const bool *selected) {
    size_t n=1;for(size_t i=0;i<g->count;i++) if(selected[i]) n+=strlen(g->items[i].code)+1;
    char *label=mem_alloc(n);
    for(size_t i=0;i<g->count;i++) if(selected[i]) {if(*label) strcat(label,",");strcat(label,g->items[i].code);}
    return label;
}
/* Return 0 to edit categories, 1 after durable save, 2 to quit. */
static int confirm(UI *ui,const char *action,const char *label) {
    char err[ERR_SIZE];bool uncertain=false;size_t scroll=0;Lines content={0};
    const Table *t=&ui->store->table;
    size_t size=strlen(cell(t,ui->row,DOMAIN))+strlen(cell(t,ui->row,CLASS))+strlen(label)+strlen(cell(t,ui->row,LABEL))+strlen(action)+400;
    char *body=mem_alloc(size);
    snprintf(body,size,"%s\nИсходный class: %s\n\nДействие: %s\n\nКатегории (label):\n%s\n\nПрежний label:\n%s",cell(t,ui->row,DOMAIN),cell(t,ui->row,CLASS),action,*label?label:"(пусто)",*cell(t,ui->row,LABEL)?cell(t,ui->row,LABEL):"(пусто)");
    int outcome=2;
    while(!stopped) {
        bool too_small=small_screen();
        if(!too_small) {
            if(content.width!=COLS-4)lines_make(&content,body,COLS-4);
            scroll_key(0,&scroll,content.count,LINES-6);
            header(uncertain?"Запись требует проверки":"Подтверждение решения");
            draw_lines(&content,3,LINES-6,scroll);
            text(LINES-2,2,uncertain?"Enter — повторить сохранение":"Enter — сохранить и продолжить",COLS-4);
            text(LINES-1,2,"↑↓ PgUp/PgDn Home/End — просмотр   Esc — изменить   Q — выход",COLS-4);refresh();
        }
        int key=read_key();
        if(key==27){outcome=0;break;}
        if(too_small) {
            if((key=='q'||key=='Q') && exit_draft(uncertain)==2)break;
            continue;
        }
        bool save=key=='\n'||key==KEY_ENTER||key=='\r';
        if(key=='q'||key=='Q') {int decision=exit_draft(uncertain);if(decision==2)break;save=decision==1;}
        if(save) {
            SaveResult result=store_commit(ui->store,ui->row,action,label,err);
            if(result==SAVE_OK) {snprintf(ui->message,sizeof ui->message,"Сохранено: %s",action);outcome=1;break;}
            if(result==SAVE_UNCERTAIN) {
                uncertain=true;
                snprintf(ui->message,sizeof ui->message,"Файл заменён, но надёжность записи не подтверждена. Проверьте рабочую копию.");
                viewer("Запись требует проверки — переход остановлен",err);
            } else viewer("Ошибка сохранения — новая попытка не записана",err);
        }
        scroll_key(key,&scroll,content.count,LINES-6);
    }
    lines_free(&content);free(body);return outcome;
}
static void preselect(const Guide *g,const char *label,bool *selected) {
    char *copy=str_copy(label),*save=NULL;
    for(char *token=strtok_r(copy,",",&save);token;token=strtok_r(NULL,",",&save)) {
        while(*token==' ') token++;
        size_t n=strlen(token);while(n && token[n-1]==' ') token[--n]=0;
        for(size_t i=0;i<g->count;i++) if(!strcmp(token,g->items[i].code)) selected[i]=true;
    }
    free(copy);
}
static int choose_categories(UI *ui,const char *action) {
    const Guide *g=ui->guide;bool *selected=mem_alloc(g->count*sizeof *selected);
    preselect(g,cell(&ui->store->table,ui->row,LABEL),selected);
    size_t cursor=0;unsigned number=0;
    while(!stopped) {
        bool too_small=small_screen();
        if(!too_small) {
            header("Категории");
            const char *hint=!strcmp(action,"OK")?"OK: выберите дополнительные категории; Enter — без дополнительных.":
                !strcmp(action,"ERROR")?"ERROR: выберите правильные категории; пусто — подходящей нет.":
                "NOT_DESC: категория, если установлена. Пусто разрешено по вашему правилу.";
            text(2,2,hint,COLS-4);
            int height=LINES-8;
            size_t first=cursor>=(size_t)height?cursor-(size_t)height+1:0;
            for(int r=0;r<height && first+(size_t)r<g->count;r++) {
                size_t i=first+(size_t)r;char item[1024];
                snprintf(item,sizeof item,"[%c] %2zu  %-27s %s",selected[i]?'x':' ',i+1,g->items[i].code,g->items[i].title);
                if(i==cursor) attron(A_REVERSE);
                text(4+r,2,item,COLS-4);
                if(i==cursor) attroff(A_REVERSE);
            }
            char status[128];snprintf(status,sizeof status,"Категорий: %zu. Номер: %s%u",g->count,number?"":"— ",number);
            text(LINES-3,2,status,COLS-4);
            text(LINES-2,2,"↑↓ / J K — выбор   Space — отметить   номер+Enter — отметить",COLS-4);
            text(LINES-1,2,"Enter — дальше   C — очистить   H — справка   Esc — отмена   Q — выход",COLS-4);refresh();
        }
        int key=read_key();
        if(key==27) {free(selected);return 0;}
        if(too_small) {
            if((key=='q'||key=='Q') && exit_draft(false)==2){free(selected);return 2;}
            continue;
        }
        if(key==KEY_DOWN || key=='j') {if(cursor+1<g->count)cursor++;number=0;}
        if(key==KEY_UP || key=='k') {if(cursor)cursor--;number=0;}
        if(key==KEY_NPAGE) {size_t step=LINES>8?(size_t)LINES-8:1;cursor=cursor+step<g->count?cursor+step:g->count-1;}
        if(key==KEY_PPAGE) {size_t step=LINES>8?(size_t)LINES-8:1;cursor=cursor>step?cursor-step:0;}
        if(key==KEY_HOME) cursor=0;
        if(key==KEY_END) cursor=g->count-1;
        if(key==' ') {selected[cursor]=!selected[cursor];number=0;}
        if(key>='0'&&key<='9') {if(number<10000) number=number*10+(unsigned)(key-'0');}
        if(key==KEY_BACKSPACE || key==127) number/=10;
        if(key=='c'||key=='C') {memset(selected,0,g->count*sizeof *selected);number=0;}
        if(key=='h'||key=='H'||key==KEY_F(1)) category_help(g,cursor);
        bool advance=key=='\n'||key=='\r'||key==KEY_ENTER;
        if(advance && number) {
            if(number<=g->count) {cursor=number-1;selected[cursor]=!selected[cursor];}
            number=0;advance=false;
        }
        if(key=='q'||key=='Q') {
            int decision=exit_draft(false);
            if(decision==2){free(selected);return 2;}
            advance=decision==1;
        }
        if(advance) {
            char *label=selected_label(g,selected);int result=confirm(ui,action,label);free(label);
            if(result){free(selected);return result;}
        }
    }
    free(selected);return 2;
}
static size_t pending(const UI *ui,size_t after) {
    const Table *t=&ui->store->table;
    if(t->count<=1) return 0;
    for(size_t step=1;step<t->count;step++) {
        size_t row=((after?after-1:t->count-2)+step)%(t->count-1)+1;
        if(!ui->deferred[row] && !*cell(t,row,ACTION)) return row;
    }
    return 0;
}
static void visit(UI *ui,size_t row) {
    ui->row=row;ui->scroll=0;lines_free(&ui->description);
    if(!row) return;
    if(ui->history_count && ui->history[ui->history_pos]==row) return;
    if(ui->history_count) ui->history_count=ui->history_pos+1;
    ui->history=mem_resize(ui->history,(ui->history_count+1)*sizeof *ui->history);
    ui->history[ui->history_count++]=row;ui->history_pos=ui->history_count-1;
}
static void back(UI *ui) {
    if(!ui->history_count) {snprintf(ui->message,sizeof ui->message,"В этом сеансе пока нет просмотренных записей.");return;}
    if(ui->row && ui->history_pos) ui->history_pos--;
    ui->row=ui->history[ui->history_pos];ui->scroll=0;lines_free(&ui->description);
}
static void general_help(void) {
    viewer("Справка URL Review",
        "Вы читаете описание и самостоятельно принимаете решение.\n\n"
        "1 — OK: исходный class верен. В label — только дополнительные категории.\n"
        "2 — ERROR: class неверен. В label — правильные категории или пусто, если подходящей нет.\n"
        "3 — NOT_DESC: описание недостаточно или считано неверно.\n"
        "По PDF при NOT_DESC нужна установленная категория. По вашему уточнению программа разрешает пустой label; это отличие от PDF.\n\n"
        "После действия выбирайте категории: Space отмечает, Enter открывает подтверждение.\n"
        "Номер+Enter отмечает категорию. Справка H на экране категорий показывает её критерии из PDF.\n\n"
        "S — отложить до конца прохода, без изменения CSV. R на итоговом экране возвращает отложенные.\n"
        "B — назад по истории текущего сеанса. Q — выход.\n"
        "↑↓, PageUp/PageDown, Home/End — прокрутка описания.\n\n"
        "Решение сохраняется только после подтверждения и успешной записи. Исходный файл не меняется.\n"
        "При повторном запуске укажите те же исходник, рабочую копию, кодировку и разделитель.\n"
        "Не открывайте рабочую копию в другом редакторе одновременно.\n\n"
        "Команда «Похожие» и эмбеддинги — следующий этап, в этой версии ещё не подключены.");
}
static void render(UI *ui) {
    const Table *t=&ui->store->table;char top[256];
    snprintf(top,sizeof top,"URL Review    Проверено: %zu / %zu",reviewed_count(t),t->count-1);header(top);
    if(!ui->row) {
        text(4,2,"Проход завершён",COLS-4);
        size_t deferred=0;for(size_t r=1;r<t->count;r++) if(ui->deferred[r]&&!*cell(t,r,ACTION)) deferred++;
        snprintf(top,sizeof top,"Отложено: %zu",deferred);text(6,2,top,COLS-4);
        text(9,2,"R — вернуться к отложенным   B — последняя просмотренная",COLS-4);
        text(11,2,"V — просмотр с первой записи   H — справка   Q — выход",COLS-4);
        text(LINES-2,2,ui->message,COLS-4);refresh();return;
    }
    snprintf(top,sizeof top,"Запись %zu    Домен:",ui->row);text(2,2,top,COLS-4);
    attron(A_BOLD);text(3,2,cell(t,ui->row,DOMAIN),COLS-4);attroff(A_BOLD);
    text(4,2,"Исходный class:",COLS-4);text(4,18,cell(t,ui->row,CLASS),COLS-20);
    snprintf(top,sizeof top,"Действие: %s",*cell(t,ui->row,ACTION)?cell(t,ui->row,ACTION):"не проверено");text(5,2,top,COLS-4);
    text(6,2,"label:",COLS-4);text(6,10,cell(t,ui->row,LABEL),COLS-12);
    int height=LINES-12;
    const char *desc=cell(t,ui->row,DESCRIPTION);
    if(ui->description.width!=COLS-4) lines_make(&ui->description,*desc?desc:"(Описание пустое)",COLS-4);
    scroll_key(0,&ui->scroll,ui->description.count,height);
    mvhline(7,1,ACS_HLINE,COLS-2);draw_lines(&ui->description,8,height,ui->scroll);
    mvhline(LINES-4,1,ACS_HLINE,COLS-2);
    text(LINES-3,2,ui->message,COLS-4);
    text(LINES-2,2,"1 OK   2 ERROR   3 NOT_DESC   S отложить   B назад   H справка   Q выход",COLS-4);
    snprintf(top,sizeof top,"↑↓ / PgUp PgDn — описание    строка %zu из %zu",ui->scroll+1,ui->description.count);text(LINES-1,2,top,COLS-4);refresh();
}
int ui_run(Store *store,const Guide *guide) {
    stopped=0;
    void (*old_int)(int)=signal(SIGINT,interrupted),(*old_term)(int)=signal(SIGTERM,interrupted);
    if(!initscr()) {fputs("Не удалось открыть терминальный интерфейс.\n",stderr);return 1;}
    cbreak();noecho();keypad(stdscr,TRUE);curs_set(0);timeout(100);set_escdelay(25);
    if(has_colors()) {start_color();use_default_colors();init_pair(1,COLOR_CYAN,-1);}
    UI ui={0};ui.store=store;ui.guide=guide;ui.deferred=mem_alloc(store->table.count*sizeof *ui.deferred);
    visit(&ui,pending(&ui,0));
    bool quit=false;
    while(!quit && !stopped) {
        if(!small_screen()) render(&ui);
        int key=read_key();if(key==ERR) continue;
        if(key=='q'||key=='Q') {quit=true;continue;}
        if(small_screen()) continue;
        if(key=='h'||key=='H'||key==KEY_F(1)) {general_help();continue;}
        if(key=='b'||key=='B') {back(&ui);continue;}
        if(!ui.row) {
            if(key=='r'||key=='R') {memset(ui.deferred,0,store->table.count*sizeof *ui.deferred);visit(&ui,pending(&ui,0));}
            if((key=='v'||key=='V') && store->table.count>1) visit(&ui,1);
            continue;
        }
        if(key>='1'&&key<='3') {
            static const char *actions[]={"OK","ERROR","NOT_DESC"};
            int result=choose_categories(&ui,actions[key-'1']);
            if(result==2) quit=true;
            else if(result==1) {ui.deferred[ui.row]=false;visit(&ui,pending(&ui,ui.row));}
        } else if(key=='s'||key=='S') {ui.deferred[ui.row]=true;visit(&ui,pending(&ui,ui.row));}
        else scroll_key(key,&ui.scroll,ui.description.count,LINES-12);
    }
    lines_free(&ui.description);free(ui.history);free(ui.deferred);endwin();
    signal(SIGINT,old_int);signal(SIGTERM,old_term);return stopped?130:0;
}
