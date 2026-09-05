"""Thống kê phòng khám — nguồn dữ liệu cho dashboard.

Mọi truy vấn đều nhận `owner_id`: khi khác None, chỉ tính trên bệnh nhân do bác
sĩ đó phụ trách (bác sĩ thường), khi None thì tính toàn phòng khám (quản trị).
Khoảng thời gian mặc định là 90 ngày gần nhất.

Chuẩn hóa tên bệnh/tên thuốc: dữ liệu do bác sĩ gõ tay nên "Viêm họng cấp" và
"viêm họng cấp " phải gộp làm một. Hàm `_norm_key` bỏ khoảng trắng thừa và so
sánh không phân biệt hoa thường, nhưng nhãn hiển thị vẫn lấy cách viết phổ biến
nhất mà bác sĩ đã dùng.
"""
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from patient_db import _connect, _calc_age

DEFAULT_WINDOW_DAYS = 90

# Nhóm tuổi dùng chung cho biểu đồ nhân khẩu học.
AGE_BUCKETS = [
    (0, 5, "0–5"), (6, 15, "6–15"), (16, 30, "16–30"),
    (31, 45, "31–45"), (46, 60, "46–60"), (61, 200, "Trên 60"),
]


def _norm_key(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    return cleaned.lower() or None


def _resolve_range(date_from: Optional[str], date_to: Optional[str]) -> Tuple[str, str]:
    try:
        end = date.fromisoformat(date_to) if date_to else date.today()
    except ValueError:
        end = date.today()
    try:
        start = date.fromisoformat(date_from) if date_from else end - timedelta(days=DEFAULT_WINDOW_DAYS)
    except ValueError:
        start = end - timedelta(days=DEFAULT_WINDOW_DAYS)
    if start > end:
        start, end = end, start
    return start.isoformat(), end.isoformat()


def _owner_clause(owner_id: Optional[str], alias: str = "p") -> Tuple[str, List[Any]]:
    """Hồ sơ chưa gán chủ vẫn hiện cho mọi bác sĩ, giống list_patients()."""
    if not owner_id:
        return "", []
    return f" AND ({alias}.owner_doctor_id = ? OR {alias}.owner_doctor_id IS NULL)", [owner_id]


def _ranked(counter: Counter, labels: Dict[str, str], limit: int) -> List[Dict[str, Any]]:
    total = sum(counter.values())
    return [
        {
            "label": labels.get(key, key),
            "count": count,
            "percent": round(count * 100 / total, 1) if total else 0.0,
        }
        for key, count in counter.most_common(limit)
    ]


# --- Tổng quan ------------------------------------------------------------

def overview(owner_id: Optional[str] = None, date_from: Optional[str] = None,
             date_to: Optional[str] = None) -> Dict[str, Any]:
    start, end = _resolve_range(date_from, date_to)
    own_sql, own_params = _owner_clause(owner_id)
    span_days = max(1, (date.fromisoformat(end) - date.fromisoformat(start)).days + 1)
    prev_start = (date.fromisoformat(start) - timedelta(days=span_days)).isoformat()

    with _connect() as conn:
        total_patients = conn.execute(
            f"SELECT COUNT(*) AS n FROM patients p WHERE 1=1{own_sql}", own_params
        ).fetchone()["n"]

        new_patients = conn.execute(
            f"""SELECT COUNT(*) AS n FROM patients p
                WHERE DATE(p.created_at) BETWEEN ? AND ?{own_sql}""",
            [start, end, *own_params],
        ).fetchone()["n"]

        prev_new_patients = conn.execute(
            f"""SELECT COUNT(*) AS n FROM patients p
                WHERE DATE(p.created_at) >= ? AND DATE(p.created_at) < ?{own_sql}""",
            [prev_start, start, *own_params],
        ).fetchone()["n"]

        visits = conn.execute(
            f"""SELECT COUNT(*) AS n FROM visits v JOIN patients p ON p.id = v.patient_id
                WHERE DATE(v.visit_date) BETWEEN ? AND ?{own_sql}""",
            [start, end, *own_params],
        ).fetchone()["n"]

        prev_visits = conn.execute(
            f"""SELECT COUNT(*) AS n FROM visits v JOIN patients p ON p.id = v.patient_id
                WHERE DATE(v.visit_date) >= ? AND DATE(v.visit_date) < ?{own_sql}""",
            [prev_start, start, *own_params],
        ).fetchone()["n"]

        # Bệnh nhân tái khám = có từ 2 lần khám trở lên trong kỳ.
        returning = conn.execute(
            f"""SELECT COUNT(*) AS n FROM (
                    SELECT v.patient_id FROM visits v JOIN patients p ON p.id = v.patient_id
                    WHERE DATE(v.visit_date) BETWEEN ? AND ?{own_sql}
                    GROUP BY v.patient_id HAVING COUNT(*) > 1
                )""",
            [start, end, *own_params],
        ).fetchone()["n"]

        active_patients = conn.execute(
            f"""SELECT COUNT(DISTINCT v.patient_id) AS n
                FROM visits v JOIN patients p ON p.id = v.patient_id
                WHERE DATE(v.visit_date) BETWEEN ? AND ?{own_sql}""",
            [start, end, *own_params],
        ).fetchone()["n"]

        notes_written = conn.execute(
            f"""SELECT COUNT(*) AS n FROM clinical_notes n JOIN patients p ON p.id = n.patient_id
                WHERE DATE(n.created_at) BETWEEN ? AND ?{own_sql}""",
            [start, end, *own_params],
        ).fetchone()["n"]

        reminders = conn.execute(
            f"""SELECT r.status, COUNT(*) AS n
                FROM reminders r JOIN patients p ON p.id = r.patient_id
                WHERE 1=1{own_sql} GROUP BY r.status""",
            own_params,
        ).fetchall()
        by_status = {row["status"]: row["n"] for row in reminders}

        overdue = conn.execute(
            f"""SELECT COUNT(*) AS n FROM reminders r JOIN patients p ON p.id = r.patient_id
                WHERE r.status = 'pending'
                  AND COALESCE(r.snoozed_until, r.due_date) < ?{own_sql}""",
            [date.today().isoformat(), *own_params],
        ).fetchone()["n"]

    done = by_status.get("done", 0)
    pending = by_status.get("pending", 0)
    followup_total = done + pending + by_status.get("dismissed", 0)

    def _delta(current: int, previous: int) -> Optional[float]:
        if previous == 0:
            return None  # không có nền so sánh — UI hiển thị "—" thay vì +∞%
        return round((current - previous) * 100 / previous, 1)

    return {
        "range": {"from": start, "to": end, "days": span_days},
        "scope": "mine" if owner_id else "clinic",
        "total_patients": total_patients,
        "new_patients": new_patients,
        "new_patients_delta_pct": _delta(new_patients, prev_new_patients),
        "visits": visits,
        "visits_delta_pct": _delta(visits, prev_visits),
        "active_patients": active_patients,
        "returning_patients": returning,
        "return_rate_pct": round(returning * 100 / active_patients, 1) if active_patients else 0.0,
        "visits_per_patient": round(visits / active_patients, 2) if active_patients else 0.0,
        "clinical_notes": notes_written,
        "followups_pending": pending,
        "followups_overdue": overdue,
        "followup_completion_pct": round(done * 100 / followup_total, 1) if followup_total else 0.0,
    }


# --- Cơ cấu bệnh ----------------------------------------------------------

def top_diagnoses(owner_id: Optional[str] = None, date_from: Optional[str] = None,
                  date_to: Optional[str] = None, limit: int = 12) -> Dict[str, Any]:
    """Số ca theo bệnh — tính trên chẩn đoán chính của từng lần khám."""
    start, end = _resolve_range(date_from, date_to)
    own_sql, own_params = _owner_clause(owner_id)
    with _connect() as conn:
        rows = conn.execute(
            f"""SELECT v.diagnosis_primary, v.diagnosis_secondary, v.patient_id
                FROM visits v JOIN patients p ON p.id = v.patient_id
                WHERE DATE(v.visit_date) BETWEEN ? AND ?{own_sql}""",
            [start, end, *own_params],
        ).fetchall()
        chronic_rows = conn.execute(
            f"SELECT p.chronic_conditions FROM patients p WHERE 1=1{own_sql}", own_params
        ).fetchall()

    primary, secondary = Counter(), Counter()
    labels: Dict[str, str] = {}
    patients_per_dx: Dict[str, set] = defaultdict(set)

    for r in rows:
        key = _norm_key(r["diagnosis_primary"])
        if key:
            primary[key] += 1
            labels.setdefault(key, r["diagnosis_primary"].strip())
            patients_per_dx[key].add(r["patient_id"])
        skey = _norm_key(r["diagnosis_secondary"])
        if skey:
            secondary[skey] += 1
            labels.setdefault(skey, r["diagnosis_secondary"].strip())

    # Bệnh mãn tính khai trong hồ sơ — dùng dấu phẩy/chấm phẩy/xuống dòng làm dấu tách.
    chronic = Counter()
    for r in chronic_rows:
        for piece in re.split(r"[,;\n]", r["chronic_conditions"] or ""):
            key = _norm_key(piece)
            if key:
                chronic[key] += 1
                labels.setdefault(key, piece.strip())

    ranked = _ranked(primary, labels, limit)
    for item in ranked:
        item["patients"] = len(patients_per_dx.get(_norm_key(item["label"]), ()))

    return {
        "range": {"from": start, "to": end},
        "primary": ranked,
        "secondary": _ranked(secondary, labels, limit),
        "chronic": _ranked(chronic, labels, limit),
        "distinct_diagnoses": len(primary),
        "visits_with_diagnosis": sum(primary.values()),
        "visits_total": len(rows),
    }


# --- Kê đơn ---------------------------------------------------------------

def top_medications(owner_id: Optional[str] = None, date_from: Optional[str] = None,
                    date_to: Optional[str] = None, limit: int = 15) -> Dict[str, Any]:
    """Thuốc kê nhiều nhất, đọc từ cột JSON `visits.medications`."""
    start, end = _resolve_range(date_from, date_to)
    own_sql, own_params = _owner_clause(owner_id)
    with _connect() as conn:
        rows = conn.execute(
            f"""SELECT v.medications, v.patient_id, v.diagnosis_primary
                FROM visits v JOIN patients p ON p.id = v.patient_id
                WHERE DATE(v.visit_date) BETWEEN ? AND ?
                  AND v.medications IS NOT NULL AND v.medications != ''{own_sql}""",
            [start, end, *own_params],
        ).fetchall()

    counter, labels = Counter(), {}
    patients_per_drug: Dict[str, set] = defaultdict(set)
    forms = Counter()
    prescriptions = 0
    total_lines = 0

    for r in rows:
        try:
            meds = json.loads(r["medications"]) or []
        except (TypeError, ValueError):
            continue
        if not isinstance(meds, list) or not meds:
            continue
        prescriptions += 1
        for med in meds:
            if not isinstance(med, dict):
                continue
            key = _norm_key(med.get("name"))
            if not key:
                continue
            total_lines += 1
            counter[key] += 1
            labels.setdefault(key, str(med.get("name")).strip())
            patients_per_drug[key].add(r["patient_id"])
            form = _norm_key(med.get("form"))
            if form:
                forms[form] += 1

    ranked = _ranked(counter, labels, limit)
    for item in ranked:
        item["patients"] = len(patients_per_drug.get(_norm_key(item["label"]), ()))

    return {
        "range": {"from": start, "to": end},
        "medications": ranked,
        "forms": _ranked(forms, {k: k.title() for k in forms}, 8),
        "prescriptions": prescriptions,
        "distinct_medications": len(counter),
        "lines_per_prescription": round(total_lines / prescriptions, 2) if prescriptions else 0.0,
    }


# --- Xu hướng theo thời gian ---------------------------------------------

def _bucket_of(day: date, granularity: str) -> Tuple[str, str]:
    """(khóa sắp xếp, nhãn hiển thị) cho một ngày, theo độ chi tiết yêu cầu."""
    if granularity == "month":
        return day.strftime("%Y-%m"), day.strftime("%m/%Y")
    if granularity == "week":
        monday = day - timedelta(days=day.weekday())
        return monday.isoformat(), f"Tuần {monday.strftime('%d/%m')}"
    return day.isoformat(), day.strftime("%d/%m")


def _bucket_series(start: date, end: date, granularity: str) -> List[Tuple[str, str]]:
    """Toàn bộ mốc thời gian trong kỳ, kể cả mốc không có ca nào — biểu đồ
    đường phải có điểm 0 chứ không được nhảy cóc qua ngày vắng bệnh nhân."""
    seen: Dict[str, str] = {}
    cursor = start
    while cursor <= end:
        key, label = _bucket_of(cursor, granularity)
        seen.setdefault(key, label)
        cursor += timedelta(days=1)
    return sorted(seen.items())


def trends(owner_id: Optional[str] = None, date_from: Optional[str] = None,
           date_to: Optional[str] = None, granularity: str = "auto") -> Dict[str, Any]:
    start_s, end_s = _resolve_range(date_from, date_to)
    start, end = date.fromisoformat(start_s), date.fromisoformat(end_s)
    span = (end - start).days + 1
    if granularity not in ("day", "week", "month"):
        granularity = "day" if span <= 45 else ("week" if span <= 240 else "month")

    own_sql, own_params = _owner_clause(owner_id)
    with _connect() as conn:
        visit_rows = conn.execute(
            f"""SELECT v.visit_date, v.patient_id FROM visits v JOIN patients p ON p.id = v.patient_id
                WHERE DATE(v.visit_date) BETWEEN ? AND ?{own_sql}""",
            [start_s, end_s, *own_params],
        ).fetchall()
        patient_rows = conn.execute(
            f"""SELECT p.created_at FROM patients p
                WHERE DATE(p.created_at) BETWEEN ? AND ?{own_sql}""",
            [start_s, end_s, *own_params],
        ).fetchall()

    buckets = _bucket_series(start, end, granularity)
    visits_by_bucket: Counter = Counter()
    patients_by_bucket: Dict[str, set] = defaultdict(set)
    new_by_bucket: Counter = Counter()

    for r in visit_rows:
        day = None
        try:
            day = date.fromisoformat(str(r["visit_date"])[:10])
        except ValueError:
            continue
        key, _ = _bucket_of(day, granularity)
        visits_by_bucket[key] += 1
        patients_by_bucket[key].add(r["patient_id"])

    for r in patient_rows:
        try:
            day = date.fromisoformat(str(r["created_at"])[:10])
        except ValueError:
            continue
        key, _ = _bucket_of(day, granularity)
        new_by_bucket[key] += 1

    series = [
        {
            "key": key,
            "label": label,
            "visits": visits_by_bucket.get(key, 0),
            "patients": len(patients_by_bucket.get(key, ())),
            "new_patients": new_by_bucket.get(key, 0),
        }
        for key, label in buckets
    ]

    # Ngày nào trong tuần đông bệnh nhân nhất — dùng để xếp lịch trực.
    weekday_names = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]
    weekday = Counter()
    for r in visit_rows:
        try:
            weekday[date.fromisoformat(str(r["visit_date"])[:10]).weekday()] += 1
        except ValueError:
            continue

    return {
        "range": {"from": start_s, "to": end_s},
        "granularity": granularity,
        "series": series,
        "peak": max(series, key=lambda s: s["visits"]) if series else None,
        "by_weekday": [
            {"label": weekday_names[i], "count": weekday.get(i, 0)} for i in range(7)
        ],
    }


# --- Nhân khẩu học --------------------------------------------------------

def demographics(owner_id: Optional[str] = None) -> Dict[str, Any]:
    own_sql, own_params = _owner_clause(owner_id)
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT p.dob, p.gender, p.blood_type FROM patients p WHERE 1=1{own_sql}",
            own_params,
        ).fetchall()

    gender, blood, ages = Counter(), Counter(), Counter()
    known_ages: List[int] = []
    for r in rows:
        gender[(r["gender"] or "Không rõ").strip() or "Không rõ"] += 1
        blood[(r["blood_type"] or "Không rõ").strip() or "Không rõ"] += 1
        age = _calc_age(r["dob"])
        if age is None:
            ages["Không rõ"] += 1
            continue
        known_ages.append(age)
        for low, high, label in AGE_BUCKETS:
            if low <= age <= high:
                ages[label] += 1
                break

    bucket_order = [label for _, _, label in AGE_BUCKETS] + ["Không rõ"]
    return {
        "total": len(rows),
        "gender": [{"label": k, "count": v} for k, v in gender.most_common()],
        "blood_type": [{"label": k, "count": v} for k, v in blood.most_common()],
        "age_groups": [
            {"label": label, "count": ages.get(label, 0)}
            for label in bucket_order if ages.get(label, 0) or label != "Không rõ"
        ],
        "average_age": round(sum(known_ages) / len(known_ages), 1) if known_ages else None,
    }


# --- Theo bác sĩ (chỉ quản trị) ------------------------------------------

def by_doctor(date_from: Optional[str] = None, date_to: Optional[str] = None) -> Dict[str, Any]:
    """Khối lượng công việc từng bác sĩ trong phòng khám."""
    import auth_db  # nhập tại chỗ: stats_db là lớp dữ liệu, không phụ thuộc auth khi khởi động

    start, end = _resolve_range(date_from, date_to)
    users = {u["id"]: u for u in auth_db.list_users()}

    with _connect() as conn:
        patient_rows = conn.execute("SELECT owner_doctor_id, COUNT(*) AS n FROM patients GROUP BY owner_doctor_id").fetchall()
        visit_rows = conn.execute(
            """SELECT p.owner_doctor_id AS owner, COUNT(*) AS n
               FROM visits v JOIN patients p ON p.id = v.patient_id
               WHERE DATE(v.visit_date) BETWEEN ? AND ?
               GROUP BY p.owner_doctor_id""",
            (start, end),
        ).fetchall()
        overdue_rows = conn.execute(
            """SELECT p.owner_doctor_id AS owner, COUNT(*) AS n
               FROM reminders r JOIN patients p ON p.id = r.patient_id
               WHERE r.status = 'pending' AND COALESCE(r.snoozed_until, r.due_date) < ?
               GROUP BY p.owner_doctor_id""",
            (date.today().isoformat(),),
        ).fetchall()

    patients_by = {r["owner_doctor_id"]: r["n"] for r in patient_rows}
    visits_by = {r["owner"]: r["n"] for r in visit_rows}
    overdue_by = {r["owner"]: r["n"] for r in overdue_rows}

    result = []
    for owner_id in set(patients_by) | set(visits_by) | set(overdue_by):
        user = users.get(owner_id)
        result.append({
            "doctor_id": owner_id,
            "doctor_name": user["display_name"] if user else "Chưa phân công",
            "role_label": user["role_label"] if user else "—",
            "patients": patients_by.get(owner_id, 0),
            "visits": visits_by.get(owner_id, 0),
            "overdue_followups": overdue_by.get(owner_id, 0),
        })
    result.sort(key=lambda r: (-r["visits"], -r["patients"]))
    return {"range": {"from": start, "to": end}, "doctors": result}
