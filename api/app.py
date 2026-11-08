# Trang Mini App Mia: trả mini/mia.html, thay {{CHU_TEN}} bằng cách gọi chủ bot (biến CHU_TEN).
# Mở từ nút Menu / nút "Mở Mia" trong Telegram.
import os
from html import escape
from http.server import BaseHTTPRequestHandler
from pathlib import Path

HTML = (Path(__file__).resolve().parent.parent / "mini" / "mia.html").read_text(encoding="utf-8")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        ten = escape(os.environ.get("CHU_TEN", "chủ bot").strip() or "chủ bot")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(HTML.replace("{{CHU_TEN}}", ten).encode("utf-8"))
