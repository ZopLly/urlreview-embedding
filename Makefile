CC ?= cc
CPPFLAGS += -D_XOPEN_SOURCE=700 -D_DEFAULT_SOURCE -Isrc
CFLAGS ?= -O2 -g
CFLAGS += -std=c17 -Wall -Wextra -Wpedantic
NCURSES_CFLAGS := $(shell pkg-config --cflags ncursesw)
NCURSES_LIBS := $(shell pkg-config --libs ncursesw)
CORE = src/csv.c src/store.c

.PHONY: all test test-core test-guide clean sanitize
all: url-review
build:
	mkdir -p build
build/test-core: tests/test_core.c $(CORE) src/core.h | build
	$(CC) $(CPPFLAGS) $(CFLAGS) tests/test_core.c $(CORE) -o $@
test-core: build/test-core
	./build/test-core
build/test-guide: tests/test_guide.c src/guide.c src/guide.h $(CORE) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) tests/test_guide.c src/guide.c $(CORE) -o $@
test-guide: build/test-guide
	./build/test-guide
url-review: src/main.c src/ui.c src/guide.c $(CORE) src/core.h src/guide.h src/ui.h
	$(CC) $(CPPFLAGS) $(CFLAGS) $(NCURSES_CFLAGS) src/main.c src/ui.c src/guide.c $(CORE) $(NCURSES_LIBS) -o $@
test: test-core test-guide url-review
	python3 -m unittest discover -s tests -p 'test_*.py' -v
clean:
	rm -rf build url-review
sanitize: | build
	$(CC) $(CPPFLAGS) -std=c17 -Wall -Wextra -Wpedantic -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_core.c $(CORE) -o build/test-sanitize
	ASAN_OPTIONS=detect_leaks=1 ./build/test-sanitize
