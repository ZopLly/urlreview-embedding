#!/bin/sh
set -eu
# Preserve caller's working directory so relative CSV paths stay meaningful.
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ ! -x "$root/.venv-embeddings/bin/python" ]; then
    echo 'Сначала запустите scripts/setup-embeddings.sh из папки проекта.' >&2
    exit 1
fi
exec "$root/.venv-embeddings/bin/python" "$root/embeddings/local_embeddings.py" build "$@"
