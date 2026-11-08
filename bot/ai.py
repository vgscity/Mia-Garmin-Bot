# Mọi chỗ cần AI (nhận xét giấc ngủ, tổng kết ngày, chọn + kể tin, soạn thực đơn, nhận xét game)
# đều đi qua đây, gọi Claude bằng SDK anthropic. Model đặt bằng CLAUDE_MODEL (mặc định claude-opus-5-5),
# độ sâu suy nghĩ bằng CLAUDE_EFFORT (mặc định "low": việc ở đây là tóm tắt số liệu, không cần nghĩ sâu).
# Trả JSON thì truyền schema → dùng structured output của API, không cần dặn "trả JSON" trong prompt.
import json
import os

import anthropic

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("CLAUDE_EFFORT", "low")

_khach_hang: anthropic.Anthropic | None = None


def _khach() -> anthropic.Anthropic:
    global _khach_hang
    if _khach_hang is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("Thiếu ANTHROPIC_API_KEY")
        # SDK tự thử lại 429/5xx; 90s đủ cho bản tin dài, cron có maxDuration 300.
        _khach_hang = anthropic.Anthropic(max_retries=3, timeout=90.0)
    return _khach_hang


def schema_chuan(s: dict) -> dict:
    """Đổi schema kiểu Gemini (type viết HOA, không có additionalProperties) sang JSON Schema chuẩn
    mà structured output của Claude đòi: type thường, object nào cũng additionalProperties=false
    và required đủ mọi trường."""
    if not isinstance(s, dict):
        return s
    ra = {}
    for k, v in s.items():
        if k == "type" and isinstance(v, str):
            ra[k] = v.lower()
        elif k == "properties":
            ra[k] = {ten: schema_chuan(con) for ten, con in v.items()}
        elif k == "items":
            ra[k] = schema_chuan(v)
        else:
            ra[k] = v
    if ra.get("type") == "object":
        ra["additionalProperties"] = False
        ra["required"] = list((ra.get("properties") or {}).keys())
    return ra


def goi_ai(system: str, du_lieu, *, max_tokens: int = 1024, schema: dict | None = None) -> str:
    """Gửi system + dữ liệu (JSON) cho Claude, trả về chữ (hoặc chuỗi JSON đúng schema nếu có schema)."""
    output_config: dict = {"effort": EFFORT}
    if schema:
        output_config["format"] = {"type": "json_schema", "schema": schema_chuan(schema)}
    try:
        r = _khach().beta.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": json.dumps(du_lieu, ensure_ascii=False)}],
            output_config=output_config,
            # Bị bộ lọc an toàn từ chối thì máy chủ tự chạy lại bằng model khác, khỏi mất bản tin.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.RateLimitError as e:
        raise RuntimeError("Claude đang quá tải (429), thử lại sau") from e
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"Claude lỗi {e.status_code}: {e.message}"[:300]) from e
    except anthropic.APIConnectionError as e:
        raise RuntimeError(f"Không nối được Claude: {type(e).__name__}") from e
    if r.stop_reason == "refusal":
        ly_do = (r.stop_details.category if r.stop_details else None) or "không rõ"
        raise RuntimeError(f"Claude từ chối trả lời ({ly_do})")
    text = "".join(b.text for b in r.content if b.type == "text").strip()
    if not text:
        raise RuntimeError("Claude không trả về nội dung")
    if r.stop_reason == "max_tokens":
        print(f"Claude bị cắt ở max_tokens={max_tokens} (model {r.model})")
    return text


def goi_gemini(system: str, du_lieu, config: dict) -> str:
    """Tên cũ (thời còn Gemini) — giữ cho chỗ nào chưa đổi. temperature bỏ qua: Claude đời mới không nhận."""
    return goi_ai(system, du_lieu, max_tokens=int(config.get("maxOutputTokens") or 1024),
                  schema=config.get("responseSchema"))


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
    return goi_ai(_xung(SYSTEM, p), du_lieu, max_tokens=1024)


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
    return goi_ai(_xung(SYSTEM_TOI, p), du_lieu, max_tokens=1024)
