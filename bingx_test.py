#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, time, hmac, hashlib, requests

BASE = "https://open-api.bingx.com"
API_KEY = os.environ.get("BINGX_API_KEY", "")
API_SECRET = os.environ.get("BINGX_API_SECRET", "")

def public_get(endpoint, params=""):
    url = BASE + endpoint
    if params:
        url += "?" + params
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.json()

def private_get(endpoint, params=""):
    if not API_KEY or not API_SECRET:
        return {"skip": True, "msg": "No API key/secret provided"}
    ts = str(int(time.time() * 1000))
    q = f"{params}&timestamp={ts}" if params else f"timestamp={ts}"
    sign = hmac.new(API_SECRET.encode(), q.encode(), hashlib.sha256).hexdigest()
    headers = {"X-BX-APIKEY": API_KEY}
    url = f"{BASE}{endpoint}?{q}&signature={sign}"
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()

def main():
    print("🔹 [BingX] Public API quick test")
    try:
        ticker = public_get("/openApi/swap/v2/quote/ticker", "symbol=BTC-USDT")
        print("ticker BTC-USDT:", ticker)
    except Exception as e:
        print("ticker error:", repr(e))

    try:
        depth = public_get("/openApi/swap/v2/quote/depth", "symbol=BTC-USDT&limit=5")
        print("orderbook depth x5:", depth)
    except Exception as e:
        print("depth error:", repr(e))

    print("\n🔹 [BingX] Private API (optional)")
    try:
        balance = private_get("/openApi/swap/v2/user/balance")
        print("balance:", balance)
    except Exception as e:
        print("balance error:", repr(e))

if __name__ == "__main__":
    main()
