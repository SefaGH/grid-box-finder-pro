# OKX Grid — Scan & Filter (relaxed)

Bu workflow **3m/5m/15m/1h** tarar ve eşikleri gevşetilmiş halde `grid_filter.py` ile OKX'e gireceğin
**Lower/Upper/Mid + GridCount + Mode** değerlerini üretir.

## Kurulum
1. Repo → Add file → Upload files
2. Yükle:
   - `.github/workflows/okx-grid-relaxed.yml`
   - `run_scan_matrix.sh` (opsiyonel ama önerilir; yoksa workflow zaten temel komutu çalıştırır)
3. Zaten eklediğin şu dosyalarla uyumludur:
   - `grid_filter.py` (5m destekli sürüm)
   - `requirements.txt` (numpy, pandas, requests)
   - Secrets: `BOT_TOKEN`, `CHAT_ID`

## Çalıştırma
- Actions → **OKX Grid — Scan & Filter (relaxed)** → Run workflow
- Otomatik: 15 dakikada bir (UTC)

## Sonuçlar
- Logs: `OKX ▶ Lower=... Upper=... Mid=... GridCount=... Mode=Geometric`
- Artifacts: `scan_*.txt`, `filtered_*.txt`

## Eşikler
env içinde:
- MIN_RANGE=2.0, MAX_DRIFT=0.30, MAX_CV=0.40, MIN_SCORE=45
- Fallback: FB_MIN_SCORE=50, FB_MAX_CV=0.45, FB_MAX_DRIFT=0.35
