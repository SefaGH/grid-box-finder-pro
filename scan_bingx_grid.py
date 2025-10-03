import os
import time
from typing import List, Dict, Any, Tuple
import math
import requests

import ccxt  # ccxt abstracts BingX public endpoints

ENABLE_RATE_LIMIT = True

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
ATR_PCT_MIN = env_float("ATR_PCT_MIN", 0.003)   # 0.3%
RANGE_PCT_MIN = env_float("RANGE_PCT_MIN", 0.02) # 2%

def pct(x: float) -> str:
    return f"{x*100:.2f}%"

def atr(values: List[Tuple[float,float,float,float]], period: int = 14) -> float:
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
    return (
        f"{d['symbol']}: last={d['last']:.6g} | ATR={d['atr_abs']:.6g} ({pct(d['atr_pct'])}) | "
        f"range≈{pct(d['range_pct'])} | grid≈[{d['grid_lower']:.6g} … {d['grid_upper']:.6g}] × {d['levels']}"
    )

def safe_fetch_tickers(ex, symbols: List[str]) -> Dict[str, Any]:
    """
    Bazı borsalar symbol listesi ile fetch_tickers desteklemez. Bu nedenle
    önce liste ile dener; NotSupported dönerse tam seti çekip filtreler.
    """
    try:
        return ex.fetch_tickers(symbols)
    except Exception as e:
        # NotSupported veya parametre reddi: fallback to all
        print("[info] fetch_tickers(symbols) desteklenmedi, tüm tickers çekiliyor…", e)
        all_tickers = ex.fetch_tickers()
        return {s: all_tickers[s] for s in symbols if s in all_tickers}

def main():
    print("== BingX Grid Scan (public via ccxt) ==")
    ex = ccxt.bingx({
        "enableRateLimit": ENABLE_RATE_LIMIT,
        "options": {"defaultType": "swap"},
    })
    markets = ex.load_markets()
    # Sadece USDT-quoted, contract=True semboller
    symbols = [s for s, m in markets.items() if m.get("contract") and m.get("quote") == "USDT"]
    if not symbols:
        raise RuntimeError("BingX USDT-M contract market listesi boş döndü.")
    tickers = safe_fetch_tickers(ex, symbols)

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

    # Top-K seçimi
    pairs = [(sym, tickers[sym]) for sym in symbols if sym in tickers]
    pairs.sort(key=lambda x: notional(x[1]), reverse=True)
    pairs = pairs[:TOP_K]

    results = []
    for sym, tk in pairs:
        try:
            # 5m OHLCV: [ ts, open, high, low, close, volume ]
            ohlcv = ex.fetch_ohlcv(sym, timeframe="5m", limit=200)
            if not ohlcv or len(ohlcv) < 60:
                print("SKIP (yetersiz OHLCV) ", sym)
                continue
            ohlc = [(float(o), float(h), float(l), float(c)) for _, o, h, l, c, v in ohlcv]
            closes = [float(c) for _, o, h, l, c, v in ohlcv]
            last = closes[-1]
            atr50 = atr(ohlc, period=50)
            window = closes[-180:] if len(closes) >= 180 else closes
            rng = (max(window) - min(window)) / last if last > 0 else 0.0
            lower, upper, levels = suggest_grid(last, atr50)
            d = {
                "symbol": sym,
                "last": last,
                "atr_abs": atr50,
                "atr_pct": (atr50 / last) if last>0 else 0.0,
                "range_pct": rng,
                "grid_lower": lower,
                "grid_upper": upper,
                "levels": levels,
            }
            # Aday filtresi
            if d["atr_pct"] >= ATR_PCT_MIN and d["range_pct"] >= RANGE_PCT_MIN:
                results.append(d)
                print("OK  ", to_human(d))
            else:
                print("SKIP", to_human(d))
            time.sleep(0.4)  # rate-limit’e saygı
        except ccxt.NetworkError as e:
            print("NETERR", sym, e)
            time.sleep(0.3)
        except Exception as e:
            print("ERR", sym, e)
            time.sleep(0.2)

    results.sort(key=lambda x: x["atr_pct"] * x["range_pct"], reverse=True)
    header = "BingX Grid Scan Sonuçları (Top adaylar)\n"
    lines = [to_human(d) for d in results[:8]]
    body = header + ("\n".join(lines) if lines else "(Aday bulunamadı)")
    print("\n" + body + "\n")
    send_telegram(body)

if __name__ == "__main__":
    main()
