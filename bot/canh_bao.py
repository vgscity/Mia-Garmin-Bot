# Nhắc nhẹ khi số giấc ngủ lệch nhiều ngày liền (08/11/2026). Không dùng AI, không chẩn đoán:
# chỉ đếm và so với chính người đó, rồi khuyên nghỉ ngơi. Đầu vào là lịch sử get_sleep_daily
# (mỗi dòng {"calendarDate", "values": {...}}) đã có sẵn trong tin sáng.
from . import nguoi


def _gt(row: dict, k: str):
    v = (row.get("values") or {}).get(k)
    return v if isinstance(v, (int, float)) and v > 0 else None


def canh_bao(lich_su: list[dict], p: dict) -> list[str]:
    rows = sorted([r for r in lich_su or [] if _gt(r, "totalSleepTimeInSeconds")], key=lambda r: r.get("calendarDate") or "")
    if len(rows) < 4:
        return []
    g, x = p["goi"], p["xung"]
    ra = []

    # Ngủ dưới 6 tiếng từ 3 trong 4 đêm gần nhất.
    gan = rows[-4:]
    it = sum(1 for r in gan if _gt(r, "totalSleepTimeInSeconds") < 6 * 3600)
    if it >= 3:
        ra.append(f"{it}/4 đêm gần đây {g} ngủ dưới 6 tiếng. Tối nay {g} thử lên giường sớm hơn 30 phút nha.")

    # Nhịp tim nghỉ tăng 3 đêm liền và đêm qua cao hơn trung bình các đêm trước từ 4 bpm.
    tim = [_gt(r, "restingHeartRate") for r in rows]
    if all(tim[-4:]) and len(tim) >= 4:
        t = tim[-4:]
        truoc = [v for v in tim[:-1] if v]
        tb = sum(truoc) / len(truoc) if truoc else 0
        if t[1] > t[0] and t[2] > t[1] and t[3] > t[2] and tb and t[3] - tb >= 4:
            ra.append(f"Nhịp tim nghỉ của {g} tăng 3 đêm liền (nay {round(t[3])} bpm, thường khoảng {round(tb)}). "
                      f"Có thể {g} đang mệt hoặc thiếu ngủ, hôm nay nên tập nhẹ và uống đủ nước.")

    # HRV đêm qua thấp hơn trung bình các đêm trước từ 15% và 2 đêm liền đều thấp.
    hrv = [_gt(r, "avgOvernightHrv") for r in rows]
    co = [v for v in hrv[:-2] if v]
    if len(co) >= 3 and hrv[-1] and hrv[-2]:
        tb = sum(co) / len(co)
        if hrv[-1] < tb * 0.85 and hrv[-2] < tb * 0.85:
            ra.append(f"HRV hai đêm gần đây thấp hơn mức thường ngày của {g} ({round(hrv[-1])} so với khoảng {round(tb)} ms). "
                      f"{nguoi.hoa(x)} nghĩ {g} nên ưu tiên nghỉ ngơi hôm nay.")
    return ra
