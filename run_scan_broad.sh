#!/usr/bin/env bash
set -euo pipefail
TF="${1:-15m}"
OUT="scan_${TF}.txt"
: > "$OUT"

run_cmd() {
  local extra="$1"
  python scan_capture.py --timeframe "$TF" $extra 2>&1 | tee -a "$OUT"
}

echo ">>> Broad scan TF=$TF" | tee -a "$OUT"
run_cmd "--regime 96h --activation 3h --pattern s_near --fallback 1" || true
echo ">>> Done." | tee -a "$OUT"
