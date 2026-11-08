# Số Garmin phụ cho tin sáng (08/11/2026): cân tự động từ cân Garmin Index, chỉ số tập luyện
# (training readiness, VO2max, trạng thái tập), thời điểm đồng hồ đồng bộ lần cuối.
# Mỗi đồng hồ / tài khoản trả dữ liệu khác nhau (vòng tay không có VO2max…), nên mọi hàm ở đây
# đọc phòng thủ: thiếu gì bỏ nấy, lỗi thì trả rỗng chứ không làm hỏng tin sáng.
from datetime import date, datetime, timedelta

from .ngu import VN

SAN_SANG = {"PRIME": "rất cao", "HIGH": "cao", "MODERATE": "vừa", "LOW": "thấp", "POOR": "rất thấp"}
TRANG_THAI = {
    "PEAKING": "đỉnh phong độ", "PRODUCTIVE": "hiệu quả", "MAINTAINING": "duy trì", "RECOVERY": "đang phục hồi",
    "UNPRODUCTIVE": "kém hiệu quả", "DETRAINING": "giảm phong độ", "OVERREACHING": "quá tải", "STRAINED": "căng",
}


def _tim(obj, khoa: str, sau: int = 0):
    """Tìm giá trị đầu tiên của khoá `khoa` ở bất kỳ tầng nào trong JSON lồng nhau."""
    if sau > 8:
        return None
    if isinstance(obj, dict):
        if obj.get(khoa) is not None:
            return obj[khoa]
        for v in obj.values():
            r = _tim(v, khoa, sau + 1)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _tim(v, khoa, sau + 1)
            if r is not None:
                return r
    return None


def chi_so_tap(g, ngay: date) -> dict:
    """{"san_sang": 72, "muc": "vừa", "vo2max": 48.2, "trang_thai": "hiệu quả"} — chỉ có khoá nào đồng hồ trả về."""
    d = ngay.isoformat()
    ra: dict = {}
    try:
        tr = g.get_training_readiness(d) or []
        diem = _tim(tr, "score")
        if isinstance(diem, (int, float)):
            ra["san_sang"] = round(diem)
            muc = _tim(tr, "level")
            if isinstance(muc, str) and muc.upper() in SAN_SANG:
                ra["muc"] = SAN_SANG[muc.upper()]
    except Exception as e:
        print(f"training readiness lỗi: {type(e).__name__}")
    try:
        mm = g.get_max_metrics(d)
        vo2 = _tim(mm, "vo2MaxPreciseValue") or _tim(mm, "vo2MaxValue")
        if isinstance(vo2, (int, float)) and vo2 > 0:
            ra["vo2max"] = round(float(vo2), 1)
    except Exception as e:
        print(f"max metrics lỗi: {type(e).__name__}")
    try:
        ts = g.get_training_status(d)
        cau = _tim(ts, "trainingStatusFeedbackPhrase")
        if isinstance(cau, str):
            for k, v in TRANG_THAI.items():
                if cau.upper().startswith(k):
                    ra["trang_thai"] = v
                    break
        if "vo2max" not in ra:
            vo2 = _tim(ts, "vo2MaxPreciseValue") or _tim(ts, "vo2MaxValue")
            if isinstance(vo2, (int, float)) and vo2 > 0:
                ra["vo2max"] = round(float(vo2), 1)
    except Exception as e:
        print(f"training status lỗi: {type(e).__name__}")
    return ra


def dong_chi_so(cs: dict) -> str | None:
    phan = []
    if "san_sang" in cs:
        phan.append(f"sẵn sàng tập {cs['san_sang']}/100" + (f" ({cs['muc']})" if cs.get("muc") else ""))
    if "vo2max" in cs:
        phan.append(f"VO2max {cs['vo2max']:g}")
    if "trang_thai" in cs:
        phan.append(f"tập luyện {cs['trang_thai']}")
    return ("💪 " + " · ".join(phan)) if phan else None


def can_hom_nay(g, ngay: date) -> float | None:
    """Số cân (kg) đo hôm nay trên cân Garmin Index, None nếu không có."""
    try:
        w = g.get_daily_weigh_ins(ngay.isoformat()) or {}
    except Exception as e:
        print(f"weigh-in lỗi: {type(e).__name__}")
        return None
    ds = w.get("dateWeightList") or []
    for muc in reversed(ds):
        gram = (muc or {}).get("weight")
        if isinstance(gram, (int, float)) and gram > 0:
            kg = gram / 1000 if gram > 500 else float(gram)
            if 30 <= kg <= 250:
                return round(kg, 1)
    return None


def dong_bo_lan_cuoi(g) -> datetime | None:
    """Lần đồng hồ đẩy dữ liệu lên Garmin Connect gần nhất (giờ VN)."""
    try:
        d = g.get_device_last_used() or {}
    except Exception as e:
        print(f"device last used lỗi: {type(e).__name__}")
        return None
    for k, v in d.items():
        if "uploadtime" in k.lower() and isinstance(v, (int, float)) and v > 0:
            return datetime.fromtimestamp(v / 1000 if v > 1e11 else v, VN)
    return None


def cu_chua(luc: datetime | None, gio: int = 18) -> bool:
    return bool(luc) and datetime.now(VN) - luc > timedelta(hours=gio)
