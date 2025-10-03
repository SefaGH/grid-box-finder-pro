#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
telegram_notify.py (v2)
Sends ONE concise Telegram message per timeframe iff there are OKX-ready lines.
"""
import os, sys, re, json, urllib.request

OKX_LINE = re.compile(r"OKX\s*▶\s*Lower=")

def send_message(token, chat_id, text):
    data = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        resp.read()

def main():
    if len(sys.argv) < 3:
        print("usage: telegram_notify.py <filtered_file> <tf>")
        sys.exit(1)
    path = sys.argv[1]
    tf = sys.argv[2]
    token = os.environ.get("BOT_TOKEN", "")
    chat_id = os.environ.get("CHAT_ID", "")
    if not token or not chat_id:
        print("No BOT_TOKEN/CHAT_ID; skipping Telegram notify.")
        sys.exit(0)
    try:
        txt = open(path, "r", encoding="utf-8", errors="ignore").read()
    except Exception as e:
        print(f"Cannot read {path}: {e}")
        sys.exit(0)

    # Grab up to first 8 OKX lines
    lines = [ln.strip() for ln in txt.splitlines() if OKX_LINE.search(ln)]
    if not lines:
        print("No OKX lines; skipping Telegram notify.")
        sys.exit(0)

    preview = "\n".join(lines[:8])
    msg = f"🧰 OKX Grid Candidates — {tf}\n{preview}"
    send_message(token, chat_id, msg)
    print("Telegram sent.")

if __name__ == "__main__":
    main()
