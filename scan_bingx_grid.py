import os
import time
from typing import List, Dict, Any, Tuple
import math
import requests

import ccxt  # ccxt abstracts BingX public endpoints

ENABLE_RATE_LIMIT = True

# ---------- ENV HELPERS ----------
def env_float(name: str, default: float) -> float:
    v = os.environ.get(name, "").strip()
    if not v:
        return default
    try:
        return float(v)
    except ValueError:
        return default

def env_int(name: str, default: int) -> int:
    v = os.environ.get(name, "").strip()
    if not v:
        return default
    try:
        return int(v)
    except ValueError:
        return default

TOP_K = env_int("TOP_K", 15)
ATR_PCT_MIN = env_float("ATR_PCT_MIN", 0.003)      # 0.3%
RANGE_PCT_MIN = env_float("RANGE_PCT_MIN", 0.02)   # 2%
ADX_MAX = env_float("ADX_MAX", 18.0)               # trend zayıflığı eşiği
MID_CROSS_MIN = env_int("MID_CROSS_MIN", 12)       # orta bant geçiş sayısı
DRIFT_MAX_RATIO = env_float("DRIFT_MAX_RATIO", 0.25)# net drift üst sınırı

# ---------- BASIC METRICS ----------
def pct(x: float) -> str:
    return f"{x*100:.2f}%"

def sma(vals: List[float], period: int) -> List[float]:
    out = []
    s = 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= period:
            s -= vals[i - period]
        if i >= period - 1:
            out.append(s / period)
        else:
            out.append(float('nan'))
    return out

def atr_from_ohlc(values: List[Tuple[float,float,float,float]], period: int = 14) -> float:
    if len(values) < period + 1:
        return 0.0
    trs = []
    prev_close = values[0][3]
    for (o,h,l,c) in values[1:]:
        tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
        trs.append(tr)
        prev_close = c
    if len(trs) < period:
        return 0.0
    return sum(trs[-period:]) / period

# ---------- ADX (saf Python) ----------
def adx14(ohlc: List[Tuple[float,float,float,float]]) -> float:
    n = 14
    if len(ohlc) < n + 1:
        return 100.0  # veri azsa trend var kabul edip eleyelim
    trs = []
    pdms = []
    ndms = []
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

    def wilder_smooth(arr: List[float], period: int) -> List[float]:
        out = []
        sm = sum(arr[:period])
        out.append(sm)
        for i in range(period, len(arr)):
            sm = sm - (sm / period) + arr[i]
            out.append(sm)
        return out

    if len(trs) < n or len(pdms) < n or len(ndms) < n:
        return 100.0

    atr_ws = wilder_smooth(trs, n)
    pdi_ws = wilder_smooth(pdms, n)
    ndi_ws = wilder_smooth(ndms, n)
    ln = min(len(atr_ws), len(pdi_ws), len(ndi_ws))
    atr_ws = atr_ws[-ln:]
    pdi_ws = pdi_ws[-ln:]
    ndi_ws = ndi_ws[-ln:]

    plus_di = [ (pdi_ws[i] / atr_ws[i] * 100.0) if atr_ws[i] > 0 else 0.0 for i in range(ln) ]
    minus_di = [ (ndi_ws[i] / atr_ws[i] * 100.0) if atr_ws[i] > 0 else 0.0 for i in range(ln) ]
    dx = []
    for i in range(ln):
        pd = plus_di[i]; md = minus_di[i]
        denom = pd + md
        if denom <= 0:
            dx.append(0.0)
        else:
            dx.append(abs(pd - md) / denom * 100.0)
    if len(dx) < n:
        return 100.0
    return sum(dx[-n:]) / n

def mid_cross_count(closes: List[float], mid: List[float]) -> int:
    cnt = 0
    prev_diff = None
    for c, m in zip(closes, mid):
        if m != m:  # NaN
            continue
        diff = c - m
        if prev_diff is not None:
            if diff == 0:
                cnt += 1
            elif (diff > 0 and prev_diff < 0) or (diff < 0 and prev_diff > 0):
                cnt += 1
        prev_diff = diff
    return cnt

def suggest_grid(last: float, atr_abs: float) -> Tuple[float,float,int]:
    if last <= 0:
        return (last, last, 12)
    atr_pct = atr_abs / last if last else 0.0
    width_pct = max(0.02, min(0.06, atr_pct * 6.0))
    half = last * width_pct / 2.0
    return (last - half, last + half, 12)

def send_telegram(msg: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or ""
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or ""
    if not token or not chat_id:
        print("[info] Telegram env değişkenleri tanımlı değil; mesaj gönderilmedi.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {"chat_id": chat_id, "text": msg}
    try:
        r = requests.post(url, data=data, timeout=15)
        if r.status_code != 200:
            print(f"[warn] Telegram gönderim hatası: {r.text}")
    except Exception as e:
        print(f"[warn] Telegram gönderim istisnası: {e}")

def to_human(d: Dict[str, Any]) -> str:
    tag = " [PING-PONG OK]" if d.get("pingpong_ok") else ""
    return (
        f"{d['symbol']}: last={d['last']:.6g} | ATR={d['atr_abs']:.6g} ({pct(d['atr_pct'])}) | "
        f"range≈{pct(d['range_pct'])} | ADX≈{d.get('adx', float('nan')):.1f} | "
        f"mid-cross={d.get('midcross', 0)} | drift%≈{pct(d.get('drift_ratio', 0.0))}{tag} | "
        f"grid≈[{d['grid_lower']:.6g} … {d['grid_upper']:.6g}] × {d['levels']}"
    )

def main():
    print("== BingX Grid Scan (public via ccxt) — Ping-Pong mode ==")
    ex = ccxt.bingx({
        "enableRateLimit": ENABLE_RATE_LIMIT,
        "options": {"defaultType": "swap"},
    })
    markets = ex.load_markets()
    symbols = [s for s, m in markets.items() if m.get("contract") and m.get("quote") == "USDT"]
    if not symbols:
        raise RuntimeError("BingX USDT-M contract market listesi boş döndü.")
    # tickers (with fallback)
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
        quote_vol = t.get("quoteVolume") or 0.0
        base_vol = t.get("baseVolume") or 0.0
        try:
            if (quote_vol or 0) > 0:
                return float(quote_vol)
            return float(last) * float(base_vol)
        except Exception:
            return 0.0

    pairs = [(sym, tickers[sym]) for sym in symbols if sym in tickers]
    pairs.sort(key=lambda x: notional(x[1]), reverse=True)
    pairs = pairs[:TOP_K]

    pp_candidates = []  # ping-pong OK
    results = []
    for sym, tk in pairs:
        try:
            ohlcv = ex.fetch_ohlcv(sym, timeframe="5m", limit=200)  # ~16h
            if not ohlcv or len(ohlcv) < 60:
                print("SKIP (yetersiz OHLCV) ", sym)
                continue
            closes = [float(c) for _, o, h, l, c, v in ohlcv]
            ohlc = [(float(o), float(h), float(l), float(c)) for _, o, h, l, c, v in ohlcv]
            last = closes[-1]
            atr50 = atr_from_ohlc(ohlc, period=50)
            # range & grid
            window = closes[-180:] if len(closes) >= 180 else closes
            rng = (max(window) - min(window)) / last if last > 0 else 0.0
            lower, upper, levels = suggest_grid(last, atr50)
            # chop metrics
            adx_val = adx14(ohlc[-150:])  # son ~12.5 saat
            mid = sma(closes, 20)
            midcross = mid_cross_count(closes[-180:], mid[-180:])
            total_range = (max(window) - min(window)) if window else 0.0
            drift = abs(closes[-1] - closes[0])
            drift_ratio = (drift / total_range) if total_range > 0 else 0.0
            d = {
                "symbol": sym,
                "last": last,
                "atr_abs": atr50,
                "atr_pct": (atr50 / last) if last>0 else 0.0,
                "range_pct": rng,
                "grid_lower": lower,
                "grid_upper": upper,
                "levels": levels,
                "adx": adx_val,
                "midcross": midcross,
                "drift_ratio": drift_ratio,
            }
            base_ok = (d["atr_pct"] >= ATR_PCT_MIN and d["range_pct"] >= RANGE_PCT_MIN)
            pingpong_ok = base_ok and (adx_val <= ADX_MAX) and (midcross >= MID_CROSS_MIN) and (drift_ratio <= DRIFT_MAX_RATIO)
            d["pingpong_ok"] = pingpong_ok
            if base_ok:
                results.append(d)
                print("OK  ", to_human(d))
            else:
                print("SKIP", to_human(d))
            if pingpong_ok:
                pp_candidates.append(d)
            time.sleep(0.35)
        except ccxt.NetworkError as e:
            print("NETERR", sym, e)
            time.sleep(0.3)
        except Exception as e:
            print("ERR", sym, e)
            time.sleep(0.2)

    # Sıralama: önce pingpong_ok olanlar; sonra ATR%*range%
    results.sort(key=lambda x: (0 if x["pingpong_ok"] else 1, -(x["atr_pct"] * x["range_pct"])))
    header = "BingX Grid Scan Sonuçları (Top adaylar)\n"
    lines = [to_human(d) for d in results[:12]]
    body = header + ("\n".join(lines) if lines else "(Aday bulunamadı)")

    # Telegram mesajını iki blok halinde gönder: önce PING-PONG, sonra genel
    if pp_candidates:
        pp_sorted = sorted(pp_candidates, key=lambda x: x["atr_pct"] * x["range_pct"], reverse=True)[:8]
        pp_header = "PING-PONG OK (S davranışı teyitli)\n"
        pp_lines = [to_human(d) for d in pp_sorted]
        send_telegram(pp_header + "\n".join(pp_lines))
    send_telegram(body)

    print("\n" + body + "\n")
    if pp_candidates:
        print("\nPING-PONG OK adayları:\n" + "\n".join([to_human(d) for d in pp_candidates[:12]]) + "\n")

if __name__ == "__main__":
    main()
