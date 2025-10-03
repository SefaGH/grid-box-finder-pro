# BingX Grid Scan Bot (GitHub Actions, ccxt tabanlı)

**Amaç:** BingX USDT-M Perpetual (swap) paritelerini **kamu verisi** ile tarayıp, 5 dakikalık mumlardan
ATR ve bant genişliği metriklerine göre **nötr grid aralığı** önerisi üretir. **Gerçek emir göndermez.**
İsterseniz Telegram’a özet gönderir.

> ccxt kullanıyoruz. Bu sayede public endpoint uyumsuzlukları / rate limit farklarını daha az sorun ederek ilerleriz.

## Hızlı Kurulum
1. Bu klasörü *yeni bir GitHub reposuna* yükleyin (root’a).
2. Repo → **Settings → Secrets and variables → Actions** altında (opsiyonel) şunları ekleyin:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. **Actions** sekmesinden workflow’u etkinleştirin.
4. **Run workflow** ile hemen tetikleyebilirsiniz. Otomatik olarak her saat **:12**’de çalışır.
5. Sonuçları **Actions → BingX Grid Scan → Logs** altında görün. Telegram verdiyseniz mesaj gelir.

## Dosya Yapısı
```
bingx-grid-scan-bot/
├─ scan_bingx_grid.py
├─ requirements.txt
└─ .github/workflows/bingx-grid-scan.yml
```

## Çalışma Mantığı (varsayılanlar)
- **Pazar:** BingX, `swap` (USDT-M perpetual)
- **Sembol filtresi:** quote = USDT, `contract = True`
- **Hacim sıralaması:** 24h notional volüme göre **ilk 15** (`TOP_K` ile değiştirilebilir)
- **Zaman penceresi:** ~16 saat (200×5m)
- **ATR periyodu:** 50
- **Aday filtresi:** ATR% ≥ **0.3%**, range% ≥ **2%** (ENV ile ayarlanabilir)
- **Öneri grid:** nötr; son fiyat merkez; genişlik **%2–%6** arası dinamik; **12 seviye**

## Ortam Değişkenleri (opsiyonel)
- `TOP_K` (int, varsayılan **15**)
- `ATR_PCT_MIN` (float, varsayılan **0.003** → %0.3)
- `RANGE_PCT_MIN` (float, varsayılan **0.02** → %2.0)

## SSS
**BingX API anahtarı gerekir mi?**  
Hayır, bu tarayıcı yalnızca **kamu verisi** kullanır; ccxt ile public OHLCV/ticker çağrıları.

**Windows’ta `chmod +x` veya shell script var mı?**  
Yok. Python direkt çalıştırılıyor.

**Telegram zorunlu mu?**  
Değil. Secrets vermezsen, sadece log’a yazılır.

---

© 2025 – BingX grid tarama iskeleti (ccxt) – güvenli fallback’ler ile.
