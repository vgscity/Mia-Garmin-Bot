# Người nhà trông nhau (08/11/2026). Cần HAI bên đồng ý:
#   - người cho xem tạo mã trong Mini App (mã 6 ký tự, sống 24h) và tự gửi cho người nhà;
#   - người xem nhập mã + đặt tên gọi (ví dụ "Ông nội").
# Mỗi sáng, đúng giờ sáng của người xem, Mia gửi một tin ngắn: người nhà ngủ thế nào, hay đồng hồ
# chưa đồng bộ (hết pin / quên đeo). Chỉ gửi tóm tắt, không gửi số chi tiết. Một bên bỏ là thôi ngay.
# Bảng mia_chia_se(tu = người cho xem, toi = người xem, nhan = tên người xem đặt).
import json
import secrets
import time
from html import escape

from . import kho, nguoi, telegram
from .ngu import _gio, hom_nay_vn, ket_noi, lay_giac_ngu

CHU_MA = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # bỏ 0/O/1/I cho khỏi nhầm khi gõ
SONG_MA = 24 * 3600
TOI_DA = 10  # mỗi người xem tối đa 10 người nhà


def _bang() -> None:
    kho._turso("CREATE TABLE IF NOT EXISTS mia_chia_se (tu TEXT NOT NULL, toi TEXT NOT NULL, nhan TEXT NOT NULL DEFAULT '', "
               "tao_luc TEXT NOT NULL DEFAULT (datetime('now')), PRIMARY KEY (tu, toi))")


def tao_ma(id_) -> str:
    ma = "".join(secrets.choice(CHU_MA) for _ in range(6))
    kho.ghi(json.dumps({"tu": str(id_), "het": time.time() + SONG_MA}), f"ma_chia_se:{ma}")
    return ma


def nhap_ma(id_, ma: str, nhan: str) -> dict:
    ma = "".join(c for c in (ma or "").upper() if c in CHU_MA)
    raw = kho.doc(f"ma_chia_se:{ma}") if len(ma) == 6 else None
    if not raw:
        raise ValueError("Mã không đúng hoặc đã hết hạn.")
    d = json.loads(raw)
    if time.time() > d["het"]:
        raise ValueError("Mã đã hết hạn, nhờ người nhà tạo mã mới nhé.")
    tu = d["tu"]
    if tu == str(id_):
        raise ValueError("Đây là mã của chính bạn.")
    _bang()
    if len(dang_xem(id_)) >= TOI_DA:
        raise ValueError(f"Mỗi người xem tối đa {TOI_DA} người nhà.")
    nguoi_cho = nguoi.lay(tu)
    if not nguoi_cho:
        raise ValueError("Không tìm thấy người tạo mã.")
    nhan = (nhan or "").strip()[:30] or nguoi_cho["ten"]
    kho._turso("INSERT INTO mia_chia_se (tu, toi, nhan) VALUES (?, ?, ?) ON CONFLICT(tu, toi) DO UPDATE SET nhan = excluded.nhan",
               [tu, str(id_), nhan])
    kho._turso("DELETE FROM garmin_kv WHERE k = ?", [f"ma_chia_se:{ma}"])  # mã dùng một lần
    nguoi_xem = nguoi.lay(id_) or {"ten": str(id_)}
    try:
        telegram.gui(tu, f"👨‍👩‍👧 {escape(nguoi_xem['ten'])} vừa được xem tin sáng tóm tắt của bạn (ngủ ra sao, đồng hồ có đồng bộ không). "
                         f"Muốn thôi thì mở Mia → Người nhà → Bỏ.")
    except Exception as e:
        print(f"Không báo được người cho xem: {type(e).__name__}")
    return {"tu": tu, "nhan": nhan}


def dang_xem(id_) -> list[dict]:
    _bang()
    rows = kho._turso("SELECT tu, nhan FROM mia_chia_se WHERE toi = ?", [str(id_)])
    return [{"id": r[0]["value"], "nhan": r[1]["value"]} for r in rows]


def cho_xem(id_) -> list[dict]:
    _bang()
    rows = kho._turso("SELECT toi FROM mia_chia_se WHERE tu = ?", [str(id_)])
    ra = []
    for r in rows:
        p = nguoi.lay(r[0]["value"])
        ra.append({"id": r[0]["value"], "ten": p["ten"] if p else r[0]["value"]})
    return ra


def bo(id_, khac, chieu: str) -> None:
    """chieu='xem': id_ thôi xem khac; chieu='cho': id_ thôi cho khac xem."""
    _bang()
    tu, toi = (str(khac), str(id_)) if chieu == "xem" else (str(id_), str(khac))
    kho._turso("DELETE FROM mia_chia_se WHERE tu = ? AND toi = ?", [tu, toi])


def _mot_nguoi(tu: str, nhan: str) -> str:
    from . import garmin_them

    p = nguoi.lay(tu)
    ten = escape(nhan)
    if not p or not p.get("co_garmin"):
        return f"• {ten}: chưa kết nối Garmin với Mia"
    try:
        g = ket_noi(tu)
    except Exception:
        return f"• {ten}: ⚠️ Mia không đọc được Garmin, nhờ {ten} mở Mia kết nối lại"
    luc = garmin_them.dong_bo_lan_cuoi(g)
    dto = (lay_giac_ngu(g, hom_nay_vn()).get("dailySleepDTO") or {})
    tong = dto.get("sleepTimeSeconds")
    if tong:
        diem = ((dto.get("sleepScores") or {}).get("overall") or {}).get("value")
        on = "✅" if (diem or 0) >= 60 and tong >= 6 * 3600 else "😴 hơi ít"
        return f"• {ten}: ngủ {_gio(tong)}" + (f", điểm {diem}" if diem else "") + f" {on}"
    if garmin_them.cu_chua(luc):
        return f"• {ten}: ⚠️ đồng hồ chưa đồng bộ từ {luc:%H:%M %d/%m} — hết pin hay quên đeo?"
    return f"• {ten}: chưa thấy dữ liệu đêm qua (có thể chưa đồng bộ sáng nay)"


def tin_sang(p: dict) -> str | None:
    ds = dang_xem(p["id"])
    if not ds:
        return None
    dong = [f"👨‍👩‍👧 <b>Người nhà sáng nay</b>"] + [_mot_nguoi(d["id"], d["nhan"]) for d in ds]
    return "\n".join(dong)
