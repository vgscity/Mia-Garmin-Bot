# Chỗ cất token Garmin. Token làm mới mỗi lần chạy nên phải ghi lại được:
# trên Vercel (ổ đĩa chỉ đọc) cất vào Turso qua HTTP, ở máy thì cất ra file.
import json
import os
import urllib.request
from pathlib import Path

TOKEN_FILE = Path(__file__).resolve().parent.parent / ".garmin_tokens.json"
KEY = "garmin_tokens"


def _turso(sql: str, args: list | None = None) -> list:
    url = os.environ["TURSO_DATABASE_URL"].replace("libsql://", "https://") + "/v2/pipeline"
    stmt = {"sql": sql, "args": [{"type": "text", "value": a} for a in (args or [])]}
    body = json.dumps({"requests": [{"type": "execute", "stmt": stmt}, {"type": "close"}]}).encode()
    req = urllib.request.Request(url, body, {
        "Authorization": f"Bearer {os.environ['TURSO_AUTH_TOKEN']}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        res = json.load(r)["results"][0]
    if res["type"] != "ok":
        raise RuntimeError(f"Turso lỗi: {res.get('error')}")
    return res["response"]["result"]["rows"]


def _dung_turso() -> bool:
    return bool(os.environ.get("TURSO_DATABASE_URL"))


def _tao_bang() -> None:
    _turso("CREATE TABLE IF NOT EXISTS garmin_kv (k TEXT PRIMARY KEY, v TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT (datetime('now')))")


def doc(key: str = KEY) -> str | None:
    if not _dung_turso():
        return TOKEN_FILE.read_text() if key == KEY and TOKEN_FILE.exists() else None
    _tao_bang()
    rows = _turso("SELECT v FROM garmin_kv WHERE k = ?", [key])
    return rows[0][0]["value"] if rows else None


def ghi(value: str, key: str = KEY) -> None:
    if not _dung_turso():
        if key == KEY:
            TOKEN_FILE.write_text(value)
            TOKEN_FILE.chmod(0o600)
        return
    _tao_bang()
    _turso(
        "INSERT INTO garmin_kv (k, v) VALUES (?, ?) "
        "ON CONFLICT(k) DO UPDATE SET v = excluded.v, updated_at = datetime('now')",
        [key, value],
    )
