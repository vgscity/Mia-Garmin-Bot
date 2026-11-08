# Thực đơn hằng ngày cho từng người (10h VN), soạn theo hồ sơ tự khai trong Mini App — giới tính,
# chiều cao, cân mục tiêu, có ăn sáng không, món thích / kiêng. Chủ bot có thể ấn định thêm trong
# CHU_HO_SO: kcal_min, kcal_max, dam_min, dam_uu_tien (câu dặn Claude về loại đạm).
# Claude soạn, dựa vào calo đốt hôm qua (nếu có Garmin); nhớ thực đơn 7 ngày gần nhất để không lặp món.
import json
from datetime import timedelta
from html import escape

from . import ai, can_nang, kho, nguoi
from .ngu import THU, hom_nay_vn, ket_noi
from .tong_ket import _so

KEY = "thuc_don_gan_day"
NHO = 7

SYSTEM = """Bạn là Mia, lo bữa ăn hằng ngày cho {goi}. Gọi "{goi}", xưng "{xung}", giọng ngọt ngào, quan tâm.
Hồ sơ của {goi}: {ho_so}.
{muc_tieu_chu}

Soạn thực đơn hôm nay cho các bữa: {cac_bua}.
- Đạm nạc làm món chính (ức gà, đùi gà bỏ da, thăn bò, bắp bò, cá, tôm, trứng, đậu hũ); hai bữa chính khác loại đạm nhau.
  {uu_tien_dam}
- Mỗi bữa: nhiều rau (ưu tiên rau Việt dễ mua: rau muống, cải, bông cải, dưa leo, cà chua, bí xanh, mồng tơi, rau thơm...), tinh bột vừa phải và chậm (cơm gạo lứt, khoai lang, bún gạo lứt), bữa tối ít tinh bột hơn bữa trưa.
- Cách nấu ít dầu: áp chảo, nướng, luộc, hấp, xào nhanh ít dầu, canh. Món kiểu Việt, nấu ở nhà trong 30 phút, nguyên liệu mua ở chợ/siêu thị Việt Nam.
- Tổng cả ngày {kcal_min}–{kcal_max} kcal, đạm từ {dam_min}g trở lên, chia đều cho các bữa.
  Hôm qua vận động nhiều (calo đốt cao, có buổi tập) thì lấy mức cao và tăng đạm; ít vận động thì lấy mức thấp.
  Tính kcal thật sát định lượng: 100g ức gà ~165 kcal, 100g thăn bò ~200 kcal, 100g cá hồi ~210 kcal,
  1 chén cơm gạo lứt ~220 kcal, 100g khoai lang ~90 kcal, 1 quả trứng ~75 kcal, 1 muỗng dầu ~120 kcal. Thiếu thì thêm tinh bột chậm, trái cây, đậu, trứng, sữa chua không đường.
- KHÔNG lặp món trong danh sách "da_an_gan_day"; đổi cách chế biến và rau đi kèm cho phong phú.
- Nếu có "chinh_calo_theo_toc_do_giam" thì nhắc ngắn cho {goi} biết {xung} đã chỉnh lượng ăn và vì sao.
- "loi_nhan": 1–2 câu dặn dò dựa vào số liệu hôm qua (ví dụ uống đủ nước, ăn chậm, bữa tối trước 19h30). Không chẩn đoán bệnh.
Định lượng thực tế (gram, chén, muỗng). Chữ thuần, không markdown."""

MON = {
    "type": "OBJECT",
    "properties": {
        "ten": {"type": "STRING", "description": "Tên bữa, ví dụ: Ức gà áp chảo sốt chanh + salad dưa leo + ½ chén cơm gạo lứt"},
        "nguyen_lieu": {"type": "ARRAY", "items": {"type": "STRING"}},
        "cach_lam": {"type": "STRING", "description": "2–3 câu ngắn"},
        "kcal": {"type": "INTEGER"},
        "dam_g": {"type": "INTEGER"},
    },
    "required": ["ten", "nguyen_lieu", "cach_lam", "kcal", "dam_g"],
}


def _schema(an_sang: bool) -> dict:
    bua = {"trua": MON, "toi": MON, "loi_nhan": {"type": "STRING"}}
    if an_sang:
        bua = {"sang": MON, **bua}
    return {"type": "OBJECT", "properties": bua, "required": list(bua)}


def _hom_qua(p: dict) -> dict:
    # Số vận động hôm qua để chỉnh lượng ăn; không có Garmin hay Garmin lỗi thì vẫn soạn được.
    if not p.get("co_garmin"):
        return {}
    try:
        g = ket_noi(p["id"])
        d = (hom_nay_vn() - timedelta(days=1)).isoformat()
        s = g.get_stats(d) or {}
        buoi = [a.get("activityName") for a in (g.get_activities_by_date(d, d) or [])]
    except Exception as e:
        print(f"Không lấy được số hôm qua của {p.get('ten')}: {type(e).__name__}: {e}")
        return {}
    return {
        "calo_dot": s.get("totalKilocalories"),
        "calo_van_dong": s.get("activeKilocalories"),
        "buoc": s.get("totalSteps"),
        "buoi_tap": buoi,
    }


def _key(p: dict) -> str:
    return KEY if nguoi.la_chu(p["id"]) else f"{KEY}:{p['id']}"


def _da_an(p: dict) -> list[dict]:
    try:
        return json.loads(kho.doc(_key(p)) or "[]")
    except Exception:
        return []


def muc_an(p: dict) -> tuple[int, int, int]:
    """(kcal_min, kcal_max, dam_min) theo hồ sơ: giảm cân thì thâm hụt vừa phải, không đặt mục tiêu thì giữ cân.
    Chủ bot ấn định sẵn trong CHU_HO_SO thì dùng số đó."""
    if p.get("kcal_min") and p.get("kcal_max"):
        return int(p["kcal_min"]), int(p["kcal_max"]), int(p.get("dam_min") or 0) or 60
    nu = p.get("gioi_tinh") == "nu"
    ds = can_nang.doc(p)
    can = ds[-1]["kg"] if ds else (55.0 if nu else 65.0)
    dich = can_nang.muc_tieu(p)
    giam = bool(dich) and dich < can - 0.5
    if giam:
        kcal = (1300, 1500) if nu else (1600, 1900)
    else:
        kcal = (1700, 1900) if nu else (2100, 2400)
    dam = int(round(can * (1.6 if giam else 1.2) / 5) * 5)
    return kcal[0], kcal[1], max(dam, 60)


def _ho_so_chu(p: dict) -> str:
    phan = []
    if p.get("gioi_tinh"):
        phan.append("nam" if p["gioi_tinh"] == "nam" else "nữ")
    if p.get("cao_cm"):
        phan.append(f"cao {p['cao_cm']} cm")
    ds = can_nang.doc(p)
    if ds:
        phan.append(f"nặng {ds[-1]['kg']:.1f} kg")
    phan.append("có ăn sáng" if p.get("an_sang", 1) else "KHÔNG ăn sáng")
    if p.get("an_uong"):
        phan.append(f"món thích / kiêng: {p['an_uong']}")
    return ", ".join(phan) or "chưa khai gì thêm"


def _bua(icon: str, ten: str, m: dict) -> list[str]:
    return [
        f"{icon} <b>{ten}:</b> {escape(m['ten'])}",
        f"   🥩 ~{_so(m['kcal'])} kcal · {m['dam_g']}g đạm",
        "   🛒 " + escape(", ".join(m["nguyen_lieu"])),
        "   👩‍🍳 " + escape(m["cach_lam"]),
    ]


def thuc_don(luu: bool = True, p: dict | None = None) -> str:
    p = p or nguoi._chu()
    g, x = p["goi"], p["xung"]
    ngay = hom_nay_vn()
    hom_qua = _hom_qua(p)
    da_an = _da_an(p)
    them, ly_do = can_nang.dieu_chinh_calo(p)
    kcal_min, kcal_max, dam_min = muc_an(p)
    kcal_min, kcal_max = kcal_min + them, kcal_max + them
    an_sang = bool(p.get("an_sang", 1))
    dich = can_nang.muc_tieu(p)
    ds_can = can_nang.doc(p)
    du_lieu = {
        "hom_nay": f"{THU[ngay.weekday()]} {ngay.isoformat()}",
        "can_nang_gan_nhat_kg": ds_can[-1]["kg"] if ds_can else None,
        "muc_tieu_kg": dich or None,
        "chinh_calo_theo_toc_do_giam": ly_do,
        "van_dong_hom_qua": hom_qua,
        "da_an_gan_day": [x_["mon"] for x_ in da_an],
    }
    if dich:
        muc_tieu_chu = (f"{nguoi.hoa(g)} đang giảm cân về {dich:g} kg (nhịp an toàn khoảng 0,5–0,9 kg/tuần). "
                        "Mục tiêu là giảm mỡ mà giữ cơ.")
    else:
        muc_tieu_chu = f"{nguoi.hoa(g)} không đặt mục tiêu giảm cân: ăn đủ chất, giữ cân, ngon miệng."
    uu_tien_dam = (p.get("dam_uu_tien") or "").strip() or \
        "Tôn trọng món thích / kiêng trong hồ sơ; không có thì chọn đạm phổ biến, dễ mua."
    cac_bua = "sáng, trưa, tối" if an_sang else "trưa, tối (KHÔNG ăn sáng, nên hai bữa phải đủ no)"
    system = (SYSTEM.replace("{goi}", g).replace("{xung}", x).replace("{ho_so}", _ho_so_chu(p))
              .replace("{muc_tieu_chu}", muc_tieu_chu).replace("{cac_bua}", cac_bua)
              .replace("{uu_tien_dam}", uu_tien_dam).replace("{kcal_min}", _so(kcal_min))
              .replace("{kcal_max}", _so(kcal_max)).replace("{dam_min}", str(dam_min)))
    schema = _schema(an_sang)
    bua_keys = ["sang", "trua", "toi"] if an_sang else ["trua", "toi"]
    for _ in range(3):  # AI hay soạn thiếu calo/đạm — lệch thì bắt soạn lại
        td = json.loads(ai.goi_ai(system, du_lieu, max_tokens=8000, schema=schema))
        tong = sum(td[k]["kcal"] for k in bua_keys)
        dam = sum(td[k]["dam_g"] for k in bua_keys)
        if kcal_min - 100 <= tong <= kcal_max + 100 and dam >= dam_min:
            break
        du_lieu["lan_truoc_bi_loai"] = (f"Tổng {tong} kcal, {dam}g đạm — cần {kcal_min}–{kcal_max} kcal "
                                        f"và từ {dam_min}g đạm, soạn lại cho đúng.")

    tieu_de = f"Thực đơn giảm cân của {g}" if dich else f"Thực đơn hôm nay của {g}"
    dong = [f"🍽 <b>{tieu_de} — {THU[ngay.weekday()]}, {ngay:%d/%m}</b>", "",
            f"{nguoi.hoa(g)} ơi, {x} lên thực đơn hôm nay cho {g} rồi nè 💕", ""]
    icon = {"sang": "🌅", "trua": "☀️", "toi": "🌙"}
    ten_bua = {"sang": "Sáng", "trua": "Trưa", "toi": "Tối"}
    for i, k in enumerate(bua_keys):
        if i:
            dong.append("")
        dong += _bua(icon[k], ten_bua[k], td[k])
    dong += ["", f"📊 Cả ngày ~<b>{_so(tong)}</b> kcal · {dam}g đạm"
             + (f" (hôm qua {g} đốt {_so(hom_qua['calo_dot'])} kcal)" if hom_qua.get("calo_dot") else "")]
    if td.get("loi_nhan"):
        dong += ["", "💬 " + escape(td["loi_nhan"])]

    if luu:
        da_an = [x_ for x_ in da_an if x_.get("ngay") != ngay.isoformat()]
        da_an.append({"ngay": ngay.isoformat(), "mon": [td[k]["ten"] for k in bua_keys],
                      "kcal": [td[k]["kcal"] for k in bua_keys]})
        kho.ghi(json.dumps(da_an[-NHO:], ensure_ascii=False), _key(p))
    return "\n".join(dong)
