# -*- coding: utf-8 -*-
"""
Nhật ký tra cứu và phản hồi của bác sĩ — dữ liệu chuẩn tích dần từ chính cách dùng.

Bộ eval hiện có là vài chục câu do người phát triển tự đặt. Câu hỏi THẬT của bác
sĩ thì khác: gõ không dấu, viết tắt, hỏi liều cho một bệnh nhân cụ thể. Mỗi lượt
tra được ghi lại cùng các trang đã trả về, và mỗi cú bấm của bác sĩ thành một nhãn:

- ``up`` / ``down``   — câu trả lời có ích hay không.
- ``open``            — bác sĩ mở trang trích dẫn thứ n (tín hiệu dương yếu).
- ``wrong_page``      — trang trích dẫn thứ n KHÔNG nói về câu hỏi: âm đã xác nhận.

Từ đó rút được bộ eval từ câu hỏi thật (eval sau này đọc bảng này), chỉnh ngưỡng,
và về lâu dài là dữ liệu tinh chỉnh reranker. Kết quả không được bấm thì KHÔNG
coi là âm — bác sĩ có thể đã đọc mà thấy đủ.

Tách riêng khỏi library.db: đây là dữ liệu đo lường, xoá đi không mất gì của
bác sĩ, và không nên lẫn vào lịch sử tra cứu mà bác sĩ nhìn thấy.
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import config

DB_PATH = os.path.join(config.DATA_DIR, "feedback.db")
KINDS = ("up", "down", "open", "wrong_page")


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS query_log (
                id TEXT PRIMARY KEY,
                owner_id TEXT,
                query TEXT NOT NULL,
                normalized_query TEXT,
                doc_scope TEXT,
                sources TEXT NOT NULL,
                outcome TEXT,
                verify TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS feedback (
                id TEXT PRIMARY KEY,
                log_id TEXT NOT NULL REFERENCES query_log(id),
                owner_id TEXT,
                kind TEXT NOT NULL,
                source_index INTEGER,
                note TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_feedback_log ON feedback(log_id);
            CREATE INDEX IF NOT EXISTS idx_query_log_created ON query_log(created_at DESC);
            """
        )


def log_query(owner_id: Optional[str], query: str, normalized_query: Optional[str],
              doc_scope: Optional[str], sources: List[Dict[str, Any]]) -> str:
    """Ghi một lượt tra; chỉ giữ toạ độ của nguồn (id, tài liệu, trang, điểm), không chép văn bản."""
    log_id = str(uuid.uuid4())
    compact = [{"id": s.get("id"), "doc_name": s.get("doc_name"), "page_num": s.get("page_num"),
                "kind": s.get("kind", "book"), "score": s.get("score")} for s in sources]
    with _connect() as conn:
        conn.execute(
            "INSERT INTO query_log (id, owner_id, query, normalized_query, doc_scope, sources, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (log_id, owner_id, query, normalized_query, doc_scope,
             json.dumps(compact, ensure_ascii=False), datetime.now().isoformat()),
        )
    return log_id


def finish_query(log_id: str, outcome: str, verify: Optional[Dict[str, Any]]) -> None:
    with _connect() as conn:
        conn.execute("UPDATE query_log SET outcome = ?, verify = ? WHERE id = ?",
                     (outcome, json.dumps(verify, ensure_ascii=False) if verify else None, log_id))


def add_feedback(log_id: str, owner_id: Optional[str], kind: str,
                 source_index: Optional[int] = None, note: Optional[str] = None) -> bool:
    """False nếu lượt tra không tồn tại hoặc không thuộc người này."""
    if kind not in KINDS:
        raise ValueError(f"kind phải thuộc {KINDS}")
    with _connect() as conn:
        row = conn.execute("SELECT owner_id, sources FROM query_log WHERE id = ?", (log_id,)).fetchone()
        if not row or row["owner_id"] != owner_id:
            return False
        if source_index is not None and not (0 <= source_index < len(json.loads(row["sources"]))):
            raise ValueError("source_index ngoài phạm vi")
        if kind in ("up", "down"):
            # Đổi ý thì ghi đè: một lượt tra chỉ có một đánh giá.
            conn.execute("DELETE FROM feedback WHERE log_id = ? AND kind IN ('up', 'down')", (log_id,))
        conn.execute(
            "INSERT INTO feedback (id, log_id, owner_id, kind, source_index, note, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), log_id, owner_id, kind, source_index, note, datetime.now().isoformat()),
        )
    return True


def summary(owner_id: Optional[str] = None) -> Dict[str, Any]:
    """Số đo hằng tuần của báo cáo kỹ thuật: tỉ lệ đánh giá xấu, sai trang, cờ số liệu."""
    where, args = ("WHERE owner_id = ?", (owner_id,)) if owner_id else ("", ())
    with _connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM query_log {where}", args).fetchone()[0]
        kinds = dict(conn.execute(
            f"SELECT kind, COUNT(DISTINCT log_id) FROM feedback {where} GROUP BY kind", args).fetchall())
        flagged = 0
        for (v,) in conn.execute(f"SELECT verify FROM query_log {where}", args):
            if v and json.loads(v).get("flags"):
                flagged += 1
    return {"queries": total, "rated_up": kinds.get("up", 0), "rated_down": kinds.get("down", 0),
            "wrong_page": kinds.get("wrong_page", 0), "opened": kinds.get("open", 0),
            "answers_with_number_flags": flagged}
