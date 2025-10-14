# Hybrid Crypto Bot — Dynamic Grid & (Planned) Tri-Arb

> **Durum:** Aktif geliştirme (Paper/DRY_RUN hazır) • **Borsa:** BingX USDT-M (CCXT) • **Koşum:** GitHub Actions (workflow_dispatch) • **Bildirim:** Telegram

---

## 🧭 İçindekiler

* [Neden bu bot?](#neden-bu-bot)
* [Bugüne kadar neler yaptık?](#bugüne-kadar-neler-yaptık)
* [Bot şu anda ne yapıyor?](#bot-şu-anda-ne-yapıyor)
* [Tamamlandığında ne yapacak?](#tamamlandığında-ne-yapacak)
* [Mimari & Mantık](#mimari--mantık)
* [Kurulum & Çalıştırma](#kurulum--çalıştırma)
* [Yapılandırma (Variables & Secrets)](#yapılandırma-variables--secrets)
* [Dosya Yapısı](#dosya-yapısı)
* [Günlük Akış (Run Lifecycle)](#günlük-akış-run-lifecycle)
* [Loglar, Bildirimler ve Test](#loglar-bildirimler-ve-test)
* [Yol Haritası (Roadmap)](#yol-haritası-roadmap)
* [Güvenlik & Risk](#güvenlik--risk)
* [Sık Sorulanlar](#sık-sorulanlar)
* [Troubleshooting](#troubleshooting)
* [Lisans / Uyarı](#lisans--uyarı)

---

## Neden bu bot?

Kripto piyasasında volatilite dalgalarında **duygusuz, sistematik** işlem yapmak; trend gücü arttığında **korumaya geçmek**, yatay/dalgalı fazlarda **ızgara (grid)** ile “mikro salınımlardan” **tekrarlı küçük kârlar** toplamak; ileride ise eşzamanlı piyasa uyumsuzluklarında **üçgen arbitraj (triangular arbitrage)** ile **düşük riskli** fırsatlara **hızlı tepki** vermek.

---

## Bugüne kadar neler yaptık?

**Başlangıç:**

* Sadece veri sağlayan “grid bot” iskeleti vardı; canlı emir yoktu.

**Eklenenler:**

* **Dynamic Grid** stratejisi (bant hesapla → grid yerleştir).
* **Guard’lar (koruma mantığı)**:

  * **ADX histerezis (HI/LO)** ile trend filtresi (trend güçlü → dur/pause).
  * **Volatilite spike** filtresi.
  * **Cooldown & ardışık tetik sayacı (debounce)**: gereksiz kur/iptal churn’ünü azaltır.
* **Sadece env/Variables ile yönetim**: parametrelerin tamamı kod dışından ayarlanır.
* **compute_grid_inline**: borsa **tick/step/minNotional** kurallarına **uyumlu** grid planlayıcı.
* **GitHub Actions workflow** (manual trigger):

  * `RUN_SECONDS` girişi,
  * job-level **sabit emniyet** (`timeout-minutes: 45`),
  * **DRY_RUN** default açık.
* **Telegram bildirimleri**: başladı / guard (bucket bazlı) / süre doldu.
* **RUN_SECONDS** + **end_ts** ile **sıkı süre kontrolü** (takılmalara rağmen düzgün kapanış).

---

## Bot şu anda ne yapıyor?

* **Paper mod (DRY_RUN=1):**

  * BingX USDT-M’den 1m OHLCV çeker, **ADX** & **volatilite** ölçer.
  * Trend güçlü ise **pause**: açık emir varsa iptal eder (DRY), grid kurmaz.
  * Trend sakinleşirse grid’i **borsa adım kurallarına uygun** yerleştirir (DRY create_order logları).
  * **Telegram’a** başlangıç ve guard olaylarını yollar.
  * `RUN_SECONDS` dolunca **kibarca** kapanır.

---

## Tamamlandığında ne yapacak?

* **Canlı emir** (DRY_RUN=0) desteği ile:

  * **Dynamic Grid**: belirlenen bantta **limit** al/sat merdivenleri, **TP**’ler, minNotional ve adım uyumlu **miktarlar**.
  * **Tri-Arb (planlı)**: üçlü döngü (ör. BTC/USDT → BTC/ETH → ETH/USDT → USDT) **edge ≥ eşik** olduğunda IOC/FOK ile hızlı yürütme, fail-safe risk kapaması.
  * **Risk Gate**: toplam açık notional / sembol başına maruziyet / günlük zarar eşiği / stop_pct.
  * **Durumsal depolama** (JsonState) ile retune aralıkları, son bant vb. hafıza.
* Amaç: **düşük risk** + **tekrarlı küçük kârlar**, trend dönemlerinde **gereksiz zarar riskini baskılama**.

---

## Mimari & Mantık

```
                ┌───────────┐    OHLCV/last    ┌───────────────┐
GitHub Actions  │  Runner   │ ───────────────→ │  ExchangeCCXT │
(workflow)      │ paper_bot │ ←────orders──────│  (BingX swap) │
                └─────┬─────┘                  └──────┬────────┘
                      │ metrics/guards                 │ ccxt
     Telegram         │                                │
   notifications ◄────┘                                │
                      ▼                                │
              ┌──────────────┐        uses             │
              │ Strategist    │────────────────────────┘
              │ pick_mode()   │
              └──────┬────────┘
                     │  mode
     ┌───────────────┴───────────────┐
     │                                │
┌────▼────┐                     ┌─────▼────┐
│Dynamic  │ grid plan → orders  │ Tri-Arb  │ (planned: edge calc/exec)
│ Grid    │ (compute_grid_inline│ Module   │
└─────────┘   tick/step/minNot) └──────────┘
```

### Strateji seçimi (şimdilik)

* **ADX < LO** ve spike yok → **Dynamic Grid** (fırsattan faydalan).
* **ADX ≥ HI** veya spike var → **Guard (pause)**.

### Guard mantığı

* **Histerezis**: HI üstünde trend_blocked=True; **LO altına** düşmeden serbest kalma yok → pingpong yok.
* **Cooldown**: tetiklendikten sonra **N saniye** sessiz mod.
* **Consecutive hits**: üst üste M tetik gerek → sınırda titreme ile anlık durma yok.
* **Telegram bucket**: aynı ADX aralığında spam yok.

---

## Kurulum & Çalıştırma

### 1) Depoyu hazırlayın

```bash
pip install -r requirements.txt
```

### 2) Workflow ile çalıştırma (önerilen)

* GitHub → **Actions** → `Hybrid Paper Bot` → **Run workflow**

  * `RUN_SECONDS`: Örn. `900` (15 dk).
* Job 45 dk üst limitli; bot **RUN_SECONDS** dolunca kendi kapanır.

### 3) Lokal (opsiyonel)

```bash
export DRY_RUN=1 RUN_SECONDS=600 SYMBOL="BTC/USDT:USDT"
python -m src.runner.paper_bot
```

---

## Yapılandırma (Variables & Secrets)

| Tür          | Ad                                        | Açıklama                       | Öneri                         |
| ------------ | ----------------------------------------- | ------------------------------ | ----------------------------- |
| **Secret**   | `BINGX_API_KEY` / `BINGX_API_SECRET`      | BingX API                      | Paper’da boş olabilir         |
| **Secret**   | `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Telegram bildirim              | İsteğe bağlı, önerilir        |
| **Variable** | `SYMBOL`                                  | `BTC/USDT:USDT`                | USDT-M sembol                 |
| **Variable** | `GRID_LEVELS`                             | Grid merdiven sayısı           | 12–20                         |
| **Variable** | `GRID_CAPITAL`                            | Grid için USDT                 | Örn. 200                      |
| **Variable** | `RETUNE_SEC`                              | Yeniden ayar periyodu          | 60–240                        |
| **Variable** | `ADX_LIMIT_HI` / `LO`                     | Trend histerezis eşikleri      | Örn. 45 / 30 *(daha az katı)* |
| **Variable** | `GUARD_COOLDOWN_SEC`                      | Guard sonrası bekleme          | 45–90                         |
| **Variable** | `GUARD_CONSEC_N`                          | Üst üste tetik sayısı          | 3–5                           |
| **Variable** | `VOL_SPIKE_FAST/SLOW/MULT`                | Spike algısı                   | 20 / 120 / 2.0                |
| **Variable** | `MAX_OPEN_NOTIONAL`                       | Toplam açık notional limiti    | RiskGate                      |
| **Variable** | `MAX_SYMBOL_EXPOSURE`                     | Sembol maruziyet limiti        | RiskGate                      |
| **Variable** | `DAILY_MAX_LOSS`                          | Günlük zarar limiti            | RiskGate                      |
| **Variable** | `STOP_PCT`                                | Stop yüzdesi                   | RiskGate                      |
| **Variable** | `FEE` / `TRI_EDGE_MIN`                    | Tri-Arb parametreleri (planlı) | 0.0006 / 0.0015               |
| **Variable** | `CCXT_TIMEOUT_MS`                         | CCXT timeout (ms)              | 15000                         |

> **Not:** `ADX_LIMIT` tek eşik verilir ise kod **HI/LO’yu türetir** (LO = HI−7). Tercihen HI/LO kullanın.

---

## Dosya Yapısı

```
.
├─ .github/workflows/hybrid-bot-paper.yml   # Actions workflow (RUN_SECONDS + env köprüsü)
├─ src/
│  ├─ runner/paper_bot.py                   # Ana döngü, guard & süre, Telegram
│  ├─ strategy/
│  │  ├─ dynamic_grid.py                    # GridParams + DynamicGrid (retune & place)
│  │  ├─ tri_arb.py                         # (planlı) edge hesap & yürütme skeleti
│  │  └─ metrics_feed.py                    # build_metrics (closes vs.)
│  ├─ core/
│  │  ├─ exchange_ccxt.py                   # CCXT sarmalayıcı
│  │  ├─ guards.py                          # adx14, volatility_spike
│  │  ├─ risk.py                            # RiskLimits + RiskGate
│  │  └─ state_store.py                     # JsonState
│  └─ strategist.py                         # pick_mode (grid vs arb)
├─ grid_sizer.py                            # compute_grid_inline (tick/step/minNotional)
├─ requirements.txt
└─ README.md
```

---

## Günlük Akış (Run Lifecycle)

1. **Başlat** (`RUN_SECONDS`, DRY_RUN=1) → Telegram: “başladı”
2. **Veri çek** → ADX/spike hesapla
3. **Guard kontrol**

   * Trend güçlü/spike → **pause**: açık emir varsa iptal (DRY) + cooldown + Telegram (bucket).
   * Trend sakin → **Dynamic Grid**:

     * Bant hesapla (mid±k*std; ileride ATR/özelleşir),
     * `compute_grid_inline` ile **tick/step/minNotional** uyumlu plan,
     * RiskGate sınırları doğrula,
     * **(DRY_RUN)** create_order logları.
4. **Süre kontrolü** → bitişte Telegram: “süre doldu”.

---

## Loglar, Bildirimler ve Test

* **Loglar:**

  * `[DRY_RUN] create_order …` satırları emir planını gösterir.
  * `[GUARD] Pause: ADX=.. spike=.. cooldown=..s` → koruma devrede.
* **Telegram:**

  * “başladı” → guard başlarken (bucket değişiminde tek) → “süre doldu”.
* **Test önerisi:**

  * `RUN_SECONDS=900`, `ADX_LIMIT_HI=45`, `ADX_LIMIT_LO=30`, `GUARD_COOLDOWN_SEC=45`, `RETUNE_SEC=60`.
  * Bu ayarlarla dalgalı piyasada **emir loglarının** görülme olasılığı yükselir.

---

## Yol Haritası (Roadmap)

* [ ] **Tri-Arb edge ölçümü** (DRY log)
* [ ] **Tri-Arb yürütme**: IOC/FOK, zaman aşımı, kısmi dolum hedge
* [ ] **PnL / muhasebe**: doldurma olaylarından PnL & performans raporu
* [ ] **Durumsal strateji geçişi**: grid ↔ tri-arb (eşik ve market koşullarına göre)
* [ ] **Parametre otomatizasyonu**: ADX/vol duruma göre retune_sec, levels, capital dağılımı
* [ ] **Web dashboard** (opsiyonel): canlı metrikler, grid görünümü, uyarılar

---

## Güvenlik & Risk

* **DRY_RUN=1** varsayılan — canlı emir **göndermez**.
* **RiskGate** limitleri **zorunlu** kullanın (max notional, maruziyet, günlük zarar, stop).
* **API anahtarları** *sadece* **Secrets**’ta tutulur.
* **Canlı (DRY_RUN=0)** geçmeden önce: küçük sermaye, tek sembol, kısa süreli prova.
* **Volatilite / likidite** ve **borsa kuralları** risk yaratır; parametreler ihtiyatlı olmalı.

---

## Sık Sorulanlar

**Q:** Emir logları neden bazen görünmüyor?
**A:** ADX yüksek / spike var ise **guard** devrede, grid yerleşmez (tasarım gereği). Eşikleri biraz gevşetin (örn. HI=45/LO=30) ve `RETUNE_SEC`’i düşürün.

**Q:** “RUN_SECONDS=900 girdim ama job daha uzun sürdü?”
**A:** Kod artık **end_ts** ile her adımda süre kontrolü yapıyor. Yine de GitHub job’ı 45 dk upper-bound ile güvence altında.

**Q:** Telegram’dan çok bildirim geliyor.
**A:** Guard pingi **bucket** bazlıdır; yine fazla ise `GUARD_COOLDOWN_SEC`’i artırın veya ADX eşiğini yükseltin.

---

## Troubleshooting

* **IndentationError / NameError**: Kopyala-yapıştırta sekme/boşluk karışımı olabilir. Editörde “Convert Tabs to Spaces” yapın.
* **ENV değerleri etkisiz**: Workflow `env:`’de ilgili **Variables**’ın köprüsü var mı kontrol edin.
* **BingX reddi**: `grid_sizer.py` adım/limits uyumlu; yine de **minNotional** büyükse `GRID_CAPITAL`/`reserve` ayarlarını revize edin.
* **Süre dolmuyor**: Son sürümde **end_ts** + **CCXT timeout** var; yine de anomali varsa logları kontrol edin.

---

## Lisans / Uyarı

* Bu bot **yatırım tavsiyesi değildir**.
* İşlem riskleri kullanıcıya aittir.
* API anahtarlarınızı koruyun, **DRY_RUN** dışında canlıya geçmeden önce küçük sermaye ile test edin.

---



