import json
import os
import urllib.request


def goi(method: str, **params) -> dict:
    url = f"https://api.telegram.org/bot{os.environ['BOT_TOKEN']}/{method}"
    req = urllib.request.Request(url, json.dumps(params).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def gui(chat_id: int | str, text: str) -> None:
    goi("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML", disable_web_page_preview=True)
