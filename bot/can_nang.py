# Ghi cân nặng (/can 75.2 hoặc trong Mini App), vẽ tiến độ về mục tiêu, và chỉnh calo thực đơn
# theo tốc độ giảm thật. Mỗi người một sổ: chủ bot key "can_nang", người nhà key "can_nang:<id>";
# mốc bắt đầu là lần cân đầu tiên, riêng chủ bot có thể đặt mốc bằng CHU_CAN_BAT_DAU="YYYY-MM-DD,kg"
# (mốc tách khỏi sổ để lần cân cùng ngày không đè mất). Mục tiêu đọc từ hồ sơ (muc_tieu_kg);
# không đặt thì chỉ ghi sổ. Dạng lưu: [{"ngay": "YYYY-MM-DD", "kg": 75.2}, ...].
import json
import os
import re
from datetime import date, timedelta
from html import escape

from . import kho, nguoi
from .ngu import hom_nay_vn

KEY = "can_nang"
CHAM, NHANH = 0.4, 1.0  # kg/tuần: dưới CHAM thì bớt calo, trên NHANH thì thêm
DU_NGAY = 10  # tuần đầu tụt nước, phải đủ 10 ngày dữ liệu mới chỉnh calo
DUOI = "▁▂▃▄▅▆▇█"


def _p(p: dict | None) -> dict:
    return p or nguoi._chu()


def _key(p: dict) -> str:
    return KEY if nguoi.la_chu(p["id"]) else f"{KEY}:{p['id']}"


def moc_chu() -> dict | None:
    """Mốc bắt đầu của chủ bot từ CHU_CAN_BAT_DAU="2026-09-19,76" (không có thì None)."""
    raw = os.environ.get("CHU_CAN_BAT_DAU", "")
    try:
        ngay, kg = raw.split(",", 1)
        date.fromisoformat(ngay.strip())
        return {"ngay": ngay.strip(), "kg": float(kg.strip().replace(",", "."))}
    except (ValueError, AttributeError):
        return None


def muc_tieu(p: dict | None) -> float:
    return float(_p(p).get("muc_tieu_kg") or 0)


def _da_luu(p: dict) -> list[dict]:
    try:
        return sorted(json.loads(kho.doc(_key(p)) or "[]"), key=lambda x: x["ngay"])
    except Exception:
        return []


def doc(p: dict | None = None) -> list[dict]:
    """Chuỗi cân để tính: mốc bắt đầu của chủ (nếu đặt, trừ khi hôm đó đã tự cân) + các lần đã ghi."""
    p = _p(p)
    ds = _da_luu(p)
    moc = moc_chu() if nguoi.la_chu(p["id"]) else None
    if moc and not any(x["ngay"] == moc["ngay"] for x in ds):
        ds = [moc] + ds
    return sorted(ds, key=lambda x: x["ngay"])


def _ghi(p: dict, ds: list[dict]) -> None:
    kho.ghi(json.dumps(ds, ensure_ascii=False), _key(p))


def doc_so(chu: str) -> float | None:
    m = re.search(r"\d{2,3}(?:[.,]\d{1,2})?", chu)
    if not m:
        return None
    kg = float(m.group().replace(",", "."))
    return kg if 35 <= kg <= 200 else None


def da_can_hom_nay(p: dict | None = None) -> bool:
    return any(x["ngay"] == hom_nay_vn().isoformat() for x in _da_luu(_p(p)))


def toc_do(ds: list[dict]) -> tuple[float, int] | None:
    """kg giảm mỗi tuần (dương = đang giảm) theo đường thẳng khớp 14 ngày gần nhất, kèm số ngày dữ liệu."""
    if len(ds) < 3:
        return None
    cuoi = date.fromisoformat(ds[-1]["ngay"])
    gan = [x for x in ds if (cuoi - date.fromisoformat(x["ngay"])).days <= 14]
    if len(gan) < 3:
        return None
    xs = [(date.fromisoformat(x["ngay"]) - cuoi).days for x in gan]
    ys = [x["kg"] for x in gan]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    mau = sum((x - mx) ** 2 for x in xs)
    if not mau:
        return None
    doc_ = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / mau
    so_ngay = (cuoi - date.fromisoformat(ds[0]["ngay"])).days
    return -doc_ * 7, so_ngay


def dieu_chinh_calo(p: dict | None = None) -> tuple[int, str | None]:
    """Số kcal cộng thêm vào khoảng thực đơn, kèm lý do để AI nói với người đọc."""
    p = _p(p)
    if not muc_tieu(p):
        return 0, None
    td = toc_do(doc(p))
    if not td or td[1] < DU_NGAY:
        return 0, None
    tuan, _ = td
    g, x = p["goi"], p["xung"]
    if tuan > NHANH:
        return 150, f"{nguoi.hoa(g)} đang giảm {tuan:.1f} kg/tuần — nhanh quá dễ mất cơ, {x} cho {g} ăn thêm chút."
    if tuan < CHAM:
        return -100, f"Hai tuần nay {g} chỉ giảm {tuan:.1f} kg/tuần — {x} bớt chút tinh bột cho {g}."
    return 0, None


def _bieu_do(ds: list[dict]) -> str:
    gan = ds[-14:]
    kgs = [x["kg"] for x in gan]
    lo, hi = min(kgs), max(kgs)
    if hi - lo < 0.05:
        return DUOI[3] * len(kgs)
    return "".join(DUOI[round((k - lo) / (hi - lo) * (len(DUOI) - 1))] for k in kgs)


def tien_do(ds: list[dict] | None = None, p: dict | None = None) -> str:
    p = _p(p)
    ds = ds or doc(p)
    g, x = p["goi"], p["xung"]
    if not ds:
        return f"{nguoi.hoa(g)} chưa ghi cân lần nào. Nhắn kiểu <b>/can 60.5</b> hoặc ghi trong Mia nha."
    dich = muc_tieu(p)
    dau, nay = ds[0]["kg"], ds[-1]["kg"]
    dong = []
    if not dich:
        dong += [f"⚖️ <b>Sổ cân của {g}</b>",
                 f"Lần đầu {dau:.1f} kg ({date.fromisoformat(ds[0]['ngay']):%d/%m}) → nay <b>{nay:.1f} kg</b>"]
        if len(ds) >= 2:
            dong.append(f"<code>{_bieu_do(ds)}</code> ({len(ds[-14:])} lần cân gần nhất)")
        dong.append(f"<i>{nguoi.hoa(g)} đặt cân mục tiêu trong Mia là {x} tính tốc độ và ngày về đích cho.</i>")
        return "\n".join(dong)

    da_giam, con = dau - nay, nay - dich
    tong = dau - dich
    phan = max(0.0, min(1.0, da_giam / tong)) if tong > 0 else 1.0
    o = round(phan * 10)
    dong += [
        f"⚖️ <b>Hành trình về {dich:g}kg của {g}</b>",
        f"<code>{'▓' * o}{'░' * (10 - o)}</code> {phan * 100:.0f}%",
        f"Bắt đầu {dau:.1f} kg ({date.fromisoformat(ds[0]['ngay']):%d/%m}) → nay <b>{nay:.1f} kg</b>"
        + (f" · đã giảm {da_giam:.1f} kg" if da_giam > 0 else ""),
    ]
    if con > 0:
        dong.append(f"Còn {con:.1f} kg nữa là tới đích 🎯")
    else:
        dong.append(f"🎉 {nguoi.hoa(g)} chạm mốc {dich:g}kg rồi! {nguoi.hoa(x)} tự hào về {g} lắm!")
    if len(ds) >= 2:
        dong.append(f"<code>{_bieu_do(ds)}</code> ({len(ds[-14:])} lần cân gần nhất)")
    td = toc_do(ds)
    if td and con > 0:
        tuan, so_ngay = td
        if so_ngay < 7:
            dong.append(f"<i>Tuần đầu cân xuống nhanh chủ yếu do mất nước, đủ 1 tuần {x} mới tính được tốc độ thật và ngày về đích.</i>")
        elif tuan > 0.05:
            ve_dich = date.fromisoformat(ds[-1]["ngay"]) + timedelta(days=round(con / tuan * 7))
            dong.append(f"Tốc độ {tuan:.1f} kg/tuần → dự kiến về đích khoảng <b>{ve_dich:%d/%m}</b>")
        else:
            dong.append(f"Mấy hôm nay cân đang đứng, {g} cứ bám thực đơn là sẽ xuống lại nha.")
    return "\n".join(dong)


def ghi_can(kg: float, p: dict | None = None) -> str:
    p = _p(p)
    g, x = p["goi"], p["xung"]
    hom_nay = hom_nay_vn().isoformat()
    luu = [x_ for x_ in _da_luu(p) if x_["ngay"] != hom_nay] + [{"ngay": hom_nay, "kg": round(kg, 1)}]
    _ghi(p, luu)
    ds = doc(p)
    truoc = [x_ for x_ in ds if x_["ngay"] < hom_nay]
    moc = moc_chu() if nguoi.la_chu(p["id"]) else None
    if not truoc and moc and hom_nay == moc["ngay"]:
        truoc = [moc]
    mo = f"{nguoi.hoa(x)} ghi rồi nha {g}: <b>{kg:.1f} kg</b> hôm nay."
    if truoc:
        lech = kg - truoc[-1]["kg"]
        if lech < -0.05:
            mo += f" Giảm {-lech:.1f} kg so với lần trước, giỏi quá {g} ơi 👏"
        elif lech > 0.05:
            mo += f" Nhích {lech:.1f} kg so với lần trước — cân dao động theo nước và muối, {g} đừng lo nha."
        else:
            mo += " Giữ nguyên so với lần trước."
    return mo + "\n\n" + tien_do(ds, p)


def xoa_hom_nay(p: dict | None = None) -> str:
    p = _p(p)
    g, x = p["goi"], p["xung"]
    ds = _da_luu(p)
    hom_nay = hom_nay_vn().isoformat()
    moi = [x_ for x_ in ds if x_["ngay"] != hom_nay]
    if len(moi) == len(ds):
        return f"Hôm nay {g} chưa ghi cân nào để xoá hết á."
    _ghi(p, moi)
    return f"{nguoi.hoa(x)} xoá số cân hôm nay rồi, {g} cân lại rồi nhắn /can nha."


def lenh(chu: str, p: dict | None = None) -> str:
    """/can 75.2 → ghi; /can → xem tiến độ; /can xoa → xoá số hôm nay."""
    p = _p(p)
    phan = chu.split(maxsplit=1)
    tham_so = phan[1].strip().lower() if len(phan) > 1 else ""
    if not tham_so:
        return tien_do(p=p)
    if tham_so in ("xoa", "xoá", "xóa"):
        return xoa_hom_nay(p)
    kg = doc_so(tham_so)
    if kg is None:
        return f"{nguoi.hoa(p['xung'])} chưa hiểu số cân \"{escape(tham_so)}\" {p['goi']} ơi, nhắn kiểu /can 75.2 nha."
    return ghi_can(kg, p)
