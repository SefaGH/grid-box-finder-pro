#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BingX (USDT-M) grid order sizer
- Çekirdek: ccxt ile market filtrelerini otomatik çek (tick-size, lot-size, min notional)
- Verilen fiyat bandı (lower..upper) ve seviye sayısına göre eşit-quote dağıtılmış grid üret
- Her order için: side, price, qty, notional, TP komşu çizgi
- İsteğe bağlı CSV çıktısı

Kullanım örneği:
    python grid_sizer.py --symbol "ETHFI/USDT:USDT" --lower 1.72 --upper 1.82 \
        --levels 12 --capital 100 --reserve 0.05 --lev 3 --csv ethfi_grid.csv
"""
from __future__ import annotations
import argparse
import math
from typing import Any, Dict, Tuple, List

try:
    import ccxt  # type: ignore
except Exception as e:
    raise SystemExit("ccxt gerekli: pip install ccxt")

# ---------- utils ----------

def _to_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def extract_filters(market: Dict[str, Any]) -> Tuple[float, float, float, float]:
    """Return (tick, qty_step, min_notional, min_qty) with robust fallbacks."""
    tick = 0.0
    qty_step = 0.0
    min_notional = 0.0
    min_qty = 0.0

    # 1) precision hints
    prec = market.get("precision", {}) or {}
    p_price = prec.get("price")
    p_amount = prec.get("amount")
    if isinstance(p_price, (int, float)) and p_price > 0:
        tick = 10 ** (-int(p_price))
    if isinstance(p_amount, (int, float)) and p_amount > 0:
        qty_step = 10 ** (-int(p_amount))

    # 2) limits
    lim = market.get("limits", {}) or {}
    price_lim = lim.get("price", {}) or {}
    amount_lim = lim.get("amount", {}) or {}
    cost_lim = lim.get("cost", {}) or {}
    # Some exchanges store step in 'min' with multiples; others store real steps in 'info'
    min_qty = _to_float(amount_lim.get("min"), 0.0) or min_qty
    min_notional = _to_float(cost_lim.get("min"), 0.0) or min_notional
    if tick == 0.0:
        tick = _to_float(price_lim.get("min"), 0.0)
    if qty_step == 0.0:
        # sometimes amount min is the real step
        qty_step = _to_float(amount_lim.get("min"), 0.0) or qty_step

    # 3) raw info (exchange-specific)
    info = market.get("info", {}) or {}
    # Common field names
    for k in ("tickSize", "tick_size", "minPrice", "priceTickSize"):
        if tick == 0.0 and k in info:
            tick = _to_float(info[k], 0.0)
    for k in ("stepSize", "step_size", "minQty", "quantityStepSize"):
        if qty_step == 0.0 and k in info:
            qty_step = _to_float(info[k], 0.0)
    for k in ("minNotional", "min_notional", "minNotionalValue", "minOrderValue"):
        if min_notional == 0.0 and k in info:
            min_notional = _to_float(info[k], 0.0)

    # Fallbacks
    if tick <= 0.0:
        tick = 0.0001
    if qty_step <= 0.0:
        qty_step = 0.01
    if min_notional <= 0.0:
        min_notional = 5.0

    return (tick, qty_step, min_notional, min_qty)


def round_step(x: float, step: float, mode: str = "down") -> float:
    if step <= 0:
        return x
    n = x / step
    if mode == "down":
        n = math.floor(n + 1e-12)
    elif mode == "up":
        n = math.ceil(n - 1e-12)
    else:  # nearest
        n = round(n)
    return n * step


def build_grid(symbol: str, lower: float, upper: float, levels: int,
               capital_usdt: float, reserve: float = 0.05,
               leverage: int = 3,
               steps_out_for_sl: int = 2) -> Dict[str, Any]:
    if not (levels >= 2 and upper > lower > 0):
        raise ValueError("geçersiz grid parametreleri")

    ex = ccxt.bingx({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    markets = ex.load_markets()
    if symbol not in markets:
        # Sembol map'inde yoksa, benzerleri ara
        alts = [s for s in markets if s.split(":")[0] == symbol.split(":")[0]]
        msg = f"Sembol bulunamadı: {symbol}. Örnekler: {alts[:5]}"
        raise ValueError(msg)

    mkt = markets[symbol]
    tick, qty_step, min_notional, min_qty = extract_filters(mkt)

    step_abs = (upper - lower) / (levels - 1)
    mid = (upper + lower) / 2.0
    step_pct = step_abs / mid

    per_order_quote = capital_usdt * (1.0 - reserve) / levels

    prices = [lower + i * step_abs for i in range(levels)]

    orders: List[Dict[str, Any]] = []
    total_quote = 0.0
    extra_quote_needed = 0.0

    for i, px in enumerate(prices):
        side = "BUY" if px <= mid else "SELL"
        price = round_step(px, tick, "down")

        # Equal-quote target → quantity
        qty_f = per_order_quote / price if price > 0 else 0.0
        qty = max(round_step(qty_f, qty_step, "down"), qty_step, min_qty or 0.0)
        notional = qty * price

        # Enforce min notional by bumping qty upward
        if notional < min_notional:
            need_qty = min_notional / price
            bumped = round_step(need_qty, qty_step, "up")
            if bumped > qty:
                extra_quote_needed += (bumped - qty) * price
                qty = bumped
                notional = qty * price

        # TP komşu çizgi
        if side == "BUY":
            tp_price = prices[min(i + 1, levels - 1)]
        else:
            tp_price = prices[max(i - 1, 0)]
        tp_price = round_step(tp_price, tick, "down")

        orders.append({
            "lvl": i + 1,
            "side": side,
            "price": round(price, 8),
            "qty": round(qty, 8),
            "notional": round(notional, 2),
            "tp": round(tp_price, 8),
        })
        total_quote += notional

    sl_upper = upper + steps_out_for_sl * step_abs
    sl_lower = lower - steps_out_for_sl * step_abs

    return {
        "symbol": symbol,
        "tick": tick,
        "qty_step": qty_step,
        "min_notional": min_notional,
        "min_qty": min_qty,
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
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="BingX USDT-M grid sizer")
    ap.add_argument("--symbol", required=True, help="örn: ETHFI/USDT:USDT")
    ap.add_argument("--lower", type=float, required=True)
    ap.add_argument("--upper", type=float, required=True)
    ap.add_argument("--levels", type=int, default=12)
    ap.add_argument("--capital", type=float, default=100.0)
    ap.add_argument("--reserve", type=float, default=0.05)
    ap.add_argument("--lev", type=int, default=3)
    ap.add_argument("--sl_steps", type=int, default=2, help="grid dışı SL için step sayısı")
    ap.add_argument("--csv", type=str, default="", help="CSV çıktısı yolu (opsiyonel)")
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
    print(f"tick (price)   : {res['tick']}")
    print(f"qty_step       : {res['qty_step']}")
    print(f"min_notional   : {res['min_notional']}")
    print(f"min_qty        : {res['min_qty']}")

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
        import csv
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["lvl","side","price","qty","notional","tp"])
            w.writeheader()
            for o in res["orders"]:
                w.writerow(o)
        print(f"\nCSV yazıldı: {args.csv}")

def compute_grid_inline(symbol: str, lower: float, upper: float, levels: int,
                        capital: float, reserve: float = 0.05, lev: int = 1,
                        exchange=None):
    """
    grid_sizer.py'nin borsa kuralına uygun (tick/lot/minNotional) grid planını
    programatik oluşturur. Dönüş: [{'side','price','qty','notional'}, ...]
    """
    import ccxt, math
    ex = exchange or ccxt.bingx()
    ex.options['defaultType'] = 'swap'
    markets = ex.load_markets()
    m = markets[symbol]
    tick_prec = m['precision']['price']
    amt_prec  = m['precision']['amount']
    min_notional = (m.get('limits', {}).get('cost', {}) or {}).get('min', 0.0) or 0.0

    step = (upper - lower) / max(1, levels - 1)
    prices = [lower + i*step for i in range(levels)]

    # eşit-quote
    alloc = capital * (1 - reserve)
    per_n = alloc / max(1, levels)

    last = ex.fetch_ticker(symbol)['last']
    out = []
    for p in prices:
        side = 'buy' if p < last else ('sell' if p > last else None)
        if not side:
            continue
        qty = max(10**-8, per_n / p)

        # precision round
        def rprice(x):
            return round(x, tick_prec) if isinstance(tick_prec, int) else x
        def rqty(x):
            return round(x, amt_prec) if isinstance(amt_prec, int) else x

        rp = rprice(p)
        rq = rqty(qty)
        notional = rp * rq
        if min_notional and notional < min_notional:
            continue
        out.append({'side': side, 'price': rp, 'qty': rq, 'notional': notional})
    return out



if __name__ == "__main__":
    main()
