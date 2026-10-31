// О файле: Общий формат индекса и интерфейс поиска; размерность совпадает с Python DIM и полем размерности .uremb.
// Пояснение: Защита заголовка: читаем содержимое только если его уникальный макрос ещё не определён.
#ifndef URL_REVIEW_EMBEDDING_H
// Пояснение: Отмечаем заголовок как подключённый, чтобы повторный #include не дублировал определения.
#define URL_REVIEW_EMBEDDING_H
// Пояснение: Подключаем core.h: общие типы Table/Store и функции CSV, памяти и сохранения.
#include "core.h"
// Пояснение: Подключаем stdint.h: целые фиксированной ширины uint32_t/uint64_t и их константы.
#include <stdint.h>
// Пояснение: У каждого вектора multilingual-e5-small здесь 384 координаты.
#define EMBEDDING_DIM 384
// Пояснение: Плоский массив count×384 float; count соответствует Table.count вместе с пустым местом заголовка.
typedef struct { float *vectors; size_t count; } Embedding;
// Пояснение: Один результат поиска: индекс Row в таблице и косинусное сходство, не вероятность.
typedef struct { size_t row; float score; } EmbeddingHit;
// Пояснение: Загружает и валидирует индекс, проверяя отпечатки доменов и описаний.
bool embedding_read(const char *path,const Table *table,Embedding *index,char err[ERR_SIZE]);
// Пояснение: Записывает не более capacity результатов в массив hits и возвращает их количество.
size_t embedding_search(const Embedding *index,const Table *table,size_t row,EmbeddingHit *hits,size_t capacity);
// Пояснение: Освобождает массив векторов и обнуляет структуру.
void embedding_free(Embedding *index);
// Пояснение: Конец условного включения заголовка.
#endif
