# src/core/guards.py
from __future__ import annotations
from typing import List, Tuple
import math

def adx14(ohlc: List[Tuple[float,float,float,float]]) -> float:
    # ohlc: [(o,h,l,c), ...]
    n = 14
    if len(ohlc) < n + 1:
        return 100.0
    trs, pdms, ndms = [], [], []
    (po,ph,pl,pc) = ohlc[0]
    for (o,h,l,c) in ohlc[1:]:
        tr = max(h-l, abs(h-pc), abs(l-pc))
        up_move = h - ph
        down_move = pl - l
        +dm = up_move if up_move > 0 and up_move > (pl - l) else 0.0
        -dm = (ph - l) if (pl - l) > 0 and (pl - l) > up_move else 0.0
        # düzeltme:
        plus_dm  = max(up_move, 0.0)
        minus_dm = max(pl - l, 0.0)
        if plus_dm < minus_dm: plus_dm = 0.0
        elif minus_dm < plus_dm: minus_dm = 0.0
        trs.append(tr); pdms.append(plus_dm); ndms.append(minus_dm)
        (po,ph,pl,pc) = (o,h,l,c)
    if len(trs) < n: return 100.0
    atr = sum(trs[-n:]) / n
    if atr == 0: return 100.0
    pdi = (sum(pdms[-n:]) / n) / atr * 100.0
    ndi = (sum(ndms[-n:]) / n) / atr * 100.0
    dx  = abs(pdi - ndi) / max(pdi + ndi, 1e-9) * 100.0
    return dx  # tek periyotluk yaklaşıklık (pratikte yeterli)

def volatility_spike(closes: List[float], win_fast: int = 20, win_slow: int = 120, mult: float = 2.0) -> bool:
    # hızlı ve yavaş pencerelerde std dev oranına bak
    if len(closes) < max(win_fast, win_slow):
        return False
    def std(vals):
        m = sum(vals)/len(vals)
        return math.sqrt(sum((v-m)**2 for v in vals)/max(len(vals)-1,1))
    fast = std(closes[-win_fast:])
    slow = std(closes[-win_slow:])
    return slow > 0 and (fast / slow) >= mult
