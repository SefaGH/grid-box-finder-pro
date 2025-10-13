from dataclasses import dataclass
from typing import Optional

@dataclass
class RiskLimits:
    max_open_notional: float = 1000.0
    max_symbol_exposure: float = 500.0
    daily_max_loss: float = 200.0
    stop_pct: float = 0.03  # 3%

class RiskGate:
    def __init__(self, limits: RiskLimits):
        self.limits = limits
        self.daily_realized_pnl = 0.0
        self.symbol_exposure = {}

    def check_order(self, symbol: str, notional: float) -> bool:
        if self.symbol_exposure.get(symbol, 0.0) + notional > self.limits.max_symbol_exposure:
            return False
        total = sum(self.symbol_exposure.values()) + notional
        if total > self.limits.max_open_notional:
            return False
        return True

    def register_order(self, symbol: str, notional: float):
        self.symbol_exposure[symbol] = self.symbol_exposure.get(symbol, 0.0) + notional

    def register_fill(self, symbol: str, notional: float, realized_pnl: float = 0.0):
        self.symbol_exposure[symbol] = max(0.0, self.symbol_exposure.get(symbol, 0.0) - notional)
        self.daily_realized_pnl += realized_pnl

    def breach(self) -> Optional[str]:
        if self.daily_realized_pnl <= -abs(self.limits.daily_max_loss):
            return "DAILY_LOSS_LIMIT"
        return None
