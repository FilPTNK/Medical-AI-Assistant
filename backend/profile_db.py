"""SQLite-backed storage for doctor profiles (hồ sơ bác sĩ).

Backs the "Chỉnh sửa hồ sơ" dialog and the sidebar account switcher. Several
doctors can share one workstation, so this keeps a row per profile plus a
single active flag; the avatar image itself lives on disk under data/avatars/
and the row stores only its filename.
"""
import os
import sqlite3
import uuid
import time
from typing import Any, Dict, List, Optional

import config

DB_PATH = os.path.join(config.DATA_DIR, "profiles.db")
AVATAR_DIR = os.path.join(config.DATA_DIR, "avatars")
os.makedirs(AVATAR_DIR, exist_ok=True)

# Fields update_profile() is allowed to write
EDITABLE_FIELDS = {"display_name", "username", "specialty", "email"}

DEFAULT_PROFILE = {
    "display_name": "BS. Hà Thanh Hùng",
    "username": "ha.thanhhung",
    "specialty": "Nội tổng quát",
    "email": "",
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                username TEXT UNIQUE NOT NULL,
                specialty TEXT DEFAULT '',
                email TEXT DEFAULT '',
                avatar_filename TEXT,
                is_active INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            """
        )
        # Seed the first profile so the UI always has something to show.
        row = conn.execute("SELECT COUNT(*) AS n FROM profiles").fetchone()
        if row["n"] == 0:
            now = time.time()
            conn.execute(
                """INSERT INTO profiles
                   (id, display_name, username, specialty, email, avatar_filename,
                    is_active, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, NULL, 1, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    DEFAULT_PROFILE["display_name"],
                    DEFAULT_PROFILE["username"],
                    DEFAULT_PROFILE["specialty"],
                    DEFAULT_PROFILE["email"],
                    now,
                    now,
                ),
            )


# Cột chỉ dành cho auth_db, không bao giờ được ra khỏi máy chủ. `SELECT *` kéo
# theo cả chúng, nên phải gạt ở đây — /api/profiles trả danh sách này cho mọi
# tài khoản đã đăng nhập, để lọt hash mật khẩu là mất cả phòng khám.
SECRET_FIELDS = ("password_hash", "password_salt", "google_id")


def _serialize(row: sqlite3.Row) -> Dict[str, Any]:
    profile = dict(row)
    for field in SECRET_FIELDS:
        profile.pop(field, None)
    profile["is_active"] = bool(profile["is_active"])
    # The client never needs the stored filename, only a URL it can render.
    filename = profile.pop("avatar_filename", None)
    profile["avatar_url"] = (
        f"/api/profiles/{profile['id']}/avatar?v={int(profile['updated_at'])}"
        if filename else None
    )
    return profile


def list_profiles() -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM profiles ORDER BY created_at ASC"
        ).fetchall()
    return [_serialize(r) for r in rows]


def get_profile(profile_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    return _serialize(row) if row else None


def get_active_profile() -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM profiles WHERE is_active = 1 ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT * FROM profiles ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
    return _serialize(row) if row else None


def _avatar_filename(profile_id: str) -> Optional[str]:
    """Raw stored filename — used internally for serving and cleanup."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT avatar_filename FROM profiles WHERE id = ?", (profile_id,)
        ).fetchone()
    return row["avatar_filename"] if row else None


def create_profile(display_name: str, username: str, specialty: str = "",
                   email: str = "", activate: bool = True) -> Dict[str, Any]:
    profile_id = str(uuid.uuid4())
    now = time.time()
    with _connect() as conn:
        if activate:
            conn.execute("UPDATE profiles SET is_active = 0")
        conn.execute(
            """INSERT INTO profiles
               (id, display_name, username, specialty, email, avatar_filename,
                is_active, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?)""",
            (profile_id, display_name, username, specialty, email,
             1 if activate else 0, now, now),
        )
    return get_profile(profile_id)


def update_profile(profile_id: str, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    updates = {k: v for k, v in fields.items() if k in EDITABLE_FIELDS and v is not None}
    if not updates:
        return get_profile(profile_id)
    assignments = ", ".join(f"{k} = ?" for k in updates)
    with _connect() as conn:
        exists = conn.execute("SELECT 1 FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        if not exists:
            return None
        conn.execute(
            f"UPDATE profiles SET {assignments}, updated_at = ? WHERE id = ?",
            (*updates.values(), time.time(), profile_id),
        )
    return get_profile(profile_id)


def set_active(profile_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        exists = conn.execute("SELECT 1 FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        if not exists:
            return None
        conn.execute("UPDATE profiles SET is_active = 0")
        conn.execute("UPDATE profiles SET is_active = 1 WHERE id = ?", (profile_id,))
    return get_profile(profile_id)


def set_avatar(profile_id: str, filename: Optional[str]) -> Optional[Dict[str, Any]]:
    """Points the profile at a new avatar file, deleting whatever it replaced."""
    previous = _avatar_filename(profile_id)
    with _connect() as conn:
        exists = conn.execute("SELECT 1 FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        if not exists:
            return None
        conn.execute(
            "UPDATE profiles SET avatar_filename = ?, updated_at = ? WHERE id = ?",
            (filename, time.time(), profile_id),
        )
    if previous and previous != filename:
        stale = os.path.join(AVATAR_DIR, previous)
        if os.path.exists(stale):
            try:
                os.remove(stale)
            except OSError:
                pass  # a leftover file is harmless; the row is what matters
    return get_profile(profile_id)


def avatar_path(profile_id: str) -> Optional[str]:
    filename = _avatar_filename(profile_id)
    if not filename:
        return None
    path = os.path.join(AVATAR_DIR, filename)
    return path if os.path.exists(path) else None


def delete_profile(profile_id: str) -> bool:
    """Removes a profile. The last remaining profile cannot be deleted."""
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM profiles").fetchone()["n"]
        if total <= 1:
            return False
        row = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
        if row["is_active"]:
            fallback = conn.execute(
                "SELECT id FROM profiles ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            if fallback:
                conn.execute("UPDATE profiles SET is_active = 1 WHERE id = ?", (fallback["id"],))

    if row["avatar_filename"]:
        stale = os.path.join(AVATAR_DIR, row["avatar_filename"])
        if os.path.exists(stale):
            try:
                os.remove(stale)
            except OSError:
                pass
    return True
