#!/usr/bin/env bash
set -euo pipefail
TF="${1:-15m}"
OUT="scan_${TF}.txt"
: > "$OUT"

ARGS=(
  --timeframe "$TF"
  --regime 96h
  --activation 3h
  --pattern s_near
  --fallback 1
)

echo ">>> Running scan (broad) TF=$TF" | tee -a "$OUT"
echo ">>> Effective args: ${ARGS[*]}" | tee -a "$OUT"

# Route through capture so Telegram messages mirror to STDOUT
python scan_capture.py "${ARGS[@]}" 2>&1 | tee -a "$OUT"
