#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$task_root"
make -s
mkdir -p results
exec ./url-review demo/synthetic.csv results/demo-review.csv
