#!/usr/bin/env bash
# run_all.sh — Bash wrapper for the Mandelbrot benchmark suite.
# Usage:  ./run_all.sh           (full run)
#         ./run_all.sh --quick   (reduced workload)
set -euo pipefail
cd "$(dirname "$0")"

PYTHON=""
for cand in python python3 py; do
    if command -v "$cand" >/dev/null 2>&1; then
        PYTHON="$cand"
        break
    fi
done
if [ -z "$PYTHON" ]; then
    echo "ERROR: Python not found on PATH." >&2
    exit 1
fi

exec "$PYTHON" run_all.py "$@"
