# API cho Mini App Mia (08/11/2026). POST JSON {initData, hd, ...}; người gọi xác thực bằng chữ ký
# initData của Telegram (HMAC theo BOT_TOKEN), không tin id gửi lên.
#   hd=toi      → thông tin của mình (chưa có thì đăng ký; tự duyệt trừ khi DUYET_TAY=1)
#   hd=luu      → goi, xung, gio_sang, gio_toi (+ từ 08/11 đợt 2: tin_thoi_su, tin_xa_hoi, tin_cong_nghe, thuc_don,
#                 gioi_tinh, cao_cm, muc_tieu_kg, an_sang, an_uong — thiếu trường nào thì giữ nguyên)
#   hd=can      → kg: ghi cân hôm nay; hd=can_xem → sổ cân + tiến độ; hd=can_xoa → xoá số hôm nay
#   hd=thucdon  → soạn và gửi thực đơn hôm nay ngay (đã bật thực đơn)
#   hd=nha_ds / nha_tao_ma / nha_nhap (ma, nhan) / nha_bo (khac, chieu=xem|cho) → người nhà trông nhau (bot/nguoi_nha.py)
#   luu còn nhận: thoi_tiet, vi_do, kinh_do, noi, nhac_van_dong, tong_ket_tuan (đợt 3, 08/11/2026)
#   hd=garmin   → email, mat_khau: đăng nhập Garmin. Garmin đòi MFA thì request này GIỮ kết nối,
#                 ghi garmin_kv mfa:<id>='can', chờ hd=ma ghi mã vào (tối đa ~4 phút) rồi đăng nhập nốt.
#                 Thư viện giữ phiên MFA trong bộ nhớ nên không tách ra hai lượt gọi được.
#                 Mật khẩu chỉ dùng trong lượt gọi này: không lưu, không in log.
#   hd=mfa      → trạng thái chờ mã ('can' | '' )
#   hd=ma       → ma: mã MFA
#   hd=thu      → gửi ngay tin giấc ngủ sáng nay cho chính mình
#   hd=ngat     → xoá token Garmin của mình
import hashlib
import hmac
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qsl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import can_nang, kho, nguoi, nguoi_nha, telegram  # noqa: E402
from bot.nguoi import bao_ba_duyet, ten_cua  # noqa: E402
from bot.thuc_don import thuc_don  # noqa: E402

CHO_MA_GIAY = 240


def xac_thuc(init_data: str) -> dict | None:
    cap = dict(parse_qsl(init_data or "", keep_blank_values=True))
    hash_ = cap.pop("hash", "")
    if not hash_:
        return None
    chuoi = "\n".join(f"{k}={v}" for k, v in sorted(cap.items()))
    khoa = hmac.new(b"WebAppData", os.environ["BOT_TOKEN"].encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(hmac.new(khoa, chuoi.encode(), hashlib.sha256).hexdigest(), hash_):
        return None
    if time.time() - int(cap.get("auth_date") or 0) > 86400:
        return None
    try:
        return json.loads(cap.get("user") or "{}") or None
    except ValueError:
        return None


def _key_mfa(id_) -> str:
    return f"mfa:{id_}"


def dang_nhap_garmin(id_, email: str, mat_khau: str) -> str:
    from garminconnect import Garmin

    kho.ghi("", _key_mfa(id_))

    def cho_ma() -> str:
        kho.ghi("can", _key_mfa(id_))
        het = time.time() + CHO_MA_GIAY
        while time.time() < het:
            v = kho.doc(_key_mfa(id_)) or ""
            if v.startswith("ma:"):
                kho.ghi("", _key_mfa(id_))
                return v[3:]
            time.sleep(2)
        kho.ghi("", _key_mfa(id_))
        raise TimeoutError("Hết giờ chờ mã xác minh")

    g = Garmin(email, mat_khau, prompt_mfa=cho_ma)
    g.login()
    kho.ghi(g.client.dumps(), nguoi.key_token(id_))
    nguoi.sua(id_, co_garmin=1)
    try:
        return g.get_full_name() or ""
    except Exception:
        return ""


def loi_garmin(e: Exception) -> str:
    chu = f"{type(e).__name__}: {e}".lower()
    if "timeout" in chu and "mã" in chu:
        return "Hết giờ chờ mã xác minh, thử lại nhé."
    if "401" in chu or "auth" in chu or "password" in chu or "credential" in chu:
        return "Sai email hoặc mật khẩu Garmin."
    if "429" in chu or "too many" in chu or "rate" in chu:
        return "Garmin đang chặn đăng nhập vì thử nhiều lần. Đợi khoảng 1 tiếng rồi thử lại."
    if "mfa" in chu or "verification" in chu:
        return "Mã xác minh không đúng hoặc đã hết hạn."
    return f"Garmin báo lỗi ({type(e).__name__}). Thử lại sau ít phút."


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._json(400, {"loi": "Dữ liệu hỏng"})
        u = xac_thuc(body.get("initData", ""))
        if not u or not u.get("id"):
            return self._json(401, {"loi": "Mở Mia từ trong Telegram nhé."})
        id_ = str(u["id"])
        hd = body.get("hd")
        try:
            if hd == "toi":
                p, moi = nguoi.dang_ky(id_, ten_cua(u))
                if moi and not nguoi.la_chu(id_):
                    bao_ba_duyet(u)
                return self._json(200, self._cong_khai(p))

            p = nguoi.lay(id_)
            if not p or p["trang_thai"] != "duyet":
                return self._json(403, {"loi": "Chưa được duyệt."})

            if hd == "luu":
                goi = str(body.get("goi") or "").strip().lower()[:20]
                xung = str(body.get("xung") or "").strip().lower()[:20]
                gs, gt = int(body.get("gio_sang", -1)), int(body.get("gio_toi", -1))
                if not goi or not xung or gs not in nguoi.GIO_SANG or gt not in nguoi.GIO_TOI:
                    return self._json(400, {"loi": "Thiếu cách xưng hô hoặc giờ chưa hợp lệ."})
                cap = {"goi": goi, "xung": xung, "gio_sang": gs, "gio_toi": gt}
                for k in ("tin_thoi_su", "tin_xa_hoi", "tin_cong_nghe", "thuc_don", "an_sang", "thoi_tiet", "nhac_van_dong", "tong_ket_tuan"):
                    if k in body:
                        cap[k] = 1 if body.get(k) else 0
                if "gioi_tinh" in body:
                    gt_ = str(body.get("gioi_tinh") or "")
                    if gt_ not in ("", "nam", "nu"):
                        return self._json(400, {"loi": "Giới tính chưa hợp lệ."})
                    cap["gioi_tinh"] = gt_
                if "cao_cm" in body:
                    cao = int(float(body.get("cao_cm") or 0))
                    if cao and not 100 <= cao <= 230:
                        return self._json(400, {"loi": "Chiều cao chưa hợp lệ (100–230 cm)."})
                    cap["cao_cm"] = cao
                if "muc_tieu_kg" in body:
                    mt = round(float(body.get("muc_tieu_kg") or 0), 1)
                    if mt and not 35 <= mt <= 200:
                        return self._json(400, {"loi": "Cân mục tiêu chưa hợp lệ (35–200 kg)."})
                    cap["muc_tieu_kg"] = mt
                if "an_uong" in body:
                    cap["an_uong"] = str(body.get("an_uong") or "").strip()[:200]
                if "vi_do" in body and "kinh_do" in body:
                    vd, kd = float(body.get("vi_do") or 0), float(body.get("kinh_do") or 0)
                    if (vd or kd) and not (-90 <= vd <= 90 and -180 <= kd <= 180):
                        return self._json(400, {"loi": "Vị trí chưa hợp lệ."})
                    cap["vi_do"], cap["kinh_do"] = round(vd, 3), round(kd, 3)
                    cap["noi"] = str(body.get("noi") or "").strip()[:40]
                return self._json(200, self._cong_khai(nguoi.sua(id_, **cap)))

            if hd == "can":
                kg = can_nang.doc_so(str(body.get("kg") or ""))
                if kg is None:
                    return self._json(400, {"loi": "Số cân chưa hợp lệ (35–200 kg)."})
                return self._json(200, {"chu": can_nang.ghi_can(kg, p), **self._so_can(p)})

            if hd == "can_xem":
                return self._json(200, {"chu": can_nang.tien_do(p=p), **self._so_can(p)})

            if hd == "can_xoa":
                return self._json(200, {"chu": can_nang.xoa_hom_nay(p), **self._so_can(p)})

            if hd == "nha_ds":
                return self._json(200, {"dang_xem": nguoi_nha.dang_xem(id_), "cho_xem": nguoi_nha.cho_xem(id_)})

            if hd == "nha_tao_ma":
                return self._json(200, {"ma": nguoi_nha.tao_ma(id_), "gio": nguoi_nha.SONG_MA // 3600})

            if hd == "nha_nhap":
                try:
                    nguoi_nha.nhap_ma(id_, str(body.get("ma") or ""), str(body.get("nhan") or ""))
                except ValueError as e:
                    return self._json(400, {"loi": str(e)})
                return self._json(200, {"dang_xem": nguoi_nha.dang_xem(id_), "cho_xem": nguoi_nha.cho_xem(id_)})

            if hd == "nha_bo":
                chieu = "xem" if body.get("chieu") == "xem" else "cho"
                nguoi_nha.bo(id_, str(body.get("khac") or ""), chieu)
                return self._json(200, {"dang_xem": nguoi_nha.dang_xem(id_), "cho_xem": nguoi_nha.cho_xem(id_)})

            if hd == "thucdon":
                if not p.get("thuc_don"):
                    return self._json(400, {"loi": "Bật “Thực đơn” rồi lưu cài đặt trước nhé."})
                telegram.gui(id_, thuc_don(p=p))
                return self._json(200, {"ok": True})

            if hd == "garmin":
                email = str(body.get("email") or "").strip()
                mat_khau = str(body.get("mat_khau") or "")
                if "@" not in email or not mat_khau:
                    return self._json(400, {"loi": "Nhập email và mật khẩu Garmin."})
                try:
                    ten = dang_nhap_garmin(id_, email, mat_khau)
                except Exception as e:
                    print(f"Garmin đăng nhập lỗi cho {id_}: {type(e).__name__}")
                    return self._json(400, {"loi": loi_garmin(e)})
                finally:
                    mat_khau = ""
                if not nguoi.la_chu(id_):
                    telegram.goi("sendMessage", chat_id=nguoi.chu(), text=f"🔗 {p['ten']} đã kết nối Garmin với Mia.")
                return self._json(200, {**self._cong_khai(nguoi.lay(id_)), "ten_garmin": ten})

            if hd == "mfa":
                return self._json(200, {"trang_thai": kho.doc(_key_mfa(id_)) or ""})

            if hd == "ma":
                ma = "".join(c for c in str(body.get("ma") or "") if c.isdigit())[:10]
                if len(ma) < 4:
                    return self._json(400, {"loi": "Mã xác minh chưa đúng."})
                kho.ghi(f"ma:{ma}", _key_mfa(id_))
                return self._json(200, {"ok": True})

            if hd == "thu":
                from bot.ngu import bao_cao
                telegram.gui(id_, bao_cao(p=p))
                return self._json(200, {"ok": True})

            if hd == "ngat":
                nguoi.xoa_token(id_)
                return self._json(200, self._cong_khai(nguoi.lay(id_)))

            return self._json(400, {"loi": "Không rõ việc cần làm."})
        except Exception as e:
            print(f"Mini App lỗi ({hd}): {type(e).__name__}: {e}")
            return self._json(500, {"loi": f"Mia bị lỗi: {type(e).__name__}"})

    @staticmethod
    def _cong_khai(p: dict) -> dict:
        return {k: p[k] for k in nguoi.COT if k != "id"} | {
            "la_chu": nguoi.la_chu(p["id"]),
            "gio_sang_cho_phep": list(nguoi.GIO_SANG), "gio_toi_cho_phep": list(nguoi.GIO_TOI),
            "xung_theo_goi": nguoi.XUNG_THEO_GOI,
        }

    @staticmethod
    def _so_can(p: dict) -> dict:
        ds = can_nang.doc(p)
        return {"ds": ds[-30:], "muc_tieu_kg": can_nang.muc_tieu(p), "da_can_hom_nay": can_nang.da_can_hom_nay(p)}

    def _json(self, code: int, data: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
