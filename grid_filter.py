#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re, sys, argparse
from pathlib import Path

DASH = r"(?:—|-)"
ELLIPSIS = r"(?:…|\.{3})"

RE_GRID = re.compile(
    rf"^{DASH}\s+(?P<sym>[A-Z0-9/:\-]+)\s+\|.*?"
    rf"grid\s*\[\s*(?P<low>[0-9.eE+-]+)\s*{ELLIPSIS}\s*(?P<high>[0-9.eE+-]+)\s*\]\s*"
    rf"mid\s*(?P<mid>[0-9.eE+-]+)\s*\|.*?"
    rf"score\s*(?P<score>[0-9]+(?:\.[0-9]+)?)\s*$"
)

def parse_line(line):
    m = RE_GRID.search(line)
    if not m:
        return None
    d = m.groupdict()
    return {
        "raw": line.rstrip(),
        "sym": d["sym"],
        "low": float(d["low"]),
        "high": float(d["high"]),
        "mid": float(d["mid"]),
        "score": float(d["score"]),
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
        print(f"⚠️ Input file not found: {p}")
        sys.exit(0)

    lines = [ln for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.strip()]
    parsed = [parse_line(ln) for ln in lines]
    parsed = [x for x in parsed if x]

    if not parsed:
        print("⚠️ No parsable candidates found.")
        sys.exit(0)

    parsed.sort(key=lambda x: x["score"], reverse=True)
    kept = parsed[: args.top]

    if not kept:
        print("(no S-GRID matches)")
        sys.exit(0)

    for it in kept:
        print(it["raw"])

if __name__ == "__main__":
    main()
