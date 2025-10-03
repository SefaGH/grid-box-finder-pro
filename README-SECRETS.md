# Telegram Secrets Setup (GitHub)

Bu workflow `auto_grid_box_finder_pro.py` içindeki `assert BOT_TOKEN and CHAT_ID` kontrolünü geçmek için
**GitHub Secrets** kullanır.

## Adımlar
1. GitHub repo → **Settings → Secrets and variables → Actions**.
2. **New repository secret** ile şunları ekle:
   - **Name:** `BOT_TOKEN`  | **Value:** Telegram bot token’in (örn: `123456:ABC...`)
   - **Name:** `CHAT_ID`    | **Value:** Telegram sohbet ID’n (örn: `123456789`)
3. Kaydet.

Artık workflow çalışırken bu değerler ortam değişkeni olarak geçecek:
- `BOT_TOKEN` → `os.environ["BOT_TOKEN"]`
- `CHAT_ID`   → `os.environ["CHAT_ID"]`

> Not: Secrets log’larda **maskelenir** (gizlenir).

Workflow’u **Actions** sekmesinden **Run workflow** ile başlatabilirsin.
