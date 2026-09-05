"""Xác thực và phân quyền (authentication & RBAC) cho phòng khám nhiều bác sĩ.

Trước đây `profile_db` chỉ là bộ chuyển hồ sơ bác sĩ: bất kỳ ai ngồi vào máy đều
đổi được sang hồ sơ bất kỳ, nên "bác sĩ chỉ xem bệnh nhân của mình" không có ý
nghĩa. Module này nâng mỗi hồ sơ thành một *tài khoản* thật — có mật khẩu băm
PBKDF2-HMAC-SHA256, vai trò, và phiên đăng nhập (session token) — dùng chung
bảng `profiles` trong data/profiles.db để không phải chép dữ liệu bác sĩ sang nơi khác.

Vai trò (role):
    admin     — Quản trị phòng khám: thấy toàn bộ bệnh nhân, quản lý tài khoản.
    doctor    — Bác sĩ: chỉ thấy bệnh nhân do mình phụ trách.
    assistant — Điều dưỡng/trợ lý: xem được toàn bộ bệnh nhân nhưng không sửa/xóa.

Lần chạy đầu tiên chưa tài khoản nào có mật khẩu → `needs_setup()` trả về True và
API mở luồng "thiết lập mật khẩu quản trị" thay vì màn hình đăng nhập.
"""
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional

import mailer
import profile_db

DB_PATH = profile_db.DB_PATH

# Vai trò hợp lệ, kèm nhãn tiếng Việt cho UI.
ROLES = {
    "admin": "Quản trị phòng khám",
    "doctor": "Bác sĩ",
    "assistant": "Điều dưỡng / Trợ lý",
}

# Vai trò xem được hồ sơ của mọi bác sĩ (bác sĩ thường chỉ thấy bệnh nhân của mình).
ROLES_SEEING_ALL_PATIENTS = {"admin", "assistant"}

# Vai trò chỉ đọc: chặn mọi thao tác ghi lên hồ sơ bệnh nhân.
READ_ONLY_ROLES = {"assistant"}

SESSION_TTL_SECONDS = 12 * 60 * 60  # một ca trực; hết hạn thì phải đăng nhập lại
PBKDF2_ITERATIONS = 240_000

# Vai trò cấp cho người tự đăng ký. Quản trị viên đổi lại được trong Quản trị phòng khám.
SELF_SIGNUP_ROLE = "doctor"

# Đăng ký chờ xác nhận email
VERIFICATION_TTL_SECONDS = 15 * 60   # trùng với câu "có hiệu lực 15 phút" trong thư
VERIFICATION_CODE_LENGTH = 6
MAX_VERIFICATION_ATTEMPTS = 5        # sai quá thì hủy đăng ký, phải làm lại từ đầu
RESEND_COOLDOWN_SECONDS = 60
MAX_RESENDS = 5

USERNAME_RE = re.compile(r"^[a-zA-Z0-9._-]{3,32}$")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Thêm cột xác thực vào bảng profiles có sẵn và tạo bảng sessions."""
    profile_db.init_db()  # đảm bảo bảng profiles + hồ sơ mặc định đã tồn tại
    with _connect() as conn:
        existing = {r["name"] for r in conn.execute("PRAGMA table_info(profiles)").fetchall()}
        additions = [
            ("password_hash", "TEXT"),
            ("password_salt", "TEXT"),
            ("role", "TEXT NOT NULL DEFAULT 'doctor'"),
            ("is_disabled", "INTEGER NOT NULL DEFAULT 0"),
            ("must_change_password", "INTEGER NOT NULL DEFAULT 0"),
            ("last_login_at", "REAL"),
            # Đăng ký tự phục vụ: email đã qua mã xác nhận, và liên kết Google.
            ("email_verified", "INTEGER NOT NULL DEFAULT 0"),
            ("google_id", "TEXT"),
        ]
        for name, decl in additions:
            if name not in existing:
                conn.execute(f"ALTER TABLE profiles ADD COLUMN {name} {decl}")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                last_seen_at REAL NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_profile ON sessions(profile_id)")

        # Đăng ký chưa xác nhận email. Chưa phải tài khoản: giữ riêng ở đây cho
        # tới khi người dùng nhập đúng mã, để tên đăng nhập chưa xác nhận không
        # chiếm chỗ vĩnh viễn và hồ sơ "ma" không lọt vào danh sách bác sĩ.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_registrations (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                username TEXT NOT NULL,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                code_salt TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                resend_count INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                last_sent_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pending_username ON pending_registrations(username)"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_google ON profiles(google_id) "
            "WHERE google_id IS NOT NULL"
        )

        # Hồ sơ đầu tiên (tạo từ thời chưa có đăng nhập) trở thành quản trị viên.
        first = conn.execute(
            "SELECT id, role FROM profiles ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        has_admin = conn.execute(
            "SELECT 1 FROM profiles WHERE role = 'admin' LIMIT 1"
        ).fetchone()
        if first and not has_admin:
            conn.execute("UPDATE profiles SET role = 'admin' WHERE id = ?", (first["id"],))

        _purge_expired(conn)
        _purge_pending(conn)


# --- Băm mật khẩu ---------------------------------------------------------

def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS
    ).hex()


def _verify_password(password: str, salt: Optional[str], expected: Optional[str]) -> bool:
    if not salt or not expected:
        return False
    return hmac.compare_digest(_hash_password(password, salt), expected)


def validate_password(password: str) -> Optional[str]:
    """Trả về thông báo lỗi tiếng Việt, hoặc None nếu mật khẩu hợp lệ."""
    if not password or len(password) < 6:
        return "Mật khẩu phải có ít nhất 6 ký tự."
    if len(password) > 128:
        return "Mật khẩu quá dài (tối đa 128 ký tự)."
    return None


def validate_username(username: str) -> Optional[str]:
    """Trả về thông báo lỗi tiếng Việt, hoặc None nếu tên đăng nhập hợp lệ."""
    username = (username or "").strip()
    if not username:
        return "Vui lòng nhập tên đăng nhập."
    if not USERNAME_RE.match(username):
        return ("Tên đăng nhập chỉ gồm chữ không dấu, số, dấu chấm, gạch ngang "
                "hoặc gạch dưới, dài 3–32 ký tự.")
    return None


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_email(email: str) -> Optional[str]:
    if not normalize_email(email):
        return "Vui lòng nhập địa chỉ email."
    if not mailer.valid_email(normalize_email(email)):
        return "Địa chỉ email không hợp lệ."
    return None


def username_taken(username: str, conn: Optional[sqlite3.Connection] = None,
                   exclude_pending_id: Optional[str] = None) -> bool:
    """Tên đã dùng bởi một tài khoản, hoặc đang bị một đăng ký chờ giữ chỗ.

    `exclude_pending_id` bỏ qua chính đăng ký đang được xử lý — nếu không, lúc
    xác nhận mã, đăng ký lại thấy tên của chính nó và tự cho là đã bị chiếm.
    """
    def _check(c: sqlite3.Connection) -> bool:
        if c.execute("SELECT 1 FROM profiles WHERE username = ? COLLATE NOCASE",
                     (username.strip(),)).fetchone():
            return True
        sql = ("SELECT 1 FROM pending_registrations "
               "WHERE username = ? COLLATE NOCASE AND expires_at > ?")
        params: tuple = (username.strip(), time.time())
        if exclude_pending_id:
            sql += " AND id != ?"
            params += (exclude_pending_id,)
        return bool(c.execute(sql, params).fetchone())

    if conn is not None:
        return _check(conn)
    with _connect() as own:
        return _check(own)


def email_taken(email: str, conn: Optional[sqlite3.Connection] = None) -> bool:
    def _check(c: sqlite3.Connection) -> bool:
        return bool(c.execute(
            "SELECT 1 FROM profiles WHERE email = ? COLLATE NOCASE AND email != ''",
            (normalize_email(email),),
        ).fetchone())

    if conn is not None:
        return _check(conn)
    with _connect() as own:
        return _check(own)


# --- Truy vấn tài khoản ---------------------------------------------------

def _serialize_user(row: sqlite3.Row) -> Dict[str, Any]:
    """Hồ sơ dạng public — không bao giờ để lộ hash/salt ra API."""
    user = profile_db._serialize(row)
    for secret_field in ("password_hash", "password_salt"):
        user.pop(secret_field, None)
    user["role"] = row["role"] or "doctor"
    user["role_label"] = ROLES.get(user["role"], user["role"])
    user["is_disabled"] = bool(row["is_disabled"])
    user["must_change_password"] = bool(row["must_change_password"])
    user["has_password"] = bool(row["password_hash"])
    user["last_login_at"] = row["last_login_at"]
    user["can_see_all_patients"] = user["role"] in ROLES_SEEING_ALL_PATIENTS
    user["read_only"] = user["role"] in READ_ONLY_ROLES
    user["email_verified"] = bool(row["email_verified"])
    user["google_linked"] = bool(row["google_id"])
    user.pop("google_id", None)
    return user


def get_user(profile_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    return _serialize_user(row) if row else None


def list_users() -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM profiles ORDER BY created_at ASC").fetchall()
    return [_serialize_user(r) for r in rows]


def needs_setup(conn: Optional[sqlite3.Connection] = None) -> bool:
    """True khi chưa ai vào được hệ thống — chưa tài khoản nào có mật khẩu và
    cũng chưa tài khoản nào liên kết Google. Lúc đó mở luồng thiết lập quản trị
    viên thay vì bắt đăng nhập.

    Tài khoản Google phải tính vào đây: nó không có password_hash, nên nếu chỉ
    đếm mật khẩu thì người đăng nhập bằng Google đầu tiên sẽ vẫn thấy màn hình
    "thiết lập phòng khám" ở lần tải trang sau.
    """
    def _check(c: sqlite3.Connection) -> bool:
        row = c.execute(
            "SELECT COUNT(*) AS n FROM profiles "
            "WHERE password_hash IS NOT NULL OR google_id IS NOT NULL"
        ).fetchone()
        return (row["n"] if row else 0) == 0

    if conn is not None:
        return _check(conn)
    with _connect() as own:
        return _check(own)


def _role_for_new_account(conn: sqlite3.Connection) -> str:
    """Người đầu tiên thực sự vào được hệ thống nhận quyền quản trị.

    Không có bước này thì ai tự đăng ký trước màn hình "thiết lập phòng khám"
    sẽ tạo ra một phòng khám không có quản trị viên nào — hồ sơ mặc định do
    profile_db gieo sẵn chưa từng có mật khẩu nên không ai đăng nhập vào được.
    """
    return "admin" if needs_setup(conn) else SELF_SIGNUP_ROLE


def setup_admin(password: str, display_name: Optional[str] = None,
                username: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Đặt mật khẩu cho tài khoản quản trị đầu tiên. Chỉ chạy được khi needs_setup()."""
    if not needs_setup():
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM profiles WHERE role = 'admin' ORDER BY created_at ASC LIMIT 1"
        ).fetchone() or conn.execute(
            "SELECT * FROM profiles ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        salt = secrets.token_hex(16)
        updates = {
            "password_hash": _hash_password(password, salt),
            "password_salt": salt,
            "role": "admin",
            "must_change_password": 0,
            "is_disabled": 0,
        }
        if display_name and display_name.strip():
            updates["display_name"] = display_name.strip()
        if username and username.strip():
            updates["username"] = username.strip()
        assignments = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE profiles SET {assignments}, updated_at = ? WHERE id = ?",
            (*updates.values(), time.time(), row["id"]),
        )
    return get_user(row["id"])


def create_user(display_name: str, username: str, password: str, role: str = "doctor",
                specialty: str = "", email: str = "",
                must_change_password: bool = True) -> Dict[str, Any]:
    """Tạo tài khoản mới. Ném sqlite3.IntegrityError nếu username đã tồn tại."""
    if role not in ROLES:
        role = "doctor"
    profile_id = str(uuid.uuid4())
    salt = secrets.token_hex(16)
    now = time.time()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO profiles
               (id, display_name, username, specialty, email, avatar_filename,
                is_active, created_at, updated_at,
                password_hash, password_salt, role, is_disabled, must_change_password)
               VALUES (?, ?, ?, ?, ?, NULL, 0, ?, ?, ?, ?, ?, 0, ?)""",
            (profile_id, display_name.strip(), username.strip(), specialty, email,
             now, now, _hash_password(password, salt), salt, role,
             1 if must_change_password else 0),
        )
    return get_user(profile_id)


def update_user(profile_id: str, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Cập nhật thông tin/vai trò/trạng thái khóa. Không đụng tới mật khẩu."""
    allowed = {"display_name", "username", "specialty", "email", "role", "is_disabled"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if "role" in updates and updates["role"] not in ROLES:
        del updates["role"]
    if "is_disabled" in updates:
        updates["is_disabled"] = 1 if updates["is_disabled"] else 0
    if not updates:
        return get_user(profile_id)
    with _connect() as conn:
        if not conn.execute("SELECT 1 FROM profiles WHERE id = ?", (profile_id,)).fetchone():
            return None
        assignments = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE profiles SET {assignments}, updated_at = ? WHERE id = ?",
            (*updates.values(), time.time(), profile_id),
        )
        # Khóa tài khoản thì mọi phiên đang mở của họ phải chấm dứt ngay.
        if updates.get("is_disabled"):
            conn.execute("DELETE FROM sessions WHERE profile_id = ?", (profile_id,))
    return get_user(profile_id)


def count_active_admins(exclude_id: Optional[str] = None) -> int:
    """Dùng để chặn việc hạ cấp/khóa/xóa vị quản trị viên cuối cùng."""
    sql = "SELECT COUNT(*) AS n FROM profiles WHERE role = 'admin' AND is_disabled = 0"
    params: tuple = ()
    if exclude_id:
        sql += " AND id != ?"
        params = (exclude_id,)
    with _connect() as conn:
        return conn.execute(sql, params).fetchone()["n"]


def set_password(profile_id: str, password: str, must_change: bool = False,
                 revoke_sessions: bool = True) -> bool:
    salt = secrets.token_hex(16)
    with _connect() as conn:
        cur = conn.execute(
            """UPDATE profiles
               SET password_hash = ?, password_salt = ?, must_change_password = ?, updated_at = ?
               WHERE id = ?""",
            (_hash_password(password, salt), salt, 1 if must_change else 0,
             time.time(), profile_id),
        )
        if cur.rowcount == 0:
            return False
        if revoke_sessions:
            conn.execute("DELETE FROM sessions WHERE profile_id = ?", (profile_id,))
    return True


def change_own_password(profile_id: str, current_password: str, new_password: str) -> Optional[str]:
    """Đổi mật khẩu của chính mình. Trả về thông báo lỗi, hoặc None nếu thành công."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    if not row:
        return "Không tìm thấy tài khoản."
    if row["password_hash"] and not _verify_password(
            current_password, row["password_salt"], row["password_hash"]):
        return "Mật khẩu hiện tại không đúng."
    error = validate_password(new_password)
    if error:
        return error
    # Giữ lại phiên hiện tại: người dùng vừa đổi mật khẩu không nên bị đá ra ngoài.
    set_password(profile_id, new_password, must_change=False, revoke_sessions=False)
    return None


def delete_user(profile_id: str) -> bool:
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE profile_id = ?", (profile_id,))
    return profile_db.delete_profile(profile_id)


# --- Phiên đăng nhập ------------------------------------------------------

def _purge_expired(conn: sqlite3.Connection):
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))


def issue_session(profile_id: str) -> str:
    """Mở một phiên mới cho tài khoản và đánh dấu đây là hồ sơ đang dùng."""
    token = secrets.token_urlsafe(32)
    now = time.time()
    with _connect() as conn:
        _purge_expired(conn)
        conn.execute(
            "INSERT INTO sessions (token, profile_id, created_at, expires_at, last_seen_at) VALUES (?, ?, ?, ?, ?)",
            (token, profile_id, now, now + SESSION_TTL_SECONDS, now),
        )
        # Đăng nhập cũng là "chọn hồ sơ đang dùng" — giữ đồng bộ với AccountMenu cũ.
        conn.execute("UPDATE profiles SET is_active = 0")
        conn.execute(
            "UPDATE profiles SET is_active = 1, last_login_at = ? WHERE id = ?", (now, profile_id)
        )
    return token


def login(username: str, password: str) -> Dict[str, Any]:
    """Trả về {"ok": True, "token", "user"} hoặc {"ok": False, "error": <tiếng Việt>}."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM profiles WHERE username = ? COLLATE NOCASE", (username.strip(),)
        ).fetchone()

    if not row or not _verify_password(password, row["password_salt"], row["password_hash"]):
        # Cùng một thông báo cho sai tên và sai mật khẩu — không tiết lộ tài khoản nào tồn tại.
        return {"ok": False, "error": "Tên đăng nhập hoặc mật khẩu không đúng."}
    if row["is_disabled"]:
        return {"ok": False, "error": "Tài khoản đã bị khóa. Liên hệ quản trị phòng khám."}

    return {"ok": True, "token": issue_session(row["id"]), "user": get_user(row["id"])}


def resolve_session(token: Optional[str]) -> Optional[Dict[str, Any]]:
    """Đổi session token lấy tài khoản, đồng thời gia hạn phiên đang hoạt động."""
    if not token:
        return None
    now = time.time()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE token = ?", (token,)).fetchone()
        if not row:
            return None
        if row["expires_at"] < now:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            return None
        conn.execute(
            "UPDATE sessions SET last_seen_at = ?, expires_at = ? WHERE token = ?",
            (now, now + SESSION_TTL_SECONDS, token),
        )
        profile = conn.execute(
            "SELECT * FROM profiles WHERE id = ?", (row["profile_id"],)
        ).fetchone()
    if not profile or profile["is_disabled"]:
        return None
    return _serialize_user(profile)


def logout(token: Optional[str]) -> None:
    if not token:
        return
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


# --- Đăng ký tự phục vụ (email + mã xác nhận) ------------------------------
# Đăng ký chia làm hai nhịp: `start_registration` cất thông tin vào bảng
# pending_registrations rồi gửi mã 6 chữ số qua Resend; `verify_registration`
# nhận đúng mã mới dựng tài khoản thật. Nhờ vậy một địa chỉ email gõ sai không
# để lại tài khoản không ai vào được, và tên đăng nhập chỉ bị giữ chỗ tạm thời.


def _purge_pending(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM pending_registrations WHERE expires_at < ?", (time.time(),))


def _hash_code(code: str, salt: str) -> str:
    """Mã 6 chữ số chỉ có một triệu khả năng, nên chi phí băm không phải là lớp
    bảo vệ — bộ đếm số lần nhập sai mới là. Dùng SHA-256 có muối cho nhẹ."""
    return hashlib.sha256((salt + code).encode("utf-8")).hexdigest()


def _new_code() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(VERIFICATION_CODE_LENGTH))


def start_registration(email: str, username: str, password: str,
                       display_name: str = "") -> Dict[str, Any]:
    """Nhận thông tin đăng ký và gửi mã xác nhận về email.

    Trả về {"ok": True, "pending_id", "email", "delivered", ...} hoặc
    {"ok": False, "error": <tiếng Việt>}.
    """
    email = normalize_email(email)
    username = (username or "").strip()

    for error in (validate_email(email), validate_username(username), validate_password(password)):
        if error:
            return {"ok": False, "error": error}

    now = time.time()
    with _connect() as conn:
        _purge_pending(conn)
        if username_taken(username, conn):
            return {"ok": False, "error": "Tên đăng nhập này đã có người dùng."}
        if email_taken(email, conn):
            return {"ok": False,
                    "error": "Email này đã được đăng ký. Hãy đăng nhập hoặc dùng email khác."}

        # Cùng một email đăng ký lại khi chưa xác nhận: thay đăng ký cũ, không chồng thêm.
        conn.execute("DELETE FROM pending_registrations WHERE email = ? COLLATE NOCASE", (email,))

        pending_id = str(uuid.uuid4())
        password_salt = secrets.token_hex(16)
        code = _new_code()
        code_salt = secrets.token_hex(16)
        conn.execute(
            """INSERT INTO pending_registrations
               (id, email, username, display_name, password_hash, password_salt,
                code_hash, code_salt, attempts, resend_count, created_at, last_sent_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?)""",
            (pending_id, email, username, (display_name or username).strip(),
             _hash_password(password, password_salt), password_salt,
             _hash_code(code, code_salt), code_salt,
             now, now, now + VERIFICATION_TTL_SECONDS),
        )

    delivery = mailer.send_verification_code(email, code, username)
    return {
        "ok": True,
        "pending_id": pending_id,
        "email": email,
        "delivered": delivery["delivered"],
        "delivery_error": delivery["error"],
        "expires_in": VERIFICATION_TTL_SECONDS,
        "resend_in": RESEND_COOLDOWN_SECONDS,
    }


def resend_registration_code(pending_id: str) -> Dict[str, Any]:
    """Gửi lại mã cho một đăng ký đang chờ, có giới hạn tần suất và số lần."""
    now = time.time()
    with _connect() as conn:
        _purge_pending(conn)
        row = conn.execute(
            "SELECT * FROM pending_registrations WHERE id = ?", (pending_id or "",)
        ).fetchone()
        if not row:
            return {"ok": False, "error": "Phiên đăng ký đã hết hạn. Vui lòng đăng ký lại."}
        if row["resend_count"] >= MAX_RESENDS:
            return {"ok": False, "error": "Đã gửi lại mã quá nhiều lần. Vui lòng đăng ký lại."}

        waited = now - row["last_sent_at"]
        if waited < RESEND_COOLDOWN_SECONDS:
            remaining = int(RESEND_COOLDOWN_SECONDS - waited) + 1
            return {"ok": False,
                    "error": f"Vui lòng đợi {remaining} giây trước khi gửi lại mã.",
                    "resend_in": remaining}

        code = _new_code()
        code_salt = secrets.token_hex(16)
        conn.execute(
            """UPDATE pending_registrations
               SET code_hash = ?, code_salt = ?, attempts = 0, resend_count = resend_count + 1,
                   last_sent_at = ?, expires_at = ?
               WHERE id = ?""",
            (_hash_code(code, code_salt), code_salt, now,
             now + VERIFICATION_TTL_SECONDS, pending_id),
        )
        email, username = row["email"], row["username"]

    delivery = mailer.send_verification_code(email, code, username)
    return {"ok": True, "delivered": delivery["delivered"], "delivery_error": delivery["error"],
            "expires_in": VERIFICATION_TTL_SECONDS, "resend_in": RESEND_COOLDOWN_SECONDS}


def verify_registration(pending_id: str, code: str) -> Dict[str, Any]:
    """Đúng mã thì dựng tài khoản thật và mở luôn phiên đăng nhập."""
    now = time.time()
    with _connect() as conn:
        _purge_pending(conn)
        row = conn.execute(
            "SELECT * FROM pending_registrations WHERE id = ?", (pending_id or "",)
        ).fetchone()
        if not row:
            return {"ok": False, "error": "Phiên đăng ký đã hết hạn. Vui lòng đăng ký lại."}

        attempts = row["attempts"] + 1
        if attempts > MAX_VERIFICATION_ATTEMPTS:
            conn.execute("DELETE FROM pending_registrations WHERE id = ?", (pending_id,))
            return {"ok": False, "error": "Nhập sai mã quá nhiều lần. Vui lòng đăng ký lại."}

        if not hmac.compare_digest(_hash_code((code or "").strip(), row["code_salt"]),
                                   row["code_hash"]):
            conn.execute("UPDATE pending_registrations SET attempts = ? WHERE id = ?",
                         (attempts, pending_id))
            left = MAX_VERIFICATION_ATTEMPTS - attempts
            suffix = f" Còn {left} lần thử." if left > 0 else ""
            return {"ok": False, "error": f"Mã xác nhận không đúng.{suffix}"}

        # Người khác có thể đã chiếm mất tên đăng nhập/email trong lúc chờ mã.
        if username_taken(row["username"], conn, exclude_pending_id=pending_id):
            conn.execute("DELETE FROM pending_registrations WHERE id = ?", (pending_id,))
            return {"ok": False,
                    "error": "Tên đăng nhập này vừa có người khác dùng. Vui lòng đăng ký lại."}
        if email_taken(row["email"], conn):
            conn.execute("DELETE FROM pending_registrations WHERE id = ?", (pending_id,))
            return {"ok": False, "error": "Email này vừa được đăng ký. Vui lòng đăng nhập."}

        profile_id = str(uuid.uuid4())
        role = _role_for_new_account(conn)
        conn.execute(
            """INSERT INTO profiles
               (id, display_name, username, specialty, email, avatar_filename,
                is_active, created_at, updated_at,
                password_hash, password_salt, role, is_disabled, must_change_password,
                email_verified)
               VALUES (?, ?, ?, '', ?, NULL, 0, ?, ?, ?, ?, ?, 0, 0, 1)""",
            (profile_id, row["display_name"], row["username"], row["email"],
             now, now, row["password_hash"], row["password_salt"], role),
        )
        conn.execute("DELETE FROM pending_registrations WHERE id = ?", (pending_id,))

    return {"ok": True, "token": issue_session(profile_id), "user": get_user(profile_id),
            "is_first_account": role == "admin"}


# --- Đăng nhập bằng Google -------------------------------------------------


def _unique_username(conn: sqlite3.Connection, base: str) -> str:
    """Dựng tên đăng nhập chưa ai dùng từ phần trước @ của email Google."""
    cleaned = re.sub(r"[^a-zA-Z0-9._-]", "", base or "").strip("._-").lower() or "bacsi"
    cleaned = cleaned[:24]
    if len(cleaned) < 3:
        cleaned = f"{cleaned}bacsi"[:24]
    candidate = cleaned
    suffix = 1
    while username_taken(candidate, conn):
        suffix += 1
        candidate = f"{cleaned}{suffix}"[:32]
    return candidate


def login_with_google(google_profile: Dict[str, Any]) -> Dict[str, Any]:
    """Đăng nhập, hoặc tạo tài khoản mới, từ hồ sơ Google *đã được xác minh*.

    Ba trường hợp: đã liên kết google_id → vào thẳng; trùng email với tài khoản
    có sẵn → gắn google_id vào tài khoản đó (email Google đã xác minh nên đây là
    cùng một người); còn lại → tạo tài khoản mới với vai trò bác sĩ.
    """
    google_id = google_profile["google_id"]
    email = normalize_email(google_profile["email"])
    now = time.time()

    with _connect() as conn:
        row = conn.execute("SELECT * FROM profiles WHERE google_id = ?", (google_id,)).fetchone()
        if not row:
            row = conn.execute(
                "SELECT * FROM profiles WHERE email = ? COLLATE NOCASE AND email != ''", (email,)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE profiles SET google_id = ?, email_verified = 1, updated_at = ? "
                    "WHERE id = ?",
                    (google_id, now, row["id"]),
                )

        if row:
            if row["is_disabled"]:
                return {"ok": False, "error": "Tài khoản đã bị khóa. Liên hệ quản trị phòng khám."}
            profile_id = row["id"]
            created = False
            first = False
        else:
            profile_id = str(uuid.uuid4())
            username = _unique_username(conn, email.split("@")[0])
            display_name = google_profile.get("name") or username
            role = _role_for_new_account(conn)
            # Chưa có mật khẩu: tài khoản này chỉ vào được bằng Google cho tới khi
            # chủ tài khoản tự đặt mật khẩu trong Cài đặt → Tài khoản.
            conn.execute(
                """INSERT INTO profiles
                   (id, display_name, username, specialty, email, avatar_filename,
                    is_active, created_at, updated_at,
                    password_hash, password_salt, role, is_disabled, must_change_password,
                    email_verified, google_id)
                   VALUES (?, ?, ?, '', ?, NULL, 0, ?, ?, NULL, NULL, ?, 0, 0, 1, ?)""",
                (profile_id, display_name, username, email, now, now, role, google_id),
            )
            created = True
            first = role == "admin"

    return {"ok": True, "token": issue_session(profile_id), "user": get_user(profile_id),
            "created": created, "is_first_account": created and first}


# --- Kiểm tra quyền -------------------------------------------------------

def can_see_all_patients(user: Optional[Dict[str, Any]]) -> bool:
    return bool(user) and user.get("role") in ROLES_SEEING_ALL_PATIENTS


def is_read_only(user: Optional[Dict[str, Any]]) -> bool:
    return bool(user) and user.get("role") in READ_ONLY_ROLES


def is_admin(user: Optional[Dict[str, Any]]) -> bool:
    return bool(user) and user.get("role") == "admin"
