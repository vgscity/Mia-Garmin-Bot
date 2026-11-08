# Tổng kết cuối ngày: vận động, calo, nhịp tim, Body Battery, stress, các buổi tập.
from datetime import date, datetime
from html import escape

from . import ai
from . import nguoi
from .ngu import THU, VN, _gio, hom_nay_vn, ket_noi

MON = {
    "pickleball": "🏓", "tennis": "🎾", "badminton": "🏸", "table_tennis": "🏓",
    "running": "🏃", "treadmill_running": "🏃", "walking": "🚶", "hiking": "🥾",
    "cycling": "🚴", "indoor_cycling": "🚴", "swimming": "🏊", "lap_swimming": "🏊",
    "strength_training": "🏋️", "yoga": "🧘", "soccer": "⚽", "basketball": "🏀",
}


def _so(n) -> str:
    return f"{round(n):,}".replace(",", ".") if n is not None else "?"


def _dinh_tim(hr: dict) -> str | None:
    # Giờ có nhịp tim cao nhất trong ngày (heartRateValues = [[ms, bpm], ...]).
    diem = [p for p in (hr.get("heartRateValues") or []) if p and p[1]]
    if not diem:
        return None
    ms, _ = max(diem, key=lambda p: p[1])
    return datetime.fromtimestamp(ms / 1000, VN).strftime("%H:%M")


def _buoi_tap(a: dict) -> dict:
    loai = (a.get("activityType") or {}).get("typeKey") or ""
    vung = {f"vung_{i}_phut": round((a.get(f"hrTimeInZone_{i}") or 0) / 60) for i in range(1, 6)}
    return {
        "ten": a.get("activityName"),
        "loai": loai,
        "bat_dau": (a.get("startTimeLocal") or "")[11:16],
        "thoi_luong_phut": round((a.get("duration") or 0) / 60),
        "calo": a.get("calories"),
        "nhip_tim_tb": a.get("averageHR"),
        "nhip_tim_max": a.get("maxHR"),
        "buoc": a.get("steps"),
        "hieu_qua_aerobic": round(a["aerobicTrainingEffect"], 1) if a.get("aerobicTrainingEffect") else None,
        **vung,
    }


def soan_tin(s: dict, buoi: list[dict], dinh: str | None, ngay: date, nhan_xet: str | None, p: dict | None = None) -> str:
    p = p or nguoi._chu()
    g, x = p["goi"], p["xung"]
    dong = [f"🌆 <b>Tổng kết ngày của {g} — {THU[ngay.weekday()]}, {ngay:%d/%m}</b>", ""]
    if not s.get("totalSteps") and not s.get("totalKilocalories"):
        return dong[0] + f"\n\nHôm nay {x} chưa thấy số liệu nào từ đồng hồ của {g} 🥺 {nguoi.hoa(g)} mở Garmin Connect cho đồng bộ nha."

    buoc, muc_tieu = s.get("totalSteps") or 0, s.get("dailyStepGoal")
    dat = " ✅" if muc_tieu and buoc >= muc_tieu else ""
    dong.append(f"👟 <b>{_so(buoc)}</b> bước" + (f" / mục tiêu {_so(muc_tieu)}{dat}" if muc_tieu else "")
                + (f" · {s['totalDistanceMeters'] / 1000:.1f} km".replace(".", ",") if s.get("totalDistanceMeters") else ""))
    if s.get("totalKilocalories"):
        dong.append(f"🔥 Tiêu hao <b>{_so(s['totalKilocalories'])}</b> kcal "
                    f"(vận động {_so(s.get('activeKilocalories'))} · nền {_so(s.get('bmrKilocalories'))})")
    vua, manh = s.get("moderateIntensityMinutes") or 0, s.get("vigorousIntensityMinutes") or 0
    if vua or manh:
        dong.append(f"⏱ Phút gắng sức: vừa {vua}p · mạnh {manh}p")

    tim = []
    if s.get("restingHeartRate"):
        tb7 = s.get("lastSevenDaysAvgRestingHeartRate")
        tim.append(f"nghỉ {s['restingHeartRate']}" + (f" (TB 7 ngày {tb7})" if tb7 else ""))
    if s.get("minHeartRate"):
        tim.append(f"thấp {s['minHeartRate']}")
    if s.get("maxHeartRate"):
        tim.append(f"cao {s['maxHeartRate']}" + (f" lúc {dinh}" if dinh else ""))
    if tim:
        dong.append("❤️ Nhịp tim " + " · ".join(tim))
    if s.get("bodyBatteryHighestValue") is not None:
        dong.append(f"🔋 Body Battery cao nhất {s['bodyBatteryHighestValue']} → giờ còn "
                    f"{s.get('bodyBatteryMostRecentValue', '?')}")
    if s.get("averageStressLevel") is not None and s["averageStressLevel"] >= 0:
        dong.append(f"😮‍💨 Stress TB {s['averageStressLevel']} (cao nhất {s.get('maxStressLevel', '?')})")

    if buoi:
        dong += ["", "<b>Buổi tập</b>"]
        for b in buoi:
            dong.append(
                f"{MON.get(b['loai'], '💪')} {escape(b['ten'] or b['loai'])} {b['bat_dau']} · "
                f"{_gio(b['thoi_luong_phut'] * 60)} · {_so(b['calo'])} kcal"
                + (f" · tim TB {round(b['nhip_tim_tb'])}/max {round(b['nhip_tim_max'])}" if b.get("nhip_tim_tb") else "")
            )

    if nhan_xet:
        dong += ["", f"🧠 <b>{nguoi.hoa(x)} phân tích</b>", escape(nhan_xet)]
    dong += ["", f"{nguoi.hoa(g)} nghỉ ngơi sớm nha, chúc {g} ngủ ngon 🌙"]
    return "\n".join(dong)


def tong_ket(ngay: date | None = None, p: dict | None = None) -> str:
    p = p or nguoi._chu()
    ngay = ngay or hom_nay_vn()
    g = ket_noi(p["id"])
    d = ngay.isoformat()
    s = g.get_stats(d) or {}
    buoi = [_buoi_tap(a) for a in (g.get_activities_by_date(d, d) or [])]
    try:
        dinh = _dinh_tim(g.get_heart_rates(d) or {})
    except Exception:
        dinh = None
    nhan_xet = None
    if s.get("totalSteps") or s.get("totalKilocalories"):
        du_lieu = {
            "ngay": d,
            "tong_ket": {k: s.get(k) for k in (
                "totalSteps", "dailyStepGoal", "totalDistanceMeters", "totalKilocalories",
                "activeKilocalories", "bmrKilocalories", "moderateIntensityMinutes",
                "vigorousIntensityMinutes", "intensityMinutesGoal", "highlyActiveSeconds",
                "activeSeconds", "sedentarySeconds", "restingHeartRate",
                "lastSevenDaysAvgRestingHeartRate", "minHeartRate", "maxHeartRate",
                "averageStressLevel", "maxStressLevel", "highStressDuration",
                "bodyBatteryHighestValue", "bodyBatteryLowestValue", "bodyBatteryMostRecentValue",
                "bodyBatteryAtWakeTime", "avgWakingRespirationValue")},
            "nhip_tim_cao_nhat_ca_ngay": {"bpm": s.get("maxHeartRate"), "luc": dinh},
            "buoi_tap": buoi,
        }
        try:
            from . import bua_an
            an = bua_an.trong_ngay(p, ngay)
            if an:
                du_lieu["bua_an_chup_anh"] = an
        except Exception as e:
            print(f"Đọc bữa ăn lỗi: {type(e).__name__}")
        try:
            nhan_xet = ai.tong_ket_ngay(du_lieu, p)
        except Exception as e:
            print(f"AI tổng kết lỗi: {type(e).__name__}: {e}")
    text = soan_tin(s, buoi, dinh, ngay, nhan_xet, p)
    try:
        from . import bua_an
        dong = bua_an.dong_tong(p, ngay)
        if dong:
            text += "\n" + dong
    except Exception as e:
        print(f"Dòng bữa ăn lỗi: {type(e).__name__}")
    return text
