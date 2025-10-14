from typing import Tuple
from src.core.exchange_ccxt import ExchangeCCXT

class TriArb:
    def __init__(self, ex: ExchangeCCXT, fee_rate: float = 0.0006, edge_min: float = 0.0015):
        self.ex = ex
        self.fee = fee_rate
        self.edge_min = edge_min

    def calc_edge(self, a: str, b: str, c: str) -> float:
        ta = self.ex.fetch_ticker(a); tb = self.ex.fetch_ticker(b); tc = self.ex.fetch_ticker(c)
        gross = (ta['last'] * tb['last'] * tc['last'])
        net = gross * (1 - self.fee)**3
        return net - 1

    def try_execute(self, a: str, b: str, c: str, quote_amount: float):
        edge = self.calc_edge(a,b,c)
        if edge < self.edge_min:
            print(f"[TRI_ARB] edge={edge:.4f} < min={self.edge_min:.4f} -> pass")
            return False, edge
        print(f"[TRI_ARB][DRY_RUN] a={a}, b={b}, c={c}, edge={edge:.4f}, quote={quote_amount}")
        return True, edge
