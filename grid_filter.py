#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re, sys, argparse
from pathlib import Path

DASH = r"(?:—|-)"
ELLIPSIS = r"(?:…|\.\.\.)"

RE = re.compile(
    rf"^{DASH}\s+(?P<sym>[A-Z0-9/:\-]+)\s+\|(?P<rest>.*?grid\s*\[\s*(?P<low>[0-9.eE+-]+)\s*{ELLIPSIS}\s*(?P<high>[0-9.eE+-]+)\s*\]\s*mid\s*(?P<mid>[0-9.eE+-]+)\s*\|\s*score\s*(?P<score>[0-9]+(?:\.[0-9]+)?)\s*)$"
)

def pick_float(pat, s, default=None):
    m = re.search(pat, s)
    return float(m.group(1)) if m else default

def parse_line(line):
    m = RE.search(line.strip())
    if not m:
        return None
    d = m.groupdict()
    rest = d["rest"]
    lrng  = pick_float(r"Lrng\s+([0-9.]+)%", rest) or 0.0
    cv    = pick_float(r"\bcv\s+([0-9.]+)\b", rest) or 999.0
    drift = pick_float(r"\bd\s+([0-9.]+)%", rest) or 999.0
    altR  = pick_float(r"\baltR\s+([0-9.]+)\b", rest) or 0.0
    return {
        "raw": line.rstrip(),
        "sym": d["sym"],
        "low": float(d["low"]),
        "high": float(d["high"]),
        "mid": float(d["mid"]),
        "score": float(d["score"]),
        "lrng": lrng, "cv": cv, "drift": drift, "altR": altR,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", help="scan_*.txt")
    ap.add_argument("--tf", choices=["3m","5m","15m","1h"], default="5m")
    ap.add_argument("--min-range", type=float, default=1.0)
    ap.add_argument("--max-drift", type=float, default=0.40)
    ap.add_argument("--max-cv", type=float, default=0.60)
    ap.add_argument("--min-score", type=float, default=25.0)
    ap.add_argument("--fb-min-score", type=float, default=40.0)
    ap.add_argument("--fb-max-cv", type=float, default=0.60)
    ap.add_argument("--fb-max-drift", type=float, default=0.40)
    ap.add_argument("--top", type=int, default=24)
    ap.add_argument("--print-okx", action="store_true")
    args = ap.parse_args()

    p = Path(args.file)
    if not p.exists():
        print(f"⚠️ Input file not found: {p}"); sys.exit(0)

    items = []
    for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        ln = ln.strip()
        if not ln: continue
        it = parse_line(ln)
        if it: items.append(it)

    if not items:
        print("⚠️ No parsable candidates found."); sys.exit(0)

    kept = []
    for it in items:
        is_fb = (it["altR"] > 0.0)
        if is_fb:
            ok = (it["lrng"] >= args.min_range and it["cv"] <= args.fb_max_cv and it["drift"] <= args.fb_max_drift and it["score"] >= args.fb_min_score)
        else:
            ok = (it["lrng"] >= args.min_range and it["cv"] <= args.max_cv and it["drift"] <= args.max_drift and it["score"] >= args.min_score)
        if ok: kept.append(it)

    kept.sort(key=lambda x: x["score"], reverse=True)
    kept = kept[: args.top]

    if not kept:
        print("(no S-GRID matches)"); sys.exit(0)

    for it in kept:
        print(it["raw"])

if __name__ == "__main__":
    main()
