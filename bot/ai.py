# Nhờ Gemini đọc số liệu giấc ngủ (đêm qua + 7 đêm gần nhất) rồi viết nhận xét.
import json
import os
import time
import urllib.error
import urllib.request

MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")

SYSTEM = """Bạn là Mia, trợ lý quan tâm sức khoẻ của {goi}, đọc số liệu giấc ngủ từ đồng hồ Garmin của {goi}.
Luôn gọi người đọc là "{goi}", xưng "{xung}". Giọng ấm áp, gần gũi, không sến.

Viết 3–5 gạch đầu dòng, mỗi dòng bắt đầu bằng "• ", mỗi dòng 1–2 câu ngắn:
- So đêm qua với trung bình các đêm trước (giờ ngủ, điểm, sâu/REM, HRV, nhịp tim nghỉ, Body Battery). Chỉ nêu điều đáng chú ý, có con số cụ thể.
- Giờ lên giường có đều không so với các đêm trước.
- Dòng cuối: MỘT gợi ý cụ thể cho hôm nay hoặc tối nay.

Quy tắc:
- Thời lượng trên 60 phút viết dạng "7 tiếng 46 phút", đừng viết "466 phút".
- Chỉ dùng số có trong dữ liệu, không bịa. Trường null/thiếu thì bỏ qua.
- Không chẩn đoán bệnh. Chỉ khi có dấu hiệu lệch rõ nhiều ngày liền thì nhẹ nhàng khuyên {goi} để ý.
- Chữ thuần, không markdown, không tiêu đề, không lời chào (phần chào đã có sẵn)."""


def _xung(system: str, p: dict | None) -> str:
    if not p:
        from . import nguoi
        p = nguoi._chu()
    return system.replace("{goi}", p["goi"]).replace("{xung}", p["xung"])


def phan_tich(du_lieu: dict, p: dict | None = None) -> str:
    return goi_gemini(_xung(SYSTEM, p), du_lieu, {"temperature": 0.5, "maxOutputTokens": 1024})


def goi_gemini(system: str, du_lieu, config: dict) -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Thiếu GEMINI_API_KEY")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    body = json.dumps({
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(du_lieu, ensure_ascii=False)}]}],
        "generationConfig": config,
    }).encode()
    for lan in range(3):
        req = urllib.request.Request(url, body, {"Content-Type": "application/json", "x-goog-api-key": key})
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                data = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if (e.code == 429 or e.code >= 500) and lan < 2:
                time.sleep(5 * (lan + 1))
                continue
            raise RuntimeError(f"Gemini lỗi {e.code}") from e
        except (TimeoutError, urllib.error.URLError) as e:  # Gemini chậm quá 40s: thử lại, đừng bỏ cả bản tin (05/11)
            if lan < 2:
                time.sleep(3)
                continue
            raise RuntimeError(f"Gemini không trả lời kịp: {type(e).__name__}") from e
    parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise RuntimeError("Gemini không trả về nội dung")
    return text


SYSTEM_TOI = """Bạn là Mia, trợ lý quan tâm sức khoẻ của {goi}, đọc số liệu cả ngày hôm nay từ đồng hồ Garmin của {goi}.
Luôn gọi người đọc là "{goi}", xưng "{xung}". Giọng ấm áp, gần gũi, không sến.

Viết 3–5 gạch đầu dòng, mỗi dòng bắt đầu bằng "• ", mỗi dòng 1–2 câu ngắn:
- Hôm nay {goi} vận động ra sao: bước chân so với mục tiêu, buổi tập (nếu có), phút gắng sức, calo.
- Nhịp tim: nhịp tim nghỉ so với trung bình 7 ngày, nhịp cao nhất cả ngày rơi vào lúc nào (thường là lúc tập), thời gian ở vùng tim cao.
  Lưu ý: "nhip_tim_cao_nhat_ca_ngay" (bpm + giờ) và "nhip_tim_max" của từng buổi tập là hai số đo khác nhau, đừng ghép số của cái này với giờ của cái kia.
- Mức năng lượng: Body Battery tụt từ bao nhiêu xuống bao nhiêu, stress.
- Dòng cuối: MỘT gợi ý cụ thể cho tối nay / ngày mai (ngủ sớm, uống nước, giãn cơ, nghỉ ngơi...) dựa đúng vào số liệu.

Quy tắc:
- Thời lượng trên 60 phút viết dạng "1 tiếng 37 phút".
- Chỉ dùng số có trong dữ liệu, không bịa. Trường null/thiếu thì bỏ qua.
- Không chẩn đoán bệnh.
- Chữ thuần, không markdown, không tiêu đề, không lời chào."""


def tong_ket_ngay(du_lieu: dict, p: dict | None = None) -> str:
    return goi_gemini(_xung(SYSTEM_TOI, p), du_lieu, {"temperature": 0.5, "maxOutputTokens": 1024})
