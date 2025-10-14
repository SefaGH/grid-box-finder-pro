#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BingX (USDT-M) grid order sizer
- ccxt'den market filtrelerini (tick/step/minNotional/minQty) okur
- Verilen [lower..upper] bandında, eşit-quote dağıtımıyla grid üretir
- CLI (build_grid) + programatik kullanım (compute_grid_inline)

Kullanım (CLI):
  python grid_sizer.py --symbol "BTC/USDT:USDT" --lower 114000 --upper 116000 \
      --levels 12 --capital 200 --reserve 0.05 --lev 3 --csv grid.csv
"""
from __future__ import annotations
import argparse
import csv
import math
from typing import Any, Dict, Tuple, List

try:
    import ccxt  # type: ignore
except Exception:
    raise SystemExit("ccxt gerekli: pip install ccxt")


# ---------- utils ----------

def _to_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def round_step(x: float, step: float, mode: str = "down") -> float:
    """
    Borsa adımına göre yuvarla.
    - mode='down': tabana yuvarla (güvenli)
    - mode='up'  : tavana yuvarla (minNotional için gerektiğinde)
    """
    if step is None or step <= 0:
        return x
    n = x / step
    if mode == "down":
        n = math.floor(n + 1e-12)
    elif mode == "up":
        n = math.ceil(n - 1e-12)
    else:  # nearest
        n = round(n)
    return n * step


def extract_filters(market: Dict[str, Any]) -> Tuple[float, float, float, float, float]:
    """
    ccxt market objesinden şunları döndürür:
      (price_step, qty_step, min_notional, min_qty, min_price)

    Öncelik:
      1) info.filters (Binance/BingX stili)
      2) limits
      3) precision (fallback olarak basamak → step)
    """
    price_step = 0.0
    qty_step = 0.0
    min_notional = 0.0
    min_qty = 0.0
    min_price = 0.0

    # (1) info.filters
    info = market.get("info") or {}
    filters = info.get("filters") or []
    for f in filters:
        ftype = (f.get("filterType") or f.get("filter_type") or "").upper()
        if ftype in ("PRICE_FILTER", "PRICE_FILTERS"):
            ts = f.get("tickSize") or f.get("tick_size") or f.get("tick")
            mp = f.get("minPrice") or f.get("min_price")
            if ts is not None:
                price_step = _to_float(ts, 0.0)
            if mp is not None:
                min_price = _to_float(mp, 0.0)
        elif ftype in ("LOT_SIZE", "LOT_SIZE_FILTER", "MARKET_LOT_SIZE"):
            ss = f.get("stepSize") or f.get("step_size") or f.get("lotStep") or f.get("step")
            mq = f.get("minQty") or f.get("min_qty")
            if ss is not None:
                qty_step = _to_float(ss, 0.0)
            if mq is not None:
                min_qty = _to_float(mq, 0.0)
        elif ftype in ("MIN_NOTIONAL", "NOTIONAL", "NOTIONAL_FILTER"):
            mn = f.get("minNotional") or f.get("min_notional") or f.get("minNotionalValue")
            if mn is not None:
                min_notional = max(min_notional, _to_float(mn, 0.0))

    # (2) limits
    limits = market.get("limits") or {}
    cost_min = (limits.get("cost") or {}).get("min")
    amt_min = (limits.get("amount") or {}).get("min")
    price_min = (limits.get("price") or {}).get("min")
    if cost_min is not None:
        min_notional = max(min_notional, _to_float(cost_min, 0.0))
    if amt_min is not None:
        min_qty = max(min_qty, _to_float(amt_min, 0.0))
    if price_min is not None and not min_price:
        min_price = _to_float(price_min, 0.0)

    # (3) precision → step fallback
    prec = market.get("precision") or {}
    p_prec = prec.get("price")
    a_prec = prec.get("amount")
    if price_step <= 0 and isinstance(p_prec, int) and p_prec >= 0:
        price_step = 10.0 ** (-p_prec) if p_prec > 0 else 0.0
    if qty_step <= 0 and isinstance(a_prec, int) and a_prec >= 0:
        qty_step = 10.0 ** (-a_prec) if a_prec > 0 else 0.0

    # Son güvenli fallbacks (makul küçük adımlar ve minNotional)
    if price_step <= 0:
        price_step = 0.0001
    if qty_step <= 0:
        qty_step = 0.0001
    if min_notional <= 0:
        min_notional = 5.0

    return price_step, qty_step, min_notional, min_qty, min_price


# ---------- çekirdek mantık ----------

def _equal_quote_qty(price: float, per_quote: float) -> float:
    return per_quote / max(price, 1e-12)


def build_grid(symbol: str, lower: float, upper: float, levels: int,
               capital_usdt: float, reserve: float = 0.05,
               leverage: int = 3,
               steps_out_for_sl: int = 2) -> Dict[str, Any]:
    """
    CLI için: borsa filtrelerini ccxt ile çeker ve grid planı üretir.
    """
    if not (levels >= 2 and upper > lower > 0):
        raise ValueError("geçersiz grid parametreleri")

    ex = ccxt.bingx({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    markets = ex.load_markets()
    if symbol not in markets:
        alts = [s for s in markets if s.split(":")[0] == symbol.split(":")[0]]
        raise ValueError(f"Sembol bulunamadı: {symbol}. Örnekler: {alts[:5]}")

    mkt = markets[symbol]
    price_step, qty_step, min_notional, min_qty, min_price = extract_filters(mkt)

    step_abs = (upper - lower) / (levels - 1)
    mid = (upper + lower) / 2.0
    step_pct = step_abs / mid

    per_order_quote = capital_usdt * (1.0 - reserve) / levels
    prices = [lower + i * step_abs for i in range(levels)]

    orders: List[Dict[str, Any]] = []
    total_quote = 0.0
    extra_quote_needed = 0.0

    last = ex.fetch_ticker(symbol)['last']

    for i, raw_p in enumerate(prices):
        side = "BUY" if raw_p <= mid else "SELL"

        # fiyatı adım + minPrice'a göre düzelt
        p = round_step(raw_p, price_step, "down")
        if min_price:
            p = max(p, min_price)

        # eşit-quote → miktar
        qty_f = _equal_quote_qty(p, per_order_quote)
        qty = round_step(qty_f, qty_step, "down")
        if min_qty:
            qty = max(qty, min_qty)

        notional = p * qty

        # minNotional'i sağla (gerekirse yukarı yuvarla)
        if notional < min_notional:
            need_qty = min_notional / max(p, 1e-12)
            bumped = round_step(need_qty, qty_step, "up")
            if bumped > qty:
                extra_quote_needed += (bumped - qty) * p
                qty = bumped
                notional = qty * p

        # TP: komşu çizgi
        tp_raw = prices[min(i + 1, levels - 1)] if side == "BUY" \
                 else prices[max(i - 1, 0)]
        tp = round_step(tp_raw, price_step, "down")

        orders.append({
            "lvl": i + 1,
            "side": side,
            "price": float(p),
            "qty": float(qty),
            "notional": round(notional, 2),
            "tp": float(tp),
        })
        total_quote += notional

    sl_upper = upper + steps_out_for_sl * step_abs
    sl_lower = lower - steps_out_for_sl * step_abs

    return {
        "symbol": symbol,
        "price_step": price_step,
        "qty_step": qty_step,
        "min_notional": min_notional,
        "min_qty": min_qty,
        "min_price": min_price,
        "lower": lower,
        "upper": upper,
        "levels": levels,
        "step_abs": step_abs,
        "step_pct": step_pct,
        "mid": mid,
        "per_order_quote": per_order_quote,
        "capital": capital_usdt,
        "reserve": reserve,
        "leverage": leverage,
        "orders": orders,
        "total_quote": round(total_quote, 2),
        "extra_quote_needed": round(extra_quote_needed, 2),
        "sl_upper": sl_upper,
        "sl_lower": sl_lower,
        "last": float(last),
    }


def compute_grid_inline(symbol: str, lower: float, upper: float, levels: int,
                        capital: float, reserve: float = 0.05, lev: int = 1,
                        exchange=None) -> List[Dict[str, float]]:
    """
    Programatik kullanım: dynamic_grid, runner vb. yerlerden çağrılır.
    - exchange: varsa mevcut ccxt instance'ını ver; yoksa yeni açar.
    Dönüş: [{'side','price','qty','notional'}, ...]
    """
    ex = exchange or ccxt.bingx({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    markets = ex.load_markets()
    m = markets[symbol]

    price_step, qty_step, min_notional, min_qty, min_price = extract_filters(m)

    # eşit-quote
    alloc = capital * (1.0 - reserve)
    per_n = alloc / max(1, levels)

    step_abs = (upper - lower) / max(1, levels - 1)
    raw_prices = [lower + i * step_abs for i in range(levels)]

    last = ex.fetch_ticker(symbol)['last']
    out: List[Dict[str, float]] = []

    for rp in raw_prices:
        side = 'buy' if rp < last else ('sell' if rp > last else None)
        if not side:
            continue

        p = round_step(rp, price_step, "down")
        if min_price:
            p = max(p, min_price)

        qty = _equal_quote_qty(p, per_n)
        qty = round_step(qty, qty_step, "down")
        if min_qty:
            qty = max(qty, min_qty)

        notional = p * qty
        if min_notional and notional < min_notional:
            need_qty = min_notional / max(p, 1e-12)
            bumped = round_step(need_qty, qty_step, "up")
            if bumped <= 0:
                continue
            qty = bumped
            notional = p * qty

        if qty <= 0:
            continue

        out.append({'side': side, 'price': float(p), 'qty': float(qty), 'notional': float(notional)})

    return out


# ---------- CLI ----------

def main() -> None:
    ap = argparse.ArgumentParser(description="BingX USDT-M grid sizer")
    ap.add_argument("--symbol", required=True, help="örn: BTC/USDT:USDT")
    ap.add_argument("--lower", type=float, required=True)
    ap.add_argument("--upper", type=float, required=True)
    ap.add_argument("--levels", type=int, default=12)
    ap.add_argument("--capital", type=float, default=100.0)
    ap.add_argument("--reserve", type=float, default=0.05)
    ap.add_argument("--lev", type=int, default=3)
    ap.add_argument("--sl_steps", type=int, default=2, help="grid dışı SL için step sayısı")
    ap.add_argument("--csv", type=str, default="", help="CSV çıktısı (opsiyonel)")
    args = ap.parse_args()

    res = build_grid(
        symbol=args.symbol,
        lower=args.lower,
        upper=args.upper,
        levels=args.levels,
        capital_usdt=args.capital,
        reserve=args.reserve,
        leverage=args.lev,
        steps_out_for_sl=args.sl_steps,
    )

    print("\n=== MARKET FILTERS ===")
    print(f"symbol         : {res['symbol']}")
    print(f"price_step     : {res['price_step']}")
    print(f"qty_step       : {res['qty_step']}")
    print(f"min_notional   : {res['min_notional']}")
    print(f"min_qty        : {res['min_qty']}")
    print(f"min_price      : {res['min_price']}")

    print("\n=== GRID SUMMARY ===")
    print(f"lower..upper   : {res['lower']} .. {res['upper']}")
    print(f"levels         : {res['levels']}")
    print(f"step_abs       : {res['step_abs']:.6f}")
    print(f"step_pct       : {res['step_pct']*100:.3f}%")
    print(f"mid            : {res['mid']:.8f}")
    print(f"per_order_quote: ${res['per_order_quote']:.2f}")
    print(f"capital_used   : ~${res['total_quote']:.2f} (reserve≈{int(res['reserve']*100)}%)")
    if res['extra_quote_needed'] > 0:
        print(f"note           : minNotional uyumu için +${res['extra_quote_needed']:.2f} fazla notional gerekebilir.")
    print(f"SL upper/lower : {res['sl_upper']:.6f} / {res['sl_lower']:.6f}")

    print("\n=== ORDERS ===")
    print("lvl,side,price,qty,notional,tp")
    for o in res["orders"]:
        print(f"{o['lvl']},{o['side']},{o['price']},{o['qty']},{o['notional']},{o['tp']}")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["lvl","side","price","qty","notional","tp"])
            w.writeheader()
            for o in res["orders"]:
                w.writerow(o)
        print(f"\nCSV yazıldı: {args.csv}")


if __name__ == "__main__":
    main()
