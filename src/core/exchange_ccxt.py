import os

import time
from typing import Any, Dict, List, Optional

import ccxt
from ccxt.base.errors import ExchangeError, NetworkError, RateLimitExceeded

class ExchangeCCXT:
    """Thin wrapper around ccxt for a single exchange (BingX USDT-M by default)."""
    def __init__(self, api_key: str, api_secret: str, symbol_whitelist: Optional[List[str]] = None):
        ex = ccxt.bingx({'apiKey': api_key, 'secret': api_secret})
        ex.options['defaultType'] = 'swap'  # USDT-M perpetual
        ex.enableRateLimit = True
        self.ex = ex
        self.symbol_whitelist = set(symbol_whitelist or [])

    def load_markets(self):
        return self.ex.load_markets()

    def _rl_wrap(self, fn, *args, **kwargs):
        for i in range(5):
            try:
                return fn(*args, **kwargs)
            except RateLimitExceeded:
                time.sleep(0.5 * (i + 1))
            except (NetworkError, ExchangeError):
                if i == 4:
                    raise
                time.sleep(0.5 * (i + 1))

    def fetch_order_book(self, symbol: str, limit: int = 50) -> Dict[str, Any]:
        return self._rl_wrap(self.ex.fetch_order_book, symbol, limit=limit)

    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        return self._rl_wrap(self.ex.fetch_ticker, symbol)

    def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        return self._rl_wrap(self.ex.fetch_open_orders, symbol)

    def fetch_positions(self) -> List[Dict[str, Any]]:
        if hasattr(self.ex, 'fetch_positions'):
            return self._rl_wrap(self.ex.fetch_positions)
        return []

    def create_order(self, symbol: str, side: str, type_: str, amount: float, price: Optional[float] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params = params or {}
        return self._rl_wrap(self.ex.create_order, symbol, type_, side, amount, price, params)

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> Dict[str, Any]:
        return self._rl_wrap(self.ex.cancel_order, order_id, symbol)

    def cancel_all_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        open_ = self.fetch_open_orders(symbol)
        out = []
        for o in open_:
            try:
                out.append(self.cancel_order(o['id'], o.get('symbol')))
            except Exception:
                pass
        return out
