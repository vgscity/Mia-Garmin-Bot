# Đăng nhập Garmin một lần ở máy (có hỏi mã MFA nếu tài khoản bật),
# lưu token vào .garmin_tokens.json để bot dùng lại, không cần mật khẩu nữa.
#   .venv/bin/python scripts/dang_nhap.py
import getpass
from pathlib import Path

from garminconnect import Garmin

TOKEN_FILE = Path(__file__).resolve().parent.parent / ".garmin_tokens.json"

email = input("Email Garmin: ").strip()
password = getpass.getpass("Mật khẩu Garmin (gõ không hiện chữ): ")

g = Garmin(email, password, prompt_mfa=lambda: input("Mã MFA Garmin gửi về: ").strip())
g.login()
TOKEN_FILE.write_text(g.client.dumps())
TOKEN_FILE.chmod(0o600)
print(f"✅ Đăng nhập xong: {g.get_full_name()} — token lưu ở {TOKEN_FILE.name}")
