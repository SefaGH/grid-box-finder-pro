# src/core/guards.py
from __future__ import annotations
from typing import List, Tuple
import math

def adx14(ohlc: List[Tuple[float, float, float, float]]) -> float:
    """
    Basit ve stabil bir ADX(~14) tahmini. ohlc: [(o,h,l,c), ...]
    Bu “yaklaşık” uygulama guard amaçlı yeterli hassasiyette.
    """
    n = 14
    if len(ohlc) < n + 1:
        return 0.0

    trs, plus_dm, minus_dm = [], [], []
    prev_o, prev_h, prev_l, prev_c = ohlc[0]

    for o, h, l, c in ohlc[1:]:
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        up_move = h - prev_h
        down_move = prev_l - l

        pdm = up_move if (up_move > 0 and up_move > down_move) else 0.0
        ndm = down_move if (down_move > 0 and down_move > up_move) else 0.0

        trs.append(tr)
        plus_dm.append(pdm)
        minus_dm.append(ndm)
        prev_o, prev_h, prev_l, prev_c = o, h, l, c

    if len(trs) < n:
        return 0.0

    atr = sum(trs[-n:]) / n
    if atr <= 0:
        return 0.0
    pdi = (sum(plus_dm[-n:]) / n) / atr * 100.0
    ndi = (sum(minus_dm[-n:]) / n) / atr * 100.0
    denom = max(pdi + ndi, 1e-9)
    dx = abs(pdi - ndi) / denom * 100.0
    return dx  # tek periyotluk DX; guard için yeterli

def volatility_spike(closes: List[float], win_fast: int = 20, win_slow: int = 120, mult: float = 2.0) -> bool:
    """
    Hızlı std / yavaş std oranına göre volatilite patlaması tespiti.
    """
    if len(closes) < max(win_fast, win_slow):
        return False

    def std(vals: List[float]) -> float:
        m = sum(vals) / len(vals)
        return math.sqrt(sum((v - m) ** 2 for v in vals) / max(len(vals) - 1, 1))

    fast = std(closes[-win_fast:])
    slow = std(closes[-win_slow:])
    return slow > 0 and (fast / slow) >= mult
