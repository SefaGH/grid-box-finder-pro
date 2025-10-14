from dataclasses import dataclass
from typing import List, Tuple, Optional
import time, os

from src.core.exchange_ccxt import ExchangeCCXT
from src.core.risk import RiskGate
from src.core.state_store import JsonState
from src.core.indicators import stddev
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
        self._last_tune: float = 0.0
        self._last_band: Optional[Tuple[float, float]] = None
        # küçük bant kaymalarında re-place etmemek için eşik (örn. %0.1)
        self._min_band_shift = float(os.environ.get("MIN_BAND_SHIFT_PCT", "0.001"))

    def _compute_band(self, closes: List[float]) -> Tuple[float, float]:
        """
        Basit band: son 20 close için mid ± 2*std.
        (İleride kendi scanner'ındaki bant mantığıyla değiştirilebilir.)
        """
        n = min(20, len(closes))
        if n <= 1:
            last = closes[-1]
            return last * 0.99, last * 1.01
        window = closes[-n:]
        mid = sum(window) / n
        sd = stddev(closes, n)
        lower = mid - 2 * sd
        upper = mid + 2 * sd
        # negatif/boş durumları koru
        last = closes[-1]
        if lower <= 0 or not (lower < upper):
            lower, upper = last * 0.99, last * 1.01
        return lower, upper

    def retune_and_place(self, symbol: str, closes: List[float]):
        """Parametrelerdeki retune periyoduna göre grid'i yeniden kurar (DRY_RUN ise sadece log)."""
        now = time.time()
        if now - self._last_tune < self.params.retune_sec:
            return
        self._last_tune = now

        # 1) bant hesapla
        lower, upper = self._compute_band(closes)

        # 2) küçük kaymalarda re-place yapma (churn azaltma)
        if self._last_band:
            l0, u0 = self._last_band
            base = max(1e-9, (u0 - l0))
            shift = (abs(lower - l0) + abs(upper - u0)) / base
            if shift < self._min_band_shift:
                # çok küçük değişim -> grid'i aynı bırak
                return
        self._last_band = (lower, upper)

        # 3) grid_sizer ile borsa kuralına uygun grid planı üret
        plan = compute_grid_inline(
            symbol=symbol,
            lower=lower,
            upper=upper,
            levels=self.params.levels,
            capital=self.params.capital,
            reserve=0.05,
            lev=1,
            exchange=self.ex.ex,   # mevcut ccxt instance'ı
        )

        if not plan:
            print("[GRID] plan boş (min_notional/precision nedeniyle filtrelenmiş olabilir).")
            return

        # 4) risk kontrolü
        total_plan = sum(x["notional"] for x in plan)
        if not self.risk.check_order(symbol, total_plan):
            print("[RISK] Plan toplam notional limitini aşıyor, grid yerleştirilmedi.")
            return

        # 5) önce eskileri iptal et, sonra yerleştir
        self.ex.cancel_all_orders(symbol)
        for line in plan:
            self.ex.create_order(symbol, line["side"], "limit", line["qty"], line["price"])
