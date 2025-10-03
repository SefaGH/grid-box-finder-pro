#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re, sys, json, os
from pathlib import Path

TARGET = Path("auto_grid_box_finder_pro.py")
if not TARGET.exists():
    print("!! auto_grid_box_finder_pro.py not found", flush=True)
    sys.exit(0)

src = TARGET.read_text(encoding="utf-8", errors="ignore")
orig = src

changes = {}

# 1) Title tag: ONLY S-GRID -> S+NEAR or fallback
src, n1 = re.subn(r'title_tag\s*=\s*"ONLY S-GRID"', 'title_tag="S+NEAR or fallback"', src)
changes["title_tag"] = n1

# 2) Header label: OKX (USDT swap) -> BingX (USDT perp)
src, n2 = re.subn(r'OKX\s*\(USDT\s*swap\)', 'BingX (USDT perp)', src)
changes["header_label"] = n2

# 3) Picks logic: prefer sgrid+near when available
patterns = [
    r'picks\s*=\s*sgrid\[:TOPK\]',
    r'picks\s*=\s*\(\s*sgrid\s*\)\s*\[:TOPK\]',
]
repl = "picks=(sgrid+near)[:TOPK] if (sgrid or near) else sorted(rows, key=lambda x: x['score'], reverse=True)[:TOPK]"
n3_total = 0
for pat in patterns:
    src, n3 = re.subn(pat, repl, src)
    n3_total += n3
changes["picks"] = n3_total

# 4) In case code prints fixed '5m' in header, try to replace with formatted TF if exists
# This is heuristic and safe to ignore if not found.
src, n4 = re.subn(r'—\s*\d+m\s*\|', '— {tf} |', src)  # harmless if not matched
changes["tf_header_hint"] = n4

if src != orig:
    TARGET.write_text(src, encoding="utf-8")
    print(">> Patch summary:", json.dumps(changes), flush=True)
else:
    print(">> No patch applied (patterns not found). Summary:", json.dumps(changes), flush=True)
