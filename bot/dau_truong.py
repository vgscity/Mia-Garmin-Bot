# Tình hình game Đấu Trường PC (vgs.zone) trong ngày — phần RIÊNG của chủ bot, chỉ chạy khi đặt
# BAO_CAO_SECRET (+ BAO_CAO_URL). Số lấy từ cổng chỉ đọc của vgs.zone, so với hôm qua để thấy lên
# hay xuống, rồi nhờ Claude nhận xét vài dòng. Không dùng VGS thì bỏ qua file này.
import json
import os
import urllib.request
from datetime import date, timedelta
from html import escape

from . import ai, nguoi
from .ngu import THU, hom_nay_vn

CONG = os.environ.get("BAO_CAO_URL", "https://vgs.zone/api/bao-cao-ngay")


def co_cau_hinh() -> bool:
    return bool(os.environ.get("BAO_CAO_SECRET"))

TEN_NGUON = {
    "don-lap": "Tiệm lắp máy", "dap-do": "Lò đập đồ", "mua-hang": "Mua ở cửa hàng", "ban-do": "Bán đồ",
    "hop": "Mở hộp", "dao": "Đào coin", "sua-may": "Tiệm sửa máy", "cho-mua": "Chợ (mua)",
    "cho-ban": "Chợ (bán)", "cho-phi": "Phí treo chợ", "os": "Màn hình OS", "nhiem-vu": "Nhiệm vụ",
    "che-tao": "Hộp may rủi", "sua-do": "Sửa đồ", "thu": "Thư ban tổ chức", "cuop-duoc": "Cướp được",
    "cuop-mat": "Bị cướp", "nang-bac": "Lò nâng cấp", "len-cap": "Lên cấp", "doi-do": "Đổi đồ",
    "thanh-tuu": "Thành tựu", "do-vui": "Đố vui", "dan-dao": "Bảo dưỡng dàn đào", "khien": "Bật khiên",
    "bench": "Benchmark", "boss": "Đánh boss", "che-bua": "Bùa", "lap-doi": "Lập đội",
    "mau-vo": "Màu vỏ case", "phong-may": "Phòng Máy", "quay-kc": "Quầy kim cương", "thu-hoi": "BTC thu hồi",
}
BAC = {"common": "Thường", "rare": "Hiếm", "epic": "Siêu hiếm", "legendary": "Huyền thoại", "mythic": "Thần thoại"}
BUOI = {"trua": "trưa", "toi": "tối"}

SYSTEM = """Bạn là Mia, giúp {goi} (chủ game) theo dõi game "Đấu Trường PC" trên vgs.zone.
Gọi "{goi}", xưng "{xung}". Đầu vào: số liệu hôm nay ("hom_nay") và hôm qua ("hom_qua") từ sổ máy chủ.
"vang.vao" là vàng game in ra cho người chơi, "vang.ra" là vàng bị rút về (lò, cửa hàng, phí...).
"nguon" là từng nguồn trong sổ ví, vang dương là in ra, âm là rút về.

Viết 2–4 gạch đầu dòng, mỗi dòng bắt đầu bằng "• ", 1–2 câu ngắn, có con số:
- Điều đáng chú ý nhất hôm nay so với hôm qua (người chơi, lạm phát vàng, nguồn nào tăng/giảm mạnh).
- Nếu có dấu hiệu bất thường (một nguồn in vàng nhảy vọt, chợ bán món rẻ với giá cao bất thường — có thể là chuyển vàng giữa nick, cướp dồn dập) thì nêu nhẹ để {goi} để ý.
Số lớn viết gọn kiểu "15,2 triệu", "434 nghìn". Gọi nguồn bằng đúng tên trong dữ liệu.
Đừng nhắc lại những con số tổng mà không có nhận xét — phần số liệu {goi} đã thấy ở trên rồi.
Chỉ dùng số có trong dữ liệu, không bịa. Chữ thuần, không markdown, không lời chào."""


def _cho_ai(d: dict | None) -> dict | None:
    # Đổi mã nguồn sang tên tiếng Việt để Claude khỏi đọc "dap-do" cho người đọc.
    if not d:
        return d
    return {**d, "nguon": [{**n, "nguon": TEN_NGUON.get(n["nguon"], n["nguon"])} for n in d["nguon"]],
            "cho": {**d["cho"], "dat": d["cho"].get("dat") and {**d["cho"]["dat"], "bac": BAC.get(d["cho"]["dat"]["bac"], d["cho"]["dat"]["bac"])}}}


def _lay(ngay: date) -> dict:
    req = urllib.request.Request(f"{CONG}?ngay={ngay.isoformat()}", headers={
        "Authorization": f"Bearer {os.environ['BAO_CAO_SECRET']}", "User-Agent": "garmin-bot",
    })
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


def _so(n) -> str:
    return f"{round(n):,}".replace(",", ".")


def _gon(n) -> str:
    # 32.010.382 → "32 triệu"; dưới 1 triệu giữ nguyên.
    n = round(n)
    if abs(n) >= 1_000_000:
        return f"{n / 1_000_000:.1f}".replace(".", ",").replace(",0", "") + " triệu"
    return _so(n)


def _lech(nay: float, qua: float) -> str:
    if not qua:
        return ""
    p = (nay - qua) / abs(qua) * 100
    return f" ({'▲' if p >= 0 else '▼'}{abs(p):.0f}% so hôm qua)"


def soan_tin(d: dict, q: dict | None, ngay: date, nhan_xet: str | None, p: dict | None = None) -> str:
    p = p or nguoi._chu()
    q = q or {}
    ng, ngq = d["nguoi"], q.get("nguoi") or {}
    dong = [f"🎮 <b>Đấu Trường PC — {THU[ngay.weekday()]}, {ngay:%d/%m}</b>", ""]
    dong.append(f"👥 <b>{ng['choi']}</b> người chơi{_lech(ng['choi'], ngq.get('choi', 0))}"
                f" · {ng['nickMoi']} nick mới")

    v, vq = d["vang"], q.get("vang") or {}
    rong = v["vao"] - v["ra"]
    dong.append(f"💰 Vàng in ra <b>{_gon(v['vao'])}</b>{_lech(v['vao'], vq.get('vao', 0))}"
                f" · rút về {_gon(v['ra'])} → {'dư' if rong >= 0 else 'hụt'} <b>{_gon(abs(rong))}</b>")
    g = d["gem"]
    dong.append(f"💎 Kim cương phát {_so(g['vao'])} · tiêu {_so(g['ra'])}")

    vao = [n for n in d["nguon"] if n["vang"] > 0][:3]
    ra = [n for n in d["nguon"] if n["vang"] < 0][:3]
    ten = lambda n: escape(TEN_NGUON.get(n["nguon"], n["nguon"]))
    if vao:
        dong.append("   ↗ " + " · ".join(f"{ten(n)} {_gon(n['vang'])}" for n in vao))
    if ra:
        dong.append("   ↘ " + " · ".join(f"{ten(n)} {_gon(-n['vang'])}" for n in ra))

    for b in d["boss"]:
        ket = "hạ gục ✅" if b["haGuc"] else f"còn {b['mauConLai'] / max(1, b['mauToiDa']) * 100:.0f}% máu"
        dong.append(f"👾 Boss {BUOI.get(b['buoi'], b['buoi'])}: {ket} · {b['nguoi']} người đánh"
                    + (f" · đầu bảng {escape(b['dauBang'])}" if b["dauBang"] else ""))

    c = d["cho"]
    if c["luot"]:
        dat = c.get("dat")
        dong.append(f"🛒 Chợ: {c['luot']} món bán được, {_gon(c['vang'])} vàng"
                    + (f" · đắt nhất {escape(dat['ten'])} [{BAC.get(dat['bac'], dat['bac'])}] {_gon(dat['gia'])}" if dat else ""))
    k = d["cuop"]
    if k["tran"]:
        dong.append(f"🦹 Cướp kho: {k['tran']} trận, {k['thang']} lần thành · {_gon(k['vang'])} vàng, {k['mon']} món bị vơ")

    if d["top"]:
        dong += ["", "🏆 <b>Lời vàng nhiều nhất</b>"]
        dong += [f"{i}. {escape(t['ten'])} +{_gon(t['vang'])}" for i, t in enumerate(d["top"], 1)]

    if nhan_xet:
        dong += ["", f"🧠 <b>{nguoi.hoa(p['xung'])} để ý</b>", escape(nhan_xet)]
    return "\n".join(dong)


def bao_cao_game(ngay: date | None = None, p: dict | None = None) -> str:
    p = p or nguoi._chu()
    ngay = ngay or hom_nay_vn()
    d = _lay(ngay)
    try:
        q = _lay(ngay - timedelta(days=1))
    except Exception:
        q = None
    nhan_xet = None
    try:
        nhan_xet = ai.goi_ai(ai._xung(SYSTEM, p), {"hom_nay": _cho_ai(d), "hom_qua": _cho_ai(q)}, max_tokens=800)
    except Exception as e:
        print(f"AI nhận xét game lỗi: {type(e).__name__}: {e}")
    return soan_tin(d, q, ngay, nhan_xet, p)
