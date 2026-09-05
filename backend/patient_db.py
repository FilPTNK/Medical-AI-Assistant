"""SQLite-backed storage for patient medical records (hồ sơ bệnh nhân).

Replaces the old flat patients.json store with a real relational database:
patients, plus their visit history (each visit doubles as a treatment plan
record), vital-sign readings and attached files.
"""
import os
import json
import sqlite3
import uuid
import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import config

# Visit columns whose values are JSON-encoded lists (medications, goals, differential_diagnoses)
VISIT_JSON_FIELDS = {"medications", "goals", "differential_diagnoses"}

# Visit columns that add_visit/update_visit are allowed to write
VISIT_EDITABLE_FIELDS = {
    "visit_date", "title", "symptoms", "diagnosis_primary", "diagnosis_secondary",
    "diagnosis_confidence", "diagnosis_note", "differential_diagnoses",
    "exam_findings", "treatment", "subclinical_orders", "doctor_name", "doctor_notes",
    "medications", "goals", "protocol_duration", "treatment_method", "diet_regimen",
    "precautions", "no_drug_recommendations",
    "care_instructions", "followup_date", "followup_purpose", "status",
}

DB_PATH = os.path.join(config.DATA_DIR, "patients.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS patients (
                id TEXT PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                dob TEXT,
                gender TEXT,
                phone TEXT,
                email TEXT,
                address TEXT,
                occupation TEXT,
                blood_type TEXT,
                height_cm REAL,
                weight_kg REAL,
                allergies TEXT,
                chronic_conditions TEXT,
                surgical_history TEXT,
                family_history TEXT,
                quick_note TEXT,
                quick_note_updated_by TEXT,
                quick_note_updated_at TEXT,
                owner_doctor_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS visits (
                id TEXT PRIMARY KEY,
                patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                visit_date TEXT NOT NULL,
                title TEXT,
                symptoms TEXT,
                diagnosis_primary TEXT,
                diagnosis_secondary TEXT,
                diagnosis_confidence INTEGER,
                diagnosis_note TEXT,
                differential_diagnoses TEXT,
                exam_findings TEXT,
                treatment TEXT,
                subclinical_orders TEXT,
                doctor_name TEXT,
                doctor_notes TEXT,
                medications TEXT,
                goals TEXT,
                protocol_duration TEXT,
                treatment_method TEXT,
                diet_regimen TEXT,
                precautions TEXT,
                no_drug_recommendations TEXT,
                care_instructions TEXT,
                followup_date TEXT,
                followup_purpose TEXT,
                status TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS vitals (
                id TEXT PRIMARY KEY,
                patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                vital_type TEXT NOT NULL,
                value TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS attachments (
                id TEXT PRIMARY KEY,
                patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                original_name TEXT NOT NULL,
                file_type TEXT,
                size_bytes INTEGER,
                uploaded_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS clinical_notes (
                id TEXT PRIMARY KEY,
                patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                visit_date TEXT,
                doctor_name TEXT,
                title TEXT,
                reason_for_visit TEXT,
                vital_pulse TEXT,
                vital_blood_pressure TEXT,
                vital_resp_rate TEXT,
                vital_temperature TEXT,
                general_exam TEXT,
                cardio_exam TEXT,
                resp_exam TEXT,
                abdomen_exam TEXT,
                other_exam TEXT,
                ent_ear TEXT,
                ent_nose TEXT,
                ent_throat TEXT,
                ent_other TEXT,
                ent_scope_nose TEXT,
                ent_scope_ear TEXT,
                ent_scope_throat TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_visits_patient ON visits(patient_id);
            CREATE INDEX IF NOT EXISTS idx_vitals_patient ON vitals(patient_id);
            CREATE INDEX IF NOT EXISTS idx_attachments_patient ON attachments(patient_id);
            CREATE INDEX IF NOT EXISTS idx_clinical_notes_patient ON clinical_notes(patient_id);
            """
        )
        _migrate_visits_columns(conn)
        _migrate_patient_columns(conn)
        _init_reminders(conn)


def _migrate_visits_columns(conn: sqlite3.Connection):
    """Adds treatment-plan columns to a pre-existing visits table (older DBs)."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(visits)").fetchall()}
    new_columns = [
        "exam_findings", "medications", "goals", "protocol_duration",
        "no_drug_recommendations", "care_instructions", "followup_date",
        "followup_purpose", "status", "subclinical_orders",
        "diagnosis_confidence", "diagnosis_note", "differential_diagnoses",
        "treatment_method", "diet_regimen", "precautions",
    ]
    for col in new_columns:
        if col not in existing:
            col_type = "INTEGER" if col == "diagnosis_confidence" else "TEXT"
            conn.execute(f"ALTER TABLE visits ADD COLUMN {col} {col_type}")


def _migrate_patient_columns(conn: sqlite3.Connection):
    """Gắn cột bác sĩ phụ trách vào bảng patients của các DB tạo trước khi có phân quyền."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(patients)").fetchall()}
    if "owner_doctor_id" not in existing:
        conn.execute("ALTER TABLE patients ADD COLUMN owner_doctor_id TEXT")
    # Chỉ mục phải tạo sau ALTER: trên DB cũ, bảng patients đã tồn tại từ trước khi
    # có cột này nên đặt chung với CREATE TABLE sẽ hỏng ngay lúc khởi động.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_patients_owner ON patients(owner_doctor_id)")


def _init_reminders(conn: sqlite3.Connection):
    """Bảng nhắc lịch — xem reminder_db.py để biết ý nghĩa từng cột."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id TEXT PRIMARY KEY,
            patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
            visit_id TEXT,
            doctor_id TEXT,
            kind TEXT NOT NULL DEFAULT 'custom',
            title TEXT,
            note TEXT,
            due_date TEXT NOT NULL,
            repeat_interval_days INTEGER,
            status TEXT NOT NULL DEFAULT 'pending',
            snoozed_until TEXT,
            completed_at TEXT,
            source TEXT NOT NULL DEFAULT 'manual',
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_reminders_patient ON reminders(patient_id);
        CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(due_date, status);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_reminders_visit_source
            ON reminders(visit_id, source) WHERE visit_id IS NOT NULL;
        """
    )


def _next_patient_code(conn: sqlite3.Connection) -> str:
    today = date.today().strftime("%Y%m%d")
    prefix = f"BN{today}-"
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM patients WHERE code LIKE ?", (f"{prefix}%",)
    ).fetchone()
    seq = (row["n"] if row else 0) + 1
    return f"{prefix}{seq:05d}"


def preview_next_code() -> str:
    with _connect() as conn:
        return _next_patient_code(conn)


def _calc_age(dob: Optional[str]) -> Optional[int]:
    if not dob:
        return None
    try:
        d = datetime.strptime(dob, "%Y-%m-%d").date()
        today = date.today()
        return today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    except ValueError:
        return None


def _row_to_patient_summary(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    d["age"] = _calc_age(d.get("dob"))
    return d


def _visit_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    for field in VISIT_JSON_FIELDS:
        raw = d.get(field)
        if raw:
            try:
                d[field] = json.loads(raw)
            except (TypeError, ValueError):
                d[field] = []
        else:
            d[field] = []
    return d


def list_patients(search: Optional[str] = None,
                  owner_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Danh sách bệnh nhân. `owner_id` khác None thì chỉ trả về bệnh nhân do bác sĩ
    đó phụ trách (kèm các hồ sơ cũ chưa gán ai, để không bị mất sau khi nâng cấp)."""
    clauses: List[str] = []
    params: List[Any] = []
    if search:
        like = f"%{search.strip()}%"
        clauses.append("(name LIKE ? OR code LIKE ? OR phone LIKE ?)")
        params += [like, like, like]
    if owner_id:
        clauses.append("(owner_doctor_id = ? OR owner_doctor_id IS NULL)")
        params.append(owner_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM patients {where} ORDER BY created_at DESC", params
        ).fetchall()
        return [_row_to_patient_summary(r) for r in rows]


def get_patient_owner(patient_id: str) -> Optional[str]:
    """id bác sĩ phụ trách; None nghĩa là hồ sơ chưa gán ai (ai cũng nhận được)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT owner_doctor_id FROM patients WHERE id = ?", (patient_id,)
        ).fetchone()
    return row["owner_doctor_id"] if row else None


def patient_exists(patient_id: str) -> bool:
    with _connect() as conn:
        return conn.execute(
            "SELECT 1 FROM patients WHERE id = ?", (patient_id,)
        ).fetchone() is not None


def set_patient_owner(patient_id: str, owner_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Chuyển bệnh nhân sang bác sĩ khác (bàn giao ca)."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE patients SET owner_doctor_id = ?, updated_at = ? WHERE id = ?",
            (owner_id, datetime.now().isoformat(), patient_id),
        )
        if cur.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
        return _row_to_patient_summary(row)


def claim_unassigned_patients(owner_id: str) -> int:
    """Gán mọi hồ sơ chưa có chủ cho một bác sĩ — dùng khi nâng cấp DB cũ."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE patients SET owner_doctor_id = ? WHERE owner_doctor_id IS NULL",
            (owner_id,),
        )
        return cur.rowcount


def get_upcoming_followups(days_ahead: int = 7) -> List[Dict[str, Any]]:
    """Lịch tái khám quá hạn hoặc sắp tới trong `days_ahead` ngày, bỏ qua các ca
    đã có lần khám mới sau ngày hẹn (coi như bệnh nhân đã quay lại)."""
    today = date.today()
    horizon = date.fromordinal(today.toordinal() + days_ahead)
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT v.id AS visit_id, v.patient_id, v.followup_date, v.followup_purpose,
                   p.name AS patient_name, p.code AS patient_code
            FROM visits v
            JOIN patients p ON p.id = v.patient_id
            WHERE v.followup_date IS NOT NULL AND TRIM(v.followup_date) != ''
              AND v.followup_date <= ?
              AND NOT EXISTS (
                  SELECT 1 FROM visits v2
                  WHERE v2.patient_id = v.patient_id
                    AND v2.id != v.id
                    AND v2.visit_date >= v.followup_date
              )
            ORDER BY v.followup_date ASC
            """,
            (horizon.isoformat(),),
        ).fetchall()

        result = []
        for r in rows:
            try:
                fd_date = date.fromisoformat(r["followup_date"][:10])
            except ValueError:
                continue
            days_diff = (fd_date - today).days
            result.append({
                "visit_id": r["visit_id"],
                "patient_id": r["patient_id"],
                "patient_name": r["patient_name"],
                "patient_code": r["patient_code"],
                "followup_date": r["followup_date"],
                "followup_purpose": r["followup_purpose"],
                "days_diff": days_diff,
                "overdue": days_diff < 0,
            })
        return result


def create_patient(data: Dict[str, Any]) -> Dict[str, Any]:
    with _connect() as conn:
        patient_id = str(uuid.uuid4())
        code = _next_patient_code(conn)
        now = datetime.now().isoformat()
        initial_note = (data.get("notes") or "").strip()
        conn.execute(
            """
            INSERT INTO patients (
                id, code, name, dob, gender, phone, email, address, occupation,
                blood_type, height_cm, weight_kg, allergies, chronic_conditions,
                surgical_history, family_history, quick_note, quick_note_updated_by,
                quick_note_updated_at, owner_doctor_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                patient_id, code, data["name"], data.get("dob"), data.get("gender"),
                data.get("phone"), data.get("email"), data.get("address"), data.get("occupation"),
                data.get("blood_type"), data.get("height_cm"), data.get("weight_kg"),
                data.get("allergies"), data.get("chronic_conditions"), data.get("surgical_history"),
                data.get("family_history"), initial_note or None,
                (data.get("created_by") if initial_note else None),
                (now if initial_note else None),
                data.get("owner_doctor_id"),
                now, now,
            ),
        )
        row = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
        return _row_to_patient_summary(row)


def get_patient(patient_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
        if not row:
            return None
        patient = _row_to_patient_summary(row)

        visits = conn.execute(
            "SELECT * FROM visits WHERE patient_id = ? ORDER BY visit_date DESC, created_at DESC",
            (patient_id,),
        ).fetchall()
        patient["visits"] = [_visit_row_to_dict(v) for v in visits]

        vitals = conn.execute(
            "SELECT * FROM vitals WHERE patient_id = ? ORDER BY recorded_at DESC",
            (patient_id,),
        ).fetchall()
        latest_by_type: Dict[str, Dict[str, Any]] = {}
        for v in vitals:
            vd = dict(v)
            if vd["vital_type"] not in latest_by_type:
                latest_by_type[vd["vital_type"]] = vd
        patient["vitals"] = list(latest_by_type.values())

        attachments = conn.execute(
            "SELECT * FROM attachments WHERE patient_id = ? ORDER BY uploaded_at DESC",
            (patient_id,),
        ).fetchall()
        patient["attachments"] = [dict(a) for a in attachments]

        notes = conn.execute(
            "SELECT * FROM clinical_notes WHERE patient_id = ? ORDER BY visit_date DESC, created_at DESC",
            (patient_id,),
        ).fetchall()
        patient["notes"] = [_note_row_to_dict(n) for n in notes]

        return patient


def delete_patient(patient_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
        return cur.rowcount > 0


def update_quick_note(patient_id: str, note: str, updated_by: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        now = datetime.now().isoformat()
        cur = conn.execute(
            "UPDATE patients SET quick_note = ?, quick_note_updated_by = ?, quick_note_updated_at = ?, updated_at = ? WHERE id = ?",
            (note, updated_by, now, now, patient_id),
        )
        if cur.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
        return _row_to_patient_summary(row)


def _encode_visit_value(field: str, value: Any) -> Any:
    if field in VISIT_JSON_FIELDS:
        return json.dumps(value if value is not None else [])
    return value


def add_visit(patient_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    with _connect() as conn:
        visit_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        conn.execute(
            """
            INSERT INTO visits (
                id, patient_id, visit_date, title, symptoms, diagnosis_primary,
                diagnosis_secondary, diagnosis_confidence, diagnosis_note, differential_diagnoses,
                exam_findings, treatment, subclinical_orders,
                doctor_name, doctor_notes,
                medications, goals, protocol_duration, treatment_method, diet_regimen, precautions,
                no_drug_recommendations,
                care_instructions, followup_date, followup_purpose, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                visit_id, patient_id, data.get("visit_date") or date.today().isoformat(),
                data.get("title"), data.get("symptoms"), data.get("diagnosis_primary"),
                data.get("diagnosis_secondary"), data.get("diagnosis_confidence"), data.get("diagnosis_note"),
                _encode_visit_value("differential_diagnoses", data.get("differential_diagnoses")),
                data.get("exam_findings"), data.get("treatment"),
                data.get("subclinical_orders"),
                data.get("doctor_name"), data.get("doctor_notes"),
                _encode_visit_value("medications", data.get("medications")),
                _encode_visit_value("goals", data.get("goals")),
                data.get("protocol_duration"), data.get("treatment_method"),
                data.get("diet_regimen"), data.get("precautions"),
                data.get("no_drug_recommendations"),
                data.get("care_instructions"), data.get("followup_date"),
                data.get("followup_purpose"), data.get("status") or "in_progress",
                now,
            ),
        )
        row = conn.execute("SELECT * FROM visits WHERE id = ?", (visit_id,)).fetchone()
        return _visit_row_to_dict(row)


def get_visit(patient_id: str, visit_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM visits WHERE id = ? AND patient_id = ?", (visit_id, patient_id)
        ).fetchone()
        return _visit_row_to_dict(row) if row else None


def update_visit(patient_id: str, visit_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    fields = {k: v for k, v in data.items() if k in VISIT_EDITABLE_FIELDS}
    if not fields:
        return get_visit(patient_id, visit_id)
    with _connect() as conn:
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = [_encode_visit_value(k, v) for k, v in fields.items()]
        cur = conn.execute(
            f"UPDATE visits SET {set_clause} WHERE id = ? AND patient_id = ?",
            (*values, visit_id, patient_id),
        )
        if cur.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM visits WHERE id = ?", (visit_id,)).fetchone()
        return _visit_row_to_dict(row)


def delete_visit(patient_id: str, visit_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM visits WHERE id = ? AND patient_id = ?", (visit_id, patient_id)
        )
        return cur.rowcount > 0


def add_vital(patient_id: str, vital_type: str, value: str) -> Dict[str, Any]:
    with _connect() as conn:
        vital_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO vitals (id, patient_id, vital_type, value, recorded_at) VALUES (?, ?, ?, ?, ?)",
            (vital_id, patient_id, vital_type, value, now),
        )
        row = conn.execute("SELECT * FROM vitals WHERE id = ?", (vital_id,)).fetchone()
        return dict(row)


def add_attachment(patient_id: str, filename: str, original_name: str, file_type: str, size_bytes: int) -> Dict[str, Any]:
    with _connect() as conn:
        att_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        conn.execute(
            """
            INSERT INTO attachments (id, patient_id, filename, original_name, file_type, size_bytes, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (att_id, patient_id, filename, original_name, file_type, size_bytes, now),
        )
        row = conn.execute("SELECT * FROM attachments WHERE id = ?", (att_id,)).fetchone()
        return dict(row)


# --- Clinical notes (Ghi chú thăm khám lâm sàng) ---

NOTE_EDITABLE_FIELDS = {
    "visit_date", "doctor_name", "title", "reason_for_visit",
    "vital_pulse", "vital_blood_pressure", "vital_resp_rate", "vital_temperature",
    "general_exam", "cardio_exam", "resp_exam", "abdomen_exam", "other_exam",
    "ent_ear", "ent_nose", "ent_throat", "ent_other",
    "ent_scope_nose", "ent_scope_ear", "ent_scope_throat",
    "status",
}

# Maps the nested `vitals` object exposed to the frontend to its flat DB columns
NOTE_VITAL_FIELDS = {
    "pulse": "vital_pulse",
    "blood_pressure": "vital_blood_pressure",
    "resp_rate": "vital_resp_rate",
    "temperature": "vital_temperature",
}


def _note_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    d["vitals"] = {key: d.pop(col, None) or "" for key, col in NOTE_VITAL_FIELDS.items()}
    return d


def add_note(patient_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    with _connect() as conn:
        note_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        fields = {k: v for k, v in data.items() if k in NOTE_EDITABLE_FIELDS}
        fields.setdefault("status", "draft")
        columns = ["id", "patient_id", "created_at", "updated_at", *fields.keys()]
        placeholders = ", ".join("?" for _ in columns)
        values = [note_id, patient_id, now, now, *fields.values()]
        conn.execute(
            f"INSERT INTO clinical_notes ({', '.join(columns)}) VALUES ({placeholders})",
            values,
        )
        row = conn.execute("SELECT * FROM clinical_notes WHERE id = ?", (note_id,)).fetchone()
        return _note_row_to_dict(row)


def get_note(patient_id: str, note_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM clinical_notes WHERE id = ? AND patient_id = ?", (note_id, patient_id)
        ).fetchone()
        return _note_row_to_dict(row) if row else None


def update_note(patient_id: str, note_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    fields = {k: v for k, v in data.items() if k in NOTE_EDITABLE_FIELDS}
    if not fields:
        return get_note(patient_id, note_id)
    with _connect() as conn:
        fields["updated_at"] = datetime.now().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        cur = conn.execute(
            f"UPDATE clinical_notes SET {set_clause} WHERE id = ? AND patient_id = ?",
            (*fields.values(), note_id, patient_id),
        )
        if cur.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM clinical_notes WHERE id = ?", (note_id,)).fetchone()
        return _note_row_to_dict(row)


def delete_note(patient_id: str, note_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM clinical_notes WHERE id = ? AND patient_id = ?", (note_id, patient_id)
        )
        return cur.rowcount > 0


def get_attachment(attachment_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,)).fetchone()
        return dict(row) if row else None


def delete_attachment(attachment_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,)).fetchone()
        if not row:
            return None
        conn.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
        return dict(row)
