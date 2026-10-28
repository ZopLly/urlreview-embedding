#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
make -s
mkdir -p results
./scripts/build-embeddings.sh demo/synthetic.csv results/demo.uremb
exec ./url-review demo/synthetic.csv results/demo-review.csv --embeddings results/demo.uremb
