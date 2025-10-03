# OKX Grid — Broad Scan & Filter (GitHub-only)

Bu paket, **S bulunamadı** durumlarında bile boş kalmamak için:
- 3m, 5m, 15m timeframelerde **çoklu tarama** yapar
- Varsa `S+NEAR` ve geniş aktivasyon pencereleri denemelerini **güvenli şekilde** dener
- Çıktıyı `grid_filter.py` ile filtreleyerek **OKX'e gireceğin** Lower/Upper/Mid + GridCount + Mode değerlerini üretir

## Kurulum
1. Repo → **Add file → Upload files**
2. Bu dosyaları **aynı yollarla** yükle:
   - `run_scan_matrix.sh` (kök dizin)
   - `grid_filter.py` (kök dizin)  — eğer zaten varsa üzerine yazabilirsin
   - `.github/workflows/okx-grid-broad.yml`
3. **requirements.txt** ve **Secrets (BOT_TOKEN, CHAT_ID)** zaten eklendiyse hazır.
   - Değilse ekle: `requirements.txt` içine `numpy`, `pandas`, `requests` yaz.
   - Secrets ekle: Settings → Secrets → Actions (BOT_TOKEN, CHAT_ID).
4. **Commit changes**.

## Çalıştırma
- **Actions** → **OKX Grid — Broad Scan & Filter** → **Run workflow**
- Otomatik olarak her **15 dakikada bir** de çalışır (UTC).

## Sonuçlar
- Job içinde **Filter Wide Range Candidates** log'unda: `OKX ▶ Lower=... Upper=... Mid=... GridCount=... Mode=Geometric`
- **Artifacts**: `scan_3m.txt`, `scan_5m.txt`, `scan_15m.txt` ve karşılık gelen `filtered_*.txt` dosyaları.

## Not
- `run_scan_matrix.sh` bazı **ek parametreleri** deniyor (`--pattern s_near`, `--activation-hours 6/12`, `--pattern only_s`). 
  Eğer bot bu parametreleri desteklemiyorsa, o denemeler **hata verse bile script durmaz** (devam eder). 
  Bu sayede **uyumlu olan kombinasyonlardan** veri toplanır.
