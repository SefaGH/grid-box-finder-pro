import math
from typing import List

def sma(vals: List[float], n: int) -> float:
    if len(vals) < n or n <= 0: 
        return sum(vals)/max(1,len(vals))
    return sum(vals[-n:])/n

def stddev(vals: List[float], n: int) -> float:
    if len(vals) < n: n = len(vals)
    if n <= 1: return 0.0
    m = sma(vals, n)
    var = sum((v-m)**2 for v in vals[-n:])/(n-1)
    return math.sqrt(var)

def atr(highs: List[float], lows: List[float], closes: List[float], n: int=14) -> float:
    trs = []
    prev_close = None
    for h,l,c in zip(highs, lows, closes):
        if prev_close is None:
            tr = h-l
        else:
            tr = max(h-l, abs(h-prev_close), abs(l-prev_close))
        trs.append(tr)
        prev_close = c
    if len(trs) < n: n = len(trs)
    if n == 0: return 0.0
    return sum(trs[-n:])/n
