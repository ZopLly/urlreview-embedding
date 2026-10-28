#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
if [ -z "${PYTHON_BIN:-}" ]; then
    PYTHON_BIN=python3
    for candidate in python3.12 python3.13 python3.11; do
        if command -v "$candidate" >/dev/null 2>&1; then PYTHON_BIN=$candidate; break; fi
    done
fi
"$PYTHON_BIN" -c 'import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,13) else "Нужен Python 3.11–3.13. Укажите PYTHON_BIN=/путь/python3.12")'
"$PYTHON_BIN" -m venv .venv-embeddings
.venv-embeddings/bin/python -m pip install -r embeddings/requirements.txt
.venv-embeddings/bin/python embeddings/local_embeddings.py download
.venv-embeddings/bin/python embeddings/local_embeddings.py smoke
