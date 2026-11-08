# Webhook Telegram. Chủ bot (OWNER_ID) dùng đủ lệnh; người nhà được chủ duyệt dùng /ngu, /tongket,
# /thoisu, /tin, /thucdon (khi đã bật trong Mia), /can, /caidat (mở Mini App). Người lạ /start → vào hàng
# chờ, chủ bấm Duyệt/Không ngay trong tin Mia gửi.
# Lệnh: /ngu = báo giấc ngủ đêm qua, /ngu hqua = đêm trước nữa, /thoisu = tin thời sự, /tin = tin công nghệ,
# /tongket = tổng kết vận động + nhịp tim hôm nay, /thucdon = thực đơn hôm nay,
# /can 75.2 = ghi cân (/can: xem tiến độ, /can xoa: xoá số hôm nay),
# /game = tình hình Đấu Trường PC (chỉ chủ bot, khi có BAO_CAO_SECRET).
import json
import os
import sys
from datetime import timedelta
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import can_nang, dau_truong, nguoi, telegram  # noqa: E402
from bot.nguoi import bao_ba_duyet, ten_cua  # noqa: E402
from bot.ngu import bao_cao, hom_nay_vn  # noqa: E402
from bot.tin import ban_tin, ban_tin_thoi_su  # noqa: E402
from bot.thuc_don import thuc_don  # noqa: E402
from bot.tong_ket import tong_ket  # noqa: E402

MIA_URL = os.environ.get("MIA_URL", "https://garmin-bot.vercel.app/api/app")
NUT_MIA = {"inline_keyboard": [[{"text": "⚙️ Mở Mia", "web_app": {"url": MIA_URL}}]]}

def chao_chu(p: dict) -> str:
    g, x = p["goi"], p["xung"]
    X = nguoi.hoa(x)
    chu = (f"{X} chào {g}! 👋 Mỗi sáng {x} báo giấc ngủ đêm qua của {g}, kèm tin thời sự và tin công nghệ nếu {g} bật; "
           f"10–11h {x} gửi thực đơn; buổi tối {x} tổng kết vận động, nhịp tim cả ngày")
    chu += " và tình hình game Đấu Trường PC" if dau_truong.co_cau_hinh() else ""
    chu += (f". Giờ sáng/tối và các mục bật/tắt {g} đổi trong /caidat.\n"
            f"{nguoi.hoa(g)} nhắn /ngu để xem giấc ngủ ngay (/ngu hqua: đêm trước), /thoisu và /tin để đọc tin, "
            f"/tongket để xem tổng kết hôm nay, /thucdon để xem thực đơn, /can 75.2 để ghi cân")
    chu += ", /game để xem game hôm nay (/game hqua: hôm qua)." if dau_truong.co_cau_hinh() else "."
    return chu


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
        if secret and self.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret:
            return self._ok(401)
        n = int(self.headers.get("Content-Length") or 0)
        update = json.loads(self.rfile.read(n) or b"{}")
        if update.get("callback_query"):
            self._nut(update["callback_query"])
            return self._ok()
        msg = update.get("message") or {}
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        text = (msg.get("text") or "").strip()
        if not chat_id or chat.get("type") != "private":
            return self._ok()
        lenh = text.split("@")[0].split()[0].lower() if text else ""
        if not nguoi.la_chu(chat_id):
            try:
                self._nguoi_nha(chat_id, msg.get("from") or {}, lenh, text)
            except Exception as e:
                print(f"Webhook người nhà lỗi: {type(e).__name__}: {e}")
            return self._ok()
        p = nguoi.lay(chat_id) or nguoi._chu()
        g, x = p["goi"], p["xung"]
        try:
            if lenh == "/caidat":
                telegram.goi("sendMessage", chat_id=chat_id, reply_markup=NUT_MIA,
                             text=f"{nguoi.hoa(g)} chỉnh giờ nhận tin, các mục bật/tắt và Garmin ở đây nha 👇")
            elif lenh == "/start":
                telegram.gui(chat_id, chao_chu(p))
            elif lenh == "/ngu":
                ngay = hom_nay_vn()
                if "hqua" in text.lower() or "hôm qua" in text.lower():
                    ngay -= timedelta(days=1)
                telegram.goi("sendChatAction", chat_id=chat_id, action="typing")
                telegram.gui(chat_id, bao_cao(ngay, p))
            elif lenh == "/tongket":
                telegram.goi("sendChatAction", chat_id=chat_id, action="typing")
                telegram.gui(chat_id, tong_ket(p=p))
            elif lenh == "/game" and dau_truong.co_cau_hinh():
                ngay = hom_nay_vn()
                if "hqua" in text.lower() or "hôm qua" in text.lower():
                    ngay -= timedelta(days=1)
                telegram.goi("sendChatAction", chat_id=chat_id, action="typing")
                telegram.gui(chat_id, dau_truong.bao_cao_game(ngay, p))
            elif lenh == "/can":
                telegram.gui(chat_id, can_nang.lenh(text, p))
            elif lenh == "/thucdon":
                telegram.goi("sendChatAction", chat_id=chat_id, action="typing")
                telegram.gui(chat_id, thuc_don(p=p))
            elif lenh == "/thoisu":
                telegram.goi("sendChatAction", chat_id=chat_id, action="typing")
                telegram.gui(chat_id, ban_tin_thoi_su(p) or f"{nguoi.hoa(x)} chưa lấy được tin thời sự mới nào {g} ơi 📭")
            elif lenh == "/tin":
                telegram.goi("sendChatAction", chat_id=chat_id, action="typing")
                telegram.gui(chat_id, ban_tin(p) or f"Hôm nay chưa có tin mới nào {g} ơi 📭")
        except Exception as e:
            telegram.goi("sendMessage", chat_id=chat_id,
                         text=f"⚠️ {nguoi.hoa(x)} bị lỗi: {type(e).__name__}: {e}"[:500])
        return self._ok()

    def _nguoi_nha(self, chat_id, u: dict, lenh: str, text: str):
        p = nguoi.lay(chat_id)
        if lenh == "/start" and not p:
            p, moi = nguoi.dang_ky(chat_id, ten_cua(u))
            if moi:
                bao_ba_duyet({**u, "id": chat_id})
            telegram.gui(chat_id, "Chào bạn 👋 Mình là Mia, trợ lý đọc giấc ngủ và vận động từ đồng hồ Garmin.\n"
                                  f"Mia đã báo {nguoi.ten_chu()} duyệt, xong Mia nhắn lại liền nha.")
            return
        if not p or p["trang_thai"] == "chan":
            return
        if p["trang_thai"] != "duyet":
            telegram.gui(chat_id, f"Mia đang chờ {nguoi.ten_chu()} duyệt, bạn đợi chút nha ⏳")
            return
        g, x = p["goi"], p["xung"]
        # Lệnh không cần Garmin: tin tức, thực đơn, cân nặng (08/11/2026, đợt 2 Mia cho cả nhà).
        khong_can_garmin = lenh in ("/thoisu", "/tin", "/thucdon", "/can")
        if lenh in ("/start", "/caidat") or (not p["co_garmin"] and not khong_can_garmin):
            telegram.goi("sendMessage", chat_id=chat_id, reply_markup=NUT_MIA, text=(
                f"Bấm “Mở Mia” để chọn cách {x} gọi {g}, giờ nhận tin sáng/tối và kết nối Garmin nha 👇"
                if not p["co_garmin"] else
                f"{nguoi.hoa(x)} gửi {g} tin giấc ngủ lúc {p['gio_sang']}:00 và tổng kết ngày lúc {p['gio_toi']}:00. "
                f"Nhắn /ngu hoặc /tongket để xem ngay, bấm dưới đây để đổi cài đặt 👇"))
            return
        try:
            if lenh == "/ngu":
                ngay = hom_nay_vn()
                if "hqua" in text.lower() or "hôm qua" in text.lower():
                    ngay -= timedelta(days=1)
                telegram.goi("sendChatAction", chat_id=chat_id, action="typing")
                telegram.gui(chat_id, bao_cao(ngay, p))
            elif lenh == "/tongket":
                telegram.goi("sendChatAction", chat_id=chat_id, action="typing")
                telegram.gui(chat_id, tong_ket(p=p))
            elif lenh == "/thoisu":
                telegram.goi("sendChatAction", chat_id=chat_id, action="typing")
                telegram.gui(chat_id, ban_tin_thoi_su(p) or f"{nguoi.hoa(x)} chưa lấy được tin thời sự mới nào {g} ơi 📭")
            elif lenh == "/tin":
                telegram.goi("sendChatAction", chat_id=chat_id, action="typing")
                telegram.gui(chat_id, ban_tin(p) or f"Hôm nay chưa có tin mới nào {g} ơi 📭")
            elif lenh == "/thucdon":
                if not p.get("thuc_don"):
                    telegram.goi("sendMessage", chat_id=chat_id, reply_markup=NUT_MIA,
                                 text=f"{nguoi.hoa(g)} bật “Thực đơn” và khai hồ sơ trong Mia trước, rồi {x} soạn cho mỗi ngày nha 👇")
                else:
                    telegram.goi("sendChatAction", chat_id=chat_id, action="typing")
                    telegram.gui(chat_id, thuc_don(p=p))
            elif lenh == "/can":
                telegram.gui(chat_id, can_nang.lenh(text, p))
            else:
                telegram.gui(chat_id, f"{nguoi.hoa(g)} nhắn /ngu (giấc ngủ), /tongket (tổng kết hôm nay), /thoisu, /tin, "
                                      f"/thucdon, /can 60.5 (ghi cân) hoặc /caidat nha.")
        except Exception as e:
            telegram.goi("sendMessage", chat_id=chat_id, text=f"⚠️ {nguoi.hoa(x)} bị lỗi: {type(e).__name__}"[:300])

    def _nut(self, cq: dict):
        data = cq.get("data") or ""
        tu = (cq.get("from") or {}).get("id")
        if not nguoi.la_chu(tu) or ":" not in data:
            telegram.goi("answerCallbackQuery", callback_query_id=cq["id"])
            return
        viec, id_ = data.split(":", 1)
        p = nguoi.lay(id_)
        if not p or viec not in ("duyet", "chan"):
            telegram.goi("answerCallbackQuery", callback_query_id=cq["id"], text="Không thấy người này")
            return
        nguoi.sua(id_, trang_thai="duyet" if viec == "duyet" else "chan")
        telegram.goi("answerCallbackQuery", callback_query_id=cq["id"], text="Xong")
        m = cq.get("message") or {}
        telegram.goi("editMessageText", chat_id=m.get("chat", {}).get("id"), message_id=m.get("message_id"),
                     text=f"{'✅ Đã duyệt' if viec == 'duyet' else '❌ Đã từ chối'} {p['ten']} (id {id_}).")
        if viec == "duyet":
            telegram.goi("sendMessage", chat_id=id_, reply_markup=NUT_MIA,
                         text=f"🎉 {nguoi.hoa(nguoi.ten_chu())} đã duyệt! Bấm “Mở Mia” để chọn cách xưng hô, giờ nhận tin và kết nối Garmin nha.")

    def _ok(self, code: int = 200):
        self.send_response(code)
        self.end_headers()
        self.wfile.write(b"ok")
