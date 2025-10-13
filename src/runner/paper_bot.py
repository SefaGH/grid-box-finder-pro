import time, os
from src.core.exchange_ccxt import ExchangeCCXT
from src.core.risk import RiskGate, RiskLimits
from src.core.state_store import JsonState
from src.strategy.dynamic_grid import DynamicGrid, GridParams
from src.strategy.strategist import pick_mode
from src.strategy.tri_arb import TriArb

def main():
    api_key = os.environ.get('BINGX_API_KEY', '')
    api_secret = os.environ.get('BINGX_API_SECRET', '')
    if not api_key or not api_secret:
        print('WARN: BINGX_API_KEY/BINGX_API_SECRET boş. Paper akışında read-only çağrılar denenir.')

    symbol = os.environ.get('SYMBOL', 'BTC/USDT:USDT')
    ex = ExchangeCCXT(api_key, api_secret, [symbol])
    ex.load_markets()

    limits = RiskLimits(
        max_open_notional=float(os.environ.get('MAX_OPEN_NOTIONAL','1000')),
        max_symbol_exposure=float(os.environ.get('MAX_SYMBOL_EXPOSURE','500')),
        daily_max_loss=float(os.environ.get('DAILY_MAX_LOSS','200')),
        stop_pct=float(os.environ.get('STOP_PCT','0.03'))
    )
    risk = RiskGate(limits)
    state = JsonState('state.paper.json')

    dg = DynamicGrid(ex, risk, state, GridParams(
        levels=int(os.environ.get('GRID_LEVELS','16')),
        capital=float(os.environ.get('GRID_CAPITAL','200')),
        atr_k=float(os.environ.get('ATR_K','1.2')),
        retune_sec=int(os.environ.get('RETUNE_SEC','120'))
    ))

    tri = TriArb(ex, fee_rate=float(os.environ.get('FEE','0.0006')), edge_min=float(os.environ.get('TRI_EDGE_MIN','0.0015')))

    closes = [30000.0] * 50
    while True:
        t = ex.fetch_ticker(symbol)
        closes.append(t['last'])
        closes = closes[-200:]

        metrics = {'adx': 18.0, 'crosses_per_hour': 8, 'touches_per_hour': 10, 'liquidity_ok': True}
        tri_edge = 0.0
        mode = pick_mode(metrics, tri_edge)

        if mode == 'DYNAMIC_GRID':
            dg.retune_and_place(symbol, closes)
        elif mode == 'TRI_ARB':
            pass

        time.sleep(5)

if __name__ == '__main__':
    main()
