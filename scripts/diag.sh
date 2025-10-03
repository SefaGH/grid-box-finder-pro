#!/usr/bin/env bash
set -euo pipefail

OUT="diag.txt"
: > "$OUT"

echo "=== Repo tree (top-level) ===" | tee -a "$OUT"
ls -la | tee -a "$OUT"
echo | tee -a "$OUT"

echo "=== Python version ===" | tee -a "$OUT"
python -V 2>&1 | tee -a "$OUT"
echo | tee -a "$OUT"

echo "=== Try --help on bot ===" | tee -a "$OUT"
( python auto_grid_box_finder_pro.py --help || true ) 2>&1 | tee -a "$OUT"
echo | tee -a "$OUT"

echo "=== Grep for key strings (case-insensitive) ===" | tee -a "$OUT"
for s in "ONLY S-GRID" "S-Pattern" "only_s_grid" "only-s-grid" "sgrid" "pattern" "activation" "regime"; do
  echo "--- $s ---" | tee -a "$OUT"
  (grep -Rin --exclude-dir=.git -n "$s" || true) | tee -a "$OUT"
  echo | tee -a "$OUT"
done

echo "=== Show surrounding context around matches ===" | tee -a "$OUT"
# show 5 lines before/after for each match of ONLY S-GRID
matches=$(grep -Rin --exclude-dir=.git -n "ONLY S-GRID" || true)
if [ -n "$matches" ]; then
  echo "$matches" | while IFS=: read -r file line rest; do
    echo "--- $file:$line ---" | tee -a "$OUT"
    nl -ba "$file" | sed -n "$((line-5)),$((line+5))p" | tee -a "$OUT"
    echo | tee -a "$OUT"
  done
fi

echo "=== Try alternative flags to disable ONLY S-GRID ===" | tee -a "$OUT"
# We'll attempt a series of invocations capturing errors but not failing
tests=(
  "--timeframe 15m --pattern s_near"
  "--timeframe 15m --pattern all"
  "--timeframe 15m --sgrid-only 0"
  "--timeframe 15m --only-s-grid 0"
  "--timeframe 15m --only_s_grid 0"
  "--timeframe 15m --sg-only 0"
)
for t in "${tests[@]}"; do
  echo ">>> python auto_grid_box_finder_pro.py $t" | tee -a "$OUT"
  ( python auto_grid_box_finder_pro.py $t || true ) 2>&1 | sed -n '1,80p' | tee -a "$OUT"
  echo | tee -a "$OUT"
done

echo "=== Done ===" | tee -a "$OUT"
