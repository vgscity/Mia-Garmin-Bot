# Nhắc vận động buổi chiều (08/11/2026): 17h VN, ai bật "nhắc vận động" mà chưa được nửa mục tiêu
# bước thì nhận một tin rủ đi bộ. Không dùng AI. Đạt rồi thì im lặng.
from . import nguoi
from .ngu import hom_nay_vn, ket_noi
from .tong_ket import _so

GIO_NHAC = 17


def nhac(p: dict) -> str | None:
    g = ket_noi(p["id"])
    s = g.get_stats(hom_nay_vn().isoformat()) or {}
    buoc, muc_tieu = s.get("totalSteps") or 0, s.get("dailyStepGoal") or 0
    if not muc_tieu or buoc >= muc_tieu / 2:
        return None
    goi, x = p["goi"], p["xung"]
    thieu = muc_tieu - buoc
    phut = max(10, min(60, round(thieu / 100)))  # đi bộ thường ~100 bước/phút
    return (f"🚶 {nguoi.hoa(goi)} ơi, {GIO_NHAC} giờ chiều rồi mà {goi} mới đi được {_so(buoc)}/{_so(muc_tieu)} bước. "
            f"Ra ngoài đi bộ chừng {phut} phút là gần chạm mục tiêu đó, {x} đợi tin tốt của {goi} nha!")
