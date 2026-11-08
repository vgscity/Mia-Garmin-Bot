# Chụp ảnh bữa ăn (08/11/2026): gửi ảnh cho Mia → Claude đoán món, lượng, calo, đạm → ghi vào
# ngày (garmin_kv "bua:<id>:<YYYY-MM-DD>") để tổng kết tối và hỏi đáp dùng lại. Là ước lượng từ ảnh,
# sai số lớn — luôn nói rõ như vậy. Giới hạn ANH_MOI_NGAY ảnh / người / ngày cho đỡ tốn.
import base64
import json
import os
import urllib.request
from datetime import datetime
from html import escape

from . import ai, kho, nguoi
from .ngu import VN, hom_nay_vn
from .tong_ket import _so

ANH_MOI_NGAY = int(os.environ.get("ANH_MOI_NGAY", "12"))
TO_TOI_DA = 5 * 1024 * 1024

SYSTEM = """Bạn là Mia, xem ảnh bữa ăn giúp {goi}. Gọi "{goi}", xưng "{xung}".
Nhìn ảnh, đoán từng món và lượng (theo chén, đĩa, gram ước chừng) theo khẩu phần thường gặp ở Việt Nam, rồi ước calo và đạm.
Ảnh không có đồ ăn hay thức uống thì co_do_an=false, mon rỗng, các số bằng 0.
"nhan_xet": 1–2 câu ngắn, thân thiện, có ích (ví dụ bữa này nhiều tinh bột, thêm rau; hoặc đủ đạm rồi). Không chẩn đoán bệnh.
{them}Chữ thuần, không markdown."""

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "co_do_an": {"type": "BOOLEAN"},
        "mon": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "ten": {"type": "STRING"}, "luong": {"type": "STRING"}, "kcal": {"type": "INTEGER"}}}},
        "tong_kcal": {"type": "INTEGER"},
        "dam_g": {"type": "INTEGER"},
        "nhan_xet": {"type": "STRING"},
    },
}


def _key(id_, ngay) -> str:
    return f"bua:{id_}:{ngay.isoformat()}"


def trong_ngay(p: dict, ngay=None) -> list[dict]:
    try:
        return json.loads(kho.doc(_key(p["id"], ngay or hom_nay_vn())) or "[]")
    except Exception:
        return []


def dong_tong(p: dict, ngay=None) -> str | None:
    ds = trong_ngay(p, ngay)
    if not ds:
        return None
    return f"🍽 Bữa ăn chụp hôm nay: {len(ds)} bữa, ~{_so(sum(b['kcal'] for b in ds))} kcal · {sum(b['dam'] for b in ds)}g đạm"


def _tai_anh(file_id: str) -> tuple[bytes, str]:
    from . import telegram

    f = telegram.goi("getFile", file_id=file_id).get("result") or {}
    duong = f.get("file_path") or ""
    if not duong or (f.get("file_size") or 0) > TO_TOI_DA:
        raise ValueError("Ảnh lớn quá hoặc không tải được.")
    url = f"https://api.telegram.org/file/bot{os.environ['BOT_TOKEN']}/{duong}"
    with urllib.request.urlopen(url, timeout=20) as r:
        du_lieu = r.read(TO_TOI_DA + 1)
    if len(du_lieu) > TO_TOI_DA:
        raise ValueError("Ảnh lớn quá.")
    duoi = duong.rsplit(".", 1)[-1].lower()
    loai = {"png": "image/png", "webp": "image/webp", "gif": "image/gif"}.get(duoi, "image/jpeg")
    return du_lieu, loai


def xu_ly_anh(p: dict, file_id: str, chu_kem: str = "") -> str:
    g, x = p["goi"], p["xung"]
    ngay = hom_nay_vn()
    dem_key = f"dem_anh:{p['id']}:{ngay.isoformat()}"
    dem = int(kho.doc(dem_key) or 0)
    if not nguoi.la_chu(p["id"]) and dem >= ANH_MOI_NGAY:
        return f"Hôm nay {g} gửi {ANH_MOI_NGAY} ảnh rồi, mai {x} xem tiếp nha 🙏"
    kho.ghi(str(dem + 1), dem_key)

    anh, loai = _tai_anh(file_id)
    them = f"Ghi chú của {g} kèm ảnh: \"{chu_kem.strip()[:200]}\". " if chu_kem.strip() else ""
    system = SYSTEM.replace("{goi}", g).replace("{xung}", x).replace("{them}", them)
    noi_dung = [
        {"type": "image", "source": {"type": "base64", "media_type": loai, "data": base64.standard_b64encode(anh).decode()}},
        {"type": "text", "text": "Ảnh bữa ăn đây, đoán giúp nha."},
    ]
    kq = json.loads(ai.goi_ai_noi_dung(system, noi_dung, max_tokens=5000, schema=SCHEMA))
    if not kq.get("co_do_an") or not kq.get("mon"):
        return f"{nguoi.hoa(x)} không thấy đồ ăn trong ảnh này {g} ơi. Chụp gần đĩa đồ ăn rồi gửi lại nha 📸"

    ds = trong_ngay(p, ngay)
    ds.append({"luc": datetime.now(VN).strftime("%H:%M"), "mon": [m["ten"] for m in kq["mon"]],
               "kcal": int(kq.get("tong_kcal") or 0), "dam": int(kq.get("dam_g") or 0)})
    kho.ghi(json.dumps(ds, ensure_ascii=False), _key(p["id"], ngay))

    dong = [f"🍽 <b>{nguoi.hoa(x)} đoán bữa này nè</b>"]
    dong += [f"• {escape(m['ten'])} ({escape(m.get('luong') or '')}) ~{_so(m.get('kcal') or 0)} kcal" for m in kq["mon"]]
    dong.append(f"Tổng ~<b>{_so(kq.get('tong_kcal') or 0)}</b> kcal · {kq.get('dam_g') or 0}g đạm")
    tong = sum(b["kcal"] for b in ds)
    dong.append(f"Hôm nay {g} đã chụp {len(ds)} bữa, ~{_so(tong)} kcal.")
    if p.get("thuc_don"):
        from .thuc_don import muc_an
        lo, hi, _ = muc_an(p)
        dong.append(f"Mức gợi ý cả ngày của {g}: {_so(lo)}–{_so(hi)} kcal.")
    if kq.get("nhan_xet"):
        dong += ["", "💬 " + escape(kq["nhan_xet"])]
    dong.append(f"<i>Số đoán từ ảnh, sai số khá lớn, {g} xem cho biết thôi nha.</i>")
    return "\n".join(dong)
