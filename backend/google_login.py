"""Xác minh ID token của Google Identity Services (nút "Đăng nhập với Google").

Giao diện tải thư viện GIS, người dùng bấm nút, Google trả về một ID token
(JWT). Token đó *phải* được kiểm ở phía máy chủ — nếu tin thẳng email do trình
duyệt gửi lên thì ai cũng đăng nhập được vào hồ sơ của người khác.

Ưu tiên kiểm bằng `google-auth` (kiểm chữ ký cục bộ, không cần gọi mạng mỗi lần
nhờ cache khóa công khai). Nếu thiếu thư viện, lùi về endpoint tokeninfo của
Google — chậm hơn và có giới hạn tần suất, nhưng vẫn là kiểm phía máy chủ.
"""
import os
from typing import Any, Dict, Optional

import requests

TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
ALLOWED_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
REQUEST_TIMEOUT = 10


def client_id() -> str:
    return (os.getenv("GOOGLE_CLIENT_ID") or "").strip()


def is_configured() -> bool:
    return bool(client_id())


def _normalize(claims: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "google_id": str(claims.get("sub") or ""),
        "email": (claims.get("email") or "").strip().lower(),
        "email_verified": str(claims.get("email_verified", "")).lower() in ("true", "1"),
        "name": (claims.get("name") or "").strip(),
        "picture": (claims.get("picture") or "").strip(),
    }


def _verify_with_library(token: str, expected_aud: str) -> Optional[Dict[str, Any]]:
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token
    except ImportError:
        return None
    claims = google_id_token.verify_oauth2_token(
        token, google_requests.Request(), expected_aud
    )
    if claims.get("iss") not in ALLOWED_ISSUERS:
        raise ValueError("Token không do Google phát hành.")
    return _normalize(claims)


def _verify_with_tokeninfo(token: str, expected_aud: str) -> Dict[str, Any]:
    response = requests.get(TOKENINFO_URL, params={"id_token": token}, timeout=REQUEST_TIMEOUT)
    if response.status_code != 200:
        raise ValueError("Token Google không hợp lệ hoặc đã hết hạn.")
    claims = response.json()
    if claims.get("aud") != expected_aud:
        raise ValueError("Token Google không dành cho ứng dụng này.")
    if claims.get("iss") not in ALLOWED_ISSUERS:
        raise ValueError("Token không do Google phát hành.")
    return _normalize(claims)


def verify_id_token(token: str) -> Dict[str, Any]:
    """Trả về hồ sơ Google đã kiểm. Ném ValueError kèm thông báo tiếng Việt."""
    expected_aud = client_id()
    if not expected_aud:
        raise ValueError("Máy chủ chưa cấu hình GOOGLE_CLIENT_ID.")
    if not token:
        raise ValueError("Thiếu token Google.")

    try:
        profile = _verify_with_library(token, expected_aud)
        if profile is None:
            profile = _verify_with_tokeninfo(token, expected_aud)
    except ValueError:
        raise
    except requests.RequestException:
        raise ValueError("Không kết nối được máy chủ Google để xác minh.")
    except Exception as exc:  # google-auth ném nhiều loại lỗi riêng
        raise ValueError(f"Token Google không hợp lệ: {exc}")

    if not profile["google_id"]:
        raise ValueError("Token Google thiếu định danh tài khoản.")
    if not profile["email"] or not profile["email_verified"]:
        raise ValueError("Tài khoản Google này chưa xác minh email.")
    return profile
