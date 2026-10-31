# О файле: Правила GNU make: цель: зависимости, затем команды с обязательной начальной табуляцией. $@ — имя текущей цели; $(...) — подстановка переменной или функции make.
# Пояснение: Компилятор по умолчанию cc; ?= позволяет переопределить его снаружи.
CC ?= cc
# Пояснение: Флаги препроцессора: POSIX/XSI API и путь поиска заголовков src.
CPPFLAGS += -D_XOPEN_SOURCE=700 -D_DEFAULT_SOURCE -Isrc
# Пояснение: Базовые флаги оптимизации -O2 и отладочной информации -g, если не переданы свои.
CFLAGS ?= -O2 -g
# Пояснение: Стандарт C17 и предупреждения компилятора о потенциальных проблемах.
CFLAGS += -std=c17 -Wall -Wextra -Wpedantic
# Пояснение: Через pkg-config получаем флаги ncursesw и удаляем дубли макросов, уже заданных выше.
NCURSES_CFLAGS := $(filter-out -D_XOPEN_SOURCE=% -D_DEFAULT_SOURCE,$(shell pkg-config --cflags ncursesw))
# Пояснение: Получаем библиотеки для линковки Unicode-версии ncurses.
NCURSES_LIBS := $(shell pkg-config --libs ncursesw)
# Пояснение: Общие исходники парсера и хранилища для приложения и тестов.
CORE = src/csv.c src/store.c src/workbook.c
# Все цели ядра должны пересобираться и при изменении контракта XLSX.
CORE_HEADERS = src/core.h src/workbook.h
# Пояснение: Отдельная переменная исходника C-поиска эмбеддингов.
EMBEDDING = src/embedding.c

# Пояснение: Эти цели не обозначают файлы; запускать их нужно даже при наличии одноимённого файла.
.PHONY: all test test-core test-guide test-browser test-embedding clean sanitize
# Пояснение: Цель по умолчанию собирает исполняемый url-review.
all: url-review
# Пояснение: Цель каталога артефактов сборки.
build:
# Пояснение: Создаём каталог; начальная табуляция делает строку командой make.
	mkdir -p build
# Пояснение: Сборка core-теста зависит от исходников и заголовка; | build — каталог нужен, но его timestamp не
# Пояснение: пересобирает цель.
build/test-core: tests/test_core.c $(CORE) $(CORE_HEADERS) src/core.h | build
# Пояснение: Компилируем core-тест вместе с реализацией; -o $@ задаёт выходной файл цели.
	$(CC) $(CPPFLAGS) $(CFLAGS) tests/test_core.c $(CORE) -o $@
# Пояснение: Зависимости теста конкурентного внешнего редактирования.
build/test-race: tests/test_race.c $(CORE) $(CORE_HEADERS) src/core.h | build
# Пояснение: Линкер --wrap=fopen перенаправляет вызовы на тестовую обёртку для воспроизведения гонки.
	$(CC) $(CPPFLAGS) $(CFLAGS) tests/test_race.c $(CORE) -Wl,--wrap=fopen -o $@
# Пояснение: Зависимости теста ошибки синхронизации.
build/test-sync: tests/test_sync.c $(CORE) $(CORE_HEADERS) src/core.h | build
# Пояснение: --wrap=fsync позволяет тесту воспроизвести отказ синхронизации каталога.
	$(CC) $(CPPFLAGS) $(CFLAGS) tests/test_sync.c $(CORE) -Wl,--wrap=fsync -o $@
# Пояснение: test-core сначала собирает три исполняемых теста.
test-core: build/test-core build/test-race build/test-sync
# Пояснение: Выполняем проверки CSV, кодировок и хранилища.
	./build/test-core
# Пояснение: Выполняем проверку конкурентного изменения копии.
	./build/test-race
# Пояснение: Выполняем проверку неопределённого результата fsync.
	./build/test-sync
# Пояснение: Зависимости теста справочника категорий.
build/test-guide: tests/test_guide.c src/guide.c src/guide.h $(CORE) $(CORE_HEADERS) | build
# Пояснение: Собираем тест справочника с его реализацией и общим ядром.
	$(CC) $(CPPFLAGS) $(CFLAGS) tests/test_guide.c src/guide.c $(CORE) -o $@
# Пояснение: test-guide требует готового исполняемого теста.
test-guide: build/test-guide
# Пояснение: Запускаем проверку справочника.
	./build/test-guide
# Пояснение: Зависимости проверки URL.
build/test-browser: tests/test_browser.c src/browser.c src/browser.h $(CORE) $(CORE_HEADERS) | build
# Пояснение: Собираем проверку URL с browser.c и общими функциями памяти/таблицы.
	$(CC) $(CPPFLAGS) $(CFLAGS) tests/test_browser.c src/browser.c $(CORE) -o $@
# Пояснение: test-browser зависит от собранного теста.
test-browser: build/test-browser
# Пояснение: Запускаем проверку нормализации и отклонения адресов.
	./build/test-browser
# Пояснение: Все исходники и заголовки основного терминального приложения.
url-review: src/main.c src/ui.c src/guide.c src/browser.c $(EMBEDDING) $(CORE) $(CORE_HEADERS) src/core.h src/guide.h src/ui.h src/browser.h src/embedding.h
# Пояснение: Собираем приложение, ncurses и математическую библиотеку -lm, нужную для сходства.
	$(CC) $(CPPFLAGS) $(CFLAGS) $(NCURSES_CFLAGS) src/main.c src/ui.c src/guide.c src/browser.c $(EMBEDDING) $(CORE) $(NCURSES_LIBS) -lm -o $@
# Пояснение: Вспомогательная программа независимой проверки чтения и записи CSV.
build/roundtrip: tests/roundtrip.c $(CORE) $(CORE_HEADERS) src/core.h | build
# Пояснение: Собираем roundtrip-конвертер для Python-теста.
	$(CC) $(CPPFLAGS) $(CFLAGS) tests/roundtrip.c $(CORE) -o $@
# Пояснение: Отдельная тестовая версия приложения с подменой fsync.
build/url-review-sync: src/main.c src/ui.c src/guide.c src/browser.c $(EMBEDDING) $(CORE) $(CORE_HEADERS) tests/sync_fault.c | build
# Пояснение: --wrap=fsync подключает sync_fault.c только к этому бинарнику, не к обычному приложению.
	$(CC) $(CPPFLAGS) $(CFLAGS) $(NCURSES_CFLAGS) src/main.c src/ui.c src/guide.c src/browser.c $(EMBEDDING) $(CORE) tests/sync_fault.c -Wl,--wrap=fsync $(NCURSES_LIBS) -lm -o $@
# Пояснение: Зависимости C-теста бинарного индекса и ранжирования.
build/test-embedding: tests/test_embedding.c $(EMBEDDING) src/embedding.h $(CORE) $(CORE_HEADERS) | build
# Пояснение: Собираем тест с математической библиотекой.
	$(CC) $(CPPFLAGS) $(CFLAGS) tests/test_embedding.c $(EMBEDDING) $(CORE) -lm -o $@
# Пояснение: Цель запуска теста эмбеддингов.
test-embedding: build/test-embedding
# Пояснение: Выполняем C-проверку векторов и поиска.
	./build/test-embedding
# Пояснение: Общая цель сначала собирает и запускает C-тесты, приложение и вспомогательные бинарники.
test: test-core test-guide test-browser test-embedding url-review build/roundtrip build/url-review-sync
# Пояснение: unittest обнаруживает test_*.py; -v показывает каждый сценарий, включая реальные PTY-сеансы.
	python3 -m unittest discover -s tests -p 'test_*.py' -v
# Пояснение: Цель удаления результатов сборки.
clean:
# Пояснение: Удаляем только build и скомпилированный url-review; исходники не затрагиваются.
	rm -rf build url-review
# Пояснение: Проверка санитайзерами требует существования build.
sanitize: | build
# Пояснение: Собираем core-тест с ASan/UBSan для поиска нарушений памяти и неопределённого поведения.
	$(CC) $(CPPFLAGS) -std=c17 -Wall -Wextra -Wpedantic -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_core.c $(CORE) -o build/test-sanitize
# Пояснение: Сохраняем явно заданные ASAN_OPTIONS; иначе отключаем LeakSanitizer и выполняем тест.
	ASAN_OPTIONS=$${ASAN_OPTIONS:-detect_leaks=0} ./build/test-sanitize
# Пояснение: Так же собираем C-тест эмбеддингов с ASan/UBSan.
	$(CC) $(CPPFLAGS) -std=c17 -Wall -Wextra -Wpedantic -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_embedding.c $(EMBEDDING) $(CORE) -lm -o build/test-embedding-sanitize
# Пояснение: Запускаем проверку эмбеддингов под санитайзерами с той же настройкой.
	ASAN_OPTIONS=$${ASAN_OPTIONS:-detect_leaks=0} ./build/test-embedding-sanitize
