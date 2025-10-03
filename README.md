# BingX Grid Scan Bot (GitHub Actions, ccxt) — **Ping-Pong (S) Pro sürüm**

**Ne yapar?**
- USDT-M perpetual pariteleri **public veri** ile tarar (API key gerekmez).
- **ATR% + range%** ile grid’e elverişli adayları seçer.
- **Chop Score** ile gerçek **S (ping‑pong)** davranışını teyit eder:
  - **ADX(14) ≤ ADX_MAX** → trend zayıf
  - **SMA(20) midline cross ≥ MID_CROSS_MIN** → sık ping-pong
  - **Net drift ≤ DRIFT_MAX_RATIO** → tek yöne kayma yok
- **Likidite filtresi**: `quoteVolume` (USDT) ≥ `MIN_QVOL_USDT`
- **Yeni listelemeleri dışlama**: `LISTED_MIN_DAYS` altında olanları ele (yaklaşık ölçüm)

**Gerçek emir göndermez.** İstersen ayrı bir `workflow_dispatch` ile paper/live modül eklenebilir.

---

## Hızlı Kurulum
1) Bu klasörü **yeni bir GitHub reposuna** yükle.
2) **Actions → Enable** et, sonra **Run workflow** ile tetikle (otomatik her saat **:12**’de de çalışır).
3) (Opsiyonel) **Settings → Secrets and variables → Actions** altında:
   - **Secrets:** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
   - **Variables (önerilen başlangıç):**
     - `TOP_K=80`
     - `ATR_PCT_MIN=0.0025`   # = %0.25
     - `RANGE_PCT_MIN=0.015`  # = %1.5
     - `ADX_MAX=15`
     - `MID_CROSS_MIN=18`
     - `DRIFT_MAX_RATIO=0.20`
     - `MIN_QVOL_USDT=500000`       # 24h USDT hacmi alt sınırı
     - `LISTED_MIN_DAYS=14`         # ~2 hafta
     - `MIN_GRID_K_ATR=1.0`         # grid genişliği ≥ k×ATR (opsiyonel; 0 → kapalı)

**Not:** Yüzde değerleri **ondalıklı** gir (örn. 0.0025), **%0.25** gibi yazma.

---

## Çıktı formatı
- Telegram’da **iki blok** mesaj:
  1) **PING-PONG OK (S davranışı teyitli)**
  2) **BingX Grid Scan Sonuçları (Top adaylar)**
- “Top adaylar”da S filtresini geçemeyenler, satır sonunda **etiket** alır:
  - `[TREND]` ADX yüksek
  - `[MID]` midline cross yetersiz
  - `[DRIFT]` net drift yüksek
  - `[LOWVOL]` ATR% düşük
  - `[LOWRANGE]` range% düşük
  - `[LOWLIQ]` likidite düşük
  - `[NEW]` yeni liste

---

## Dosyalar
```
bingx-grid-scan-bot/
├─ scan_bingx_grid.py
├─ requirements.txt
└─ .github/workflows/bingx-grid-scan.yml
```

© 2025
