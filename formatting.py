from typing import List, Dict, Any, Optional, Tuple
import html
TELEGRAM_HARD_LIMIT = 4096
SAFE_MARGIN = 560
CHUNK_LIMIT = TELEGRAM_HARD_LIMIT - SAFE_MARGIN
def _fmt_float(x: Optional[float], digits: int = 6) -> str:
    if x is None:
        return "-"
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "-"
    if x != 0.0 and (abs(x) < 1e-4 or abs(x) >= 1e6):
        return f"{x:.3e}"
    s = f"{x:.{digits}f}".rstrip("0").rstrip(".")
    return s if s else "0"
def _fmt_pct(ratio: Optional[float], digits: int = 2) -> str:
    if ratio is None:
        return "-"
    try:
        return f"{float(ratio) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "-"
def _fmt_range(lo: Optional[float], hi: Optional[float], mult: int) -> str:
    if lo is None or hi is None or mult is None:
        return "-"
    try:
        mult = int(mult)
    except Exception:
        mult = 0
    return f"[{_fmt_float(lo)} – {_fmt_float(hi)}] × {mult}"
def _fmt_tag_list(tags: List[Any]) -> str:
    if not tags:
        return ""
    safe = []
    for t in tags:
        try:
            safe.append(f"[{html.escape(str(t))}]")
        except Exception:
            continue
    return " ".join(safe)
def _fmt_speed(speed: Dict[str, Any]) -> str:
    if not speed:
        return ""
    parts: List[str] = []
    xph = speed.get("xph", None)
    if xph is not None:
        try:
            parts.append(f"xph={_fmt_float(float(xph), 2)}")
        except Exception:
            parts.append(f"xph={html.escape(str(xph))}")
    med = speed.get("med", None)
    if med is not None and med != "":
        try:
            med_num = float(med)
            med_txt = f"{int(med_num)}m"
        except Exception:
            med_txt = str(med)
        parts.append(f"med={html.escape(med_txt)}")
    edge = speed.get("edgeph", None)
    if edge is not None:
        try:
            parts.append(f"edge={_fmt_float(float(edge), 1)}")
        except Exception:
            parts.append(f"edge={html.escape(str(edge))}")
    return " | ".join(parts)
def _safe_num(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default
def _fmt_coin_block(i: int, c: Dict[str, Any]) -> str:
    sym = html.escape(c.get("symbol", "-"))
    last    = _fmt_float(_safe_num(c.get("last")))
    atr_abs = _fmt_float(_safe_num(c.get("atr_abs")))
    atr_pct = _fmt_pct(_safe_num(c.get("atr_pct")))
    rng_pct = _fmt_pct(_safe_num(c.get("range_pct")))
    adx     = _fmt_float(_safe_num(c.get("adx"), 1), 1)
    mid     = c.get("mid_cross", None)
    drift   = _fmt_pct(_safe_num(c.get("drift_pct")))
    tags    = _fmt_tag_list(c.get("tags", []))
    grid    = _fmt_range(_safe_num(c.get("grid_low")), _safe_num(c.get("grid_high")), c.get("grid_lines") or 0)
    speed   = _fmt_speed(c.get("speed", {}))
    lines: List[str] = []
    lines.append(f"{i}️⃣ <b>{sym}</b>")
    lines.append(f" • Fiyat: <b>{last}</b>")
    if atr_abs != "-" or atr_pct != "-":
        lines.append(f" • ATR: {atr_abs} ({atr_pct})")
    if rng_pct != "-":
        lines.append(f" • Range: ≈{rng_pct}")
    if adx != "-" or mid is not None:
        mid_txt = f" | Mid-Cross: {mid}" if mid is not None else ""
        lines.append(f" • ADX: ≈{adx}{mid_txt}")
    if drift != "-":
        lines.append(f" • Drift: {drift}")
    if tags:
        lines.append(f" • {tags}")
    if grid != "-":
        lines.append(f" • Grid: <code>{html.escape(grid)}</code>")
    if speed:
        lines.append(f" • Hız: {html.escape(speed)}")
    return "\n".join(lines)
def _split_chunks(text: str, limit: int = CHUNK_LIMIT) -> List[str]:
    if len(text) <= limit:
        return [text]
    parts: List[str] = []
    buf: List[str] = []
    size = 0
    for line in text.splitlines(keepends=True):
        if size + len(line) > limit and buf:
            parts.append("".join(buf))
            buf, size = [], 0
        buf.append(line)
        size += len(line)
    if buf:
        parts.append("".join(buf))
    return parts
def format_telegram_scan_message(
    *,
    scan_started_at: Optional[str] = None,
    s_behavior: Optional[Dict[str, Any]] = None,
    top_candidates: List[Dict[str, Any]] = None,
    fast_candidates: Optional[List[Dict[str, Any]]] = None,
    title_scanner: str = "🟢 Scanner Up — Starting Scan",
    title_s_behavior: str = "📊 <b>S Davranışı (Ping-Pong Teyitli)</b>",
    title_top: str = "📋 <b>BingX Grid Scan — En İyi Adaylar</b>",
    title_fast: str = "⚡ <b>FAST-S — Wide & Quick S</b>",
) -> List[str]:
    sections: List[str] = []
    if top_candidates is None:
        top_candidates = []
    head = [title_scanner]
    if scan_started_at:
        head.append(f"<i>{html.escape(scan_started_at)}</i>")
    sections.append("\n".join(head))
    if fast_candidates:
        blocks: List[str] = [title_fast]
        for idx, c in enumerate(fast_candidates, start=1):
            blocks.append(_fmt_coin_block(idx, c))
            blocks.append("—" * 17)
        if blocks and blocks[-1].startswith("—"):
            blocks.pop()
        sections.append("\n".join(blocks))
    if s_behavior:
        sb = s_behavior
        sym   = html.escape(sb.get("symbol", "-"))
        last  = _fmt_float(_safe_num(sb.get("last")))
        atr_a = _fmt_float(_safe_num(sb.get("atr_abs")))
        atr_p = _fmt_pct(_safe_num(sb.get("atr_pct")))
        rng   = _fmt_pct(_safe_num(sb.get("range_pct")))
        adx   = _fmt_float(_safe_num(sb.get("adx"), 1), 1)
        mid   = sb.get("mid_cross", None)
        drift = _fmt_pct(_safe_num(sb.get("drift_pct")))
        grid  = _fmt_range(_safe_num(sb.get("grid_low")), _safe_num(sb.get("grid_high")), sb.get("grid_lines") or 0)
        speed = _fmt_speed(sb.get("speed", {}))
        block = [
            title_s_behavior,
            f"🔸 Coin: <b>{sym}</b>",
            f"🔹 Fiyat: <b>{last}</b>",
        ]
        if atr_a != "-" or atr_p != "-":
            block.append(f"🔹 ATR: {atr_a} ({atr_p})")
        if rng != "-":
            block.append(f"🔹 Range: ≈{rng}")
        line_adx = f"🔹 ADX: ≈{adx}"
        if mid is not None:
            line_adx += f" | Mid-Cross: {mid}"
        block.append(line_adx)
        if drift != "-":
            block.append(f"🔹 Drift: {drift}")
        if grid != "-":
            block.append(f"📈 Grid Aralığı: <code>{html.escape(grid)}</code>")
        if speed:
            block.append(f"⚡ Hız: {html.escape(speed)}")
        sections.append("\n".join(block))
    if top_candidates:
        blocks = [title_top]
        for idx, c in enumerate(top_candidates, start=1):
            blocks.append(_fmt_coin_block(idx, c))
            blocks.append("—" * 17)
        if blocks and blocks[-1].startswith("—"):
            blocks.pop()
        sections.append("\n".join(blocks))
    full_text = "\n\n".join(sections)
    return _split_chunks(full_text)
