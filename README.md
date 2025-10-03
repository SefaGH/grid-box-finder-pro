# BingX Grid Scan Bot (GitHub Actions, ccxt) — **Ping‑Pong (S) sürümü**

**Amaç:** BingX USDT‑M perpetual paritelerini **kamu verisi** ile tarayıp,
- ATR% ve range% ile **grid’e elverişli** adayları bulur,
- Ek olarak **“chop score”** (trend zayıflığı + orta bant geçişi + net drift) hesaplayarak **“PING‑PONG OK”** etiketiyle gerçekten **S davranışı** verenleri işaretler.

**Gerçek emir göndermez.** (İstersen ayrı bir `workflow_dispatch` ile paper/live modül ekleriz.)

## Hızlı Kurulum
1) Bu klasörü *yeni bir GitHub reposuna* yükleyin.
2) (Opsiyonel) **Settings → Secrets and variables → Actions** altında:
   - **Secrets:** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
   - **Variables (önerilen başlangıç):**
     - `TOP_K=60`
     - `ATR_PCT_MIN=0.0025`  (≥%0.25)
     - `RANGE_PCT_MIN=0.015` (≥%1.5)
     - `ADX_MAX=18`          (trend zayıf)
     - `MID_CROSS_MIN=12`    (16 saatte ≥12 orta bant geçişi)
     - `DRIFT_MAX_RATIO=0.25`(net drift ≤ toplam range’in %25’i)
3) **Actions**’ı etkinleştirip **Run workflow** ile çalıştırın (otomatik olarak her saat **:12**’de de çalışır).
4) Sonuçları **Actions → BingX Grid Scan → Logs**’ta görün; Telegram secrets giriliyse özet mesaj gelir.

## Dosyalar
```
bingx-grid-scan-bot/
├─ scan_bingx_grid.py
├─ requirements.txt
└─ .github/workflows/bingx-grid-scan.yml
```

## Ne değişti? (Özet)
- **ADX(14)** (TA‑Lib yok; saf Python) ile trend zayıflığı ölçümü (`ADX_MAX` eşiği).
- **SMA(20) orta bant geçiş sayısı** (son ~16 saat içinde) `MID_CROSS_MIN` ile eşiklenir.
- **Net drift**: son ~16 saatte ilk‑son kapanış farkının, toplam range’e oranı `DRIFT_MAX_RATIO` altında olmalı.
- Bu üç şart **ATR%/range%** filtrelerine **ek** olarak sağlanırsa, aday **“PING‑PONG OK”** etiketi alır ve Telegram’da ayrı başlıkta listelenir.

---

© 2025 — BingX grid tarama (S‑davranışı ölçümleriyle).
