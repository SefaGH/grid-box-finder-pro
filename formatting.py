# formatting.py
# Rich Telegram message formatting for BingX Grid Scan
# No pin logic, no file/CSV emission. Returns a list[str] (each is a chunk).

from typing import List, Dict, Any, Optional
import html

# === number formatting helpers ===

def _fmt_pct(x) -> str:
    try:
        return f"{float(x)*100:.2f}%"
    except Exception:
        return "-"

def _fmt_float(x, digits=6) -> str:
    try:
        x = float(x)
        # fewer digits for big numbers
        if abs(x) >= 1000:
            return f"{x:,.2f}".replace(",", "_")  # guard against locale
        if abs(x) >= 1:
            return f"{x:.4f}"
        # small numbers: keep more precision
        return f"{x:.{digits}f}"
    except Exception:
        return "-"

def _fmt_price(x) -> str:
    # Price-friendly formatting
    try:
        x = float(x)
        if x == 0:
            return "0"
        if x >= 1000:
            return f"{x:,.2f}".replace(",", "_")
        if x >= 1:
            return f"{x:.4f}"
        # for tiny alts
        s = f"{x:.10f}".rstrip("0").rstrip(".")
        # ensure at least 6 decimals shown if tiny
        parts = s.split(".")
        if len(parts) == 2 and len(parts[1]) < 6:
            return f"{x:.6f}".rstrip("0").rstrip(".")
        return s
    except Exception:
        return "-"

def _fmt_speed(speed: Dict[str, Any]) -> str:
    if not isinstance(speed, dict) or not speed:
        return "xph=NA | med=NA | edgeph=NA"
    xph = speed.get("xph", "NA")
    med = speed.get("med", "NA")
    edge = speed.get("edgeph", "NA")
    return f"xph={xph} | med={med} | edgeph={edge}"

def _esc(s: Any) -> str:
    try:
        return html.escape(str(s), quote=False)
    except Exception:
        return str(s)

# === block renderers ===

def format_s_behavior_block(entry: Optional[Dict[str, Any]]) -> Optional[str]:
    """Return the '📊 S Davranışı (Ping-Pong Teyitli)' section as HTML-capable text."""
    if not entry:
        return None
    symbol = entry.get("symbol", "-")
    last   = _fmt_price(entry.get("last"))
    atr_a  = _fmt_price(entry.get("atr_abs"))
    atr_p  = _fmt_pct(entry.get("atr_pct"))
    rng    = _fmt_pct(entry.get("range_pct"))
    adx    = _fmt_float(entry.get("adx"), 2)
    mid    = entry.get("mid_cross") or entry.get("midcross") or "-"
    driftp = _fmt_pct(entry.get("drift_pct") if "drift_pct" in entry else entry.get("drift_ratio"))
    glow   = _fmt_price(entry.get("grid_low"))
    ghigh  = _fmt_price(entry.get("grid_high"))
    glines = entry.get("grid_lines", 12)
    spd    = _fmt_speed(entry.get("speed", {}))

    lines = [
        "<b>📊 S Davranışı (Ping-Pong Teyitli)</b>",
        f"🔸 Coin: {_esc(symbol)}",
        f"🔹 Fiyat: {last}",
        f"🔹 ATR: {atr_a} ({atr_p})",
        f"🔹 Range: ≈{rng}",
        f"🔹 ADX: ≈{adx} | Mid-Cross: {_esc(mid)}",
        f"🔹 Drift: {driftp}",
        f"📈 Grid Aralığı: [{glow} – {ghigh}] × {glines}",
        f"⚡ Hız: {spd}",
    ]
    return "\n".join(lines)

def _render_candidate_item(idx: int, d: Dict[str, Any]) -> str:
    symbol = d.get("symbol","-")
    last   = _fmt_price(d.get("last"))
    atr_a  = _fmt_price(d.get("atr_abs"))
    atr_p  = _fmt_pct(d.get("atr_pct"))
    rng    = _fmt_pct(d.get("range_pct"))
    adx    = _fmt_float(d.get("adx"), 2)
    mid    = d.get("mid_cross") or d.get("midcross") or "-"
    driftp = _fmt_pct(d.get("drift_pct") if "drift_pct" in d else d.get("drift_ratio"))
    tags   = d.get("tags", [])
    tagtxt = (" [" + "][".join(tags) + "]") if tags else ""
    glow   = _fmt_price(d.get("grid_low"))
    ghigh  = _fmt_price(d.get("grid_high"))
    glines = d.get("grid_lines", 12)

    lines = [
        f"{idx}️⃣ {_esc(symbol)}",
        f" • Fiyat: {last}",
        f" • ATR: {atr_a} ({atr_p})",
        f" • Range: ≈{rng}",
        f" • ADX: ≈{adx} | Mid-Cross: {_esc(mid)}",
        f" • Drift: {driftp}",
        (f" • Tags: {tagtxt[1:-1]}" if tags else None),
        f" • Grid: [{glow} – {ghigh}] × {glines}",
    ]
    return "\n".join([ln for ln in lines if ln])

def format_top_candidates_block(items: List[Dict[str, Any]]) -> Optional[str]:
    if not items:
        return None
    out = ["<b>📋 BingX Grid Scan — En İyi Adaylar</b>"]
    for i, d in enumerate(items, 1):
        out.append(_render_candidate_item(i, d))
        out.append("—" * 33)
    if out and out[-1].startswith("—"):
        out.pop()
    return "\n".join(out)

def format_fast_candidates_block(items: List[Dict[str, Any]]) -> Optional[str]:
    if not items:
        return None
    out = ["<b>⚡ FAST S — Hızlı S Davranışları</b>"]
    for i, d in enumerate(items, 1):
        # reuse candidate renderer but add speed to the bottom if present
        blk = _render_candidate_item(i, d)
        spd = _fmt_speed(d.get("speed", {})) if d.get("speed") else None
        if spd:
            blk += f"\n   ⚡ {spd}"
        out.append(blk)
        out.append("—" * 33)
    if out and out[-1].startswith("—"):
        out.pop()
    return "\n".join(out)

# === final composer ===

def _split_chunks(text: str, max_len: int = 3500) -> List[str]:
    """Split into safe chunks for Telegram (we still split again in send_telegram but this keeps blocks tidy)."""
    if not text or len(text) <= max_len:
        return [text] if text else []
    parts, buf, size = [], [], 0
    for ln in text.splitlines(keepends=True):
        if size + len(ln) > max_len and buf:
            parts.append("".join(buf))
            buf, size = [], 0
        buf.append(ln)
        size += len(ln)
    if buf:
        parts.append("".join(buf))
    return parts

def format_telegram_scan_message(*, scan_started_at: str, s_behavior: Optional[Dict[str, Any]] = None,
                                 top_candidates: Optional[List[Dict[str, Any]]] = None,
                                 fast_candidates: Optional[List[Dict[str, Any]]] = None) -> List[str]:
    """
    Returns a list of message chunks (HTML-capable). No pin, no files.
    """
    header_lines = [
        "<b>🟢 Scanner Up — Starting Scan</b>",
        _esc(scan_started_at),
        ""
    ]
    blocks = []
    sb = format_s_behavior_block(s_behavior) if s_behavior else None
    if sb:
        blocks.append(sb)
        blocks.append("")
    topb = format_top_candidates_block(top_candidates or [])
    if topb:
        blocks.append(topb)
        blocks.append("")
    fastb = format_fast_candidates_block(fast_candidates or [])
    if fastb:
        blocks.append(fastb)
    text = "\n".join(header_lines + blocks).strip()
    return _split_chunks(text, max_len=3500)
