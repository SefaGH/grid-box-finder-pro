#!/usr/bin/env bash
set -euo pipefail

TF="${1:-15m}"
OUT="scan_${TF}.txt"
: > "${OUT}"

echo ">>> Broad scan matrix for TF=${TF}"

echo "----- default scan -----" | tee -a "${OUT}"
(python auto_grid_box_finder_pro.py --timeframe "${TF}" || true) | tee -a "${OUT}"

echo "----- attempt: S+NEAR -----" | tee -a "${OUT}"
(python auto_grid_box_finder_pro.py --timeframe "${TF}" --pattern s_near || true) | tee -a "${OUT}"

for H in 6 12 18 24; do
  echo "----- attempt: activation=${H}h -----" | tee -a "${OUT}"
  (python auto_grid_box_finder_pro.py --timeframe "${TF}" --activation-hours "${H}" || true) | tee -a "${OUT}"
done

echo "----- attempt: ONLY S-GRID -----" | tee -a "${OUT}"
(python auto_grid_box_finder_pro.py --timeframe "${TF}" --pattern only_s || true) | tee -a "${OUT}"

echo ">>> Done. Output in ${OUT}"
