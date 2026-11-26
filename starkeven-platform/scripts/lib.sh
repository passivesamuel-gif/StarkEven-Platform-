#!/usr/bin/env bash
# Shared helpers for the stage verification scripts.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

require_files() {
  local missing=0
  for f in "$@"; do
    if [ ! -s "$f" ]; then echo "  MISSING/EMPTY: $f"; missing=1; fi
  done
  return $missing
}

compile_python() {
  python3 -m py_compile "$@" && echo "  python syntax OK ($# files)"
}

check_stage() {
  local name="$1"; shift
  echo "== $name =="
  require_files "$@" || { echo "FAILED: $name"; exit 1; }
  local py=()
  for f in "$@"; do case "$f" in *.py) py+=("$f");; esac; done
  [ ${#py[@]} -gt 0 ] && compile_python "${py[@]}"
  echo "  OK: $name"
}
