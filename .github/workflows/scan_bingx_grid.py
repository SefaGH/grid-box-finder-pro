import os, time, math, requests
from typing import List, Dict, Any, Tuple

import ccxt  # public-only BingX access via ccxt


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
FAST_TF = _env_str("FAST_TF", "1m").strip('\"\\'')
# fallback to 1m if invalid
if FAST_TF not in ("1m","3m","5m","15m","30m","1h","2h","4h","6h","8h","12h","1d","3d","1w","1M"):
    FAST_TF = "1m"
FAST_LIMIT = _env_int("FAST_LIMIT", 360)               # ~6h in 1m
MIN_CROSSES_PER_HOUR = _env_float("MIN_CROSSES_PER_HOUR", 10)
CYCLE_MIN_MIN = _env_float("CYCLE_MIN_MIN", 5)
CYCLE_MAX_MIN = _env_float("CYCLE_MAX_MIN", 35)
MIN_EDGE_TOUCHES_PH = _env_float("MIN_EDGE_TOUCHES_PH", 6)
WIDE_MIN_RANGE_PCT = _env_float("WIDE_MIN_RANGE_PCT", 0.04)  # >= 4% range on 5m window


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
    try:
        r = requests.post(url, data={"chat_id": chat_id, "text": msg}, timeout=15)
        if r.status_code != 200:
            print("[warn] Telegram response:", r.text)
    except Exception as e:
        print("[warn] Telegram exception:", e)


def _human_tags(tags: List[str]) -> str:
    return "".join([f"[{t}]" for t in tags])


def to_human(d: Dict[str, Any]) -> str:
    tag = " [PING-PONG OK]" if d.get("pingpong_ok") else ""
    fast = " [FAST S OK]" if d.get("fast_ok") else ""
    why = _human_tags(d.get("why_tags", []))
    extra = ""
    if d.get("fast_checked"):
        extra = f" | fast: xph={d.get('xph','-')}, med={d.get('med','-')}m, edgeph={d.get('edgeph','-')}"
    return (
        f"{d['symbol']}: last={d['last']:.6g} | ATR={d['atr_abs']:.6g} ({pct(d['atr_pct'])}) | "
        f"range≈{pct(d['range_pct'])} | ADX≈{d.get('adx', float('nan')):.1f} | "
        f"mid-cross={d.get('midcross', 0)} | drift%≈{pct(d.get('drift_ratio', 0.0))}{tag}{fast}"
        f"{(' ' + why) if why else ''} | grid≈[{d['grid_lower']:.6g} … {d['grid_upper']:.6g}] × {d['levels']}{extra}"
    )


def ticker_quote_usdt(tk: Dict[str, Any]) -> float:
    qv = tk.get("quoteVolume")
    if qv is not None:
        try:
            return float(qv)
        except Exception:
            pass
    last = tk.get("last") or tk.get("close") or 0.0
    base = tk.get("baseVolume") or 0.0
    try:
        return float(last) * float(base)
    except Exception:
        return 0.0


def estimate_listing_age_days(exchange, symbol: str, market_info: Dict[str, Any]) -> float:
    info = market_info.get("info", {}) if isinstance(market_info, dict) else {}
    for key in ("listingTime", "createTime", "listTime", "onboardDate", "launchTime", "created"):
        if key in info:
            try:
                ts = int(info[key])
                if ts > 1e12:
                    while ts > 1e13:
                        ts //= 10
                if ts < 1e11:
                    ts *= 1000  # seconds→ms
                now_ms = exchange.milliseconds()
                return (now_ms - ts) / (1000 * 60 * 60 * 24)
            except Exception:
                continue
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe="1h", limit=500)
        return (len(bars) / 24.0)  # rough lower bound
    except Exception:
        return -1.0  # unknown → don't block


# ---------------- MAIN ----------------
def main():
    print("== BingX Grid Scan — Fast S mode ==")
    ex = ccxt.bingx({"enableRateLimit": True, "options": {"defaultType": "swap"}})

    markets = ex.load_markets()
    symbols = [s for s, m in markets.items() if m.get("contract") and m.get("quote") == "USDT"]
    if not symbols:
        raise RuntimeError("BingX USDT-M contract listesi boş.")

    # fetch tickers (with fallback)
    def safe_fetch_tickers(symbols):
        try:
            return ex.fetch_tickers(symbols)
        except Exception as e:
            print("[info] fetch_tickers(symbols) desteklenmedi, tüm tickers çekiliyor…", e)
            all_tickers = ex.fetch_tickers()
            return {s: all_tickers[s] for s in symbols if s in all_tickers}

    tickers = safe_fetch_tickers(symbols)

    def notional(t: Dict[str, Any]) -> float:
        last = t.get("last") or t.get("close") or 0.0
        qv = t.get("quoteVolume") or 0.0
        bv = t.get("baseVolume") or 0.0
        try:
            return float(qv) if qv else float(last) * float(bv)
        except Exception:
            return 0.0

    # rank by notional and cut to TOP_K
    pairs = [(s, tickers[s]) for s in symbols if s in tickers]
    pairs.sort(key=lambda x: notional(x[1]), reverse=True)
    pairs = pairs[:TOP_K]

    pp, fast_pp, allres = [], [], []
    for sym, tk in pairs:
        try:
            qvol = ticker_quote_usdt(tk)
            liq_ok = (qvol >= MIN_QVOL_USDT) if MIN_QVOL_USDT > 0 else True

            # ----- 5m window (≈16h) -----
            ohlcv5 = ex.fetch_ohlcv(sym, timeframe="5m", limit=200)
            if not ohlcv5 or len(ohlcv5) < 60:
                print("SKIP (yetersiz 5m OHLCV) ", sym)
                continue

            closes5 = [float(c) for _, o, h, l, c, v in ohlcv5]
            ohlc5 = [(float(o), float(h), float(l), float(c)) for _, o, h, l, c, v in ohlcv5]
            last = closes5[-1]

            atr50 = atr_from_ohlc(ohlc5, period=50)
            window = closes5[-180:] if len(closes5) >= 180 else closes5
            total_range = (max(window) - min(window)) if window else 0.0
            rng = (total_range / last) if last > 0 else 0.0

            lower, upper, levels = suggest_grid(last, atr50)

            adx_val = adx14(ohlc5[-150:])
            mid5 = sma(closes5, 20)
            midcross5 = mid_cross_count(closes5[-180:], mid5[-180:])
            drift = abs(closes5[-1] - closes5[0])
            drift_ratio = (drift / total_range) if total_range > 0 else 0.0

            atr_pct = (atr50 / last) if last > 0 else 0.0
            base_ok = (atr_pct >= ATR_PCT_MIN and rng >= RANGE_PCT_MIN and liq_ok)
            age_ok = True
            if base_ok and LISTED_MIN_DAYS > 0:
                days = estimate_listing_age_days(ex, sym, markets.get(sym, {}))
                age_ok = (days < 0) or (days >= LISTED_MIN_DAYS)

            pingpong_ok = (
                base_ok and age_ok and (adx_val <= ADX_MAX) and (midcross5 >= MID_CROSS_MIN) and (drift_ratio <= DRIFT_MAX_RATIO)
            )

            # ----- FAST S (1m) — only if ping-pong OK -----
            fast_checked = False
            fast_ok = False
            xph = med = edgeph = "-"
            if FAST_S_MODE and pingpong_ok:
                fast_checked = True
                ohlcv1 = ex.fetch_ohlcv(sym, timeframe=FAST_TF, limit=FAST_LIMIT)
                if ohlcv1 and len(ohlcv1) >= 120:
                    closes1 = [float(c) for _, o, h, l, c, v in ohlcv1]
                    xph_val, med_min = crosses_per_hour(closes1)  # per hour & median minutes
                    edgeph_val = touches_per_hour(closes1, 0.2, 0.8)
                    wide_ok = (rng >= WIDE_MIN_RANGE_PCT)
                    fast_ok = (
                        xph_val >= MIN_CROSSES_PER_HOUR
                        and (CYCLE_MIN_MIN <= med_min <= CYCLE_MAX_MIN)
                        and edgeph_val >= MIN_EDGE_TOUCHES_PH
                        and wide_ok
                    )
                    xph, med, edgeph = f"{xph_val:.1f}", f"{med_min:.0f}", f"{edgeph_val:.1f}"
                else:
                    xph, med, edgeph = "NA", "NA", "NA"
                    fast_ok = False

            # ----- why-tags for readability -----
            why = []
            if atr_pct < ATR_PCT_MIN:
                why.append("LOWVOL")
            if rng < RANGE_PCT_MIN:
                why.append("LOWRANGE")
            if not liq_ok:
                why.append("LOWLIQ")
            if LISTED_MIN_DAYS > 0 and base_ok and not age_ok:
                why.append("NEW")
            if adx_val > ADX_MAX:
                why.append("TREND")
            if midcross5 < MID_CROSS_MIN:
                why.append("MID")
            if drift_ratio > DRIFT_MAX_RATIO:
                why.append("DRIFT")

            d = {
                "symbol": sym,
                "last": last,
                "atr_abs": atr50,
                "atr_pct": atr_pct,
                "range_pct": rng,
                "grid_lower": lower,
                "grid_upper": upper,
                "levels": levels,
                "adx": adx_val,
                "midcross": midcross5,
                "drift_ratio": drift_ratio,
                "pingpong_ok": pingpong_ok,
                "why_tags": ([] if pingpong_ok else why),
                "fast_checked": fast_checked,
                "fast_ok": fast_ok,
                "xph": xph,
                "med": med,
                "edgeph": edgeph,
            }

            if base_ok:
                allres.append(d)
                print("OK  ", to_human(d))
            else:
                print("SKIP", to_human(d))

            if pingpong_ok:
                pp.append(d)
            if pingpong_ok and fast_ok:
                fast_pp.append(d)

            time.sleep(0.25)  # be gentle with API
        except ccxt.NetworkError as e:
            print("NETERR", sym, e)
            time.sleep(0.25)
        except Exception as e:
            print("ERR", sym, e)
            time.sleep(0.2)

    # ----- Ranking & Telegram -----
    allres.sort(
        key=lambda x: (0 if x["pingpong_ok"] else 1, 0 if x.get("fast_ok") else 1, -(x["atr_pct"] * x["range_pct"]))
    )

    if fast_pp:
        fst = sorted(fast_pp, key=lambda x: x["atr_pct"] * x["range_pct"], reverse=True)[:8]
        send_telegram("FAST S OK (wide & quick S)\n" + "\n".join([to_human(d) for d in fst]))

    if pp:
        pps = sorted(pp, key=lambda x: x["atr_pct"] * x["range_pct"], reverse=True)[:8]
        send_telegram("PING-PONG OK (S davranışı teyitli)\n" + "\n".join([to_human(d) for d in pps]))

    header = "BingX Grid Scan Sonuçları (Top adaylar)\n"
    lines = [to_human(d) for d in allres[:12]]
    send_telegram(header + ("\n".join(lines) if lines else "(Aday bulunamadı)"))
    print("\n" + header + ("\n".join(lines) if lines else "(Aday bulunamadı)") + "\n")


if __name__ == "__main__":
    main()
