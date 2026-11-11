"""Private chat threads and bounded, idempotent turn commits."""

import json
import sqlite3
import threading
import time
import uuid
from contextlib import closing


class ChatError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class WorkchatStore:
    MAX_THREADS = 200
    MAX_TURNS = 60
    ATTEMPTS_PER_MINUTE = 10
    LEASE_SECONDS = 75

    def __init__(self, path):
        self.path = path
        self._initialized = False
        self._init_lock = threading.Lock()

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=4)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            if not self._initialized:
                with self._init_lock:
                    if not self._initialized:
                        conn.executescript("""
                            PRAGMA journal_mode = WAL;
                            CREATE TABLE IF NOT EXISTS workchat_threads (
                                id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
                                title TEXT NOT NULL, specialty TEXT,
                                pinned INTEGER NOT NULL DEFAULT 0,
                                archived INTEGER NOT NULL DEFAULT 0,
                                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                                lease TEXT, lease_until REAL NOT NULL DEFAULT 0
                            );
                            CREATE INDEX IF NOT EXISTS workchat_thread_owner
                                ON workchat_threads (owner_id, updated_at DESC);
                            CREATE TABLE IF NOT EXISTS workchat_turns (
                                id INTEGER PRIMARY KEY, thread_id TEXT NOT NULL
                                    REFERENCES workchat_threads(id) ON DELETE CASCADE,
                                request_id TEXT NOT NULL, request_hash TEXT NOT NULL,
                                question TEXT NOT NULL, data TEXT NOT NULL,
                                created_at INTEGER NOT NULL,
                                UNIQUE (thread_id, request_id)
                            );
                            CREATE TABLE IF NOT EXISTS workchat_attempts (
                                owner_id TEXT NOT NULL, time REAL NOT NULL
                            );
                            CREATE INDEX IF NOT EXISTS workchat_attempt_time
                                ON workchat_attempts (time);
                        """)
                        self._initialized = True
            return conn
        except Exception:
            conn.close()
            raise

    @staticmethod
    def _summary(row):
        return {
            "id": row["id"], "ownerId": row["owner_id"], "title": row["title"],
            "specialty": row["specialty"], "pinned": bool(row["pinned"]),
            "archived": bool(row["archived"]), "createdAt": row["created_at"],
            "updatedAt": row["updated_at"], "storage": "workchat",
        }

    @staticmethod
    def _thread(conn, owner_id, thread_id):
        row = conn.execute(
            "SELECT * FROM workchat_threads WHERE id = ? AND owner_id = ?", (thread_id, owner_id),
        ).fetchone()
        if row is None:
            raise ChatError(404, "Không tìm thấy cuộc trò chuyện.")
        return row

    @staticmethod
    def _turn(row):
        return {
            "id": row["request_id"], "question": row["question"], "createdAt": row["created_at"],
            **json.loads(row["data"]),
        }

    def list_threads(self, owner_id):
        with closing(self._connect()) as conn:
            return [self._summary(row) for row in conn.execute(
                "SELECT * FROM workchat_threads WHERE owner_id = ? ORDER BY updated_at DESC",
                (owner_id,),
            )]

    def create(self, owner_id, title, specialty):
        thread_id = "wc-" + uuid.uuid4().hex
        now = int(time.time() * 1000)
        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            count = conn.execute("SELECT COUNT(*) FROM workchat_threads WHERE owner_id = ?", (owner_id,)).fetchone()[0]
            if count >= self.MAX_THREADS:
                raise ChatError(409, "Đã đạt giới hạn cuộc trò chuyện. Xóa một cuộc trò chuyện để tạo thêm.")
            conn.execute(
                """INSERT INTO workchat_threads (id, owner_id, title, specialty, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""", (thread_id, owner_id, title, specialty, now, now),
            )
            return self._summary(self._thread(conn, owner_id, thread_id))

    def read(self, owner_id, thread_id, *, recent=None):
        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN")
            thread = self._thread(conn, owner_id, thread_id)
            rows = conn.execute(
                """SELECT turn.* FROM workchat_turns turn
                   JOIN workchat_threads thread ON turn.thread_id = thread.id
                   WHERE turn.thread_id = ? AND thread.owner_id = ?
                   ORDER BY turn.id DESC LIMIT ?""",
                (thread_id, owner_id, recent if recent is not None else self.MAX_TURNS),
            ).fetchall()
            return self._summary(thread), [self._turn(row) for row in reversed(rows)]

    def update(self, owner_id, thread_id, *, title=None, pinned=None, archived=None):
        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            thread = self._thread(conn, owner_id, thread_id)
            if archived is not None and thread["lease_until"] > time.time():
                raise ChatError(409, "Hãy dừng lượt hỏi đang chạy trước khi lưu trữ.")
            next_archived = thread["archived"] if archived is None else archived
            next_pinned = (thread["pinned"] if pinned is None else pinned) and not next_archived
            if next_pinned and not thread["pinned"]:
                count = conn.execute(
                    "SELECT COUNT(*) FROM workchat_threads WHERE owner_id = ? AND pinned = 1 AND archived = 0",
                    (owner_id,),
                ).fetchone()[0]
                if count >= 3:
                    raise ChatError(409, "Chỉ có thể ghim tối đa 3 cuộc trò chuyện.")
            conn.execute(
                "UPDATE workchat_threads SET title = ?, pinned = ?, archived = ? WHERE id = ? AND owner_id = ?",
                (title if title is not None else thread["title"], next_pinned, next_archived, thread_id, owner_id),
            )
            return self._summary(self._thread(conn, owner_id, thread_id))

    def delete(self, owner_id, thread_id):
        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            thread = self._thread(conn, owner_id, thread_id)
            if thread["lease_until"] > time.time():
                raise ChatError(409, "Hãy dừng lượt hỏi đang chạy trước khi xóa.")
            conn.execute("DELETE FROM workchat_threads WHERE id = ? AND owner_id = ?", (thread_id, owner_id))

    def change_all(self, owner_id, *, archive):
        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute(
                "SELECT 1 FROM workchat_threads WHERE owner_id = ? AND lease_until > ?",
                (owner_id, time.time()),
            ).fetchone():
                raise ChatError(409, "Hãy dừng lượt hỏi đang chạy trước khi tiếp tục.")
            if archive:
                conn.execute(
                    "UPDATE workchat_threads SET archived = 1, pinned = 0 WHERE owner_id = ?", (owner_id,),
                )
            else:
                conn.execute("DELETE FROM workchat_threads WHERE owner_id = ?", (owner_id,))

    def reserve(self, owner_id, thread_id, request_id, request_hash):
        """Only one active turn per account, including across server workers."""
        now = time.time()
        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            thread = self._thread(conn, owner_id, thread_id)
            if thread["archived"]:
                raise ChatError(409, "Mở lại cuộc trò chuyện đã lưu trữ để gửi câu hỏi.")
            existing = conn.execute(
                """SELECT turn.* FROM workchat_turns turn JOIN workchat_threads thread
                   ON turn.thread_id = thread.id WHERE thread.owner_id = ?
                   AND turn.thread_id = ? AND turn.request_id = ?""",
                (owner_id, thread_id, request_id),
            ).fetchone()
            if existing:
                if existing["request_hash"] != request_hash:
                    raise ChatError(409, "Lượt hỏi này đã được dùng cho một nội dung khác.")
                return None, self._turn(existing)
            if conn.execute(
                "SELECT 1 FROM workchat_threads WHERE owner_id = ? AND lease_until > ?",
                (owner_id, now),
            ).fetchone():
                raise ChatError(409, "Đang xử lý một lượt hỏi của tài khoản này. Hãy thử lại sau.")
            count = conn.execute(
                """SELECT COUNT(*) FROM workchat_turns turn JOIN workchat_threads thread
                   ON turn.thread_id = thread.id WHERE turn.thread_id = ? AND thread.owner_id = ?""",
                (thread_id, owner_id),
            ).fetchone()[0]
            if count >= self.MAX_TURNS:
                raise ChatError(409, "Cuộc trò chuyện đã đạt giới hạn. Tạo cuộc trò chuyện mới để tiếp tục.")
            conn.execute("DELETE FROM workchat_attempts WHERE time < ?", (now - 60,))
            attempts = conn.execute(
                "SELECT COUNT(*) FROM workchat_attempts WHERE owner_id = ?", (owner_id,),
            ).fetchone()[0]
            if attempts >= self.ATTEMPTS_PER_MINUTE:
                raise ChatError(429, "Bạn gửi quá nhanh. Hãy chờ một chút rồi thử lại.")
            lease = uuid.uuid4().hex
            conn.execute("INSERT INTO workchat_attempts (owner_id, time) VALUES (?, ?)", (owner_id, now))
            conn.execute(
                "UPDATE workchat_threads SET lease = ?, lease_until = ? WHERE id = ? AND owner_id = ?",
                (lease, now + self.LEASE_SECONDS, thread_id, owner_id),
            )
            return lease, None

    def finish(self, owner_id, thread_id, lease, request_id, request_hash, question, data):
        now = int(time.time() * 1000)
        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            thread = self._thread(conn, owner_id, thread_id)
            if thread["lease"] != lease or thread["lease_until"] * 1000 < now or thread["archived"]:
                raise ChatError(409, "Lượt hỏi đã hết thời gian. Hãy gửi lại.")
            conn.execute(
                """INSERT INTO workchat_turns (thread_id, request_id, request_hash, question, data, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (thread_id, request_id, request_hash, question, json.dumps(data, ensure_ascii=False), now),
            )
            conn.execute(
                """UPDATE workchat_threads SET updated_at = ?, lease = NULL, lease_until = 0
                   WHERE id = ? AND owner_id = ? AND lease = ?""", (now, thread_id, owner_id, lease),
            )
            return self._summary(self._thread(conn, owner_id, thread_id)), {
                "id": request_id, "question": question, "createdAt": now, **data,
            }

    def release(self, owner_id, thread_id, lease):
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """UPDATE workchat_threads SET lease = NULL, lease_until = 0
                   WHERE id = ? AND owner_id = ? AND lease = ?""",
                (thread_id, owner_id, lease),
            )
