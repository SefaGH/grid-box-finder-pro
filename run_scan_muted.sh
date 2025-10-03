#!/usr/bin/env bash
set -euo pipefail
TF="${1:-15m}"
OUT="scan_${TF}.txt"
: > "${OUT}"

# Run scanner with dummy env so internal Telegram is muted
BOT_TOKEN="0" CHAT_ID="0" python auto_grid_box_finder_pro.py --timeframe "${TF}" | tee "${OUT}"

# Optional extra sweeps (won't fail the job if args unsupported)
# Try S+NEAR and wider activation windows by appending to the same OUT
for MODE in "s_near"; do
  echo "----- attempt: pattern=${MODE} -----" | tee -a "${OUT}"
  (BOT_TOKEN="0" CHAT_ID="0" python auto_grid_box_finder_pro.py --timeframe "${TF}" --pattern "${MODE}" || true) | tee -a "${OUT}"
done

for H in 6 12 24; do
  echo "----- attempt: activation=${H}h -----" | tee -a "${OUT}"
  (BOT_TOKEN="0" CHAT_ID="0" python auto_grid_box_finder_pro.py --timeframe "${TF}" --activation-hours "${H}" || true) | tee -a "${OUT}"
done

echo "Scan written to ${OUT}"
