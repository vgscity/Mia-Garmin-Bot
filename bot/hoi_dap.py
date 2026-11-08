# Hỏi gì đáp nấy (08/11/2026): tin nhắn tự do (không phải lệnh) → Claude trả lời, tự gọi công cụ đọc
# Garmin / sổ cân / bữa ăn của CHÍNH người hỏi. Nhớ vài lượt hỏi trong ngày (garmin_kv "hoi:<id>")
# để hỏi tiếp được. Giới hạn HOI_MOI_NGAY câu / người / ngày (chủ bot không giới hạn).
import json
import os
from datetime import date, timedelta
from html import escape

from anthropic import beta_tool

from . import ai, can_nang, kho, nguoi
from .ngu import THU, du_lieu_cho_ai, hom_nay_vn, ket_noi, lay_giac_ngu

HOI_MOI_NGAY = int(os.environ.get("HOI_MOI_NGAY", "30"))
NHO_LUOT = 8  # số tin (hỏi + đáp) giữ lại trong ngày
TOI_DA_NGAY = 62

SYSTEM = """Bạn là Mia, trợ lý sức khoẻ trên Telegram của {goi}. Gọi "{goi}", xưng "{xung}". Giọng ấm áp, gần gũi, ngắn gọn.
Hôm nay là {hom_nay} (giờ Việt Nam). "Hôm qua", "tuần này", "tháng trước"… tính theo ngày đó; tuần bắt đầu từ Thứ Hai.
Bạn có công cụ đọc số liệu đồng hồ Garmin, sổ cân và bữa ăn đã chụp của {goi}. Câu hỏi cần số thì gọi công cụ rồi trả lời
bằng đúng số lấy được; không có số thì nói thẳng là chưa có, đừng đoán. {garmin}
Câu hỏi ngoài sức khoẻ thì cứ trả lời bình thường, ngắn gọn.
Không chẩn đoán bệnh, không kê thuốc; dấu hiệu đáng lo thì khuyên {goi} hỏi bác sĩ.
Trả lời tối đa khoảng 6 câu, chữ thuần, không markdown, không bảng. Thời lượng viết dạng "7 tiếng 20 phút"."""


def _ngay(s: str) -> date:
    return date.fromisoformat(s.strip()[:10])


def _khoang(tu: str, den: str) -> tuple[date, date]:
    a, b = _ngay(tu), _ngay(den)
    if a > b:
        a, b = b, a
    if (b - a).days > TOI_DA_NGAY:
        a = b - timedelta(days=TOI_DA_NGAY)
    return a, b


def _cong_cu(p: dict) -> list:
    garmin = {"g": None}

    def g():
        if garmin["g"] is None:
            garmin["g"] = ket_noi(p["id"])
        return garmin["g"]

    @beta_tool
    def giac_ngu(ngay: str) -> str:
        """Chi tiết giấc ngủ của đêm kết thúc vào sáng ngày `ngay` (điểm, tổng giờ, sâu/nông/REM, nhịp tim, HRV, SpO2, Body Battery).

        Args:
            ngay: Ngày YYYY-MM-DD (đêm qua = hôm nay).
        """
        d = _ngay(ngay)
        data = lay_giac_ngu(g(), d)
        if not (data.get("dailySleepDTO") or {}).get("sleepTimeSeconds"):
            return json.dumps({"ngay": d.isoformat(), "co_du_lieu": False})
        return json.dumps(du_lieu_cho_ai(data, [], d)["dem_qua"], ensure_ascii=False)

    @beta_tool
    def giac_ngu_nhieu_dem(tu: str, den: str) -> str:
        """Tóm tắt giấc ngủ từng đêm trong một khoảng ngày (tối đa ~2 tháng): giờ ngủ, điểm, giờ lên giường, nhịp tim nghỉ, HRV.

        Args:
            tu: Ngày đầu YYYY-MM-DD.
            den: Ngày cuối YYYY-MM-DD.
        """
        a, b = _khoang(tu, den)
        ra = []
        for r in g().get_sleep_daily(a.isoformat(), b.isoformat()) or []:
            v = r.get("values") or {}
            if v.get("totalSleepTimeInSeconds"):
                ra.append({"ngay": r.get("calendarDate"), "phut": round(v["totalSleepTimeInSeconds"] / 60),
                           "diem": v.get("sleepScore"), "sau_phut": round((v.get("deepTime") or 0) / 60),
                           "rem_phut": round((v.get("remTime") or 0) / 60), "nhip_tim_nghi": v.get("restingHeartRate"),
                           "hrv": v.get("avgOvernightHrv")})
        return json.dumps(ra, ensure_ascii=False)

    @beta_tool
    def mot_ngay(ngay: str) -> str:
        """Vận động trong một ngày: bước chân, mục tiêu, calo, phút gắng sức, nhịp tim nghỉ/thấp/cao, Body Battery, stress, các buổi tập.

        Args:
            ngay: Ngày YYYY-MM-DD.
        """
        from .tong_ket import _buoi_tap
        d = _ngay(ngay).isoformat()
        s = g().get_stats(d) or {}
        keys = ("totalSteps", "dailyStepGoal", "totalDistanceMeters", "totalKilocalories", "activeKilocalories",
                "moderateIntensityMinutes", "vigorousIntensityMinutes", "restingHeartRate", "minHeartRate", "maxHeartRate",
                "bodyBatteryHighestValue", "bodyBatteryLowestValue", "bodyBatteryMostRecentValue",
                "averageStressLevel", "maxStressLevel")
        buoi = [_buoi_tap(a) for a in (g().get_activities_by_date(d, d) or [])]
        return json.dumps({"ngay": d, **{k: s.get(k) for k in keys}, "buoi_tap": buoi}, ensure_ascii=False)

    @beta_tool
    def buoc_chan(tu: str, den: str) -> str:
        """Bước chân từng ngày trong một khoảng ngày (tối đa ~2 tháng), kèm mục tiêu bước.

        Args:
            tu: Ngày đầu YYYY-MM-DD.
            den: Ngày cuối YYYY-MM-DD.
        """
        a, b = _khoang(tu, den)
        ra = [{"ngay": r.get("calendarDate"), "buoc": r.get("totalSteps"), "muc_tieu": r.get("stepGoal")}
              for r in g().get_daily_steps(a.isoformat(), b.isoformat()) or []]
        return json.dumps(ra, ensure_ascii=False)

    @beta_tool
    def buoi_tap(tu: str, den: str) -> str:
        """Các buổi tập (chạy, đạp xe, pickleball, đi bộ…) trong một khoảng ngày: giờ bắt đầu, thời lượng, calo, nhịp tim TB/max, vùng tim.

        Args:
            tu: Ngày đầu YYYY-MM-DD.
            den: Ngày cuối YYYY-MM-DD.
        """
        from .tong_ket import _buoi_tap
        a, b = _khoang(tu, den)
        ra = []
        for act in g().get_activities_by_date(a.isoformat(), b.isoformat()) or []:
            ra.append({"ngay": (act.get("startTimeLocal") or "")[:10], **_buoi_tap(act)})
        return json.dumps(ra, ensure_ascii=False)

    @beta_tool
    def chi_so_tap(ngay: str) -> str:
        """Chỉ số tập luyện của một ngày nếu đồng hồ có: sẵn sàng tập (0–100), VO2max, trạng thái tập.

        Args:
            ngay: Ngày YYYY-MM-DD.
        """
        from .garmin_them import chi_so_tap as cs
        return json.dumps(cs(g(), _ngay(ngay)) or {"co_du_lieu": False}, ensure_ascii=False)

    @beta_tool
    def so_can() -> str:
        """Sổ cân nặng (tối đa 60 lần cân gần nhất) và cân mục tiêu nếu có."""
        ds = can_nang.doc(p)
        return json.dumps({"lan_can": ds[-60:], "muc_tieu_kg": can_nang.muc_tieu(p) or None}, ensure_ascii=False)

    @beta_tool
    def bua_an(ngay: str) -> str:
        """Các bữa ăn đã chụp ảnh gửi Mia trong một ngày: giờ, món, calo, đạm (ước lượng từ ảnh).

        Args:
            ngay: Ngày YYYY-MM-DD.
        """
        from . import bua_an as ba
        return json.dumps(ba.trong_ngay(p, _ngay(ngay)), ensure_ascii=False)

    cung = [so_can, bua_an]
    if p.get("co_garmin"):
        cung = [giac_ngu, giac_ngu_nhieu_dem, mot_ngay, buoc_chan, buoi_tap, chi_so_tap] + cung
    return cung


def tra_loi(p: dict, cau: str) -> str:
    g, x = p["goi"], p["xung"]
    hom_nay = hom_nay_vn()
    dem_key = f"dem_hoi:{p['id']}:{hom_nay.isoformat()}"
    dem = int(kho.doc(dem_key) or 0)
    if not nguoi.la_chu(p["id"]) and dem >= HOI_MOI_NGAY:
        return f"Hôm nay {g} hỏi {HOI_MOI_NGAY} câu rồi, mai {x} trả lời tiếp nha 🙏"
    kho.ghi(str(dem + 1), dem_key)

    nho_key = f"hoi:{p['id']}"
    try:
        nho = json.loads(kho.doc(nho_key) or "{}")
    except ValueError:
        nho = {}
    lich_su = nho.get("ds") if nho.get("ngay") == hom_nay.isoformat() else []

    system = (SYSTEM.replace("{goi}", g).replace("{xung}", x)
              .replace("{hom_nay}", f"{THU[hom_nay.weekday()]} {hom_nay.isoformat()}")
              .replace("{garmin}", "" if p.get("co_garmin") else
                       f"{nguoi.hoa(g)} chưa kết nối Garmin nên chỉ có sổ cân và bữa ăn; hỏi số Garmin thì nhắc {g} bấm /caidat để kết nối."))
    messages = (lich_su or []) + [{"role": "user", "content": cau.strip()[:2000]}]
    dap = ai.chay_cong_cu(system, messages, _cong_cu(p)) or f"{nguoi.hoa(x)} chưa nghĩ ra câu trả lời, {g} hỏi lại kiểu khác nha."
    lich_su = (messages + [{"role": "assistant", "content": dap}])[-NHO_LUOT:]
    if lich_su and lich_su[0]["role"] != "user":
        lich_su = lich_su[1:]
    kho.ghi(json.dumps({"ngay": hom_nay.isoformat(), "ds": lich_su}, ensure_ascii=False), nho_key)
    return escape(dap)
