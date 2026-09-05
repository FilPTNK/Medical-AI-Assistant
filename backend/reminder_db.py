"""Reminder engine — nhắc lịch tái khám và theo dõi bệnh nhân mãn tính.

Trước đây `/api/notifications` chỉ đọc thẳng cột `visits.followup_date`: mỗi lần
khám sinh đúng một lời nhắc, không hoãn được, không đánh dấu đã xong được, và
không thể tạo lịch theo dõi định kỳ cho bệnh nhân mãn tính (tăng huyết áp, đái
tháo đường...). Module này thay bằng một bảng `reminders` thật trong
data/patients.db với vòng đời đầy đủ:

    pending ──(hoãn)──> pending (due_date lùi lại)
       │
       ├──(hoàn thành)──> done ──(nếu lặp lại)──> sinh lời nhắc kế tiếp
       └──(bỏ qua)──────> dismissed

Lời nhắc tái khám vẫn được sinh tự động từ `visits.followup_date` (source='visit')
nên dữ liệu cũ không mất; bác sĩ có thể tạo thêm lời nhắc thủ công (source='manual')
với chu kỳ lặp — ví dụ "đo HbA1c mỗi 90 ngày".
"""
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from patient_db import _connect

# Loại nhắc lịch, kèm nhãn tiếng Việt cho UI.
REMINDER_KINDS = {
    "followup": "Tái khám",
    "chronic": "Theo dõi mãn tính",
    "lab": "Xét nghiệm / cận lâm sàng",
    "medication": "Nhắc thuốc",
    "custom": "Khác",
}

STATUSES = {"pending", "done", "dismissed"}

# Các cột update_reminder() được phép ghi.
EDITABLE_FIELDS = {
    "kind", "title", "note", "due_date", "repeat_interval_days", "doctor_id",
}


def _today() -> date:
    return date.today()


def _now_iso() -> str:
    return datetime.now().isoformat()


def _as_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _row_to_reminder(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    d["kind_label"] = REMINDER_KINDS.get(d.get("kind"), d.get("kind"))
    # Lời nhắc đang hoãn thì ngày đến hạn *thực tế* là ngày hết hoãn.
    effective = _as_date(d.get("snoozed_until")) or _as_date(d.get("due_date"))
    d["effective_date"] = effective.isoformat() if effective else d.get("due_date")
    if effective:
        days_diff = (effective - _today()).days
        d["days_diff"] = days_diff
        d["overdue"] = days_diff < 0 and d.get("status") == "pending"
    else:
        d["days_diff"] = None
        d["overdue"] = False
    d["snoozed"] = bool(d.get("snoozed_until"))
    return d


# --- Đồng bộ từ lịch tái khám ghi trong phiếu khám ------------------------

def sync_from_visits() -> Dict[str, int]:
    """Sinh/cập nhật lời nhắc tái khám từ `visits.followup_date`.

    Chạy trước mỗi lần đọc danh sách nên lịch hẹn bác sĩ vừa ghi trong phiếu khám
    xuất hiện ngay. Thao tác thủ công (hoãn, đánh dấu xong, sửa nội dung) được
    giữ nguyên: hàm chỉ tạo mới, cập nhật ngày hẹn khi phiếu khám đổi, và tự
    đóng lời nhắc khi bệnh nhân đã quay lại khám sau ngày hẹn.
    """
    created = updated = auto_closed = 0
    now = _now_iso()
    with _connect() as conn:
        visits = conn.execute(
            """
            SELECT v.id, v.patient_id, v.followup_date, v.followup_purpose, v.doctor_name,
                   (SELECT COUNT(*) FROM visits v2
                     WHERE v2.patient_id = v.patient_id
                       AND v2.id != v.id
                       AND v2.visit_date >= v.followup_date) AS returned
            FROM visits v
            WHERE v.followup_date IS NOT NULL AND TRIM(v.followup_date) != ''
            """
        ).fetchall()

        for v in visits:
            if _as_date(v["followup_date"]) is None:
                continue  # ngày hẹn ghi sai định dạng — bỏ qua thay vì tạo rác
            existing = conn.execute(
                "SELECT * FROM reminders WHERE visit_id = ? AND source = 'visit'", (v["id"],)
            ).fetchone()

            if existing is None:
                # Bệnh nhân đã quay lại trước khi engine chạy lần đầu → tạo thẳng trạng thái done.
                status = "done" if v["returned"] else "pending"
                conn.execute(
                    """INSERT INTO reminders
                       (id, patient_id, visit_id, doctor_id, kind, title, note, due_date,
                        repeat_interval_days, status, snoozed_until, completed_at,
                        source, created_by, created_at, updated_at)
                       VALUES (?, ?, ?, NULL, 'followup', ?, ?, ?, NULL, ?, NULL, ?, 'visit', ?, ?, ?)""",
                    (str(uuid.uuid4()), v["patient_id"], v["id"],
                     "Tái khám theo hẹn", v["followup_purpose"], v["followup_date"][:10],
                     status, now if status == "done" else None,
                     v["doctor_name"], now, now),
                )
                created += 1
                continue

            if existing["status"] == "pending":
                if v["returned"]:
                    conn.execute(
                        "UPDATE reminders SET status = 'done', completed_at = ?, updated_at = ? WHERE id = ?",
                        (now, now, existing["id"]),
                    )
                    auto_closed += 1
                elif existing["due_date"] != v["followup_date"][:10]:
                    # Bác sĩ dời lịch hẹn trong phiếu khám → lời nhắc đi theo.
                    conn.execute(
                        "UPDATE reminders SET due_date = ?, snoozed_until = NULL, updated_at = ? WHERE id = ?",
                        (v["followup_date"][:10], now, existing["id"]),
                    )
                    updated += 1

    return {"created": created, "updated": updated, "auto_closed": auto_closed}


# --- Truy vấn -------------------------------------------------------------

def list_reminders(owner_id: Optional[str] = None,
                   status: Optional[str] = "pending",
                   patient_id: Optional[str] = None,
                   kind: Optional[str] = None,
                   days_ahead: Optional[int] = None,
                   sync: bool = True) -> List[Dict[str, Any]]:
    """Danh sách lời nhắc kèm thông tin bệnh nhân.

    `owner_id` giới hạn theo bác sĩ phụ trách bệnh nhân; `days_ahead` chỉ lấy các
    lời nhắc đã quá hạn hoặc đến hạn trong ngần ấy ngày tới.
    """
    if sync:
        sync_from_visits()

    clauses: List[str] = []
    params: List[Any] = []
    if status and status != "all":
        clauses.append("r.status = ?")
        params.append(status)
    if patient_id:
        clauses.append("r.patient_id = ?")
        params.append(patient_id)
    if kind:
        clauses.append("r.kind = ?")
        params.append(kind)
    if owner_id:
        clauses.append("(p.owner_doctor_id = ? OR p.owner_doctor_id IS NULL)")
        params.append(owner_id)
    if days_ahead is not None:
        horizon = (_today() + timedelta(days=days_ahead)).isoformat()
        clauses.append("COALESCE(r.snoozed_until, r.due_date) <= ?")
        params.append(horizon)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT r.*, p.name AS patient_name, p.code AS patient_code,
                   p.phone AS patient_phone, p.chronic_conditions,
                   p.owner_doctor_id
            FROM reminders r
            JOIN patients p ON p.id = r.patient_id
            {where}
            ORDER BY COALESCE(r.snoozed_until, r.due_date) ASC, r.created_at ASC
            """,
            params,
        ).fetchall()
    return [_row_to_reminder(r) for r in rows]


def get_notifications(owner_id: Optional[str] = None, days_ahead: int = 7) -> List[Dict[str, Any]]:
    """Nguồn dữ liệu cho chuông thông báo: lời nhắc quá hạn + sắp đến hạn.

    Giữ nguyên các khóa `visit_id`/`followup_date`/`followup_purpose` mà giao diện
    chuông cũ đang dùng, đồng thời bổ sung trường của reminder engine.
    """
    reminders = list_reminders(owner_id=owner_id, status="pending", days_ahead=days_ahead)
    notifications = []
    for r in reminders:
        notifications.append({
            # khóa cũ — chuông thông báo dùng làm React key và để mở hồ sơ
            "visit_id": r["visit_id"] or r["id"],
            "patient_id": r["patient_id"],
            "patient_name": r["patient_name"],
            "patient_code": r["patient_code"],
            "followup_date": r["effective_date"],
            "followup_purpose": r["note"] or r["title"],
            "days_diff": r["days_diff"],
            "overdue": r["overdue"],
            # khóa mới của reminder engine
            "reminder_id": r["id"],
            "kind": r["kind"],
            "kind_label": r["kind_label"],
            "title": r["title"],
            "snoozed": r["snoozed"],
        })
    return notifications


def summarize(owner_id: Optional[str] = None) -> Dict[str, int]:
    """Đếm nhanh cho thẻ tổng quan: quá hạn / hôm nay / 7 ngày tới."""
    pending = list_reminders(owner_id=owner_id, status="pending")
    overdue = sum(1 for r in pending if (r["days_diff"] or 0) < 0)
    today = sum(1 for r in pending if r["days_diff"] == 0)
    week = sum(1 for r in pending if 0 < (r["days_diff"] or 999) <= 7)
    return {
        "overdue": overdue,
        "today": today,
        "next_7_days": week,
        "pending_total": len(pending),
    }


def get_reminder(reminder_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            """SELECT r.*, p.name AS patient_name, p.code AS patient_code,
                      p.phone AS patient_phone, p.chronic_conditions, p.owner_doctor_id
               FROM reminders r JOIN patients p ON p.id = r.patient_id
               WHERE r.id = ?""",
            (reminder_id,),
        ).fetchone()
    return _row_to_reminder(row) if row else None


# --- Ghi ------------------------------------------------------------------

def create_reminder(patient_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    reminder_id = str(uuid.uuid4())
    now = _now_iso()
    due = _as_date(data.get("due_date")) or _today()
    kind = data.get("kind") if data.get("kind") in REMINDER_KINDS else "custom"
    repeat = data.get("repeat_interval_days")
    with _connect() as conn:
        conn.execute(
            """INSERT INTO reminders
               (id, patient_id, visit_id, doctor_id, kind, title, note, due_date,
                repeat_interval_days, status, snoozed_until, completed_at,
                source, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL, NULL, 'manual', ?, ?, ?)""",
            (reminder_id, patient_id, data.get("visit_id"), data.get("doctor_id"),
             kind, (data.get("title") or REMINDER_KINDS[kind]), data.get("note"),
             due.isoformat(), int(repeat) if repeat else None,
             data.get("created_by"), now, now),
        )
    return get_reminder(reminder_id)


def update_reminder(reminder_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    fields = {k: v for k, v in data.items() if k in EDITABLE_FIELDS and v is not None}
    if "kind" in fields and fields["kind"] not in REMINDER_KINDS:
        del fields["kind"]
    if "due_date" in fields:
        due = _as_date(fields["due_date"])
        if due is None:
            del fields["due_date"]
        else:
            fields["due_date"] = due.isoformat()
            fields["snoozed_until"] = None  # đổi ngày hẹn thì bỏ trạng thái hoãn
    if not fields:
        return get_reminder(reminder_id)
    with _connect() as conn:
        assignments = ", ".join(f"{k} = ?" for k in fields)
        cur = conn.execute(
            f"UPDATE reminders SET {assignments}, updated_at = ? WHERE id = ?",
            (*fields.values(), _now_iso(), reminder_id),
        )
        if cur.rowcount == 0:
            return None
    return get_reminder(reminder_id)


def complete_reminder(reminder_id: str) -> Optional[Dict[str, Any]]:
    """Đánh dấu đã thực hiện. Lời nhắc có chu kỳ lặp sẽ tự sinh lần kế tiếp.

    Trả về lời nhắc vừa đóng, kèm khóa `next_reminder` nếu có lần kế tiếp.
    """
    now = _now_iso()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE reminders SET status = 'done', completed_at = ?, updated_at = ? WHERE id = ?",
            (now, now, reminder_id),
        )
        next_id = None
        interval = row["repeat_interval_days"]
        if interval and int(interval) > 0:
            # Mốc kế tiếp tính từ hôm nay, không từ ngày hẹn cũ: một lời nhắc quá
            # hạn ba tháng không nên đẻ ra ba lời nhắc quá hạn nữa.
            next_due = _today() + timedelta(days=int(interval))
            next_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO reminders
                   (id, patient_id, visit_id, doctor_id, kind, title, note, due_date,
                    repeat_interval_days, status, snoozed_until, completed_at,
                    source, created_by, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL, NULL, ?, ?, ?, ?)""",
                (next_id, row["patient_id"], row["visit_id"], row["doctor_id"], row["kind"],
                 row["title"], row["note"], next_due.isoformat(), int(interval),
                 row["source"] if row["source"] != "visit" else "manual",
                 row["created_by"], now, now),
            )

    result = get_reminder(reminder_id)
    if result and next_id:
        result["next_reminder"] = get_reminder(next_id)
    return result


def snooze_reminder(reminder_id: str, days: int = 1) -> Optional[Dict[str, Any]]:
    """Hoãn lời nhắc thêm `days` ngày kể từ hôm nay."""
    until = (_today() + timedelta(days=max(1, int(days)))).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE reminders SET snoozed_until = ?, status = 'pending', updated_at = ? WHERE id = ?",
            (until, _now_iso(), reminder_id),
        )
        if cur.rowcount == 0:
            return None
    return get_reminder(reminder_id)


def dismiss_reminder(reminder_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE reminders SET status = 'dismissed', updated_at = ? WHERE id = ?",
            (_now_iso(), reminder_id),
        )
        if cur.rowcount == 0:
            return None
    return get_reminder(reminder_id)


def reopen_reminder(reminder_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        cur = conn.execute(
            """UPDATE reminders
               SET status = 'pending', completed_at = NULL, snoozed_until = NULL, updated_at = ?
               WHERE id = ?""",
            (_now_iso(), reminder_id),
        )
        if cur.rowcount == 0:
            return None
    return get_reminder(reminder_id)


def delete_reminder(reminder_id: str) -> bool:
    with _connect() as conn:
        return conn.execute(
            "DELETE FROM reminders WHERE id = ?", (reminder_id,)
        ).rowcount > 0
