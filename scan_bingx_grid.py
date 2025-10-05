import os, time, math, requests
from typing import List, Dict, Any, Tuple

import ccxt  # public-only BingX access via ccxt
from formatting import format_telegram_scan_message

# ---------------- ENV & CONSTANTS ----------------
def _env_float(n: str, d: float) -> float:
    try:
        v = os.environ.get(n, "")
        return float(v) if v not in ("", None) else d
    except Exception:
        return d

def _env_int(n: str, d: int) -> int:
    try:
        v = os.environ.get(n, "")
        return int(v) if v not in ("", None) else d
    except Exception:
        return d

def _env_str(n: str, d: str) -> str:
    v = os.environ.get(n, "")
    return v if v not in ("", None) else d

ENABLE_RATE_LIMIT = True

# Core scope
TOP_K = _env_int("TOP_K", 80)
ATR_PCT_MIN = _env_float("ATR_PCT_MIN", 0.0025)       # >= 0.25%
RANGE_PCT_MIN = _env_float("RANGE_PCT_MIN", 0.015)    # >= 1.5%
ADX_MAX = _env_float("ADX_MAX", 13.0)
MID_CROSS_MIN = _env_int("MID_CROSS_MIN", 18)
DRIFT_MAX_RATIO = _env_float("DRIFT_MAX_RATIO", 0.15)

# Liquidity & listing age
MIN_QVOL_USDT = _env_float("MIN_QVOL_USDT", 1_000_000.0)  # 24h quoteVolume
LISTED_MIN_DAYS = _env_int("LISTED_MIN_DAYS", 30)         # exclude too-new listings (approx)

# Grid width floor (based on ATR)
MIN_GRID_K_ATR = _env_float("MIN_GRID_K_ATR", 1.0)

# Fast S controls (1m diagnostics)
FAST_S_MODE = _env_int("FAST_S_MODE", 1)               # 1=on, 0=off
FAST_TF = _env_str("FAST_TF", "1m").replace('"','').replace("'","")
if FAST_TF not in ("1m","3m","5m","15m","30m","1h","2h","4h","6h","8h","12h","1d","3d","1w","1M"):
    FAST_TF = "1m"
FAST_LIMIT = _env_int("FAST_LIMIT", 360)               # ~6h in 1m
MIN_CROSSES_PER_HOUR = _env_float("MIN_CROSSES_PER_HOUR", 10)
CYCLE_MIN_MIN = _env_float("CYCLE_MIN_MIN", 5)
CYCLE_MAX_MIN = _env_float("CYCLE_MAX_MIN", 35)
MIN_EDGE_TOUCHES_PH = _env_float("MIN_EDGE_TOUCHES_PH", 6)
WIDE_MIN_RANGE_PCT = _env_float("WIDE_MIN_RANGE_PCT", 0.04)  # >= 4% range on 5m window

# Hard caps for Top list + NEAR specific threshold
TOP_ADX_HARD_MAX   = _env_float("TOP_ADX_HARD_MAX", 30.0)
TOP_DRIFT_HARD_MAX = _env_float("TOP_DRIFT_HARD_MAX", 0.70)   # 70% of window range
FAST_NEAR_MIN_XPH  = _env_float("FAST_NEAR_MIN_XPH", 18.0)    # tighter speed for NEAR/FAST
FAST_REQUIRE_PINGPONG = _env_int("FAST_REQUIRE_PINGPONG", 1)  # 1=require PP, 0=allow FAST without PP

# How many lines to send per section
TOP_FAST = _env_int("TOP_FAST", 12)
TOP_SEND = _env_int("TOP_SEND", 12)

# Optional Telegram knobs
TELEGRAM_ALWAYS_NEAR = str(os.environ.get("TELEGRAM_ALWAYS_NEAR", "0")).strip().lower() in ("1","true","yes")
TELEGRAM_HEALTH_PING = str(os.environ.get("TELEGRAM_HEALTH_PING", "0")).strip().lower() in ("1","true","yes")
TELEGRAM_DEBUG       = str(os.environ.get("TELEGRAM_DEBUG", "0")).strip().lower() not in ("", "0", "false", "no")

# ---------------- HELPERS ----------------
def pct(x: float) -> str:
    return f"{x * 100:.2f}%"

def sma(vals: List[float], period: int) -> List[float]:
    out, s = [], 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= period:
            s -= vals[i - period]
        out.append(s / period if i >= period - 1 else float("nan"))
    return out

def atr_from_ohlc(values: List[Tuple[float, float, float, float]], period: int = 14) -> float:
    if len(values) < period + 1:
        return 0.0
    trs = []
    prev_close = values[0][3]
    for (o, h, l, c) in values[1:]:
        tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
        trs.append(tr)
        prev_close = c
    if len(trs) < period:
        return 0.0
    return sum(trs[-period:]) / period

def adx14(ohlc: List[Tuple[float, float, float, float]]) -> float:
    n = 14
    if len(ohlc) < n + 1:
        return 100.0  # insufficient history → treat as trending to be safe
    trs, pdms, ndms = [], [], []
    prev = ohlc[0]
    for cur in ohlc[1:]:
        (po, ph, pl, pc) = prev
        (o, h, l, c) = cur
        tr = max(h - l, abs(h - pc), abs(l - pc))
        up_move = h - ph
        down_move = pl - l
        plus_dm = max(up_move, 0.0)
        minus_dm = max(down_move, 0.0)
        if plus_dm < minus_dm:
            plus_dm = 0.0
        elif minus_dm < plus_dm:
            minus_dm = 0.0
        trs.append(tr)
        pdms.append(plus_dm)
        ndms.append(minus_dm)
        prev = cur

    def wilder(arr: List[float], p: int) -> List[float]:
        out = []
        sm = sum(arr[:p])
        out.append(sm)
        for i in range(p, len(arr)):
            sm = sm - (sm / p) + arr[i]
            out.append(sm)
        return out

    if min(len(trs), len(pdms), len(ndms)) < n:
        return 100.0

    atr_ws, pdi_ws, ndi_ws = wilder(trs, n), wilder(pdms, n), wilder(ndms, n)
    ln = min(len(atr_ws), len(pdi_ws), len(ndi_ws))
    atr_ws, pdi_ws, ndi_ws = atr_ws[-ln:], pdi_ws[-ln:], ndi_ws[-ln:]

    plus_di = [(pdi_ws[i] / atr_ws[i] * 100.0) if atr_ws[i] > 0 else 0.0 for i in range(ln)]
    minus_di = [(ndi_ws[i] / atr_ws[i] * 100.0) if atr_ws[i] > 0 else 0.0 for i in range(ln)]

    dx = []
    for i in range(ln):
        s = plus_di[i] + minus_di[i]
        dx.append((abs(plus_di[i] - minus_di[i]) / s * 100.0) if s > 0 else 0.0)

    if len(dx) < n:
        return 100.0
    return sum(dx[-n:]) / n

def mid_cross_count(closes: List[float], mid: List[float]) -> int:
    cnt, prev_diff = 0, None
    for c, m in zip(closes, mid):
        if m != m:
            continue
        diff = c - m
        if prev_diff is not None:
            if diff == 0:
                cnt += 1
            elif (diff > 0 and prev_diff < 0) or (diff < 0 and prev_diff > 0):
                cnt += 1
        prev_diff = diff
    return cnt

def percentile(sorted_vals: List[float], q: float) -> float:
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
    S = sorted(closes)
    lo = percentile(S, q_lo)
    hi = percentile(S, q_hi)
    touches = 0
    for c in closes:
        if c <= lo or c >= hi:
            touches += 1
    hours = max(len(closes) / 60.0, 1e-6)
    return touches / hours

def crosses_per_hour(closes: List[float]) -> Tuple[float, float]:
    mid = sma(closes, 20)
    cross_idx = []
    prev_diff = None
    for i, (c, m) in enumerate(zip(closes, mid)):
        if m != m:  # NaN (first 19 bars)
            continue
        diff = c - m
        if prev_diff is not None:
            if diff == 0 or (diff > 0 and prev_diff < 0) or (diff < 0 and prev_diff > 0):
                cross_idx.append(i)
        prev_diff = diff

    # Exclude warmup (~20 bars) from the duration
    warmup = 19
    effective_len = max(len(closes) - warmup, 1)
    hours = max(effective_len / 60.0, 1e-6)

    # 1) count-based rate
    count_rate = len(cross_idx) / hours

    # 2) rate derived from median interval (more robust)
    intervals = [(cross_idx[i] - cross_idx[i - 1]) for i in range(1, len(cross_idx))]
    if not intervals:
        return count_rate, float('inf')
    intervals.sort()
    med = float(intervals[len(intervals) // 2])  # bars in minutes (1 bar = 1 min on 1m tf)
    rate_from_med = (60.0 / med) if (med > 0 and math.isfinite(med)) else 0.0

    return max(count_rate, rate_from_med), med

def suggest_grid(last: float, atr_abs: float) -> Tuple[float, float, int]:
    if last <= 0:
        return (last, last, 12)
    atr_pct = atr_abs / last if last else 0.0
    width_pct = max(0.02, min(0.06, atr_pct * 6.0))
    min_pct_by_atr = (MIN_GRID_K_ATR * atr_abs / last) if (MIN_GRID_K_ATR > 0 and last > 0) else 0.0
    width_pct = max(width_pct, min_pct_by_atr)
    half = last * width_pct / 2.0
    return (last - half, last + half, 12)

def send_telegram(msg: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or ""
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or ""
    if not token or not chat_id:
        print("[info] Telegram env yok; mesaj atılmadı.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    dbg = TELEGRAM_DEBUG

    def _mask_chat(cid: str) -> str:
        s = str(cid)
        if len(s) <= 6:
            return "***"
        return s[:2] + "***" + s[-3:]

    parts = [msg[i:i+3500] for i in range(0, len(msg), 3500)] or [msg]
    for idx, part in enumerate(parts, 1):
        try:
            if dbg:
                preview = part.replace("\\n", " ")[:120]
                print(f"[tg-debug] send chunk {idx}/{len(parts)} to {_mask_chat(chat_id)} | len={len(part)} | preview='{preview}…'")
            r = requests.post(
                url,
                data={"chat_id": chat_id, "text": part},
                timeout=20
            )
        except Exception as e:
            print(f"[warn] Telegram exception (chunk {idx}/{len(parts)}): {e}")
            continue

        ok = False
        desc = ""
        code = None
        try:
            j = r.json()
            ok = bool(j.get("ok", False))
            desc = j.get("description", "")
            code = j.get("error_code")
        except Exception:
            pass

        if r.status_code != 200 or not ok:
            body = ""
            try:
                body = r.text[:300]
            except Exception:
                pass
            print(f"[warn] Telegram API error (chunk {idx}/{len(parts)}): status={r.status_code}, ok={ok}, code={code}, desc={desc}, body={body}")
        else:
            if dbg:
                print(f"[tg-debug] chunk {idx}/{len(parts)} delivered: ok={ok}")

def _human_tags(tags: List[str]) -> str:
    return "".join([f"[{t}]" for t in tags])
