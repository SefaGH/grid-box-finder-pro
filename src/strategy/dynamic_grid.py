from dataclasses import dataclass
from typing import List, Tuple
import time

from src.core.exchange_ccxt import ExchangeCCXT
from src.core.risk import RiskGate, RiskLimits
from src.core.state_store import JsonState
from src.core.indicators import atr, stddev

@dataclass
class GridParams:
    levels: int
    capital: float
    atr_k: float
    retune_sec: int
    adx_trend_limit: float = 25.0
    stop_pct: float = 0.03

class DynamicGrid:
    def __init__(self, ex: ExchangeCCXT, risk: RiskGate, state: JsonState, params: GridParams):
        self.ex = ex
        self.risk = risk
        self.state = state
        self.params = params
        self._last_tune = 0

    def _compute_band(self, closes: List[float]) -> Tuple[float,float]:
        sd = stddev(closes, 20)
        mid = sum(closes[-20:])/min(20,len(closes))
        lower = mid - 2*sd
        upper = mid + 2*sd
        if lower <= 0: lower = closes[-1]*0.9
        return lower, upper

    def _grid_prices(self, lower: float, upper: float, levels: int) -> List[float]:
        step = (upper - lower) / max(1, levels-1)
        return [lower + i*step for i in range(levels)]

    def retune_and_place(self, symbol: str, closes: List[float]):
        now = time.time()
        if now - self._last_tune < self.params.retune_sec:
            return
        self._last_tune = now

        lower, upper = self._compute_band(closes)
        prices = self._grid_prices(lower, upper, self.params.levels)

        notional_per = self.params.capital / max(1,len(prices))
        last = closes[-1]

        # Basit yerleştirme (örnek): last altına alım, üstüne satım
        self.ex.cancel_all_orders(symbol)
        for p in prices:
            qty = max(1e-6, notional_per / last)
            if p < last:
                self.ex.create_order(symbol, 'buy', 'limit', qty, p)
            elif p > last:
                self.ex.create_order(symbol, 'sell', 'limit', qty, p)
