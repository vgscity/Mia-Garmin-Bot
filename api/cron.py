# Vercel Cron mỗi giờ (từ 08/11/2026, Mia cho cả nhà): ai đặt giờ sáng = giờ VN hiện tại thì nhận
# báo giấc ngủ (+ tin thời sự / tin công nghệ nếu người đó bật, + nhắc cân nếu có mục tiêu cân mà
# hôm nay chưa ghi); ai đặt giờ tối = giờ hiện tại thì nhận tổng kết ngày. Riêng chủ bot: tối kèm
# tình hình game Đấu Trường PC nếu có đặt BAO_CAO_SECRET (phần riêng của VGS).
# ?loai=trua (0 3 * * * UTC = 10h VN): thực đơn cho mọi người đã bật "thực đơn" trong Mia (bot/thuc_don.py).
# Thử không gửi: GET /api/cron?dry=1[&gio=7], ?dry=1&loai=trua, hoặc ?dry=1&tin=thoi-su|xa-hoi|cong-nghe
# kèm Authorization: Bearer <CRON_SECRET>.
# Đợt 3 (08/11/2026): tin sáng kèm dòng thời tiết (nếu bật), Chủ nhật thêm tổng kết tuần, thêm tin "người nhà"
# cho ai đang xem người nhà; 17h nhắc vận động cho ai bật mà chưa được nửa mục tiêu bước.
# Người nào lỗi thì người khác vẫn nhận; lỗi Garmin báo cho chính người đó + một dòng cho chủ bot.
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import can_nang, nguoi, telegram  # noqa: E402
from bot import dau_truong, nguoi_nha, thoi_tiet, tuan, van_dong  # noqa: E402
from bot.ngu import VN, bao_cao  # noqa: E402
from bot.thuc_don import thuc_don  # noqa: E402
from bot.tin import ban_tin, ban_tin_thoi_su, ban_tin_xa_hoi  # noqa: E402
from bot.tong_ket import tong_ket  # noqa: E402


def bao_cao_sang(p: dict) -> str:
    text = bao_cao(p=p)
    tt = thoi_tiet.dong_thoi_tiet(p)
    if tt:
        text += "\n\n" + tt
    try:
        if can_nang.muc_tieu(p) and not can_nang.da_can_hom_nay(p):
            g, x = p["goi"], p["xung"]
            text += (f"\n\n⚖️ {nguoi.hoa(g)} cân xong nhắn {x} kiểu <b>/can 75.2</b> nha, "
                     f"{x} theo dõi đường về {can_nang.muc_tieu(p):g}kg cho {g}.")
    except Exception as e:
        print(f"Không đọc được cân nặng của {p.get('ten')}: {type(e).__name__}: {e}")
    return text


def viec_cua(p: dict, gio: int) -> list[tuple[str, callable]]:
    ba = nguoi.la_chu(p["id"])
    viec = []
    if p["gio_sang"] == gio:
        if p["co_garmin"]:
            viec.append(("giấc ngủ từ Garmin", lambda: bao_cao_sang(p)))
            if p.get("tong_ket_tuan") and datetime.now(VN).weekday() == 6:
                viec.append(("tổng kết tuần từ Garmin", lambda: tuan.tong_ket_tuan(p)))
        elif p.get("thoi_tiet"):
            viec.append(("thời tiết", lambda: thoi_tiet.dong_thoi_tiet(p)))
        viec.append(("tin người nhà", lambda: nguoi_nha.tin_sang(p)))
        if p.get("tin_thoi_su"):
            viec.append(("tin thời sự", lambda: ban_tin_thoi_su(p)))
        if p.get("tin_xa_hoi"):
            viec.append(("tin xã hội · văn hoá · thể thao", lambda: ban_tin_xa_hoi(p)))
        if p.get("tin_cong_nghe"):
            viec.append(("tin công nghệ", lambda: ban_tin(p)))
    if gio == van_dong.GIO_NHAC and p["co_garmin"] and p.get("nhac_van_dong"):
        viec.append(("nhắc vận động", lambda: van_dong.nhac(p)))
    if p["gio_toi"] == gio:
        if p["co_garmin"]:
            viec.append(("tổng kết ngày từ Garmin", lambda: tong_ket(p=p)))
        if ba and dau_truong.co_cau_hinh():
            viec.append(("tình hình Đấu Trường PC", lambda: dau_truong.bao_cao_game(p=p)))
    return viec


def chay_cho(p: dict, gio: int, dry: bool) -> tuple[list[str], bool]:
    ra, loi = [], False
    for ten, ham in viec_cua(p, gio):
        try:
            text = ham()
            if not text:
                continue
            if not dry:
                telegram.gui(p["id"], text)
        except Exception as e:  # báo lỗi, đừng im lặng
            loi = True
            text = f"⚠️ {nguoi.hoa(p['xung'])} không lấy được {ten}: {type(e).__name__}: {e}"[:500]
            if not dry:
                telegram.goi("sendMessage", chat_id=p["id"], text=text)
                if not nguoi.la_chu(p["id"]) and "Garmin" in ten:
                    telegram.goi("sendMessage", chat_id=nguoi.chu(),
                                 text=f"⚠️ Mia lỗi với {p['ten']} ({ten}): {type(e).__name__}"[:300])
        ra.append(f"[{p['ten']}] {text}")
    return ra, loi


def trua_cho(p: dict, dry: bool) -> tuple[str, bool]:
    try:
        text = thuc_don(luu=not dry, p=p)
        if text and not dry:
            telegram.gui(p["id"], text)
        return f"[{p['ten']}] {text or ''}", False
    except Exception as e:
        text = f"⚠️ {nguoi.hoa(p['xung'])} không lấy được thực đơn hôm nay: {type(e).__name__}: {e}"[:500]
        if not dry:
            telegram.goi("sendMessage", chat_id=p["id"], text=text)
        return f"[{p['ten']}] {text}", True


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        secret = os.environ.get("CRON_SECRET")
        if secret and self.headers.get("Authorization") != f"Bearer {secret}":
            return self._tra(401, "unauthorized")
        path = self.path or ""
        dry = "dry=1" in path
        if "loai=trua" in path:
            return self._trua(dry)
        m = re.search(r"tin=(thoi-su|xa-hoi|cong-nghe)", path)
        if m and dry:  # soạn thử một bản tin cho chủ bot, không gửi
            ham = {"thoi-su": ban_tin_thoi_su, "xa-hoi": ban_tin_xa_hoi, "cong-nghe": ban_tin}[m.group(1)]
            return self._tra(200, ham(nguoi.lay(nguoi.chu()) or nguoi._chu()) or "(không có tin)")
        m = re.search(r"gio=(\d+)", path)
        gio = int(m.group(1)) if m else datetime.now(VN).hour
        ds = [p for p in nguoi.tat_ca_duyet() if viec_cua(p, gio)]
        if not ds:
            return self._tra(200, f"{gio}h: không ai nhận tin")
        with ThreadPoolExecutor(max_workers=4) as pool:
            kq = list(pool.map(lambda p: chay_cho(p, gio, dry), ds))
        loi = any(l for _, l in kq)
        return self._tra(500 if loi else 200, "\n\n=====\n\n".join(t for ra, _ in kq for t in ra))

    def _trua(self, dry: bool):
        ds = [p for p in nguoi.tat_ca_duyet() if p.get("thuc_don")]
        if not ds:
            c = nguoi.lay(nguoi.chu()) or nguoi._chu()
            return self._tra(200, f"trưa: không ai bật thực đơn (chủ bot thuc_don={c.get('thuc_don')}, "
                                  f"gioi_tinh='{c.get('gioi_tinh')}'; {nguoi.HO_SO_LOI or 'CHU_HO_SO đọc được'})")
        with ThreadPoolExecutor(max_workers=3) as pool:
            kq = list(pool.map(lambda p: trua_cho(p, dry), ds))
        loi = any(l for _, l in kq)
        return self._tra(500 if loi else 200, "\n\n=====\n\n".join(t for t, _ in kq))

    def _tra(self, code: int, body: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())
