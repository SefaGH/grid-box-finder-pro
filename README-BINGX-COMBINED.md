# BingX — Combined Test Pack (manual)

Bu paketle üç şeyi **mevcut repo**'na ekleyip test edeceğiz:
1) Secrets var/yok kontrolü
2) BingX API erişimi (public + optional private)
3) Grid taraması (sessiz) + filtre + tek Telegram bildirimi

## Hangi klasöre yüklenecek?
- **Mevcut kurulumun olduğu repo**'ya kuracağız (yeni repo gerekmiyor).
- Dosya yerleşimi:
  - `bingx_test.py`, `run_scan_muted_bingx.sh`, `telegram_notify.py` → **kök dizin**
  - `.github/workflows/bingx-*.yml` → **.github/workflows/**

## Adımlar
1) **API Key oluştur (BingX)** — Read + Perpetual Futures Trading ✓, Withdraw ✗, IP whitelist boş.
2) Repo → **Settings → Secrets → Actions** → şunları ekle:
   - `BINGX_API_KEY`, `BINGX_API_SECRET`  (Telegram için `BOT_TOKEN`, `CHAT_ID` zaten varsa yeterli)
3) **Dosyaları yükle** (bu paketten):
   - `.github/workflows/bingx-secrets-check.yml`
   - `.github/workflows/bingx-api-test.yml`
   - `.github/workflows/bingx-grid-silent.yml`
   - `bingx_test.py`, `run_scan_muted_bingx.sh`, `telegram_notify.py`
4) **Actions → Secrets Presence Check (BingX)** → **Run workflow**
5) **Actions → BingX API Test** → **Run workflow**
6) **Actions → BingX Grid — Silent Scan + Single Notify (test)** → **Run workflow**
   - `scan_*.txt` ve `filtered_*.txt` artifacts olarak iner.
   - `filtered_*.txt` içinde `OKX ▶ Lower=... Upper=... Mid=... GridCount=... Mode=Geometric` satırları varsa Telegram’a **tek mesaj** gelir.
   - Eğer bot `--exchange bingx` argümanını tanımıyorsa script otomatik **fallback** yapar (no --exchange). Bu durumda bot OKX’e sabit kodluysa yine OKX verisini kullanır.

## Notlar
- Grid filtre eşikleri test için gevşek: MIN_RANGE=1.5, MAX_DRIFT=0.35, MAX_CV=0.45, MIN_SCORE=40.
- Tam BingX entegrasyonu için bot kodu `--exchange bingx` argümanını desteklemelidir. Desteklemiyorsa, botta küçük bir yama gerekir — istersen patch dosyasını hazırlarım.
