
from typing import Dict, Any, List

def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

def _badge(text: str) -> str:
    return f'<code>{_esc(text)}</code>'

def _row(label: str, value: str) -> str:
    return f'<b>{_esc(label)}</b> {_esc(value)}'

def _fmt_speed(sp: Dict[str, Any]) -> str:
    if not sp:
        return ""
    xph = sp.get("xph", "-")
    med = sp.get("med", "-")
    edge = sp.get("edgeph", "-")
    return f' | speed xph={_esc(xph)}, med={_esc(med)}, edge={_esc(edge)}'

def _fmt_entry(d: Dict[str, Any]) -> str:
    sym = d.get("symbol","-")
    last = d.get("last","-")
    atr_abs = d.get("atr_abs","-")
    atr_pct = d.get("atr_pct","-")
    rng = d.get("range_pct","-")
    adx = d.get("adx","-")
    mid = d.get("mid_cross","-")
    drift = d.get("drift_pct","-")
    low = d.get("grid_low","-")
    high = d.get("grid_high","-")
    lines = d.get("grid_lines","-")
    tags = d.get("tags", [])
    tag_html = " ".join([_badge(t) for t in tags]) if tags else ""
    sp = d.get("speed", {})
    return (
        f'{_esc(sym)}: last={last:.6g} | ATR={atr_abs:.6g} ({atr_pct*100:.2f}%) | '
        f'range≈{rng*100:.2f}% | ADX≈{adx:.1f} | mid-cross={mid} | drift%≈{drift*100:.2f}% '
        f'{tag_html} | grid≈[{low:.6g} … {high:.6g}] × {lines}{_fmt_speed(sp)}'
    )

def format_telegram_scan_message(*, scan_started_at: str, s_behavior: Dict[str,Any]=None,
                                 top_candidates: List[Dict[str,Any]] = None,
                                 fast_candidates: List[Dict[str,Any]] = None) -> List[str]:
    """Return list of HTML strings (each chunk will be sent separately)."""
    chunks: List[str] = []
    # Header / health
    chunks.append(_esc(f"🟢 Scanner Up — Starting Scan\n{scan_started_at}"))

    if s_behavior:
        chunks.append("<b>📊 S Davranışı (Ping-Pong Teyitli)</b>\n" + _fmt_entry(s_behavior))

    if fast_candidates:
        body = ["<b>⚡ FAST S — wide & quick</b>"]
        for d in fast_candidates:
            body.append(_fmt_entry(d))
        chunks.append("\n".join(body))

    if top_candidates:
        body = ["<b>📋 BingX Grid Scan — En İyi Adaylar</b>"]
        for d in top_candidates:
            body.append(_fmt_entry(d))
        chunks.append("\n".join(body))

    return chunks
