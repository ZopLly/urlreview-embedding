# Local Embeddings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** По команде P показывать похожие проверенные записи локально.
**Architecture:** Python ONNX CPU builder пишет проверяемый бинарный индекс; C читает его один раз и сравнивает нормализованные векторы. Разметка всегда из текущего Store.
**Tech Stack:** C17/ncursesw, Python 3.12+, numpy, tokenizers, onnxruntime.
**Spec:** docs/superpowers/specs/2026-10-28-local-embeddings.md

## Global Constraints
Рабочие CSV не читать помощником; только synthetic. Не менять учебный main.c. Никакой автоматической разметки или передачи описаний в интернет. Индекс опционален.

## Review Focus
- Устаревший индекс после перестановки/смены описания отклоняется; изменение action/label разрешается.
- Непроверенные/пустые записи и сама текущая запись исключаются из результатов.
- Повреждённый индекс не приводит к выходу за границы/выделению неограниченной памяти.
- Длинные описания обрабатываются целиком по окнам; остаток не отбрасывается.
- Подготовка индекса не перезаписывает CSV, сбой не оставляет полузаписанный индекс.

### Task 1: C index reader/search
Files: src/embedding.h,c, tests/test_embedding.c, Makefile.
Interface: embedding_read(path,table,index,err), embedding_search(index,table,row,hits,capacity), embedding_free(index).
- [x] Write tests: independent binary fixtures, exact ranking, dynamic actions, stale/malformed index.
- [x] Run RED, implement bounded reader/FNV fingerprints/dot-product search, run GREEN and suite.

### Task 2: Offline Python builder/model setup
Files: embeddings/local_embeddings.py, scripts/setup-embeddings.sh, scripts/build-embeddings.sh, tests/test_embeddings.py.
Interfaces: fingerprint(domain,description), chunks(token_ids,window=320,overlap=32), build_index(input,output,encoder,encoding,delimiter), model CLI download/build/smoke.
- [x] Write/run failing tests for window tails, binary compatibility, output isolation and no CSV mutations.
- [x] Implement and run GREEN; install isolated dependencies, download pinned model files, smoke with actual model and synthetic Russian text, benchmark.

### Task 3: UI integration and delivery
Files: src/main.c,ui.h,ui.c, tests/test_ui.py, README.md, docs/embeddings.md, PROGRESS.md.
- [x] Write/run failing PTY tests: P with and without index; shortlist/detail/cancel; live saved decisions.
- [x] Implement --embeddings and P viewer; run all tests with -Werror and sanitizers.
- [x] Independent review, fix substantive findings, document evidence; commit and export source archive with no private data/model/dependencies.
