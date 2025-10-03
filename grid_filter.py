#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
grid_filter.py  (5m destekli)
--------------------------------
Pro Grid Box Finder çıktısını filtreler ve OKX'e gireceğin değerleri üretir.

- Primary: geniş aralık + düşük drift + düşük CV + yeterli skor
- Fallback: dar ama "makine gibi" çalışanlar (yüksek skor, düşük drift/CV, yüksek aktivasyon)
- Timeframe'e göre önerilen grid sayısını hesaplar (3m, **5m**, 15m, 1h)

KULLANIM
--------
python grid_filter.py scan_5m.txt --tf 5m --print-okx
python grid_filter.py scan_15m.txt --tf 15m --min-range 3.0 --max-drift 0.18 --max-cv 0.30 --min-score 48
"""

import re
import sys
import argparse
from pathlib import Path
from typing import List, Tuple, Dict, Any

LINE_RE = re.compile(
    r"[—\-]\s*(?P<sym>[A-Z0-9\-]+)\s*\|\s*"
    r"Lrng\s*(?P<lrng>[\d\.]+)%.*?\|\s*"
    r"Ratr\s*(?P<ratr>[\d\.]+)%.*?T(?P<T>\d+)\s*A(?P<A>\d+)\s*\|\s*"
    r"S\s*.*?cv\s*(?P<cv>[\d\.]+)\s*d\s*(?P<d>[\d\.]+)%\s*\|\s*"
    r"grid\s*\[(?P<low>[\deE\.\-]+)\s*[…\.]{1,3}\s*(?P<high>[\deE\.\-]+)\]\s*mid\s*(?P<mid>[\deE\.\-]+)\s*\|\s*"
    r"score\s*(?P<score>[\d\.]+)",
    re.IGNORECASE
)

def parse_lines(text: str) -> List[Dict[str, Any]]:
    items = []
    for m in LINE_RE.finditer(text):
        g = m.groupdict()
        try:
            low = float(g["low"]); high = float(g["high"]); mid = float(g["mid"])
            lrng = float(g["lrng"]); ratr = float(g["ratr"])
            cv = float(g["cv"]); d = float(g["d"]); score = float(g["score"])
            T = int(g["T"]); A = int(g["A"])
        except Exception:
            continue
        if mid == 0:
            continue
        rng_pct = (high - low) / mid * 100.0
        items.append({
            "sym": g["sym"],
            "low": low, "high": high, "mid": mid,
            "lrng": lrng, "ratr": ratr,
            "cv": cv, "d": d, "score": score,
            "touches": T, "activations": A,
            "range_pct": rng_pct
        })
    return items

def recommend(items: List[Dict[str, Any]],
              min_range: float, max_drift: float, max_cv: float, min_score: float,
              fallback: Dict[str, float]) -> Tuple[List[Dict[str, Any]], str]:
    cand = [x for x in items if x["lrng"] >= min_range and x["d"] <= max_drift and x["cv"] <= max_cv and x["score"] >= min_score]
    if cand:
        cand.sort(key=lambda x: (-x["score"], x["d"], x["cv"], -x["activations"]))
        return cand, "wide"
    fc = [x for x in items if x["score"] >= fallback["min_score"] and x["cv"] <= fallback["max_cv"] and x["d"] <= fallback["max_drift"]]
    if fc:
        fc.sort(key=lambda x: (-x["activations"], -x["score"], x["d"], x["cv"]))
        return fc, "fallback"
    return [], "none"

def grid_step_pct_for_tf(tf: str) -> float:
    # Conservative default steps; 5m, 3m arasına yerleştirildi
    return {"3m": 0.10, "5m": 0.15, "15m": 0.20, "1h": 0.35}.get(tf, 0.20)

def grid_count_for_timeframe(low: float, high: float, mid: float, tf: str) -> Tuple[int, float]:
    pct = (high - low) / mid * 100.0 if mid else 0.0
    step = grid_step_pct_for_tf(tf)
    gc = round(pct / step) if step > 0 else 20
    gc = max(12, min(60, gc))
    return gc, pct

def print_candidates(cand: List[Dict[str, Any]], tf: str, top: int, okx: bool) -> None:
    print(f"Timeframe: {tf}  |  Top: {top}")
    for x in cand[:top]:
        gc, pct = grid_count_for_timeframe(x["low"], x["high"], x["mid"], tf)
        line = (
            f"- {x['sym']:>16} | range[{x['low']} … {x['high']}] mid {x['mid']} | "
            f"Lrng {x['lrng']}%  CV {x['cv']}  d {x['d']}%  score {x['score']}  A {x['activations']} | "
            f"range%≈{pct:.2f}  → grid_count≈{gc}  | mode=Geometric"
        )
        print(line)
        if okx:
            print(f"  OKX ▶ Lower={x['low']}  Upper={x['high']}  Mid={x['mid']}  GridCount={gc}  Mode=Geometric")

def main():
    ap = argparse.ArgumentParser(description="Filter Pro Grid Box Finder output and produce OKX-ready parameters.")
    ap.add_argument("file", help="Path to scan .txt (raw bot output)")
    ap.add_argument("--tf", default="15m", choices=["3m","5m","15m","1h"], help="Timeframe for grid_count estimation (default: 15m)")
    ap.add_argument("--min-range", type=float, default=2.5, help="Min Lrng%% for primary filter (default: 2.5)")
    ap.add_argument("--max-drift", type=float, default=0.20, help="Max drift%% (default: 0.20)")
    ap.add_argument("--max-cv", type=float, default=0.35, help="Max CV (default: 0.35)")
    ap.add_argument("--min-score", type=float, default=45.0, help="Min score (default: 45)")
    ap.add_argument("--fb-min-score", type=float, default=50.0, help="Fallback min score (default: 50)")
    ap.add_argument("--fb-max-cv", type=float, default=0.40, help="Fallback max CV (default: 0.40)")
    ap.add_argument("--fb-max-drift", type=float, default=0.30, help="Fallback max drift%% (default: 0.30)")
    ap.add_argument("--top", type=int, default=8, help="How many candidates to display (default: 8)")
    ap.add_argument("--print-okx", action="store_true", help="Also print OKX-ready parameters for quick entry")
    args = ap.parse_args()

    p = Path(args.file)
    if not p.exists():
        print(f"❌ File not found: {p}")
        sys.exit(1)

    text = p.read_text(encoding="utf-8", errors="ignore")
    items = parse_lines(text)

    if not items:
        print("⚠️ No parsable candidates found. Ensure you pasted raw bot lines (with '— ... grid [low … high] mid ... | score ...').")
        sys.exit(0)

    cand, mode = recommend(
        items,
        args.min_range, args.max_drift, args.max_cv, args.min_score,
        {"min_score": args.fb_min_score, "max_cv": args.fb_max_cv, "max_drift": args.fb_max_drift}
    )

    if not cand:
        print("⚠️ No candidates matched thresholds. Try loosening --min-range or raising --max-drift/--max-cv, or change timeframe.")
        sys.exit(0)

    print(f"✅ Mode: {mode}  |  Candidates found: {len(cand)}")
    print_candidates(cand, args.tf, args.top, args.print_okx)

if __name__ == "__main__":
    main()
