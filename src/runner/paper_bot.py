import os, time, json, urllib.request
from src.core.exchange_ccxt import ExchangeCCXT
from src.core.risk import RiskGate, RiskLimits
from src.core.state_store import JsonState
from src.strategy.dynamic_grid import DynamicGrid, GridParams
from src.strategy.strategist import pick_mode
from src.strategy.tri_arb import TriArb
from src.strategy.metrics_feed import build_metrics
from src.core.guards import adx14, volatility_spike

# --- Telegram & bildirim bucket yardımcıları ---
last_notify_bucket = {"k": None}
def _adx_bucket(x: float) -> str:
    return "hi_60p" if x >= 60 else ("hi_45_60" if x >= 45 else ("hi_35_45" if x >= 35 else ("lo_28_35" if x >= 28 else "lo_<28")))

def _tg_send(msg: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {"chat_id": chat_id, "text": msg, "disable_web_page_preview": True}
        req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:
        pass


def main():
    api_key = os.environ.get("BINGX_API_KEY", "")
    api_secret = os.environ.get("BINGX_API_SECRET", "")
    if not api_key or not api_secret:
        print("WARN: BINGX_API_KEY/BINGX_API_SECRET boş. Paper akışında read-only çağrılar denenir.")

    symbol = os.environ.get("SYMBOL", "BTC/USDT:USDT")
    ex = ExchangeCCXT(api_key, api_secret, [symbol])
    ex.load_markets()

    limits = RiskLimits(
        max_open_notional=float(os.environ.get("MAX_OPEN_NOTIONAL", "1000")),
        max_symbol_exposure=float(os.environ.get("MAX_SYMBOL_EXPOSURE", "500")),
        daily_max_loss=float(os.environ.get("DAILY_MAX_LOSS", "200")),
        stop_pct=float(os.environ.get("STOP_PCT", "0.03")),
    )
    risk = RiskGate(limits)
    state = JsonState("state.paper.json")

    dg = DynamicGrid(
        ex,
        risk,
        state,
        GridParams(
            levels=int(os.environ.get("GRID_LEVELS", "16")),
            capital=float(os.environ.get("GRID_CAPITAL", "200")),
            atr_k=float(os.environ.get("ATR_K", "1.2")),
            retune_sec=int(os.environ.get("RETUNE_SEC", "120")),
        ),
    )

    tri = TriArb(
        ex,
        fee_rate=float(os.environ.get("FEE", "0.0006")),
        edge_min=float(os.environ.get("TRI_EDGE_MIN", "0.0015")),
    )

    # --- Guard konfig (tamamı env/Variables üzerinden) ---
    ADX_LIMIT_ENV = os.environ.get("ADX_LIMIT")  # tek eşik vermek istersen
    ADX_LIMIT_HI = float(os.environ.get("ADX_LIMIT_HI", ADX_LIMIT_ENV or "35"))
    ADX_LIMIT_LO = float(os.environ.get("ADX_LIMIT_LO", str(float(ADX_LIMIT_ENV) - 7 if ADX_LIMIT_ENV else 28)))
    GUARD_COOLDOWN_SEC = int(os.environ.get("GUARD_COOLDOWN_SEC", "60"))
    GUARD_CONSEC_N = int(os.environ.get("GUARD_CONSEC_N", "3"))

    # --- Süre sınırı (Run workflow input’undan gelebilir) ---
    run_seconds = int(os.environ.get("RUN_SECONDS", "0"))  # 0 = sınırsız
    run_cycles  = int(os.environ.get("RUN_CYCLES", "0"))   # 0 = sınırsız
    start_ts    = time.time()
    cycles      = 0

    # --- Guard durum değişkenleri ---
    trend_blocked = False
    last_guard_ts = 0.0
    guard_hits    = 0

    _tg_send(f"🟢 Hybrid Paper bot başladı | SYMBOL={symbol} | DRY_RUN={os.environ.get('DRY_RUN','0')} | RUN_SECONDS={os.environ.get('RUN_SECONDS','0')}")

    while True:
        # Mutlak süre kontrolü (döngü başında)
        if run_seconds and (time.time() - start_ts) >= run_seconds:
            _tg_send("🟡 Hybrid Paper bot süre doldu, kapanıyor.")
            break

        # 1) Metrikler
        metrics = build_metrics(ex, symbol)
        closes = metrics.get("closes", [])

        # 2) ADX & spike
        ohlc = ex.fetch_ohlcv(symbol, timeframe="1m", limit=120)  # [ts,o,h,l,c,v]
        ohlc4 = [(row[1], row[2], row[3], row[4]) for row in ohlc]
        adx_val = adx14(ohlc4)
        closes_full = [row[4] for row in ohlc]
        spike = volatility_spike(
            closes_full,
            win_fast=int(os.environ.get("VOL_SPIKE_FAST", "20")),
            win_slow=int(os.environ.get("VOL_SPIKE_SLOW", "120")),
            mult=float(os.environ.get("VOL_SPIKE_MULT", "2.0")),
        )

        # 3) Guard/histerezis + cooldown/debounce
        now_ts = time.time()

        if trend_blocked:
            if adx_val <= ADX_LIMIT_LO:
                trend_blocked = False
        else:
            if adx_val >= ADX_LIMIT_HI:
                trend_blocked = True

        if trend_blocked or spike:
            guard_hits += 1
        else:
            guard_hits = 0

        in_cooldown = (now_ts - last_guard_ts) < GUARD_COOLDOWN_SEC
        if guard_hits >= GUARD_CONSEC_N or in_cooldown:
            started_now = False
            if guard_hits >= GUARD_CONSEC_N:
                last_guard_ts = now_ts
                guard_hits = 0
                started_now = True

            msg = f"[GUARD] Pause: ADX={adx_val:.1f}, spike={spike}, cooldown={int(max(0, GUARD_COOLDOWN_SEC - (now_ts - last_guard_ts)))}s"
            print(msg)

            # Telegram: sadece başlarken veya ADX bucket değişince
            cur_bucket = _adx_bucket(adx_val)
            if started_now or last_notify_bucket["k"] != cur_bucket:
                _tg_send(f"⏸️ {msg}")
                last_notify_bucket["k"] = cur_bucket

            # ❗ İptal & uyku & continue — guard BLOĞU İÇİNDE
            try:
                openos = ex.fetch_open_orders(symbol)
                if openos:
                    ex.cancel_all_orders(symbol)
            except Exception:
                ex.cancel_all_orders(symbol)

            # kısa uyku
            time.sleep(10)
            continue

        # 4) Strateji seçimi ve yürütme
        metrics["adx"] = adx_val
        tri_edge = 0.0  # tri.calc_edge(...) ileride aktif edilecek
        mode = pick_mode(metrics, tri_edge)

        if mode == "DYNAMIC_GRID" and closes:
            dg.retune_and_place(symbol, closes)
        elif mode == "TRI_ARB":
            pass  # tri.try_execute(...) bağlanacak

        # Süre/iterasyon sınırı + uyku
        cycles += 1
        if run_seconds and (time.time() - start_ts) >= run_seconds:
            _tg_send("🟡 Hybrid Paper bot süre doldu, kapanıyor.")
            break
        if run_cycles and cycles >= run_cycles:
            _tg_send("🟡 Hybrid Paper bot cycle limiti doldu, kapanıyor.")
            break

        time.sleep(10)


if __name__ == "__main__":
    main()
