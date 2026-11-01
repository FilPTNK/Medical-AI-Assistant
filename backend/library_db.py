"""SQLite-backed storage for the document-research features (tra cứu tài liệu).

Three related stores share one database file:

* ``highlights``     — đoạn tô sáng + ghi chú của bác sĩ trên từng trang tài liệu.
* ``doc_notes``      — ghi chú cá nhân ở cấp tài liệu (mỗi tài liệu một bản ghi).
* ``search_history`` — lịch sử câu hỏi tra cứu kèm câu trả lời, nguồn và vector
  embedding của câu hỏi, dùng để gợi ý "câu hỏi tương tự đã hỏi trước đây" và
  tái sử dụng lại kết quả cũ mà không cần gọi lại LLM.

Cả ba đều là dữ liệu CỦA TỪNG TÀI KHOẢN, khoá theo ``owner_id`` (id hồ sơ đăng
nhập, do máy chủ gắn — không lấy từ trình duyệt). Câu hỏi tra cứu có thể chứa
thông tin bệnh nhân, nên bác sĩ này không được thấy lịch sử của bác sĩ khác.
Mọi hàm đọc/ghi ở đây đều nhận ``owner_id`` bắt buộc: không có đường nào lỡ
quên lọc.

``doc_notes`` cũ khoá theo doc_name (một ghi chú chung cho cả phòng khám) nên
không sửa tại chỗ được; ghi chú theo tài khoản nằm ở ``user_doc_notes``.
"""
import json
import math
import os
import re
import sqlite3
import unicodedata
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import config

DB_PATH = os.path.join(config.DATA_DIR, "library.db")

# Bảng màu tô sáng được phép (khớp với bảng màu ở frontend)
HIGHLIGHT_COLORS = {"yellow", "green", "blue", "pink", "purple"}
DEFAULT_COLOR = "yellow"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS highlights (
                id TEXT PRIMARY KEY,
                doc_name TEXT NOT NULL,
                page_num INTEGER NOT NULL,
                quote TEXT NOT NULL,
                start_offset INTEGER NOT NULL,
                end_offset INTEGER NOT NULL,
                color TEXT NOT NULL,
                note TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS doc_notes (
                doc_name TEXT PRIMARY KEY,
                content TEXT,
                updated_by TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS search_history (
                id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                answer TEXT,
                sources TEXT,
                embedding TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_highlights_doc ON highlights(doc_name, page_num);
            CREATE INDEX IF NOT EXISTS idx_history_created ON search_history(created_at DESC);
            """
        )
        # Vector câu hỏi chỉ so sánh được với vector do CÙNG một model sinh ra.
        # Trước đây không ghi lại model, nên khi đổi embedding thì các vector cũ
        # vẫn được đem ra tính cosine với vector mới — ra một con số vô nghĩa,
        # không phải lỗi mà cũng không phải kết quả đúng. Cột này để lọc chúng.
        cols = {r[1] for r in conn.execute("PRAGMA table_info(search_history)")}
        if "embedding_model" not in cols:
            conn.execute("ALTER TABLE search_history ADD COLUMN embedding_model TEXT")

        for table in ("search_history", "highlights"):
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            if "owner_id" not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN owner_id TEXT")
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_history_owner ON search_history(owner_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_highlights_owner ON highlights(owner_id, doc_name, page_num);

            CREATE TABLE IF NOT EXISTS user_doc_notes (
                owner_id TEXT NOT NULL,
                doc_name TEXT NOT NULL,
                content TEXT,
                updated_by TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (owner_id, doc_name)
            );
            """
        )


def assign_legacy_owners(name_to_id: Dict[str, str]) -> Dict[str, int]:
    """Gắn chủ cho dòng cũ (trước khi có owner_id) theo tên người tạo đã lưu.

    `name_to_id` chỉ nên chứa tên khớp ĐÚNG MỘT tài khoản — tên trùng nhau thì
    không đoán. Dòng không gắn được giữ nguyên với owner_id NULL: không ai thấy
    nữa, nhưng cũng không bị xoá.

    Chỉ chạy MỘT lần (có dấu trong bảng `migrations`): nếu chạy mỗi lần khởi
    động, một tài khoản tạo sau này tình cờ trùng tên với dòng mồ côi sẽ nhận
    luôn lịch sử của người khác.
    """
    counts = {}
    with _connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        if conn.execute("SELECT 1 FROM migrations WHERE name = 'owner_id_backfill'").fetchone():
            return counts
        conn.execute("INSERT INTO migrations (name, applied_at) VALUES ('owner_id_backfill', ?)",
                     (datetime.now().isoformat(),))
        for table, col in (("search_history", "created_by"), ("highlights", "created_by")):
            n = 0
            for name, owner in name_to_id.items():
                n += conn.execute(f"UPDATE {table} SET owner_id = ? WHERE owner_id IS NULL AND {col} = ?",
                                  (owner, name)).rowcount
            counts[table] = n
        n = 0
        for row in conn.execute("SELECT * FROM doc_notes").fetchall():
            owner = name_to_id.get(row["updated_by"] or "")
            if owner and (row["content"] or "").strip():
                n += conn.execute(
                    "INSERT OR IGNORE INTO user_doc_notes (owner_id, doc_name, content, updated_by, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (owner, row["doc_name"], row["content"], row["updated_by"], row["updated_at"]),
                ).rowcount
        counts["doc_notes"] = n
    return counts


# ---------------------------------------------------------------- highlights

def _highlight_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return dict(row)


def list_highlights(owner_id: str, doc_name: Optional[str] = None, page_num: Optional[int] = None) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM highlights"
    params: List[Any] = [owner_id]
    clauses = ["owner_id = ?"]
    if doc_name:
        clauses.append("doc_name = ?")
        params.append(doc_name)
    if page_num is not None:
        clauses.append("page_num = ?")
        params.append(page_num)
    sql += " WHERE " + " AND ".join(clauses)
    # Trong cùng một trang, sắp theo vị trí để frontend dựng lớp tô sáng tuần tự.
    sql += " ORDER BY page_num ASC, start_offset ASC, created_at ASC"
    with _connect() as conn:
        return [_highlight_row_to_dict(r) for r in conn.execute(sql, params).fetchall()]


def search_highlights(owner_id: str, keyword: str, limit: int = 200) -> List[Dict[str, Any]]:
    like = f"%{keyword.strip()}%"
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM highlights
            WHERE owner_id = ? AND (quote LIKE ? OR note LIKE ? OR doc_name LIKE ?)
            ORDER BY updated_at DESC LIMIT ?
            """,
            (owner_id, like, like, like, limit),
        ).fetchall()
        return [_highlight_row_to_dict(r) for r in rows]


def create_highlight(owner_id: str, doc_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.now().isoformat()
    highlight_id = str(uuid.uuid4())
    color = str(data.get("color") or DEFAULT_COLOR)
    if color not in HIGHLIGHT_COLORS:
        color = DEFAULT_COLOR
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO highlights (
                id, doc_name, page_num, quote, start_offset, end_offset,
                color, note, created_by, created_at, updated_at, owner_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                highlight_id, doc_name, int(data.get("page_num") or 1),
                str(data.get("quote") or ""),
                int(data.get("start_offset") or 0), int(data.get("end_offset") or 0),
                color, (data.get("note") or None), (data.get("created_by") or None),
                now, now, owner_id,
            ),
        )
        row = conn.execute("SELECT * FROM highlights WHERE id = ?", (highlight_id,)).fetchone()
        return _highlight_row_to_dict(row)


def update_highlight(owner_id: str, highlight_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    fields = []
    params: List[Any] = []
    if "note" in data:
        fields.append("note = ?")
        params.append(data.get("note") or None)
    if "color" in data:
        color = str(data.get("color") or DEFAULT_COLOR)
        fields.append("color = ?")
        params.append(color if color in HIGHLIGHT_COLORS else DEFAULT_COLOR)
    if not fields:
        return get_highlight(owner_id, highlight_id)

    fields.append("updated_at = ?")
    params.append(datetime.now().isoformat())
    params.extend([highlight_id, owner_id])
    with _connect() as conn:
        conn.execute(f"UPDATE highlights SET {', '.join(fields)} WHERE id = ? AND owner_id = ?", params)
    return get_highlight(owner_id, highlight_id)


def get_highlight(owner_id: str, highlight_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM highlights WHERE id = ? AND owner_id = ?",
                           (highlight_id, owner_id)).fetchone()
        return _highlight_row_to_dict(row) if row else None


def delete_highlight(owner_id: str, highlight_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM highlights WHERE id = ? AND owner_id = ?", (highlight_id, owner_id))
        return cur.rowcount > 0


def delete_highlights_for_document(doc_name: str):
    """Dọn ghi chú của MỌI tài khoản khi tài liệu bị xóa khỏi thư viện."""
    with _connect() as conn:
        conn.execute("DELETE FROM highlights WHERE doc_name = ?", (doc_name,))
        conn.execute("DELETE FROM doc_notes WHERE doc_name = ?", (doc_name,))
        conn.execute("DELETE FROM user_doc_notes WHERE doc_name = ?", (doc_name,))


def count_highlights_by_document(owner_id: str) -> Dict[str, int]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT doc_name, COUNT(*) AS n FROM highlights WHERE owner_id = ? GROUP BY doc_name",
            (owner_id,),
        ).fetchall()
        return {r["doc_name"]: r["n"] for r in rows}


# ---------------------------------------------------------------- doc notes

def _note_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    d.pop("owner_id", None)
    return d


def get_doc_note(owner_id: str, doc_name: str) -> Dict[str, Any]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM user_doc_notes WHERE owner_id = ? AND doc_name = ?",
                           (owner_id, doc_name)).fetchone()
        if not row:
            return {"doc_name": doc_name, "content": "", "updated_by": None, "updated_at": None}
        return _note_dict(row)


def save_doc_note(owner_id: str, doc_name: str, content: str, updated_by: Optional[str] = None) -> Dict[str, Any]:
    now = datetime.now().isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO user_doc_notes (owner_id, doc_name, content, updated_by, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(owner_id, doc_name) DO UPDATE SET
                content = excluded.content,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (owner_id, doc_name, content, updated_by, now),
        )
        row = conn.execute("SELECT * FROM user_doc_notes WHERE owner_id = ? AND doc_name = ?",
                           (owner_id, doc_name)).fetchone()
        return _note_dict(row)


# ---------------------------------------------------------------- history

def _history_row_to_dict(row: sqlite3.Row, include_embedding: bool = False) -> Dict[str, Any]:
    d = dict(row)
    d.pop("owner_id", None)
    raw_sources = d.pop("sources", None)
    try:
        d["sources"] = json.loads(raw_sources) if raw_sources else []
    except (TypeError, ValueError):
        d["sources"] = []
    embedding = d.pop("embedding", None)
    # embedding_model là chi tiết nội bộ để lọc vector cũ, không phải thứ API
    # cần trả ra; chỉ giữ lại cho đúng nhánh đang so vector.
    model_name = d.pop("embedding_model", None)
    if include_embedding:
        d["embedding_model"] = model_name
        try:
            d["embedding"] = json.loads(embedding) if embedding else None
        except (TypeError, ValueError):
            d["embedding"] = None
    return d


def add_history(
    owner_id: str,
    query: str,
    answer: str,
    sources: List[Dict[str, Any]],
    embedding: Optional[List[float]] = None,
    created_by: Optional[str] = None,
    embedding_model: Optional[str] = None,
) -> Dict[str, Any]:
    now = datetime.now().isoformat()
    record_id = str(uuid.uuid4())
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO search_history
                (id, query, answer, sources, embedding, created_by, created_at, embedding_model, owner_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id, query, answer,
                json.dumps(sources, ensure_ascii=False),
                json.dumps(embedding) if embedding else None,
                created_by, now,
                embedding_model if embedding else None,
                owner_id,
            ),
        )
        row = conn.execute("SELECT * FROM search_history WHERE id = ?", (record_id,)).fetchone()
        return _history_row_to_dict(row)


def list_history(owner_id: str, keyword: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    with _connect() as conn:
        if keyword and keyword.strip():
            like = f"%{keyword.strip()}%"
            rows = conn.execute(
                """
                SELECT * FROM search_history
                WHERE owner_id = ? AND (query LIKE ? OR answer LIKE ?)
                ORDER BY created_at DESC LIMIT ?
                """,
                (owner_id, like, like, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM search_history WHERE owner_id = ? ORDER BY created_at DESC LIMIT ?",
                (owner_id, limit),
            ).fetchall()
        return [_history_row_to_dict(r) for r in rows]


def get_history(owner_id: str, record_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM search_history WHERE id = ? AND owner_id = ?",
                           (record_id, owner_id)).fetchone()
        return _history_row_to_dict(row) if row else None


def delete_history(owner_id: str, record_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM search_history WHERE id = ? AND owner_id = ?", (record_id, owner_id))
        return cur.rowcount > 0


def clear_history(owner_id: str):
    """Xoá lịch sử của MỘT tài khoản. Trước đây nút "Xoá hết" xoá của cả phòng khám."""
    with _connect() as conn:
        conn.execute("DELETE FROM search_history WHERE owner_id = ?", (owner_id,))


# ------------------------------------------------- similar question matching

# Từ nối/hư từ tiếng Việt không mang thông tin phân biệt câu hỏi
_STOPWORDS = {
    "la", "cua", "cho", "va", "voi", "khi", "nao", "the", "duoc", "co", "khong",
    "bi", "trong", "tren", "duoi", "bao", "nhieu", "gi", "nhu", "mot", "cac",
    "nhung", "hay", "thi", "ra", "sao", "can", "phai", "de", "tai", "tu", "den",
}


def _strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt để so khớp được cả khi bác sĩ gõ không dấu."""
    text = (text or "").lower().replace("đ", "d")
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text)
        if not unicodedata.combining(ch)
    )


def _tokenize(text: str) -> set:
    """Token không dấu, bỏ hư từ — dùng cho so khớp từ khóa."""
    words = re.findall(r"\w+", _strip_accents(text))
    return {w for w in words if len(w) > 1 and w not in _STOPWORDS}


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _dice(a: set, b: set) -> float:
    """Hệ số Dice giữa hai tập từ khóa (rộng tay hơn Jaccard với câu ngắn)."""
    if not a or not b:
        return 0.0
    return 2 * len(a & b) / (len(a) + len(b))


# Ngưỡng cosine để coi hai câu hỏi là gần nghĩa, RIÊNG cho từng model.
#
# Không dùng chung một con số được: mỗi model trải điểm cosine trên một khoảng
# khác nhau. Họ e5 nén điểm lên rất cao — hai câu KHÔNG liên quan vẫn quanh
# 0,85 — nên ngưỡng 0,55 của model cũ sẽ coi gần như mọi câu hỏi là giống nhau.
# Số đo ở eval/calibrate_similarity.py.
_EMBEDDING_THRESHOLDS = {
    "intfloat/multilingual-e5-small": 0.92,
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": 0.55,
}
_DEFAULT_EMBEDDING_THRESHOLD = 0.90


def find_similar_questions(
    owner_id: str,
    query: str,
    query_embedding: Optional[List[float]] = None,
    limit: int = 4,
    min_score: float = 0.55,
    scan_limit: int = 500,
    embedding_model: Optional[str] = None,
    min_embedding_score: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Tìm các câu hỏi đã tra cứu trước đây gần nghĩa với `query`.

    Kết hợp hai tín hiệu và lấy điểm cao hơn:
    * embedding (cùng model với vector store) — bắt được câu hỏi diễn đạt khác;
    * trùng từ khóa không dấu (hệ số Dice) — bắt được trường hợp bác sĩ gõ
      không dấu, thứ mà embedding tiếng Việt xử lý khá kém, và cũng là phương án
      dự phòng khi không nạp được model embedding.

    Hai tín hiệu này có thang điểm KHÁC NHAU nên mỗi cái một ngưỡng: `min_score`
    cho từ khoá, `min_embedding_score` cho cosine. Trước đây dùng chung 0,55 —
    chấp nhận được với model cũ, nhưng với e5 thì cosine hai câu bất kỳ đã quanh
    0,85 nên mọi câu hỏi cũ đều vượt ngưỡng.

    Vector chỉ được đem ra so khi sinh bởi ĐÚNG model đang chạy; bản ghi cũ mang
    model khác (hoặc không ghi model) chỉ còn khớp bằng từ khoá.
    """
    q_norm = _strip_accents(query).strip()
    q_tokens = _tokenize(query)
    if not q_norm:
        return []

    if min_embedding_score is None:
        min_embedding_score = _EMBEDDING_THRESHOLDS.get(
            embedding_model, _DEFAULT_EMBEDDING_THRESHOLD
        )

    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM search_history WHERE owner_id = ? ORDER BY created_at DESC LIMIT ?",
            (owner_id, scan_limit),
        ).fetchall()

    scored: List[Dict[str, Any]] = []
    for row in rows:
        record = _history_row_to_dict(row, include_embedding=True)
        past_query = record["query"]
        if _strip_accents(past_query).strip() == q_norm:
            # Câu hỏi trùng khít (kể cả khác dấu): luôn xếp trên cùng.
            score, method, passed = 1.0, "exact", True
        else:
            keyword_score = _dice(q_tokens, _tokenize(past_query))
            emb = record.get("embedding")
            row_model = record.get("embedding_model")
            comparable = bool(query_embedding and emb and embedding_model
                              and row_model == embedding_model)
            embedding_score = _cosine(query_embedding, emb) if comparable else 0.0

            # So từng tín hiệu với ngưỡng của chính nó, rồi mới chọn cái mạnh hơn.
            emb_ok = comparable and embedding_score >= min_embedding_score
            kw_ok = keyword_score >= min_score
            if emb_ok and (not kw_ok or embedding_score >= keyword_score):
                score, method, passed = embedding_score, "embedding", True
            elif kw_ok:
                score, method, passed = keyword_score, "keyword", True
            else:
                score, method, passed = max(keyword_score, embedding_score), "", False

        if passed:
            record.pop("embedding", None)
            record.pop("embedding_model", None)
            record["similarity"] = round(float(score), 4)
            record["match_method"] = method
            scored.append(record)

    scored.sort(key=lambda r: r["similarity"], reverse=True)
    return scored[:limit]
