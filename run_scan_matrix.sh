#!/usr/bin/env bash
set -euo pipefail

# Usage: ./run_scan_matrix.sh 15m
TF="${1:-15m}"
OUT="scan_${TF}.txt"
: > "${OUT}"  # truncate

echo ">>> Running scan matrix for TF=${TF}"

# Try plain/default scan
echo "----- default scan -----" | tee -a "${OUT}"
(python auto_grid_box_finder_pro.py --timeframe "${TF}" || true) | tee -a "${OUT}"

# Try S+NEAR (if supported)
echo "----- attempt: S+NEAR -----" | tee -a "${OUT}"
(python auto_grid_box_finder_pro.py --timeframe "${TF}" --pattern s_near || true) | tee -a "${OUT}"

# Try broader activation windows (if supported)
echo "----- attempt: activation=6h -----" | tee -a "${OUT}"
(python auto_grid_box_finder_pro.py --timeframe "${TF}" --activation-hours 6 || true) | tee -a "${OUT}"

echo "----- attempt: activation=12h -----" | tee -a "${OUT}"
(python auto_grid_box_finder_pro.py --timeframe "${TF}" --activation-hours 12 || true) | tee -a "${OUT}"

# Try pattern-only S-GRID last (diagnostic; may be empty)
echo "----- attempt: ONLY S-GRID -----" | tee -a "${OUT}"
(python auto_grid_box_finder_pro.py --timeframe "${TF}" --pattern only_s || true) | tee -a "${OUT}"

echo ">>> Done. Output in ${OUT}"
