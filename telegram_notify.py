#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, json, urllib.request

def send_message(token, chat_id, text):
    data = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    req = urllib.request.Request(url, data=data, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        resp.read()

def load_nonempty_lines(path, limit=10):
    try:
        txt = open(path, "r", encoding="utf-8", errors="ignore").read().strip()
    except Exception:
        return []
    lines = [ln.strip() for ln in txt.splitlines() if ln.strip() and not ln.strip().startswith("(") and "No parsable" not in ln]
    return lines[:limit]

if __name__ == "__main__":
    # Accept multiple pairs: <file> <tf> [<file> <tf> ...]
    token, chat_id = os.environ.get("BOT_TOKEN",""), os.environ.get("CHAT_ID","")
    if not token or not chat_id:
        sys.exit(0)
    args = sys.argv[1:]
    if len(args) < 2 or len(args) % 2 != 0:
        sys.exit(0)
    parts = []
    for i in range(0, len(args), 2):
        path, tf = args[i], args[i+1]
        lines = load_nonempty_lines(path, 10)
        if lines:
            parts.append(f"⏱ {tf}\n" + "\n".join(lines))
    if not parts:
        sys.exit(0)
    text = "🧰 Grid Candidates\n" + "\n\n".join(parts)
    send_message(token, chat_id, text)
    print("Telegram sent.")
