#!/usr/bin/env bash
# Robust silent scan wrapper for BingX/OKX bot
set -euo pipefail

TF="${1:-15m}"
OUT="scan_${TF}.txt"

# reset output
: > "$OUT"

run_cmd() {
  local extra="$1"
  # Force silent mode by zeroing telegram envs for scan phase
  BOT_TOKEN="0" CHAT_ID="0" python auto_grid_box_finder_pro.py --timeframe "$TF" $extra 2>&1 | tee -a "$OUT"
}

echo ">>> Silent scan for TF=$TF" | tee -a "$OUT"
echo "----- default (try --exchange bingx) -----" | tee -a "$OUT"
run_cmd "--exchange bingx" || echo "command exited nonzero; continuing" | tee -a "$OUT"

# If the bot doesn't support --exchange arg, retry without it
if grep -qi "unrecognized arguments: --exchange" "$OUT"; then
  echo "----- fallback: no --exchange (bot may be hardcoded to OKX) -----" | tee -a "$OUT"
  : > "$OUT"
  run_cmd ""
fi

echo "----- attempt: pattern=s_near -----" | tee -a "$OUT"
run_cmd "--pattern s_near" || true

for H in 6 12 24; do
  echo "----- attempt: activation=${H}h -----" | tee -a "$OUT"
  run_cmd "--activation-hours ${H}" || true
done

echo "----- attempt: ONLY S-GRID -----" | tee -a "$OUT"
run_cmd "--only-s-grid" || true

echo ">>> Done. Output in $OUT" | tee -a "$OUT"
