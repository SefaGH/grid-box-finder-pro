#!/usr/bin/env bash
set -euo pipefail
TF=\"${1:-15m}\"
OUT=\"scan_${TF}.txt\"
: > \"${OUT}\"

run_cmd() {
  local extra=\"$1\"
  BOT_TOKEN=\"0\" CHAT_ID=\"0\" python auto_grid_box_finder_pro.py --timeframe \"${TF}\" ${extra} 2>&1 | tee -a \"${OUT}\"
}

echo \">>> Silent scan for TF=${TF}\" | tee -a \"${OUT}\"
echo \"----- default (try --exchange bingx) -----\" | tee -a \"${OUT}\"
: > \"${OUT}\"
if run_cmd \"--exchange bingx\"; then
  true
else
  echo \"command exited nonzero; continuing\" | tee -a \"${OUT}\"
fi

if grep -qi \"unrecognized arguments: --exchange\" \"${OUT}\"; then
  echo \"----- fallback: no --exchange (bot may be hardcoded to OKX) -----\" | tee -a \"${OUT}\"
  : > \"${OUT}\"
  run_cmd \"\\"
fi

echo \"----- attempt: pattern=s_near -----\" | tee -a \"${OUT}\"
run_cmd \"--pattern s_near\" || true

for H in 6 12 24; do
  echo \"----- attempt: activation=${H}h -----\" | tee -a \"${OUT}\"
  run_cmd \"--activation-hours ${H}\" || true
done

echo \">>> Done. OUT=${OUT}\"
