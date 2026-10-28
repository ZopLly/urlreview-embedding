# URL Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Дать пользователю надёжную локальную ручную разметку CSV в терминале.
**Architecture:** Независимые модули CSV, безопасного хранения, справочника и ncursesw UI. Вход хранится отдельно; рабочая копия проверяется, блокируется и сохраняется атомарно. Все тесты синтетические.
**Tech Stack:** C17, iconv, POSIX flock/fsync, ncursesw; Python standard library для интеграционных/PTY-тестов.
**Spec:** docs/superpowers/specs/2026-10-28-url-review.md

## Global Constraints

- Настоящие CSV помощник не открывает.
- Учебный main.c не изменяется.
- Перезапись входа запрещена; меняются только action/label рабочей копии.
- UTF-8 или Windows-1251 задаются явно, как и разделитель.
- Компиляция с -Wall -Wextra -Wpedantic.
- Поиск похожих и графический интерфейс — следующие этапы.

## Review Focus

- Кавычки/CRLF/пустые поля и описания >12000 символов: точное совпадение полей после сохранения.
- Ошибка сохранения и конфликт внешнего изменения: исходник и рабочая копия не повреждены, состояние решения откатывается.
- Повторяющиеся домены и возврат: идентичность по неизменной позиции, прогресс не завышается.
- Многобайтовый текст, resize и узкое окно: интерфейс не обращается за границы, остаётся доступен выход.
- Несовпадение кодировки или схемы: ошибка до записи, без тихой потери символов.

### Task 1: CSV и безопасная рабочая копия

**Files:** src/core.h, src/csv.c, src/store.c, tests/test_core.c, Makefile.
**Interfaces:** Table/Row, table_read(path,encoding,separator,...), table_free, table_serialize; Store, store_open(input,output,...), store_commit(store,row,action,label,...), store_close. Возврат bool, диагностическая строка при false. Store владеет таблицей и блокировкой.
- [x] Написать проверки чтения CSV и запуска хранения; запуск до реализации должен показать отсутствие реализации.
- [x] Реализовать парсер, строгую проверку схемы/кодировки и сериализацию.
- [x] Реализовать совместимость, блокировку, атомарное сохранение, защиту исходника/внешних изменений и откат решения при ошибке.
- [x] Запустить `make test-core`; Expected: все тесты проходят без предупреждений.
- [x] Commit task 1.

### Task 2: Справочник категорий

**Files:** src/guide.h, src/guide.c, data/categories.tsv, scripts/extract_guide.py, tests/test_guide.c.
**Interfaces:** Guide/Category с code/title/include/exclude; guide_read и guide_free. Порядок фиксируется в data/categories.tsv. Критерии извлекаются только из двух предоставленных PDF, спорные гипотезы не включаются.
- [x] Тест до реализации: стабильный порядок, загрузка правил, отказ дублирующегося/неверного справочника.
- [x] Подготовить справочник и реализовать загрузку; разделить справочные правила и допустимый пустой NOT_DESC, описанный пользователем.
- [x] `make test-guide`; Expected: все тесты проходят.
- [x] Commit task 2.

### Task 3: Терминальный рабочий сценарий

**Files:** src/main.c, src/ui.h, src/ui.c, tests/test_ui.py.
**Interfaces:** main CLI принимает INPUT OUTPUT, --encoding, --delimiter, --guide, --check; ui_run(Store*,Guide*) ведёт ручной сценарий, store_commit единственная операция записи решений.
- [x] Написать PTY-тесты реального приложения: выбор статуса/нескольких категорий, подтверждение, отмена, отложить/вернуть, назад, выход, resize, возобновление.
- [x] Проверить RED: бинарник отсутствует/сценарий не реализован.
- [x] Реализовать Unicode-прокрутку, категории, справку, подтверждение/выход, прогресс и команды; обходить уже проверенные строки, помнить историю и отложенные в сеансе.
- [x] `make test`; Expected: core/guide/PTY проходят, данные подтверждены независимым csv.reader.
- [x] Commit task 3.

### Task 4: Доставка и учебный маршрут

**Files:** README.md, .gitignore, demo/synthetic.csv, scripts/run-demo.sh, docs/learning.md, tests/test_cli.py.
**Interfaces:** `make`, `make test`, `./scripts/run-demo.sh`, `./url-review --help`, валидатор `--check`.
- [x] Добавить тесты неверных CLI-настроек/заголовков/недоступного вывода, Windows-1251 и возобновления.
- [x] Документировать команды, сохранение/ограничения/пропуск и учебное изменение; явно отметить различие правила пустого NOT_DESC и PDF.
- [x] Проверить warnings-as-errors, sanitizers для ядра, полный тестовый запуск и реальный PTY.
- [x] Независимый обзор кода по spec; значимые дефекты исправить с regression RED→GREEN.
- [x] Упаковать только код, справочник, синтетические примеры и документацию в outputs; без рабочего CSV/векторов/моделей/истории других задач.
- [x] Commit проверенный результат. Не публиковать GitHub.
