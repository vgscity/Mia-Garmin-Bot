# Một dòng thời tiết cho tin sáng (08/11/2026), nguồn Open-Meteo (miễn phí, không cần khoá).
# Toạ độ lấy từ Mini App (chọn thành phố hoặc dùng vị trí hiện tại). Gợi ý vận động tính bằng luật
# đơn giản, không dùng AI.
import json
import urllib.request
from urllib.parse import urlencode

THANH_PHO = {
    "Hà Nội": (21.03, 105.85), "TP.HCM": (10.82, 106.63), "Đà Nẵng": (16.05, 108.22), "Hải Phòng": (20.86, 106.68),
    "Cần Thơ": (10.03, 105.78), "Vinh": (18.68, 105.69), "Huế": (16.46, 107.59), "Nha Trang": (12.24, 109.19),
    "Đà Lạt": (11.94, 108.44), "Quy Nhơn": (13.78, 109.22), "Vũng Tàu": (10.35, 107.08), "Hạ Long": (20.95, 107.08),
}

# Mã thời tiết WMO → chữ
MA = [
    ((0,), "trời quang"), ((1, 2), "ít mây"), ((3,), "nhiều mây"), ((45, 48), "sương mù"),
    ((51, 53, 55, 56, 57), "mưa phùn"), ((61, 63, 80, 81), "có mưa"), ((65, 82), "mưa to"),
    ((66, 67), "mưa lạnh"), ((71, 73, 75, 77, 85, 86), "tuyết"), ((95, 96, 99), "giông"),
]


def _chu_ma(ma: int) -> str:
    for ds, chu in MA:
        if ma in ds:
            return chu
    return "thời tiết thay đổi"


def du_bao(vi_do: float, kinh_do: float) -> dict | None:
    q = urlencode({
        "latitude": vi_do, "longitude": kinh_do, "timezone": "Asia/Ho_Chi_Minh", "forecast_days": 1,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
    })
    req = urllib.request.Request(f"https://api.open-meteo.com/v1/forecast?{q}", headers={"User-Agent": "mia-garmin-bot"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.load(r).get("daily") or {}
        return {"ma": d["weather_code"][0], "cao": d["temperature_2m_max"][0], "thap": d["temperature_2m_min"][0],
                "mua": d.get("precipitation_probability_max", [None])[0]}
    except Exception as e:
        print(f"Open-Meteo lỗi: {type(e).__name__}: {e}")
        return None


def dong_thoi_tiet(p: dict) -> str | None:
    if not p.get("thoi_tiet") or not (p.get("vi_do") or p.get("kinh_do")):
        return None
    d = du_bao(p["vi_do"], p["kinh_do"])
    if not d:
        return None
    g = p["goi"]
    mua = d["mua"] if isinstance(d["mua"], (int, float)) else 0
    if mua >= 60 or d["ma"] in (65, 82, 95, 96, 99):
        goi_y = f"hôm nay {g} tập trong nhà cho chắc"
    elif d["cao"] >= 35:
        goi_y = f"nắng nóng, {g} vận động sáng sớm hoặc chiều tối nha"
    elif d["thap"] <= 15:
        goi_y = f"trời lạnh, {g} mặc ấm và khởi động kỹ trước khi tập"
    else:
        goi_y = f"trời đẹp, hợp đi bộ hay chạy ngoài trời"
    noi = p.get("noi") or "Chỗ " + g
    return (f"🌤 {noi}: {_chu_ma(d['ma'])}, {round(d['thap'])}–{round(d['cao'])}°C"
            + (f", mưa {round(mua)}%" if mua else "") + f" — {goi_y}.")
