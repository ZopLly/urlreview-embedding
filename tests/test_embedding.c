// О файле: C-проверка формата .uremb, сортировки, актуальных статусов и повреждений. Векторы создаются вручную; модель для этого теста не нужна.
// Пояснение: Подключаем embedding.h: типы индекса векторов и функции поиска.
#include "embedding.h"
// Пояснение: Подключаем assert.h: assert: немедленный провал теста, если условие ложно.
#include <assert.h>
// Пояснение: Подключаем math.h: нормы, корни и проверку конечности чисел.
#include <math.h>
// Пояснение: Подключаем stdio.h: файловые потоки FILE, printf, snprintf и ввод/вывод.
#include <stdio.h>
// Пояснение: Подключаем stdlib.h: выделение и освобождение памяти, exit и другие базовые функции.
#include <stdlib.h>
// Пояснение: Подключаем string.h: strlen, strcmp, memcpy, memset и другие операции строк/байтов.
#include <string.h>
// Пояснение: Подключаем unistd.h: POSIX-вызовы read/write/close/fsync и работу с процессами.
#include <unistd.h>
// Пояснение: Пишем unsigned int32 по одному байту от младшего к старшему; &255 выделяет нужный байт.
static void u32(FILE *f,unsigned n){for(int i=0;i<4;i++)fputc((n>>(8*i))&255,f);}
// Пояснение: Аналогичная запись uint64 в восемь байтов little-endian.
static void u64(FILE *f,uint64_t n){for(int i=0;i<8;i++)fputc((int)((n>>(8*i))&255),f);}
// Пояснение: Создаёт синтетический индекс; broken намеренно повреждает один float.
static void fixture(const char *path,const uint64_t *hashes,bool broken){
 // Пояснение: Открываем файл и пишем сигнатуру, число записей 4 и размерность 384.
 FILE *f=fopen(path,"wb");assert(f);fwrite("UREMB01\n",1,8,f);u32(f,4);u32(f,384);
 // Пояснение: Генерируем четыре вектора.
 for(int r=0;r<4;r++){
  // Пояснение: Сначала пишем соответствующий хеш, затем обходим 384 координаты.
  u64(f,hashes[r]);for(int d=0;d<384;d++){
   // Пояснение: Третий вектор направлен по второй оси, остальные — по первой, что задаёт известное
   // Пояснение: ранжирование.
   float v=d==0?(r==2?0:1):d==1&&r==2?1:0;
   // Пояснение: В повреждённом варианте первую координату первого сайта заменяем NaN.
   if(broken&&r==0&&d==0)v=NAN;
   // Пояснение: Через memcpy берём биты float как uint32 и записываем little-endian.
   uint32_t bits;memcpy(&bits,&v,4);u32(f,bits);
  // Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
  }
 // Пояснение: После окончания обеих вложенных итераций закрываем файл.
 }fclose(f);
// Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
}
// Пояснение: Точка входа набора проверок индекса.
int main(void){
 // Пояснение: Синтетический CSV: две непроверенные записи и две с OK/ERROR.
 const char *csv="domain;class;label;action;description\none.example;shopping;;;Инструменты\ntwo.example;shopping;;OK;Магазин\nthree.example;music;music;ERROR;Музыка\nfour.example;shopping;;;Пусто\n";
 // Пояснение: Пустые таблица и индекс, массив результатов и буфер ошибки.
 Table t={0};Embedding e={0};EmbeddingHit hits[5];char err[ERR_SIZE];
 // Пояснение: Разбор исходного синтетического CSV обязан пройти.
 assert(table_parse(csv,strlen(csv),';',&t,err));
 // Пояснение: Заранее известные FNV-1a хеши конкретных пар домен/описание для независимой проверки формата.
 const uint64_t hashes[]={UINT64_C(0x1952e5c4f4004a9),UINT64_C(0x8770eac1df2d82fc),UINT64_C(0x40326ad3f533a71a),UINT64_C(0xf6fc2ed5b0c1884d)};
 // Пояснение: Создаём временный файл индекса; дескриптор пока закрываем, fixture откроет его отдельно.
 char path[]="/tmp/embedding-XXXXXX";int fd=mkstemp(path);assert(fd>=0);close(fd);
 // Пояснение: Пишем корректный индекс.
 fixture(path,hashes,false);
 // Пояснение: C-загрузчик должен принять его для этой таблицы.
 assert(embedding_read(path,&t,&e,err));
 // Пояснение: Из поиска первой записи возвращаются только два проверенных сайта.
 assert(embedding_search(&e,&t,1,hits,5)==2);
 // Пояснение: Второй сайт имеет сходство 1 и должен стоять первым; третий — следующим.
 assert(hits[0].row==2&&fabsf(hits[0].score-1)<.001f);assert(hits[1].row==3);
 // Пояснение: Меняем action четвёртого сайта на NOT_DESC прямо в таблице.
 free(t.rows[4].cells[t.col[ACTION]]);t.rows[4].cells[t.col[ACTION]]=str_copy("NOT_DESC");
 // NOT_DESC не подтверждает категорию, даже если его вектор близок запросу.
 assert(embedding_search(&e,&t,1,hits,5)==2);
 // ERROR без исправленного label тоже не даёт подтверждённого примера категории.
 free(t.rows[3].cells[t.col[LABEL]]);t.rows[3].cells[t.col[LABEL]]=str_copy("");
 assert(embedding_search(&e,&t,1,hits,5)==1);
 // Пояснение: Проверяем освобождение и повторное чтение; изменение статуса не делает индекс устаревшим.
 embedding_free(&e);assert(embedding_read(path,&t,&e,err));embedding_free(&e);
 // Пояснение: Меняем описание второго сайта, освобождая старую строку.
 free(t.rows[2].cells[t.col[DESCRIPTION]]);t.rows[2].cells[t.col[DESCRIPTION]]=str_copy("Изменено");
 // Пояснение: Изменение описания обязано вызвать отказ устаревшего индекса.
 assert(!embedding_read(path,&t,&e,err));
 // Пояснение: Возвращаем исходную таблицу и пишем индекс с NaN.
 table_free(&t);assert(table_parse(csv,strlen(csv),';',&t,err));fixture(path,hashes,true);
 // Пояснение: Загрузчик обязан отклонить нечисловую координату.
 assert(!embedding_read(path,&t,&e,err));
 // Пояснение: Записываем только заголовок с заведомо невозможным числом записей.
 FILE *f=fopen(path,"wb");assert(f);fputs("UREMB01\n",f);u32(f,999999999);u32(f,384);fclose(f);
 // Пояснение: Проверка размеров должна отклонить файл без попытки использовать мнимые векторы.
 assert(!embedding_read(path,&t,&e,err));
 // Пояснение: Удаляем файл, освобождаем таблицу и печатаем успех.
 unlink(path);table_free(&t);puts("Embeddings: ranking/live labels/stale index/NaN/size guards OK");
// Пояснение: Конец текущего блока: функции, цикла или условной ветки, открытого фигурной скобкой.
}
