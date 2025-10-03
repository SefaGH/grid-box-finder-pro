#!/usr/bin/env bash
set -euo pipefail
TF="${1:-15m}"
OUT="scan_${TF}.txt"
: > "$OUT"

run_cmd() {
  local extra="$1"
  BOT_TOKEN="0" CHAT_ID="0" python auto_grid_box_finder_pro.py --timeframe "$TF" $extra 2>&1 | tee -a "$OUT"
}

echo ">>> Silent scan TF=$TF" | tee -a "$OUT"
echo "----- try: --exchange bingx -----" | tee -a "$OUT"
run_cmd "--exchange bingx" || echo "non-zero exit (continue)" | tee -a "$OUT"

if grep -qi "unrecognized arguments: --exchange" "$OUT"; then
  echo "----- fallback: no --exchange -----" | tee -a "$OUT"
  : > "$OUT"
  run_cmd ""
fi

echo "----- attempt: pattern=s_near -----" | tee -a "$OUT"
run_cmd "--pattern s_near" || true

for H in 6 12 24; do
  echo "----- attempt: activation=${H}h -----" | tee -a "$OUT"
  run_cmd "--activation-hours ${H}" || true
done

echo ">>> Done."
