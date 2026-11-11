"""Deterministic drug reference catalog backed by existing books and admin imports."""
import csv
import hashlib
import io
import json
import re
import sqlite3
import unicodedata
from contextlib import closing
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

import config
import documents
from drug_alias import SYNONYMS_PATH
from drug_name import is_suspect_name
from text_fold import fold

MAX_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 5000
DB_PATH = Path(config.DATA_DIR) / "drug_catalog.db"
VERIFIED_DIR = Path(config.DATA_DIR) / "verified_monographs"

CSV_SECTIONS = {
    "dosage_form": "Dạng thuốc và hàm lượng",
    "indications": "Chỉ định",
    "dosage": "Liều lượng và cách dùng",
    "contraindications": "Chống chỉ định",
    "warnings": "Thận trọng",
    "adverse_effects": "Tác dụng không mong muốn",
    "interactions": "Tương tác thuốc",
    "pregnancy": "Thời kỳ mang thai",
    "lactation": "Thời kỳ cho con bú",
    "storage": "Bảo quản",
}
COMMON_FIELDS = {"id", "name", "aliases", "drug_class", "atc_code", "source_title", "source_url", "source_page"}


def _string(value, field, limit, *, required=False, verbatim=False):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f"{field} phải là văn bản tối đa {limit} ký tự.")
    if required and not value.strip():
        raise ValueError(f"Thiếu {field}.")
    if any(unicodedata.category(char) in {"Cc", "Cs"} and char not in "\n\r\t" for char in value):
        raise ValueError(f"{field} chứa ký tự điều khiển.")
    return value if verbatim else value.strip()


def _record(row):
    if not isinstance(row, dict) or row.keys() - (COMMON_FIELDS | {"sections"}):
        raise ValueError("Có trường không thuộc mẫu dữ liệu.")
    key = _string(row.get("id", ""), "id", 80, required=True)
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", key):
        raise ValueError("id chỉ gồm chữ thường không dấu, số, dấu gạch ngang hoặc gạch dưới.")
    name = _string(row.get("name", ""), "name", 200, required=True)
    if not fold(name):
        raise ValueError("Tên thuốc phải có ký tự tìm kiếm.")
    title = _string(row.get("source_title", ""), "source_title", 300, required=True)
    url = _string(row.get("source_url", ""), "source_url", 2000)
    if url:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("source_url phải là địa chỉ HTTP hoặc HTTPS hợp lệ.")
    aliases = row.get("aliases", [])
    if not isinstance(aliases, list) or len(aliases) > 50:
        raise ValueError("aliases phải là danh sách tối đa 50 tên.")
    aliases = [_string(item, "aliases", 200, required=True) for item in aliases]
    sections = row.get("sections")
    if not isinstance(sections, list) or not 1 <= len(sections) <= 50:
        raise ValueError("Cần từ 1 đến 50 mục nội dung.")
    clean_sections = []
    for section in sections:
        if not isinstance(section, dict) or section.keys() - {"label", "text"}:
            raise ValueError("Mỗi mục nội dung cần label và text.")
        clean_sections.append({
            "label": _string(section.get("label", ""), "label", 150, required=True),
            "text": _string(section.get("text", ""), "text", 50_000, required=True, verbatim=True),
        })
    return {
        "id": f"import-{key}", "name": name, "aliases": list(dict.fromkeys(aliases)),
        "drug_class": _string(row.get("drug_class", ""), "drug_class", 300),
        "atc_code": _string(row.get("atc_code", ""), "atc_code", 100),
        "source_title": title, "source_url": url,
        "source_page": _string(row.get("source_page", ""), "source_page", 100),
        "sections": clean_sections,
    }


def _csv_rows(data):
    reader = csv.DictReader(io.StringIO(data, newline=""), strict=True)
    fields = reader.fieldnames or []
    if (len(set(fields)) != len(fields)
            or not {"id", "name", "source_title"}.issubset(fields)
            or set(fields) - COMMON_FIELDS - CSV_SECTIONS.keys()):
        raise ValueError("Tiêu đề CSV không khớp mẫu. Kiểm tra tên cột và cột trùng.")
    for row in reader:
        if None in row or None in row.values():
            raise ValueError(f"Dòng {reader.line_num}: số ô khác số cột trong tiêu đề.")
        item = {key: row[key] for key in COMMON_FIELDS if key in row}
        item["aliases"] = [alias.strip() for alias in item.get("aliases", "").split("|") if alias.strip()]
        item["sections"] = [
            {"label": label, "text": row[key]}
            for key, label in CSV_SECTIONS.items() if row.get(key, "").strip()
        ]
        yield reader.line_num, item


def _unique_object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("JSON có trường bị lặp.")
    return result


def parse_upload(content, file_format):
    try:
        data = content.decode("utf-8-sig")
        if file_format == "csv":
            rows = _csv_rows(data)
        elif file_format == "json":
            decoded = json.loads(data, object_pairs_hook=_unique_object)
            if not isinstance(decoded, list):
                raise ValueError("JSON phải chứa một mảng bản ghi thuốc.")
            rows = enumerate(decoded, 1)
        else:
            raise ValueError("Chỉ hỗ trợ CSV và JSON.")
        records = []
        seen = set()
        for position, row in rows:
            try:
                if len(records) >= MAX_RECORDS:
                    raise ValueError(f"Mỗi tệp tối đa {MAX_RECORDS} bản ghi.")
                record = _record(row)
                if record["id"] in seen:
                    raise ValueError("id trùng trong tệp.")
            except ValueError as exc:
                raise ValueError(f"Bản ghi {position}: {exc}") from exc
            seen.add(record["id"])
            records.append(record)
        if not records:
            raise ValueError("Tệp không có bản ghi thuốc.")
        return records
    except UnicodeDecodeError as exc:
        raise ValueError("Lưu tệp dưới dạng UTF-8 rồi thử lại.") from exc
    except (json.JSONDecodeError, csv.Error, RecursionError) as exc:
        raise ValueError("Không đọc được cấu trúc tệp. Kiểm tra theo mẫu tải xuống.") from exc


def _db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS drugs (
            id TEXT PRIMARY KEY, summary TEXT NOT NULL, record TEXT NOT NULL
        )""")
    except Exception:
        conn.close()
        raise
    return conn


def _summary(record):
    summary = {key: record[key] for key in ("id", "name", "aliases", "drug_class", "source_title")}
    if record.get("intl_name"):
        summary["intl_name"] = record["intl_name"]
    return summary


def publish(records):
    with closing(_db()) as conn, conn:
        conn.executemany(
            """INSERT INTO drugs (id, summary, record) VALUES (?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET summary=excluded.summary, record=excluded.record""",
            [(record["id"], json.dumps(_summary(record), ensure_ascii=False),
              json.dumps(record, ensure_ascii=False)) for record in records],
        )


@lru_cache(maxsize=1)
def _approved_aliases():
    with open(SYNONYMS_PATH, encoding="utf-8") as file:
        return [item for item in json.load(file)["pairs"] if item.get("approved")]


def _book_id(doc_name, name):
    identity = unicodedata.normalize("NFC", name).casefold()
    return "book-" + hashlib.sha256(f"{doc_name}\0{identity}".encode()).hexdigest()[:24]


@lru_cache(maxsize=4)
def _verified_records(path, revision):
    with path.open(encoding="utf-8") as file:
        return json.load(file)


@lru_cache(maxsize=4)
def _book_records(doc_name, source_title, revision):
    with open(documents.chunks_path(doc_name), encoding="utf-8") as file:
        chunks = json.load(file)
    records = {}
    names = {}
    suspect = {}
    # The parser resets section counters for each monograph. Keep its source order.
    for chunk in chunks:
        name = (chunk.get("generic_name") or "").strip()
        content = chunk.get("content")
        if not name or name == "UNKNOWN_DRUG" or not content:
            continue
        if name not in suspect:
            suspect[name] = is_suspect_name(name)
        flagged, _ = suspect[name]
        if chunk.get("name_suspect") or flagged:
            continue
        key = _book_id(doc_name, name)
        record = records.get(key)
        if record is None:
            record = records[key] = {
                "id": key, "name": name, "aliases": [],
                "drug_class": chunk.get("drug_class") or "", "source_title": source_title,
                "atc_code": chunk.get("atc_code") or "",
                "ocr": True, "doc_name": doc_name, "sections": [],
            }
            names.setdefault(fold(name), []).append(record)
        label = chunk.get("field_name") or "Nội dung"
        page = chunk.get("page_in_file")
        pdf_page = chunk.get("pdf_page")
        sections = record["sections"]
        if not sections or (sections[-1]["label"], sections[-1]["pdf_page"]) != (label, pdf_page):
            sections.append({"label": label, "page": page, "pdf_page": pdf_page, "text": content})
        else:
            sections[-1]["text"] += "\n\n" + content
        for text in [*(chunk.get("synonyms") or []), chunk.get("intl_name") or ""]:
            record["aliases"].extend(alias.strip() for alias in re.split(r"[,;]", text) if alias.strip())

    for item in _approved_aliases():
        matches = names.get(fold(item["canonical"]), [])
        if len(matches) == 1:
            matches[0]["aliases"].append(item["alias"])
    for record in records.values():
        aliases = {}
        for alias in record["aliases"]:
            aliases.setdefault(fold(alias), alias)
        aliases.pop(fold(record["name"]), None)
        record["aliases"] = list(aliases.values())
    return records


def _books():
    for manifest in documents.list_manifests():
        if not documents.is_drug_reference(manifest):
            continue
        doc_name = manifest["doc_name"]
        title = manifest.get("doc_title") or doc_name
        chunks_path = Path(documents.chunks_path(doc_name))
        try:
            # Overlay a copy so updates to manual data never mutate the OCR cache.
            records = _book_records(doc_name, title, chunks_path.stat().st_mtime_ns).copy()
        except FileNotFoundError:
            records = {}
        path = VERIFIED_DIR / f"{documents.safe_doc_name(doc_name)}.json"
        try:
            verified = _verified_records(path, path.stat().st_mtime_ns)
        except FileNotFoundError:
            verified = []
        for entry in verified:
            key = _book_id(doc_name, entry["name"])
            records[key] = {
                **entry,
                "id": key, "aliases": entry.get("aliases", []),
                "source_title": title, "doc_name": doc_name,
                "ocr": False, "transcribed": True,
            }
        yield records


def list_drugs():
    with closing(_db()) as conn:
        summaries = [json.loads(row[0]) for row in conn.execute("SELECT summary FROM drugs")]
    for book in _books():
        summaries.extend(_summary(record) for record in book.values())
    return summaries


def get_drug(drug_id):
    if drug_id.startswith("book-"):
        for book in _books():
            if drug_id in book:
                return book[drug_id]
        return None
    with closing(_db()) as conn:
        row = conn.execute("SELECT record FROM drugs WHERE id = ?", (drug_id,)).fetchone()
    return json.loads(row[0]) if row else None
