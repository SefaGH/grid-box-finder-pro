#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, re, json, urllib.request
OKX_LINE = re.compile(r"OKX\s*▶\s*Lower=")

def send_message(token, chat_id, text):
    data = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    req = urllib.request.Request(url, data=data, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        resp.read()

if __name__ == "__main__":
    if len(sys.argv) < 3: sys.exit("usage: telegram_notify.py <filtered_file> <tf>")
    path, tf = sys.argv[1], sys.argv[2]
    token, chat_id = os.environ.get("BOT_TOKEN",""), os.environ.get("CHAT_ID","")
    if not token or not chat_id: sys.exit(0)
    try:
        txt = open(path, "r", encoding="utf-8", errors="ignore").read()
    except Exception:
        sys.exit(0)
    lines = [ln.strip() for ln in txt.splitlines() if OKX_LINE.search(ln)]
    if not lines: sys.exit(0)
    preview = "\n".join(lines[:8])
    send_message(token, chat_id, f"🧰 Grid Candidates — {tf}\n{preview}")
    print("Telegram sent.")
