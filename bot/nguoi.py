# Người dùng Mia: chủ bot (OWNER_ID) + người nhà đeo Garmin, mỗi người token Garmin riêng,
# cách xưng hô riêng, giờ nhận tin sáng/tối riêng. Người lạ nhắn /start thì vào hàng chờ,
# chủ bot duyệt bằng nút trong Telegram. Bảng mia_nguoi nằm cùng Turso với garmin_kv (kho.py).
#
# Mỗi người tự bật thêm trong Mini App: tin buổi sáng (thời sự / công nghệ), thực đơn 10h theo
# hồ sơ của mình (giới tính, cao, cân mục tiêu, có ăn sáng không, thích/kiêng), và theo dõi cân
# nặng (/can hoặc ghi trong Mini App). Cột mới thêm bằng ALTER, bảng cũ vẫn chạy.
#
# Hồ sơ của CHỦ BOT không nằm trong code mà ở biến môi trường (xem .env.example):
#   CHU_TEN      cách nhắc tới chủ bot với người khác, ví dụ "anh Alex" (mặc định "chủ bot")
#   CHU_GOI / CHU_XUNG   Mia gọi chủ là gì, xưng gì (mặc định "bạn" / "mình")
#   CHU_HO_SO    JSON: gioi_tinh, cao_cm, muc_tieu_kg, an_sang, an_uong, tin_thoi_su, tin_cong_nghe,
#                thuc_don, và riêng cho thực đơn: kcal_min, kcal_max, dam_min, dam_uu_tien (câu dặn Gemini)
import json
import os

from . import kho, telegram

# Mia gọi người dùng là gì → Mia tự xưng là gì
XUNG_THEO_GOI = {"ba": "con", "mẹ": "con", "ông": "cháu", "bà": "cháu", "anh": "em", "chị": "em",
                 "cô": "cháu", "chú": "cháu", "dì": "cháu", "bác": "cháu", "em": "chị", "bạn": "mình"}
GIO_SANG = range(5, 11)   # 5h–10h
GIO_TOI = range(18, 24)   # 18h–23h
COT = ("id", "ten", "goi", "xung", "gio_sang", "gio_toi", "trang_thai", "co_garmin",
       "tin_thoi_su", "tin_cong_nghe", "thuc_don", "gioi_tinh", "cao_cm", "muc_tieu_kg", "an_sang", "an_uong",
       "tin_xa_hoi")
COT_SO = ("gio_sang", "gio_toi", "co_garmin", "tin_thoi_su", "tin_cong_nghe", "thuc_don", "cao_cm", "an_sang", "tin_xa_hoi")
# Cột thêm sau khi bảng đã có — (tên, khai báo SQL). Thứ tự ổn định để ALTER từng cái.
COT_MOI = (
    ("tin_thoi_su", "INTEGER NOT NULL DEFAULT 0"),
    ("tin_cong_nghe", "INTEGER NOT NULL DEFAULT 0"),
    ("thuc_don", "INTEGER NOT NULL DEFAULT 0"),
    ("gioi_tinh", "TEXT NOT NULL DEFAULT ''"),
    ("cao_cm", "INTEGER NOT NULL DEFAULT 0"),
    ("muc_tieu_kg", "REAL NOT NULL DEFAULT 0"),
    ("an_sang", "INTEGER NOT NULL DEFAULT 1"),
    ("an_uong", "TEXT NOT NULL DEFAULT ''"),
    ("tin_xa_hoi", "INTEGER NOT NULL DEFAULT 0"),
)
HO_SO_MAC_DINH = {"tin_thoi_su": 1, "tin_cong_nghe": 0, "thuc_don": 0, "gioi_tinh": "", "cao_cm": 0,
                  "muc_tieu_kg": 0.0, "an_sang": 1, "an_uong": "", "tin_xa_hoi": 0}
# Trường chỉ có ở hồ sơ chủ (không phải cột bảng), dùng cho thực đơn.
HO_SO_THEM = ("kcal_min", "kcal_max", "dam_min", "dam_uu_tien")

_da_nang_cap = False
HO_SO_LOI = ""  # lý do CHU_HO_SO không đọc được (hiện ở cron ?dry=1 để dò cấu hình)


def chu() -> str:
    return os.environ["OWNER_ID"]


def ten_chu() -> str:
    """Cách Mia nhắc tới chủ bot với người khác: "anh Alex", "cô Lan"..."""
    return os.environ.get("CHU_TEN", "chủ bot").strip() or "chủ bot"


def ho_so_chu() -> dict:
    """Hồ sơ chủ bot từ CHU_HO_SO (JSON), thiếu gì lấy mặc định; JSON hỏng thì coi như không có."""
    global HO_SO_LOI
    try:
        them = json.loads(os.environ.get("CHU_HO_SO") or "{}")
        HO_SO_LOI = ""
    except ValueError as e:
        them = {}
        HO_SO_LOI = f"CHU_HO_SO không phải JSON: {e}"
    ho_so = {**HO_SO_MAC_DINH}
    for k in HO_SO_MAC_DINH:
        if k in them and them[k] is not None:
            ho_so[k] = them[k]
    for k in HO_SO_THEM:
        if them.get(k):
            ho_so[k] = them[k]
    ho_so["muc_tieu_kg"] = float(ho_so["muc_tieu_kg"] or 0)
    for k in ("tin_thoi_su", "tin_cong_nghe", "thuc_don", "cao_cm", "an_sang", "tin_xa_hoi"):
        ho_so[k] = int(ho_so[k] or 0)
    return ho_so


def la_chu(id_) -> bool:
    return str(id_) == chu()


def key_token(id_) -> str:
    # Token của chủ bot giữ khoá cũ để khỏi đăng nhập lại.
    return kho.KEY if la_chu(id_) else f"{kho.KEY}:{id_}"


def _tao_bang() -> None:
    global _da_nang_cap
    kho._turso(
        "CREATE TABLE IF NOT EXISTS mia_nguoi (id TEXT PRIMARY KEY, ten TEXT NOT NULL DEFAULT '', "
        "goi TEXT NOT NULL DEFAULT 'bạn', xung TEXT NOT NULL DEFAULT 'mình', "
        "gio_sang INTEGER NOT NULL DEFAULT 7, gio_toi INTEGER NOT NULL DEFAULT 21, "
        "trang_thai TEXT NOT NULL DEFAULT 'cho', co_garmin INTEGER NOT NULL DEFAULT 0, "
        "tao_luc TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    if _da_nang_cap:
        return
    # Thêm cột mới cho bảng cũ; cột đã có thì SQLite báo "duplicate column", bỏ qua.
    for ten, khai_bao in COT_MOI:
        try:
            kho._turso(f"ALTER TABLE mia_nguoi ADD COLUMN {ten} {khai_bao}")
        except Exception as e:
            if "duplicate" not in str(e).lower():
                raise
    # Dòng của chủ lập trước khi có các cột mới thì chúng đang là 0/'' — nạp hồ sơ chủ từ biến
    # môi trường đúng một lần (gioi_tinh rỗng là dấu hiệu chưa nạp; không khai gioi_tinh thì thôi).
    hs = ho_so_chu()
    if hs["gioi_tinh"]:
        kho._turso(
            "UPDATE mia_nguoi SET tin_thoi_su = ?, tin_cong_nghe = ?, thuc_don = ?, gioi_tinh = ?, cao_cm = ?, "
            "muc_tieu_kg = ?, an_sang = ?, an_uong = ? WHERE id = ? AND gioi_tinh = ''",
            [str(hs["tin_thoi_su"]), str(hs["tin_cong_nghe"]), str(hs["thuc_don"]), hs["gioi_tinh"], str(hs["cao_cm"]),
             str(hs["muc_tieu_kg"]), str(hs["an_sang"]), hs["an_uong"], chu()],
        )
    _da_nang_cap = True


def _dong(row) -> dict:
    d = {k: c.get("value") for k, c in zip(COT, row)}
    for k in COT_SO:
        d[k] = int(float(d[k] or 0))
    d["muc_tieu_kg"] = float(d["muc_tieu_kg"] or 0)
    d["gioi_tinh"] = d["gioi_tinh"] or ""
    d["an_uong"] = d["an_uong"] or ""
    return d


def _chu() -> dict:
    # Chủ bot luôn có mặt, kể cả khi bảng chưa có dòng của chủ; xưng hô + hồ sơ lấy từ biến môi trường.
    return {"id": chu(), "ten": ten_chu(), "goi": os.environ.get("CHU_GOI", "bạn").strip() or "bạn",
            "xung": os.environ.get("CHU_XUNG", "mình").strip() or "mình", "gio_sang": 7, "gio_toi": 21,
            "trang_thai": "duyet", "co_garmin": 1, **ho_so_chu()}


# Tên cũ, vài chỗ còn gọi.
_ba = _chu


def _them_ho_so_chu(p: dict) -> dict:
    """Dòng của chủ trong bảng không có kcal_min... — gắn thêm từ biến môi trường."""
    if la_chu(p["id"]):
        hs = ho_so_chu()
        for k in HO_SO_THEM:
            if k in hs:
                p[k] = hs[k]
    return p


def lay(id_) -> dict | None:
    _tao_bang()
    rows = kho._turso(f"SELECT {', '.join(COT)} FROM mia_nguoi WHERE id = ?", [str(id_)])
    if rows:
        return _them_ho_so_chu(_dong(rows[0]))
    return _chu() if la_chu(id_) else None


def tat_ca_duyet() -> list[dict]:
    _tao_bang()
    rows = kho._turso(f"SELECT {', '.join(COT)} FROM mia_nguoi WHERE trang_thai = 'duyet'")
    ds = [_them_ho_so_chu(_dong(r)) for r in rows]
    if not any(la_chu(n["id"]) for n in ds):
        ds.insert(0, _chu())
    return ds


def dang_ky(id_, ten: str) -> tuple[dict, bool]:
    """Trả (người, mới_tạo). Chủ bot thì tự duyệt và mang sẵn hồ sơ từ biến môi trường."""
    if _co_dong(id_):
        return lay(id_), False
    la_chu_ = la_chu(id_)
    c = _chu()
    trang_thai = "duyet" if la_chu_ else "cho"
    goi, xung = (c["goi"], c["xung"]) if la_chu_ else ("bạn", "mình")
    kho._turso(
        "INSERT OR IGNORE INTO mia_nguoi (id, ten, goi, xung, trang_thai, co_garmin) VALUES (?, ?, ?, ?, ?, ?)",
        [str(id_), ten[:60], goi, xung, trang_thai, "1" if la_chu_ else "0"],
    )
    if la_chu_:
        sua(id_, **{k: c[k] for k in HO_SO_MAC_DINH})
    return lay(id_), True


def _co_dong(id_) -> bool:
    _tao_bang()
    return bool(kho._turso("SELECT 1 FROM mia_nguoi WHERE id = ?", [str(id_)]))


def sua(id_, **truong) -> dict:
    if la_chu(id_) and not _co_dong(id_):
        dang_ky(id_, ten_chu())
    cho_phep = set(COT) - {"id"}
    cap = {k: v for k, v in truong.items() if k in cho_phep}
    if cap:
        kho._turso(
            f"UPDATE mia_nguoi SET {', '.join(f'{k} = ?' for k in cap)} WHERE id = ?",
            [str(v) for v in cap.values()] + [str(id_)],
        )
    return lay(id_)


def xoa_token(id_) -> None:
    kho._turso("DELETE FROM garmin_kv WHERE k = ?", [key_token(id_)])
    sua(id_, co_garmin=0)


def hoa(s: str) -> str:
    return s[:1].upper() + s[1:]


def ten_cua(u: dict) -> str:
    ten = " ".join(x for x in (u.get("first_name"), u.get("last_name")) if x).strip()
    return ten or u.get("username") or str(u.get("id"))


def bao_ba_duyet(u: dict) -> None:
    ten = ten_cua(u) + (f" (@{u['username']})" if u.get("username") else "")
    c = lay(chu()) or _chu()
    telegram.goi(
        "sendMessage", chat_id=chu(),
        text=f"👤 {ten} muốn dùng Mia (id {u['id']}). {hoa(c['goi'])} duyệt không?",
        reply_markup={"inline_keyboard": [[
            {"text": "✅ Duyệt", "callback_data": f"duyet:{u['id']}"},
            {"text": "❌ Không", "callback_data": f"chan:{u['id']}"},
        ]]},
    )
