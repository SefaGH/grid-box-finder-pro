
# Pro Grid Box Finder — Regime + Activation (Dual Window)

**Sorun:** Ping-pong rejimleri kısa sürüyor.  
**Çözüm:** Uzun pencere ile **sürdürülebilir geniş bant**ı doğrula (**Regime**), kısa pencere ile **aktif ping‑pong**u yakala (**Activation**). Koşullar birlikte sağlanınca bildir.

## Secrets (önerilen)
- MARKET=futures, INTERVAL=5m
- LONG_HRS=96, RECENT_HRS=3
- TOPK=12, QUOTE=USDT, MAX_SYMBOLS=150, VOL24_MIN_Q=50000000
- LONG_RANGE_MIN_PCT=15.0, LONG_SLOPE_MAX_PCT=0.60, LONG_Q_LOW=0.10, LONG_Q_HIGH=0.90, LONG_CONTAIN_MIN=0.65
- RECENT_ATR_MIN_PCT=0.60, RECENT_TOUCH_MIN=10, RECENT_ALT_MIN=6, RECENT_CONTAIN_MIN=0.70
- TOUCH_EPS_PCT=0.25, GRID_COUNT=12

## Çalışma
- **Regime (LONG_HRS)**: range%, slope%, inside% hesaplanır ve eşik kontrolü yapılır; grid bandı uzun pencereden türetilir.
- **Activation (RECENT_HRS)**: ATR%, touches, alternations, inside% ile kısa süreli canlı ping‑pong teyit edilir.
- Mesaj: ✅ işaretliler hem rejim hem aktivasyon sağlayanlardır; grid bandı ve metrikler birlikte verilir.
