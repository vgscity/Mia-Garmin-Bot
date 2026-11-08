# Số gọn cho dashboard màn phụ của chủ bot (phần riêng VGS: vgs.zone/admin/man-phu): giấc ngủ đêm qua,
# vận động + Body Battery hôm nay, cân nặng 30 ngày, thực đơn hôm nay. Chỉ đọc.
# Auth: Authorization: Bearer <MAN_PHU_KEY>. vgs.zone giữ bản đệm 10 phút nên Garmin
# không bị gọi dồn. Phần nào lỗi thì để null, phần kia vẫn trả.
import json
import os
import sys
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import can_nang, kho  # noqa: E402
from bot.ngu import VN, hom_nay_vn, ket_noi, lay_giac_ngu  # noqa: E402
from bot.thuc_don import KEY as KEY_THUC_DON  # noqa: E402


def _luc(ms):
    return datetime.fromtimestamp(ms / 1000, VN).strftime("%H:%M") if ms else None


def _ngu(g, ngay) -> dict | None:
    data = lay_giac_ngu(g, ngay)
    dto = data.get("dailySleepDTO") or {}
    if not dto.get("sleepTimeSeconds"):
        return None
    overall = (dto.get("sleepScores") or {}).get("overall") or {}
    return {
        "tongGiay": dto.get("sleepTimeSeconds"),
        "diem": overall.get("value"),
        "muc": overall.get("qualifierKey"),
        "batDau": _luc(dto.get("sleepStartTimestampGMT")),
        "ketThuc": _luc(dto.get("sleepEndTimestampGMT")),
        "sau": dto.get("deepSleepSeconds") or 0,
        "nhe": dto.get("lightSleepSeconds") or 0,
        "rem": dto.get("remSleepSeconds") or 0,
        "thuc": dto.get("awakeSleepSeconds") or 0,
    }


def _pin_theo_gio(g, ngay) -> list:
    """Body Battery từng giờ trong ngày (24 ô, giờ VN); giờ chưa tới để null."""
    o = [None] * 24
    try:
        ds = g.get_body_battery(ngay.isoformat()) or []
    except Exception:
        return o
    for muc in ds:
        for p in (muc or {}).get("bodyBatteryValuesArray") or []:
            # Dạng [ts, mức] hoặc [ts, "MEASURED", mức, phiên bản] tuỳ phiên bản API.
            if not p or not isinstance(p[0], (int, float)):
                continue
            so = p[2] if len(p) >= 3 and isinstance(p[2], (int, float)) else p[1] if len(p) >= 2 else None
            if isinstance(so, (int, float)):
                o[datetime.fromtimestamp(p[0] / 1000, VN).hour] = so
    return o


def _hom_nay(g, ngay) -> dict:
    s = g.get_stats(ngay.isoformat()) or {}
    vua, manh = s.get("moderateIntensityMinutes") or 0, s.get("vigorousIntensityMinutes") or 0
    return {
        "buoc": s.get("totalSteps") or 0,
        "mucTieuBuoc": s.get("dailyStepGoal"),
        "timNghi": s.get("restingHeartRate"),
        "timNghi7": s.get("lastSevenDaysAvgRestingHeartRate"),
        "phutVanDong": vua + 2 * manh,  # Garmin tính phút mạnh gấp đôi
        "mucTieuPhutTuan": s.get("intensityMinutesGoal"),
        "calo": s.get("totalKilocalories"),
        "pin": s.get("bodyBatteryMostRecentValue"),
        "pinTheoGio": _pin_theo_gio(g, ngay),
    }


def _thuc_don(ngay) -> dict | None:
    try:
        ds = json.loads(kho.doc(KEY_THUC_DON) or "[]")
    except Exception:
        return None
    m = next((x for x in ds if x.get("ngay") == ngay.isoformat()), None)
    if not m:
        return None
    kcal = m.get("kcal") or [None, None]
    return {"trua": m["mon"][0], "toi": m["mon"][1], "kcalTrua": kcal[0], "kcalToi": kcal[1]}


def du_lieu() -> dict:
    ngay = hom_nay_vn()
    ra: dict = {"ngay": ngay.isoformat(), "luc": datetime.now(VN).isoformat()}
    try:
        g = ket_noi()
    except Exception as e:
        g = None
        ra["loiGarmin"] = f"{type(e).__name__}: {e}"[:200]
    for ten, ham in (("ngu", lambda: _ngu(g, ngay)), ("homNay", lambda: _hom_nay(g, ngay))):
        try:
            ra[ten] = ham() if g else None
        except Exception as e:
            ra[ten] = None
            ra[f"loi_{ten}"] = f"{type(e).__name__}: {e}"[:200]
    try:
        tu = (ngay - timedelta(days=30)).isoformat()
        ra["canNang"] = [x for x in can_nang.doc() if x["ngay"] >= tu]
        ra["mucTieuCan"] = can_nang.muc_tieu(None)
    except Exception:
        ra["canNang"] = None
    ra["thucDon"] = _thuc_don(ngay)
    return ra


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        key = os.environ.get("MAN_PHU_KEY")
        if not key or self.headers.get("Authorization") != f"Bearer {key}":
            return self._tra(401, {"error": "unauthorized"})
        return self._tra(200, du_lieu())

    def _tra(self, code: int, obj: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode())
