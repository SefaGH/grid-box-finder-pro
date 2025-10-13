from dataclasses import dataclass
from typing import List, Tuple
import time

from src.core.exchange_ccxt import ExchangeCCXT
from src.core.risk import RiskGate, RiskLimits
from src.core.state_store import JsonState
from src.core.indicators import atr, stddev
from grid_sizer import compute_grid_inline

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

  # grid_sizer ile borsa kurallı grid üret
        plan = compute_grid_inline(
            symbol=symbol,
            lower=lower,
            upper=upper,
            levels=self.params.levels,
            capital=self.params.capital,
            reserve=0.05,
            lev=1,
            exchange=self.ex.ex
        )

        # risk kontrolü (toplam notional)
        total_plan = sum(x['notional'] for x in plan) if plan else 0.0
        if not self.risk.check_order(symbol, total_plan):
            return

        # önce eskileri iptal et
        self.ex.cancel_all_orders(symbol)

        # emirleri yerleştir
        for line in plan:
            self.ex.create_order(symbol, line['side'], 'limit', line['qty'], line['price'])
