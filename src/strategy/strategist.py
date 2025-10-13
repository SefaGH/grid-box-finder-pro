from typing import Literal

Mode = Literal['DYNAMIC_GRID','TRI_ARB','PAUSE']

def pick_mode(metrics: dict, tri_edge: float, adx_limit: float = 25.0,
              cross_min: float = 6.0, touch_min: float = 8.0, tri_edge_min: float = 0.0015) -> Mode:
    if tri_edge >= tri_edge_min and metrics.get('liquidity_ok', True):
        return 'TRI_ARB'
    adx = metrics.get('adx', 15.0)
    if adx < adx_limit and metrics.get('crosses_per_hour', 0) >= cross_min and metrics.get('touches_per_hour', 0) >= touch_min:
        return 'DYNAMIC_GRID'
    return 'PAUSE'
