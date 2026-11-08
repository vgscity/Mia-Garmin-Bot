# Bản tin buổi sáng: lấy tin 24h qua, Claude chọn vài tin, đọc nội dung từng bài,
# tóm tắt rồi kể lại theo cách xưng hô của từng người. Ba bản: thời sự (RSS báo Việt), xã hội · văn hoá · thể thao (RSS),
# và công nghệ (nguồn JSON, mặc định VGSNews).
import html
import json
import os
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import escape
from xml.etree import ElementTree

from . import ai, kho, nguoi
from .ngu import THU, VN

VGSNEWS = os.environ.get("VGSNEWS_URL", "https://news.alexvgs.tech/tin.json?limit=30")
RSS_THOI_SU = [
    ("VnExpress", "https://vnexpress.net/rss/thoi-su.rss"),
    ("VnExpress", "https://vnexpress.net/rss/the-gioi.rss"),
    ("Tuổi Trẻ", "https://tuoitre.vn/rss/thoi-su.rss"),
]
# Xã hội · văn hoá · thể thao: mỗi mảng vài nguồn, Claude chọn sao cho mảng nào cũng có tin.
RSS_XA_HOI = [
    ("VnExpress · Đời sống", "https://vnexpress.net/rss/doi-song.rss"),
    ("VnExpress · Giáo dục", "https://vnexpress.net/rss/giao-duc.rss"),
    ("Tuổi Trẻ · Nhịp sống trẻ", "https://tuoitre.vn/rss/nhip-song-tre.rss"),
    ("Tuổi Trẻ · Văn hoá", "https://tuoitre.vn/rss/van-hoa.rss"),
    ("VnExpress · Giải trí", "https://vnexpress.net/rss/giai-tri.rss"),
    ("VnExpress · Thể thao", "https://vnexpress.net/rss/the-thao.rss"),
    ("Tuổi Trẻ · Thể thao", "https://tuoitre.vn/rss/the-thao.rss"),
]
MOI_NGUON = 25  # giữ đầu vào cho Claude gọn

SYSTEM_CHON = """Bạn là biên tập viên chọn tin {chu_de} buổi sáng cho một người đọc bận rộn.
Đầu vào là danh sách tin, mỗi tin có số thứ tự "i".
Chọn {so_tin} tin đáng chú ý nhất, {uu_tien}; cùng một sự việc từ nhiều báo thì chỉ lấy một.
Trả về mảng số "i", xếp theo thứ tự nên kể."""

SYSTEM_KE = """Bạn là Mia, kể tin {chu_de} buổi sáng cho {goi} nghe. Gọi "{goi}", xưng "{xung}".
Đầu vào là vài bài báo (tiêu đề + nội dung), mỗi bài có số "i".

Làm hai bước cho TỪNG bài:
1. "tom_tat": đọc nội dung bài, tóm tắt các ý chính trong 2–3 câu khách quan (ai, việc gì, ở đâu, con số quan trọng, vì sao đáng quan tâm).
2. "ke": dựa trên bản tóm tắt, kể lại cho {goi} nghe thành một đoạn 2–4 câu, giọng nói chuyện tự nhiên, dễ hiểu.
   Nối các đoạn với nhau cho liền mạch như đang kể liền một hơi (ví dụ "Còn ở ngoài Bắc thì...", "Chuyển qua thế giới nè {goi},...").
   Đừng đoạn nào cũng mở đầu giống nhau. Được thêm một câu ngắn giải thích bối cảnh nếu giúp {goi} hiểu hơn, nhưng chỉ dựa vào nội dung bài.
   Câu nối phải hợp lý, không gượng (đừng bịa quan hệ địa lý hay chủ đề giữa hai tin không liên quan; khi đó cứ chuyển tin gọn gàng).
   Tin buồn, thiên tai, tai nạn thì kể nghiêm túc, không đùa.
   Tin chính trị, pháp luật thì kể trung lập, không tự bình luận hay gắn nhãn tốt/xấu/buồn/vui.

Giữ đúng sự thật trong bài, không bịa thêm. Chữ thuần, không markdown."""

SCHEMA_CHON = {"type": "ARRAY", "items": {"type": "INTEGER"}}
SCHEMA_KE = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "i": {"type": "INTEGER"},
            "tom_tat": {"type": "STRING"},
            "ke": {"type": "STRING"},
        },
        "required": ["i", "tom_tat", "ke"],
    },
}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (garmin-bot)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read()


def _thoi_diem(chuoi: str | None) -> float | None:
    if not chuoi:
        return None
    try:
        return parsedate_to_datetime(chuoi).timestamp()
    except (TypeError, ValueError):
        pass
    try:  # Tuổi Trẻ: "9/17/2026 10:36:00 AM", giờ VN
        return datetime.strptime(chuoi.strip(), "%m/%d/%Y %I:%M:%S %p").replace(tzinfo=VN).timestamp()
    except ValueError:
        return None


def _chu_thuan(s: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def lay_thoi_su(gio: int = 24) -> list[dict]:
    return lay_rss(RSS_THOI_SU, gio)


def lay_xa_hoi(gio: int = 24) -> list[dict]:
    return lay_rss(RSS_XA_HOI, gio)


def lay_rss(feeds: list[tuple[str, str]], gio: int = 24) -> list[dict]:
    moc = time.time() - gio * 3600
    bai = []
    for nguon, url in feeds:
        try:
            goc = ElementTree.fromstring(_get(url))
        except Exception as e:  # một báo lỗi thì vẫn dùng các báo còn lại
            print(f"RSS {url} lỗi: {type(e).__name__}: {e}")
            continue
        dem = 0
        for item in goc.iter("item"):
            ts = _thoi_diem(item.findtext("pubDate"))
            link = (item.findtext("link") or "").strip()
            if not link or (ts is not None and ts < moc):
                continue
            bai.append({"title": _chu_thuan(item.findtext("title")),
                        "digest": _chu_thuan(item.findtext("description"))[:400],
                        "url": link, "source": nguon})
            dem += 1
            if dem >= MOI_NGUON:
                break
    return bai


def lay_cong_nghe(gio: int = 24) -> list[dict]:
    bai = json.loads(_get(VGSNEWS)).get("articles") or []
    moc = (time.time() - gio * 3600) * 1000
    return [{**b, "source": "VGSNews"} for b in bai if (b.get("ts") or 0) >= moc]


def noi_dung_bai(url: str, toi_da: int = 3000) -> str:
    # Lấy chữ trong các thẻ <p> của trang bài — đủ dùng cho VnExpress, Tuổi Trẻ, VGSNews.
    try:
        trang = _get(url).decode("utf-8", "replace")
    except Exception as e:
        print(f"Không tải được {url}: {type(e).__name__}: {e}")
        return ""
    doan, da_thay, tong = [], set(), 0
    for m in re.finditer(r"<p\b[^>]*>(.*?)</p>", trang, re.S | re.I):
        chu = _chu_thuan(m.group(1))
        if len(chu) < 40 or chu in da_thay:
            continue
        da_thay.add(chu)
        doan.append(chu)
        tong += len(chu)
        if tong >= toi_da:
            break
    return "\n".join(doan)[:toi_da]


def _json_ai(system: str, du_lieu, schema: dict, max_tokens: int):
    return json.loads(ai.goi_ai(system, du_lieu, max_tokens=max_tokens, schema=schema))


def _soan(bai: list[dict], chu_de: str, uu_tien: str, tieu_de: str, cuoi: str | None,
          so_tin: str = "5–6", p: dict | None = None) -> str | None:
    if not bai:
        return None
    p = p or nguoi._chu()
    # Bước 1: chọn tin từ tiêu đề + mô tả ngắn.
    danh_sach = [{"i": i, "tieu_de": b.get("title"), "mo_ta": b.get("digest"),
                  "nguon": b.get("source")} for i, b in enumerate(bai)]
    chon = []
    for i in _json_ai(SYSTEM_CHON.format(chu_de=chu_de, so_tin=so_tin, uu_tien=uu_tien),
                          danh_sach, SCHEMA_CHON, 3000):
        if isinstance(i, int) and 0 <= i < len(bai) and i not in chon:
            chon.append(i)
    chon = chon[:7]
    if not chon:
        return None

    # Bước 2: đọc nội dung từng bài, tóm tắt rồi kể lại.
    with ThreadPoolExecutor(max_workers=len(chon)) as pool:
        noi_dung = list(pool.map(lambda i: noi_dung_bai(bai[i]["url"]), chon))
    dau_vao = [{"i": i, "tieu_de": bai[i].get("title"), "nguon": bai[i].get("source"),
                "noi_dung": nd or bai[i].get("digest")} for i, nd in zip(chon, noi_dung)]
    ke = _json_ai(SYSTEM_KE.format(chu_de=chu_de, goi=p["goi"], xung=p["xung"]), dau_vao, SCHEMA_KE, 10000)

    hom_nay = datetime.now(VN)
    dong = [f"{tieu_de} sáng {THU[hom_nay.weekday()]}, {hom_nay:%d/%m}</b>", ""]
    da_co = set()
    for muc in ke:
        i = muc.get("i")
        doan = (muc.get("ke") or "").strip()
        if i not in chon or i in da_co or not doan:
            continue
        da_co.add(i)
        b = bai[i]
        dong.append(f"{escape(doan)} <a href=\"{escape(b['url'])}\">({escape(b['source'])})</a>")
        dong.append("")
    if not da_co:
        return None
    if cuoi:
        dong.append(cuoi)
    return "\n".join(dong).rstrip()


def _key_dem(loai: str, p: dict) -> str:
    # Bản tin soạn xong giữ trong ngày theo cách xưng hô, để nhiều người cùng gọi "anh" / "chị"
    # không tốn Claude soạn lại, và /thoisu nhắn nhiều lần cũng không soạn lại (08/11/2026).
    return f"tin:{loai}:{datetime.now(VN):%Y-%m-%d}:{p['goi']}-{p['xung']}"


def _doc_dem(loai: str, p: dict) -> str | None:
    try:
        return kho.doc(_key_dem(loai, p))
    except Exception:
        return None


def _ghi_dem(loai: str, p: dict, text: str) -> None:
    try:
        kho.ghi(text, _key_dem(loai, p))
        kho._turso("DELETE FROM garmin_kv WHERE k LIKE 'tin:%' AND k NOT LIKE ?",
                   [f"tin:%:{datetime.now(VN):%Y-%m-%d}:%"])
    except Exception as e:
        print(f"Không lưu đệm bản tin: {type(e).__name__}: {e}")


def ban_tin_thoi_su(p: dict | None = None) -> str | None:
    p = p or nguoi._chu()
    dem = _doc_dem("thoi-su", p)
    if dem:
        return dem
    text = _soan(
        lay_thoi_su(),
        "thời sự",
        "ưu tiên tin trong nước quan trọng và nhất định có 1–2 tin thế giới (nếu đầu vào có)",
        "🗞 <b>Tin thời sự",
        None,
        p=p,
    )
    if text:
        _ghi_dem("thoi-su", p, text)
    return text


def ban_tin_xa_hoi(p: dict | None = None) -> str | None:
    p = p or nguoi._chu()
    dem = _doc_dem("xa-hoi", p)
    if dem:
        return dem
    text = _soan(
        lay_xa_hoi(),
        "xã hội, văn hoá và thể thao",
        "chọn sao cho có cả ba mảng: 2 tin xã hội / đời sống, 2 tin văn hoá / giải trí, 2 tin thể thao (ưu tiên thể thao Việt Nam); tin nhẹ nhàng, gần gũi, tránh tin hình sự hay tai nạn",
        "🎭 <b>Tin xã hội · văn hoá · thể thao",
        None,
        so_tin="6",
        p=p,
    )
    if text:
        _ghi_dem("xa-hoi", p, text)
    return text


def ban_tin(p: dict | None = None) -> str | None:
    p = p or nguoi._chu()
    dem = _doc_dem("cong-nghe", p)
    if dem:
        return dem
    text = _soan(
        lay_cong_nghe(),
        "công nghệ",
        "ưu tiên đa dạng chủ đề",
        "📰 <b>Tin công nghệ",
        f'Xem thêm ở <a href="https://news.alexvgs.tech">VGSNews</a> {p["goi"]} nha 📱',
        p=p,
    )
    if text:
        _ghi_dem("cong-nghe", p, text)
    return text
