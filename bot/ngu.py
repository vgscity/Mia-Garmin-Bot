# Kéo giấc ngủ từ Garmin Connect và soạn tin báo buổi sáng.
# Người nhận mặc định (p=None) là chủ bot; cách xưng hô đọc từ biến môi trường (bot/nguoi.py).
from datetime import date, datetime, timedelta, timezone
from html import escape

from garminconnect import Garmin

from . import ai, kho, nguoi

VN = timezone(timedelta(hours=7))
THU = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
MUC = {"EXCELLENT": "Rất tốt", "GOOD": "Tốt", "FAIR": "Tạm", "POOR": "Kém"}
HRV = {"BALANCED": "cân bằng", "UNBALANCED": "chưa cân bằng", "LOW": "thấp", "POOR": "kém"}


def hom_nay_vn() -> date:
    # Vercel chạy UTC, phải tính ngày theo giờ VN tường minh.
    return datetime.now(VN).date()


def ket_noi(nguoi_id=None) -> Garmin:
    key = nguoi.key_token(nguoi_id) if nguoi_id else kho.KEY
    tokens = kho.doc(key)
    if not tokens:
        raise RuntimeError("Chưa kết nối Garmin — mở Mia (nút Menu) để kết nối")
    g = Garmin()
    g.login(tokens)
    moi = g.client.dumps()
    if moi != tokens:
        kho.ghi(moi, key)
    return g


def lay_giac_ngu(g: Garmin, ngay: date) -> dict:
    return g.get_sleep_data(ngay.isoformat()) or {}


def _gio(giay) -> str:
    if not giay:
        return "0p"
    phut = round(giay / 60)
    return f"{phut // 60}g{phut % 60:02d}" if phut >= 60 else f"{phut}p"


def _luc(ms) -> str:
    return datetime.fromtimestamp(ms / 1000, VN).strftime("%H:%M") if ms else "?"


def _loi_nhan(diem, tong, p: dict | None = None) -> str:
    p = p or nguoi._chu()
    g, x = p["goi"], p["xung"]
    if diem is None:
        diem = 80 if tong >= 7 * 3600 else 60 if tong >= 6 * 3600 else 40
    if diem >= 85:
        return f"Đêm qua {g} ngủ ngon lắm, hôm nay chiến hết mình nha {g} 💪"
    if diem >= 70:
        return f"{nguoi.hoa(g)} ngủ khá ổn, chúc {g} một ngày thật nhiều năng lượng ☀️"
    if diem >= 55:
        return f"Giấc ngủ hơi chập chờn, trưa nay {g} tranh thủ chợp mắt chút nha 😴"
    return f"Đêm qua {g} ngủ ít quá, tối nay {g} đi ngủ sớm giúp {x} nha ❤️"


def soan_tin(data: dict, ngay: date, nhan_xet: str | None = None, p: dict | None = None) -> str:
    p = p or nguoi._chu()
    g, x = p["goi"], p["xung"]
    dto = data.get("dailySleepDTO") or {}
    tong = dto.get("sleepTimeSeconds")
    tieu_de = f"🌙 <b>Giấc ngủ của {g} — {THU[ngay.weekday()]}, {ngay:%d/%m}</b>"
    if not tong:
        return (
            f"{tieu_de}\n\n{nguoi.hoa(x)} chưa thấy dữ liệu giấc ngủ đêm qua của {g} 🥺\n"
            f"{nguoi.hoa(g)} mở app Garmin Connect cho đồng hồ đồng bộ, rồi nhắn /ngu là {x} báo lại liền nha."
        )

    dong = [tieu_de, "", f"{nguoi.hoa(x)} chào buổi sáng {g}! ☀️"]
    scores = dto.get("sleepScores") or {}
    overall = scores.get("overall") or {}
    diem = overall.get("value")
    if diem is not None:
        muc = MUC.get(overall.get("qualifierKey"), "")
        dong.append(f"⭐ Điểm ngủ: <b>{diem}</b>/100" + (f" ({muc})" if muc else ""))
    can = (dto.get("sleepNeed") or {}).get("actual")
    dong.append(
        f"🛏 Ngủ <b>{_gio(tong)}</b>" + (f" / cần {_gio(can * 60)}" if can else "")
        + f" ({_luc(dto.get('sleepStartTimestampGMT'))} → {_luc(dto.get('sleepEndTimestampGMT'))})"
    )
    giai_doan = [
        ("Sâu", dto.get("deepSleepSeconds")),
        ("Nông", dto.get("lightSleepSeconds")),
        ("REM", dto.get("remSleepSeconds")),
        ("Thức", dto.get("awakeSleepSeconds")),
    ]
    if any(v for _, v in giai_doan):
        dong.append("   " + " · ".join(f"{t} {_gio(v)}" for t, v in giai_doan if v is not None))

    phu = []
    if data.get("restingHeartRate"):
        phu.append(f"❤️ Nhịp tim nghỉ {data['restingHeartRate']} bpm")
    if data.get("avgOvernightHrv"):
        hrv = HRV.get(data.get("hrvStatus"))
        phu.append(f"💓 HRV đêm {round(data['avgOvernightHrv'])} ms" + (f" ({hrv})" if hrv else ""))
    if dto.get("averageSpO2Value"):
        spo2 = f"🫁 SpO2 TB {round(dto['averageSpO2Value'])}%"
        if dto.get("lowestSpO2Value"):
            spo2 += f" (thấp nhất {dto['lowestSpO2Value']}%)"
        phu.append(spo2)
    if dto.get("averageRespirationValue"):
        phu.append(f"🌬 Nhịp thở {round(dto['averageRespirationValue'])} lần/phút")
    if data.get("bodyBatteryChange") is not None:
        phu.append(f"🔋 Body Battery hồi {round(data['bodyBatteryChange']):+d}")
    if dto.get("avgSleepStress") is not None:
        phu.append(f"😌 Stress khi ngủ {round(dto['avgSleepStress'])}")
    if data.get("avgSkinTempDeviationC") is not None:
        phu.append(f"🌡 Nhiệt độ da {data['avgSkinTempDeviationC']:+.1f}°C so với thường ngày")
    if phu:
        dong += [""] + phu

    if nhan_xet:
        dong += ["", f"🧠 <b>{nguoi.hoa(x)} phân tích</b>", escape(nhan_xet)]
    else:
        dong += ["", escape(_loi_nhan(diem, tong, p))]
    return "\n".join(dong)


def _phut(giay):
    return round(giay / 60) if giay is not None else None


def du_lieu_cho_ai(data: dict, lich_su: list[dict], ngay: date) -> dict:
    dto = data.get("dailySleepDTO") or {}
    scores = dto.get("sleepScores") or {}
    dem_qua = {
        "ngay": ngay.isoformat(),
        "diem_ngu": (scores.get("overall") or {}).get("value"),
        "danh_gia_tung_muc": {k: v.get("qualifierKey") for k, v in scores.items() if isinstance(v, dict)},
        "tong_ngu_phut": _phut(dto.get("sleepTimeSeconds")),
        "can_ngu_phut": (dto.get("sleepNeed") or {}).get("actual"),
        "len_giuong": _luc(dto.get("sleepStartTimestampGMT")),
        "thuc_day": _luc(dto.get("sleepEndTimestampGMT")),
        "sau_phut": _phut(dto.get("deepSleepSeconds")),
        "nong_phut": _phut(dto.get("lightSleepSeconds")),
        "rem_phut": _phut(dto.get("remSleepSeconds")),
        "thuc_giac_phut": _phut(dto.get("awakeSleepSeconds")),
        "so_lan_thuc": dto.get("awakeCount"),
        "nhip_tim_tb_khi_ngu": dto.get("avgHeartRate"),
        "nhip_tim_nghi": data.get("restingHeartRate"),
        "hrv_dem": data.get("avgOvernightHrv"),
        "hrv_trang_thai": data.get("hrvStatus"),
        "spo2_tb": dto.get("averageSpO2Value"),
        "nhip_tho_tb": dto.get("averageRespirationValue"),
        "stress_khi_ngu": dto.get("avgSleepStress"),
        "body_battery_hoi": data.get("bodyBatteryChange"),
        "nhiet_do_da_lech_C": data.get("avgSkinTempDeviationC"),
        "so_lan_tro_minh": data.get("restlessMomentsCount"),
        "garmin_nhan_xet": dto.get("sleepScoreFeedback"),
    }
    cac_dem_truoc = []
    for row in lich_su:
        v = row.get("values") or {}
        if row.get("calendarDate") == ngay.isoformat() or not v.get("totalSleepTimeInSeconds"):
            continue
        cac_dem_truoc.append({
            "ngay": row.get("calendarDate"),
            "diem_ngu": v.get("sleepScore"),
            "tong_ngu_phut": _phut(v.get("totalSleepTimeInSeconds")),
            "len_giuong": _luc(v.get("gmtSleepStartTimeInMillis")),
            "thuc_day": _luc(v.get("gmtSleepEndTimeInMillis")),
            "sau_phut": _phut(v.get("deepTime")),
            "rem_phut": _phut(v.get("remTime")),
            "nhip_tim_nghi": v.get("restingHeartRate"),
            "hrv_dem": v.get("avgOvernightHrv"),
            "body_battery_hoi": v.get("bodyBatteryChange"),
        })
    return {"dem_qua": dem_qua, "cac_dem_truoc": cac_dem_truoc}


def bao_cao(ngay: date | None = None, p: dict | None = None) -> str:
    p = p or nguoi._chu()
    ngay = ngay or hom_nay_vn()
    g = ket_noi(p["id"])
    data = lay_giac_ngu(g, ngay)
    nhan_xet = None
    if (data.get("dailySleepDTO") or {}).get("sleepTimeSeconds"):
        try:
            lich_su = g.get_sleep_daily((ngay - timedelta(days=7)).isoformat(), ngay.isoformat())
            nhan_xet = ai.phan_tich(du_lieu_cho_ai(data, lich_su, ngay), p)
        except Exception as e:  # AI hỏng thì vẫn gửi số liệu
            print(f"AI phân tích lỗi: {type(e).__name__}: {e}")
    return soan_tin(data, ngay, nhan_xet, p)
