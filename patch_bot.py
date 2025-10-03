#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re, sys, json
from pathlib import Path

TARGET = Path("auto_grid_box_finder_pro.py")
if not TARGET.exists():
    print("!! auto_grid_box_finder_pro.py not found")
    sys.exit(0)

src = TARGET.read_text(encoding="utf-8", errors="ignore")
orig = src
changes = {}

src, n_title1 = re.subn(r'title_tag\s*=\s*["\'][^"\']*["\']', 'title_tag="S+NEAR or fallback"', src)
changes["title_tag"] = n_title1

src, n_hdr = re.subn(r'OKX\s*\(USDT\s*swap\)', 'BingX (USDT perp)', src)
changes["header_label"] = n_hdr

pat_picks = re.compile(r'picks\s*=\s*(?:\(\s*)?sgrid(?:\s*\))?\s*\[:\s*TOPK\s*\]')
src, n_picks = pat_picks.subn("picks=(sgrid+near)[:TOPK] if (sgrid or near) else sorted(rows, key=lambda x: x['score'], reverse=True)[:TOPK]", src)
changes["picks_combined"] = n_picks

src, n_tf = re.subn(r'—\s*\d+m\s*\|', '— {tf} |', src)
changes["tf_header_hint"] = n_tf

if src != orig:
    TARGET.write_text(src, encoding="utf-8")
    print(">> Patch summary:", json.dumps(changes))
else:
    print(">> No patch applied. Summary:", json.dumps(changes))
