#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Wrapper to run auto_grid_box_finder_pro.py while capturing Telegram sendMessage
# payloads to STDOUT (instead of actually sending). Only intercepts requests to
# api.telegram.org/bot*/sendMessage; other HTTP calls are passed through.
import sys, os, runpy
from urllib.parse import urlparse
import requests as _real_requests

_real_post = _real_requests.post

def _post_patch(url, *args, **kwargs):
    try:
        parsed = urlparse(url)
        if parsed.netloc == "api.telegram.org" and parsed.path.endswith("/sendMessage"):
            payload = kwargs.get("json") or {}
            text = payload.get("text", "")
            if text:
                print(text, flush=True)  # mirror to STDOUT
            class _DummyResp:
                status_code = 200
                def json(self): return {"ok": True, "result": {"message_id": 0}}
                def raise_for_status(self): return None
                @property
                def text(self): return "OK"
            return _DummyResp()
    except Exception:
        pass
    return _real_post(url, *args, **kwargs)

def main():
    import requests
    requests.post = _post_patch  # type: ignore
    os.environ.setdefault("BOT_TOKEN", "0")
    os.environ.setdefault("CHAT_ID", "0")
    sys.argv = ["auto_grid_box_finder_pro.py"] + sys.argv[1:]
    runpy.run_path("auto_grid_box_finder_pro.py", run_name="__main__")

if __name__ == "__main__":
    main()
