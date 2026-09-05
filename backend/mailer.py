"""Gửi thư giao dịch qua Resend (https://resend.com).

Chỉ một loại thư duy nhất được gửi đi: mã xác nhận 6 chữ số cho người vừa đăng
ký tài khoản. Dùng thẳng REST API bằng `requests` thay vì SDK `resend` để không
thêm phụ thuộc mới — endpoint chỉ có một, và đây là toàn bộ bề mặt ta cần.

Khi RESEND_API_KEY chưa được đặt (máy của bác sĩ chạy nội bộ, chưa cấu hình),
thư không gửi đi được nhưng luồng đăng ký vẫn phải chạy: mã sẽ in ra console
của máy chủ để người cài đặt đọc và nhập tay. `send_verification_code` trả về
cờ `delivered` để API nói đúng sự thật với giao diện thay vì báo "đã gửi".
"""
import os
import re
from typing import Any, Dict

import requests

RESEND_API_URL = "https://api.resend.com/emails"
REQUEST_TIMEOUT = 15  # giây; Resend thường trả lời dưới 1s

# Địa chỉ mặc định của Resend dùng được ngay khi chưa xác minh domain riêng.
DEFAULT_FROM = "Trợ lý Fil <onboarding@resend.dev>"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def api_key() -> str:
    return (os.getenv("RESEND_API_KEY") or "").strip()


def sender() -> str:
    return (os.getenv("RESEND_FROM") or "").strip() or DEFAULT_FROM


def is_configured() -> bool:
    return bool(api_key())


def valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match((email or "").strip()))


def _verification_html(code: str, username: str) -> str:
    """Thư dạng bảng, style nội tuyến — client mail không dùng CSS ngoài."""
    return f"""\
<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
            background:#f6f7f9;padding:32px 16px;">
  <div style="max-width:460px;margin:0 auto;background:#ffffff;border-radius:14px;
              padding:32px;border:1px solid #e6e8eb;">
    <p style="margin:0 0 4px;font-size:13px;color:#6b7280;letter-spacing:.02em;">TRỢ LÝ FIL</p>
    <h1 style="margin:0 0 16px;font-size:20px;color:#111827;">Xác nhận địa chỉ email</h1>
    <p style="margin:0 0 20px;font-size:14px;line-height:1.6;color:#374151;">
      Tài khoản <strong>{username}</strong> vừa được đăng ký với địa chỉ email này.
      Nhập mã dưới đây để hoàn tất đăng ký:
    </p>
    <div style="font-size:32px;font-weight:700;letter-spacing:.32em;color:#111827;
                background:#f3f4f6;border-radius:10px;padding:18px;text-align:center;">
      {code}
    </div>
    <p style="margin:20px 0 0;font-size:13px;line-height:1.6;color:#6b7280;">
      Mã có hiệu lực trong 15 phút. Nếu bạn không đăng ký tài khoản nào,
      hãy bỏ qua thư này — chưa có tài khoản nào được tạo.
    </p>
  </div>
</div>"""


def send_verification_code(email: str, code: str, username: str) -> Dict[str, Any]:
    """Trả về {"delivered": bool, "error": str|None}. Không bao giờ ném lỗi:
    đăng ký hỏng vì mạng chập chờn thì tệ hơn là báo cho người dùng thử lại."""
    key = api_key()
    if not key:
        print(f"[MAILER] RESEND_API_KEY chưa cấu hình — mã xác nhận cho {email}: {code}")
        return {"delivered": False, "error": "not_configured"}

    try:
        response = requests.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "from": sender(),
                "to": [email],
                "subject": f"{code} là mã xác nhận Trợ lý Fil của bạn",
                "html": _verification_html(code, username),
                "text": (f"Mã xác nhận Trợ lý Fil của tài khoản {username}: {code}\n"
                         "Mã có hiệu lực trong 15 phút."),
            },
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        print(f"[MAILER] Không gọi được Resend: {exc}")
        print(f"[MAILER] Mã xác nhận cho {email}: {code}")
        return {"delivered": False, "error": "network"}

    if response.status_code // 100 == 2:
        return {"delivered": True, "error": None}

    # Lỗi thường gặp: domain người gửi chưa xác minh, hoặc key sai.
    detail = ""
    try:
        detail = (response.json() or {}).get("message", "")
    except ValueError:
        detail = response.text[:200]
    print(f"[MAILER] Resend trả {response.status_code}: {detail}")
    print(f"[MAILER] Mã xác nhận cho {email}: {code}")
    return {"delivered": False, "error": detail or f"http_{response.status_code}"}
