# Tổng kết tuần (08/11/2026): sáng Chủ nhật, kèm tin giấc ngủ; lệnh /tuan để xem bất cứ lúc nào.
# So 7 ngày gần nhất (hết hôm qua) với 7 ngày trước đó: giấc ngủ, bước chân, buổi tập.
# Số liệu tính bằng code, AI chỉ viết 2–3 dòng nhận xét + một mục tiêu nhỏ cho tuần tới.
from datetime import date, timedelta
from html import escape

from . import ai, nguoi
from .ngu import THU, _gio, hom_nay_vn, ket_noi
from .tong_ket import _so, _buoi_tap

SYSTEM = """Bạn là Mia, quan tâm sức khoẻ của {goi}. Gọi "{goi}", xưng "{xung}". Giọng ấm áp, gần gũi, không sến.
Đầu vào là số liệu tuần này ("tuan_nay") và tuần trước ("tuan_truoc") từ đồng hồ Garmin.
Viết 2–3 gạch đầu dòng bắt đầu bằng "• " (mỗi dòng 1–2 câu, có con số) về điều đáng chú ý nhất khi so hai tuần,
rồi một dòng cuối bắt đầu bằng "🎯 Tuần tới: " nêu MỘT mục tiêu nhỏ, cụ thể, làm được (ví dụ lên giường trước 23h ít nhất 5 đêm).
Thời lượng viết dạng "6 tiếng 27 phút", đừng viết số phút trần. Chỉ dùng số có trong dữ liệu, không bịa, không chẩn đoán bệnh. Chữ thuần, không markdown, không lời chào."""


def _tuan(g, tu: date, den: date) -> dict:
    d1, d2 = tu.isoformat(), den.isoformat()
    ngu = []
    try:
        for r in g.get_sleep_daily(d1, d2) or []:
            v = r.get("values") or {}
            if v.get("totalSleepTimeInSeconds"):
                ngu.append({"ngay": r.get("calendarDate"), "giay": v["totalSleepTimeInSeconds"], "diem": v.get("sleepScore")})
    except Exception as e:
        print(f"Tuần: giấc ngủ lỗi: {type(e).__name__}")
    buoc = []
    try:
        for r in g.get_daily_steps(d1, d2) or []:
            if r.get("totalSteps") is not None:
                buoc.append({"ngay": r.get("calendarDate"), "buoc": r["totalSteps"], "muc_tieu": r.get("stepGoal")})
    except Exception as e:
        print(f"Tuần: bước chân lỗi: {type(e).__name__}")
    tap = []
    try:
        tap = [_buoi_tap(a) for a in (g.get_activities_by_date(d1, d2) or [])]
    except Exception as e:
        print(f"Tuần: buổi tập lỗi: {type(e).__name__}")

    tb_ngu = sum(x["giay"] for x in ngu) / len(ngu) if ngu else None
    diem = [x["diem"] for x in ngu if x.get("diem")]
    te = min(ngu, key=lambda x: x["giay"]) if ngu else None
    tong_buoc = sum(x["buoc"] for x in buoc)
    dat = sum(1 for x in buoc if x.get("muc_tieu") and x["buoc"] >= x["muc_tieu"])
    return {
        "so_dem": len(ngu), "ngu_tb_giay": tb_ngu, "diem_tb": round(sum(diem) / len(diem)) if diem else None,
        "dem_te_nhat": te, "tong_buoc": tong_buoc, "so_ngay_buoc": len(buoc), "ngay_dat_muc_tieu": dat,
        "so_buoi_tap": len(tap), "phut_tap": sum(b["thoi_luong_phut"] for b in tap),
        "loai_tap": sorted({b["loai"] for b in tap if b["loai"]}),
    }


def _ngay_ngan(s: str | None) -> str:
    try:
        d = date.fromisoformat(s or "")
        return f"{THU[d.weekday()]} {d:%d/%m}"
    except ValueError:
        return s or "?"


def tong_ket_tuan(p: dict | None = None, ngay: date | None = None) -> str:
    p = p or nguoi._chu()
    g_, x = p["goi"], p["xung"]
    den = (ngay or hom_nay_vn()) - timedelta(days=1)
    tu = den - timedelta(days=6)
    g = ket_noi(p["id"])
    nay = _tuan(g, tu, den)
    truoc = _tuan(g, tu - timedelta(days=7), tu - timedelta(days=1))

    dong = [f"📅 <b>Tổng kết tuần của {g_} — {tu:%d/%m} → {den:%d/%m}</b>", ""]
    if not nay["so_dem"] and not nay["so_ngay_buoc"]:
        return dong[0] + f"\n\nTuần này {x} chưa thấy số liệu nào từ đồng hồ của {g_} 🥺"
    if nay["ngu_tb_giay"]:
        so = f" (tuần trước {_gio(truoc['ngu_tb_giay'])})" if truoc["ngu_tb_giay"] else ""
        dong.append(f"😴 Ngủ trung bình <b>{_gio(nay['ngu_tb_giay'])}</b>/đêm{so}"
                    + (f" · điểm TB {nay['diem_tb']}" if nay["diem_tb"] else ""))
        te = nay["dem_te_nhat"]
        if te:
            dong.append(f"   Đêm ngủ ít nhất: {_ngay_ngan(te['ngay'])}, {_gio(te['giay'])}")
    if nay["so_ngay_buoc"]:
        tb = nay["tong_buoc"] / nay["so_ngay_buoc"]
        dong.append(f"👟 Tổng <b>{_so(nay['tong_buoc'])}</b> bước (TB {_so(tb)}/ngày)"
                    + (f" · {nay['ngay_dat_muc_tieu']}/{nay['so_ngay_buoc']} ngày đạt mục tiêu" if nay["ngay_dat_muc_tieu"] else "")
                    + (f" · tuần trước {_so(truoc['tong_buoc'])}" if truoc["tong_buoc"] else ""))
    if nay["so_buoi_tap"] or truoc["so_buoi_tap"]:
        dong.append(f"🏃 {nay['so_buoi_tap']} buổi tập · {_gio(nay['phut_tap'] * 60)}"
                    + f" (tuần trước {truoc['so_buoi_tap']} buổi)")

    try:
        bo = lambda t: {k: v for k, v in t.items() if k != "dem_te_nhat"} | {
            "dem_te_nhat": t["dem_te_nhat"] and {"ngay": t["dem_te_nhat"]["ngay"], "phut": round(t["dem_te_nhat"]["giay"] / 60)},
            "ngu_tb_phut": round(t["ngu_tb_giay"] / 60) if t["ngu_tb_giay"] else None}
        nhan_xet = ai.goi_ai(ai._xung(SYSTEM, p), {"tuan_nay": bo(nay), "tuan_truoc": bo(truoc)}, max_tokens=5000)
        dong += ["", f"🧠 <b>{nguoi.hoa(x)} nhận xét</b>", escape(nhan_xet)]
    except Exception as e:
        print(f"AI tổng kết tuần lỗi: {type(e).__name__}: {e}")
    return "\n".join(dong)
