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
    def __init__(...):
        ...
        self._last_tune = 0
        self._last_band = None
        self._min_band_shift = float(os.environ.get('MIN_BAND_SHIFT_PCT', '0.001'))

    def retune_and_place(self, symbol: str, closes: List[float]):
        ...
        lower, upper = self._compute_band(closes)

        # küçük kaymalarda re-place yapma
        if self._last_band:
            l0, u0 = self._last_band
            base = max(1e-9, (u0 - l0))
            shift = (abs(lower - l0) + abs(upper - u0)) / base
            if shift < self._min_band_shift:
                return
        self._last_band = (lower, upper)

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

        total_plan = sum(x['notional'] for x in plan) if plan else 0.0
        if not self.risk.check_order(symbol, total_plan):
            print("[RISK] Plan toplam notional limitini aşıyor.")
            return

        self.ex.cancel_all_orders(symbol)
        for line in plan:
            self.ex.create_order(symbol, line['side'], 'limit', line['qty'], line['price'])
