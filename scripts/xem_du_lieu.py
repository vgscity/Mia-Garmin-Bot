# Kéo thô dữ liệu giấc ngủ vài đêm gần nhất để xem vòng tay trả về trường gì.
#   .venv/bin/python scripts/xem_du_lieu.py <thư mục ra>
import json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from garminconnect import Garmin

TOKEN_FILE = Path(__file__).resolve().parent.parent / ".garmin_tokens.json"
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)

g = Garmin()
g.login(str(TOKEN_FILE))
today = datetime.now(timezone(timedelta(hours=7))).date()
for i in range(3):
    d = (today - timedelta(days=i)).isoformat()
    (out / f"sleep-{d}.json").write_text(json.dumps(g.get_sleep_data(d), ensure_ascii=False, indent=1))
    print(d, "ok")
