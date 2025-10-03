#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Capture Telegram sendMessage payloads (POST/GET; json/form/query) to STDOUT
# and run auto_grid_box_finder_pro.py transparently.
import sys, os, runpy
from urllib.parse import urlparse, parse_qs
import requests as _req

_real_post = _req.post
_real_get  = _req.get

def _extract_text_from_kwargs(kwargs):
    js = kwargs.get("json")
    if isinstance(js, dict) and isinstance(js.get("text"), str):
        return js["text"]
    data = kwargs.get("data")
    if isinstance(data, dict) and isinstance(data.get("text"), str):
        return data["text"]
    return None

def _mirror_if_telegram(url, *args, **kwargs):
    try:
        p = urlparse(url)
        if p.netloc == "api.telegram.org" and p.path.endswith("/sendMessage"):
            text = _extract_text_from_kwargs(kwargs)
            if not text and p.query:
                q = parse_qs(p.query)
                v = q.get("text", [])
                if v and isinstance(v[0], str):
                    text = v[0]
            if text:
                print(text, flush=True)
                class _R:
                    status_code = 200
                    def json(self): return {"ok": True, "result": {"message_id": 0}}
                    def raise_for_status(self): return None
                    @property
                    def text(self): return "OK"
                return _R()
    except Exception:
        pass
    return None

def _post(url, *args, **kwargs):
    r = _mirror_if_telegram(url, *args, **kwargs)
    return r if r is not None else _real_post(url, *args, **kwargs)

def _get(url, *args, **kwargs):
    r = _mirror_if_telegram(url, *args, **kwargs)
    return r if r is not None else _real_get(url, *args, **kwargs)

def main():
    import requests
    requests.post = _post  # type: ignore
    requests.get  = _get   # type: ignore
    os.environ.setdefault("BOT_TOKEN", "0")
    os.environ.setdefault("CHAT_ID", "0")
    sys.argv = ["auto_grid_box_finder_pro.py"] + sys.argv[1:]
    runpy.run_path("auto_grid_box_finder_pro.py", run_name="__main__")

if __name__ == "__main__":
    main()
