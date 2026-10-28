CC ?= cc
CPPFLAGS += -D_XOPEN_SOURCE=700 -D_DEFAULT_SOURCE -Isrc
CFLAGS ?= -O2 -g
CFLAGS += -std=c17 -Wall -Wextra -Wpedantic
NCURSES_CFLAGS := $(filter-out -D_XOPEN_SOURCE=% -D_DEFAULT_SOURCE,$(shell pkg-config --cflags ncursesw))
NCURSES_LIBS := $(shell pkg-config --libs ncursesw)
CORE = src/csv.c src/store.c
EMBEDDING = src/embedding.c

.PHONY: all test test-core test-guide test-browser test-embedding clean sanitize
all: url-review
build:
	mkdir -p build
build/test-core: tests/test_core.c $(CORE) src/core.h | build
	$(CC) $(CPPFLAGS) $(CFLAGS) tests/test_core.c $(CORE) -o $@
build/test-race: tests/test_race.c $(CORE) src/core.h | build
	$(CC) $(CPPFLAGS) $(CFLAGS) tests/test_race.c $(CORE) -Wl,--wrap=fopen -o $@
build/test-sync: tests/test_sync.c $(CORE) src/core.h | build
	$(CC) $(CPPFLAGS) $(CFLAGS) tests/test_sync.c $(CORE) -Wl,--wrap=fsync -o $@
test-core: build/test-core build/test-race build/test-sync
	./build/test-core
	./build/test-race
	./build/test-sync
build/test-guide: tests/test_guide.c src/guide.c src/guide.h $(CORE) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) tests/test_guide.c src/guide.c $(CORE) -o $@
test-guide: build/test-guide
	./build/test-guide
build/test-browser: tests/test_browser.c src/browser.c src/browser.h $(CORE) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) tests/test_browser.c src/browser.c $(CORE) -o $@
test-browser: build/test-browser
	./build/test-browser
url-review: src/main.c src/ui.c src/guide.c src/browser.c $(EMBEDDING) $(CORE) src/core.h src/guide.h src/ui.h src/browser.h src/embedding.h
	$(CC) $(CPPFLAGS) $(CFLAGS) $(NCURSES_CFLAGS) src/main.c src/ui.c src/guide.c src/browser.c $(EMBEDDING) $(CORE) $(NCURSES_LIBS) -lm -o $@
build/roundtrip: tests/roundtrip.c $(CORE) src/core.h | build
	$(CC) $(CPPFLAGS) $(CFLAGS) tests/roundtrip.c $(CORE) -o $@
build/url-review-sync: src/main.c src/ui.c src/guide.c src/browser.c $(EMBEDDING) $(CORE) tests/sync_fault.c | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(NCURSES_CFLAGS) src/main.c src/ui.c src/guide.c src/browser.c $(EMBEDDING) $(CORE) tests/sync_fault.c -Wl,--wrap=fsync $(NCURSES_LIBS) -lm -o $@
build/test-embedding: tests/test_embedding.c $(EMBEDDING) src/embedding.h $(CORE) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) tests/test_embedding.c $(EMBEDDING) $(CORE) -lm -o $@
test-embedding: build/test-embedding
	./build/test-embedding
test: test-core test-guide test-browser test-embedding url-review build/roundtrip build/url-review-sync
	python3 -m unittest discover -s tests -p 'test_*.py' -v
clean:
	rm -rf build url-review
sanitize: | build
	$(CC) $(CPPFLAGS) -std=c17 -Wall -Wextra -Wpedantic -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_core.c $(CORE) -o build/test-sanitize
	ASAN_OPTIONS=$${ASAN_OPTIONS:-detect_leaks=0} ./build/test-sanitize
	$(CC) $(CPPFLAGS) -std=c17 -Wall -Wextra -Wpedantic -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_embedding.c $(EMBEDDING) $(CORE) -lm -o build/test-embedding-sanitize
	ASAN_OPTIONS=$${ASAN_OPTIONS:-detect_leaks=0} ./build/test-embedding-sanitize
