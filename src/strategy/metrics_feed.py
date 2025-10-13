from __future__ import annotations
from typing import Dict, List, Tuple
import math, time
from src.core.exchange_ccxt import ExchangeCCXT

def _sma(vals: List[float], n: int) -> float:
    if len(vals) < n or n <= 0:
        return sum(vals) / max(1, len(vals))
    return sum(vals[-n:]) / n

def _percentile(sorted_vals: List[float], q: float) -> float:
    if not sorted_vals:
        return float("nan")
    q = min(max(q, 0.0), 1.0)
    idx = q * (len(sorted_vals) - 1)
    lo, hi = int(math.floor(idx)), int(math.ceil(idx))
    if lo == hi:
        return sorted_vals[lo]
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac

def touches_per_hour(closes: List[float], q_lo: float = 0.2, q_hi: float = 0.8) -> float:
    if len(closes) < 60:  # en az 1 saatlik 1m bar
        return 0.0
    S = sorted(closes)
    lo = _percentile(S, q_lo); hi = _percentile(S, q_hi)
    touches = sum(1 for c in closes if (c <= lo or c >= hi))
    hours = max(len(closes) / 60.0, 1e-6)
    return touches / hours

def crosses_per_hour(closes: List[float]) -> float:
    if len(closes) < 60:
        return 0.0
    mid = _sma(closes, 20)
    # mid sabit sayı yerine seri olmalı -> kayan ortalama:
    mids = []
    for i in range(len(closes)):
        window = closes[max(0, i-19):i+1]
        mids.append(sum(window) / len(window))
    cross = 0
    prev_diff = None
    for c, m in zip(closes, mids):
        diff = c - m
        if prev_diff is not None and (diff == 0 or (diff > 0) != (prev_diff > 0)):
            cross += 1
        prev_diff = diff
    hours = max(len(closes) / 60.0, 1e-6)
    return cross / hours

def fetch_closes(ex: ExchangeCCXT, symbol: str, tf: str = "1m", limit: int = 360) -> List[float]:
    # ccxt fetch_ohlcv default: [timestamp, open, high, low, close, volume]
    ohlc = ex.ex.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
    return [c[4] for c in ohlc]

def build_metrics(ex: ExchangeCCXT, symbol: str) -> Dict[str, float]:
    closes = fetch_closes(ex, symbol, "1m", 360)
    return {
        "crosses_per_hour": crosses_per_hour(closes),
        "touches_per_hour": touches_per_hour(closes),
        # Basit ADX vekili: buraya gerçek ADX eklenecekse scan_bingx_grid.py fonksiyonlarını port edelim
        "adx": 18.0,
        "liquidity_ok": True,
        "last": closes[-1] if closes else None,
        "closes": closes[-200:]
    }
