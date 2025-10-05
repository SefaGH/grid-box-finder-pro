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

    if TELEGRAM_HEALTH_PING:
#         send_telegram("🟢 Scanner up — starting scan")
  # removed in B-clean
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

            # ----- FAST S (1m) -----
            fast_checked = False
            fast_ok = False
            xph = med = edgeph = "-"
            allow_fast = FAST_S_MODE and (pingpong_ok or (FAST_REQUIRE_PINGPONG == 0))
            if allow_fast:
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
                    xph_n, med_n, edgeph_n = float(xph_val), float(med_min), float(edgeph_val)
                else:
                    xph, med, edgeph = "NA", "NA", "NA"
                    xph_n = med_n = edgeph_n = 0.0
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
                "xph_n": (xph_n if "xph_n" in locals() else 0.0),
                "med_n": (med_n if "med_n" in locals() else 0.0),
                "edgeph_n": (edgeph_n if "edgeph_n" in locals() else 0.0),
            }

            if base_ok:
                allres.append(d)
                print("OK  ", to_human(d))
            else:
                print("SKIP", to_human(d))

            if pingpong_ok:
                pp.append(d)
            if fast_ok and (pingpong_ok or FAST_REQUIRE_PINGPONG == 0):
                fast_pp.append(d)

            time.sleep(0.25)  # be gentle with API
        except ccxt.NetworkError as e:
            print("NETERR", sym, e)
            time.sleep(0.25)
        except Exception as e:
            print("ERR", sym, e)
            time.sleep(0.2)

    # ----- Ranking & Telegram -----
    allres = [d for d in allres
          if float(d.get("adx", 0.0)) <= TOP_ADX_HARD_MAX
          and float(d.get("drift_ratio", 0.0)) <= TOP_DRIFT_HARD_MAX]

    allres.sort(
        key=lambda x: (0 if x["pingpong_ok"] else 1, 0 if x.get("fast_ok") else 1, -(x["atr_pct"] * x["range_pct"]))
    )

    # --- Compose & send Telegram messages ---
    # 2.1 FAST / NEAR list (apply FAST_NEAR_MIN_XPH before sorting/sending)
    if fast_pp:
        _fst = [x for x in fast_pp if float(x.get("xph_n", 0.0)) >= FAST_NEAR_MIN_XPH]
        fst = sorted(
            _fst,
            key=lambda x: (-float(x.get("xph_n", 0.0)),
                           -float(x.get("edgeph_n", 0.0)),
                            float(x.get("med_n", 1e9)),
                           -float(x.get("range_pct", 0.0))),
        )[:TOP_FAST]
        if fst:
            send_telegram("FAST S OK (wide & quick S)\n" + "\n".join([to_human(d) for d in fst]))
    else:
        if TELEGRAM_ALWAYS_NEAR:
            send_telegram("FAST S OK (wide & quick S)\n(şu an eşleşme yok — filtreler sıkı)")

    # 2.2 PING-PONG OK list (S davranışı teyitli)
    if pp:
        pps = sorted(
            pp,
            key=lambda x: (-float(x.get("xph_n", 0.0)),
                           -float(x.get("edgeph_n", 0.0)),
                            float(x.get("med_n", 1e9)),
                           -float(x.get("range_pct", 0.0))),
        )[:TOP_FAST]
#         send_telegram("PING-PONG OK (S davranışı teyitli)\n" + "\n".join([to_human(d) for d in pps]))  # removed in B-clean
    else:
        if TELEGRAM_ALWAYS_NEAR:
#             send_telegram("PING-PONG OK (S davranışı teyitli)\n(şu an eşleşme yok — filtreler sıkı)")
  # removed in B-clean
    # 2.3 Top candidates (after hard caps and ranking)
    header = "BingX Grid Scan Sonuçları (Top adaylar)\n"
    lines = [to_human(d) for d in allres[:TOP_SEND]]
    send_telegram(header + ("\n".join(lines) if lines else "(Aday bulunamadı)"))
    print("\n" + header + ("\n".join(lines) if lines else "(Aday bulunamadı)") + "\n")

    # === HTML/CSV emitter (B-clean) ===
    try:
        # s_candidates: 'pps' if exists else 'pp'
        s_candidates = pps if 'pps' in locals() else (pp if 'pp' in locals() else [])
        # fast list: prefer 'fst' if built; else 'fast_pp'
        fast_list = fst if 'fst' in locals() else (fast_pp if 'fast_pp' in locals() else [])
        emit_html_and_csv(s_candidates, fast_list, allres)
    except Exception as e:
        print("[warn] emitter error:", e)


def send_telegram(msg: str, *, parse_mode: str = None, disable_preview: bool = True) -> None:
    import os, requests, time
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or ""
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or ""
    TELEGRAM_DEBUG = bool(str(os.environ.get("TELEGRAM_DEBUG", "")))
    if not token or not chat_id:
        print("[info] Telegram env yok; mesaj atılmadı.")
        return
    # Drop legacy plain-text messages (duplicates) — HTML messages carry parse_mode
    drop_plain = str(os.environ.get("TELEGRAM_PLAIN_DISABLE", "1")).strip() == "1"
    if drop_plain and (parse_mode is None):
        low = (msg or "").lower()
        legacy_prefixes = (
            "🟢 scanner up",
            "ping-pong ok",
            "bingx grid scan sonuçları",
            "== bingx grid scan",
        )
        if any(low.startswith(p) for p in legacy_prefixes):
            if TELEGRAM_DEBUG:
                print("[tg-debug] drop plain message by TELEGRAM_PLAIN_DISABLE")
            return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    HARD_LIMIT = 4096
    SAFE = 560
    LIM = HARD_LIMIT - SAFE
    lines = msg.splitlines(keepends=True)
    parts, buf, size = [], [], 0
    for ln in lines:
        if size + len(ln) > LIM and buf:
            parts.append("".join(buf))
            buf, size = [], 0
        buf.append(ln)
        size += len(ln)
    if buf:
        parts.append("".join(buf))
    if not parts:
        parts = [msg]
    for idx, part in enumerate(parts, 1):
        try:
            payload = {
                "chat_id": chat_id,
                "text": part,
                "disable_web_page_preview": "true" if disable_preview else "false",
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode
            if TELEGRAM_DEBUG:
                preview = part.replace("\\n", " ")[:140]
                print(f"[tg-debug] send chunk {idx}/{len(parts)} | len={len(part)} | parse_mode={parse_mode} | preview='{preview}…'")
            r = requests.post(url, data=payload, timeout=20)
            try:
                j = r.json()
                if not j.get("ok", False) and TELEGRAM_DEBUG:
                    print("[warn] Telegram sendMessage error:", j)
            except Exception:
                if TELEGRAM_DEBUG:
                    print("[warn] Telegram sendMessage non-JSON:", getattr(r, "text", "")[:200])
        except Exception as e:
            print(f"[warn] Telegram exception (chunk {idx}/{len(parts)}): {e}")
        time.sleep(0.2)


def send_document(file_path: str, *, caption: str = "", parse_mode: str = None) -> None:
    import os, requests
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or ""
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or ""
    if not token or not chat_id:
        print("[info] Telegram env yok; dosya gönderilmedi.")
        return
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    try:
        with open(file_path, "rb") as fh:
            files = {"document": fh}
            data = {"chat_id": chat_id}
            if caption:
                data["caption"] = caption
            if parse_mode:
                data["parse_mode"] = parse_mode
            r = requests.post(url, data=data, files=files, timeout=30)
            try:
                j = r.json()
                if not j.get("ok", False):
                    print("[warn] sendDocument error:", j)
            except Exception:
                print("[warn] sendDocument non-JSON:", getattr(r, "text", "")[:200])
    except Exception as e:
        print("[warn] Telegram sendDocument exception:", e)

def pin_last_message(message_id: int) -> None:
    import os, requests
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or ""
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or ""
    if not token or not chat_id or not message_id:
        return
    if not str(os.environ.get("TELEGRAM_PIN_FAST", "")).strip():
        return
    url = f"https://api.telegram.org/bot{token}/pinChatMessage"
    try:
        print(f"[tg-debug] trying to pin message_id={message_id}")
        r = requests.post(url, data={"chat_id": chat_id, "message_id": message_id, "disable_notification": True}, timeout=20)
        print("[tg-debug] pin attempted")
        try:
            j = r.json()
            if not j.get("ok", False):
                print("[warn] pinChatMessage error:", j)
        except Exception:
            pass
    except Exception as e:
        print("[warn] pinChatMessage exception:", e)

def generate_grid_csv(d: dict, out_path: str) -> None:
    import csv
    try:
        low = float(d.get("grid_lower") if ("grid_lower" in d) else d.get("grid_low"))
        high = float(d.get("grid_upper") if ("grid_upper" in d) else d.get("grid_high"))
        levels = int(d.get("levels") if ("levels" in d) else d.get("grid_lines") or 0)
    except Exception as e:
        print("[warn] grid csv: invalid input:", e); return
    if levels <= 1 or high <= low:
        print("[warn] grid csv: levels/interval invalid"); return
    step = (high - low) / (levels - 1)
    rows = [("index", "price")]
    for i in range(levels):
        price = low + step * i
        rows.append((i+1, f"{price:.12f}".rstrip("0").rstrip(".")))
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        import csv as _csv
        cw = _csv.writer(f)
        cw.writerows(rows)


def _to_fmt_speed(d):
    try:
        med_val = d.get("med", None)
        med_txt = med_val if (med_val in (None, "", "NA")) else f"{int(float(med_val))}m"
    except Exception:
        med_txt = d.get("med", "-")
    return {"xph": d.get("xph"), "med": med_txt, "edgeph": d.get("edgeph")}

def _to_fmt_entry(d):
    import re as _re
    base = d.get("base")
    quote = d.get("quote")
    sym = d.get("symbol")
    if isinstance(base, str) and isinstance(quote, str) and base and quote:
        sym = f"{base}/{quote}"
    if isinstance(sym, str):
        sym = _re.sub(r":USDT$", "", sym)
        sym = _re.sub(r":USDC$", "", sym)
        sym = _re.sub(r":BUSD$", "", sym)
    return {
        "symbol": sym,
        "last": d.get("last"),
        "atr_abs": d.get("atr_abs"),
        "atr_pct": d.get("atr_pct"),
        "range_pct": d.get("range_pct"),
        "adx": d.get("adx"),
        "mid_cross": d.get("midcross") if ("midcross" in d) else d.get("mid_cross"),
        "drift_pct": d.get("drift_ratio") if ("drift_ratio" in d) else d.get("drift_pct"),
        "tags": (["PING-PONG OK"] if d.get("pingpong_ok") else d.get("why_tags", [])) + (["FAST S OK"] if d.get("fast_ok") else []),
        "grid_low": d.get("grid_lower") if ("grid_lower" in d) else d.get("grid_low"),
        "grid_high": d.get("grid_upper") if ("grid_upper" in d) else d.get("grid_high"),
        "grid_lines": d.get("levels") if ("levels" in d) else d.get("grid_lines"),
        "speed": _to_fmt_speed(d) if d.get("fast_checked") or d.get("speed") else d.get("speed", {}),
    }

def emit_html_and_csv(s_candidates, fast_candidates, allres) -> None:
    import os, requests
    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Europe/Istanbul")
    except Exception:
        tz = None

    print("[v4] HTML+CSV emitter running")

    s_behavior = _to_fmt_entry(s_candidates[0]) if s_candidates else None
    try_top_send = int(os.environ.get("TOP_SEND", "5") or "5")
    top_fmt = [_to_fmt_entry(d) for d in (allres[:try_top_send] if allres else [])]
    try_top_fast = int(os.environ.get("TOP_FAST", "3") or "3")
    _fast_max = min(3, try_top_fast)
    fast_fmt = [_to_fmt_entry(d) for d in (fast_candidates[:_fast_max] if fast_candidates else [])]

    ts = datetime.now(tz).strftime("%Y-%m-%d %H:%M") if tz else datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # FAST first
    last_mid = None
    if fast_fmt:
        chunks_fast = format_telegram_scan_message(
            scan_started_at=ts,
            s_behavior=None,
            top_candidates=[],
            fast_candidates=fast_fmt,
        )
        token = os.environ.get("TELEGRAM_BOT_TOKEN") or ""
        chat_id = os.environ.get("TELEGRAM_CHAT_ID") or ""
        if token and chat_id:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            for ch in chunks_fast:
                try:
                    r = requests.post(url, data={"chat_id": chat_id, "text": ch, "parse_mode": "HTML", "disable_web_page_preview": "true"}, timeout=20)
                    j = r.json()
                    if j.get("ok", False):
                        last_mid = j["result"]["message_id"]
                    else:
                        print("[warn] FAST send error:", j)
                except Exception as e:
                    print("[warn] FAST send exception:", e)
        else:
            for ch in chunks_fast:
                send_telegram(ch, parse_mode="HTML", disable_preview=True)

        if last_mid and str(os.environ.get("TELEGRAM_PIN_FAST", "")).strip():
            try:
                pin_last_message(last_mid)
            except Exception as e:
                print("[warn] pin exception:", e)

    # General (S + Top)
    if s_behavior or top_fmt:
        chunks = format_telegram_scan_message(
            scan_started_at=ts,
            s_behavior=s_behavior,
            top_candidates=top_fmt,
            fast_candidates=None,
        )
        for ch in chunks:
            send_telegram(ch, parse_mode="HTML", disable_preview=True)

    # CSV for S
    if s_candidates and str(os.environ.get("SEND_GRID_CSV", "1")).strip():
        try:
            src_dict = s_candidates[0]
            tmp = "/tmp/grid.csv"
            generate_grid_csv(src_dict, tmp)
            send_document(tmp, caption=f"<b>Grid CSV</b> — {s_behavior.get('symbol','?')}", parse_mode="HTML")
        except Exception as e:
            print("[warn] grid.csv send exception:", e)


# Canonical single entrypoint
def _run_emitter_guard():
    # kept for compatibility; emitter is already called in main. No-op here.
    return

if __name__ == "__main__":
    try:
        main()
    finally:
        _run_emitter_guard()
