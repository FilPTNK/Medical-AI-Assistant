"""
Parser cho cấu trúc chuyên luận Dược thư Quốc gia Việt Nam.

Chạy song song với drug_parser.py chứ không thay thế: hai cuốn sách có cấu trúc
khác hẳn nhau. Thuốc Biệt Dược dùng nhãn viết tắt (TD:, CĐ:, CCĐ:); Dược thư
dùng tiêu đề mục viết đầy đủ, đứng riêng một dòng và KHÔNG có dấu hai chấm.

Ba neo cấu trúc, quan sát trực tiếp trên text OCR:

    Cập nhật lần cuối: 2020.          <- kết thúc chuyên luận trước
    DIHYDROERGOTAMIN                  <- tên thuốc, chữ hoa, đứng riêng dòng
    Tên chung quốc tế: ...            <- trường nội dòng, CÓ dấu hai chấm
    Mã ATC: N02CA01.
    Dạng thuốc và hàm lượng           <- tiêu đề mục khối, KHÔNG dấu hai chấm
    ...nội dung...

Neo mở chuyên luận là dòng "Tên chung quốc tế", không phải tỉ lệ chữ hoa của
dòng tên thuốc. Trên cuốn Thuốc Biệt Dược, heuristic "dòng ≥70% chữ hoa" trượt
17,9% số khối (3 341/18 717 chunk mang generic_name UNKNOWN_DRUG) vì OCR trả
chữ hoa lẫn lộn. "Tên chung quốc tế" là chuỗi cố định nên bền hơn hẳn.
"""

import os
import re
import sys
import json
import difflib
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from drug_name import normalize_drug_name

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import documents

# --- Tiêu đề mục khối: tiêu đề -> (field_type, mã ngắn dùng trong chunk_id) ---
BLOCK_SECTIONS: Dict[str, Tuple[str, str]] = {
    "Dạng thuốc và hàm lượng": ("DOSAGE_FORM", "DT"),
    "Dược lực học": ("PHARMACODYNAMICS", "DLH"),
    "Dược động học": ("PHARMACOKINETICS", "DDH"),
    "Chỉ định": ("INDICATIONS", "CD"),
    "Chống chỉ định": ("CONTRAINDICATION", "CCD"),
    "Thận trọng": ("WARNINGS", "TT"),
    "Thời kỳ mang thai": ("PREGNANCY", "TKMT"),
    "Thời kỳ cho con bú": ("LACTATION", "TKCB"),
    "Tác dụng không mong muốn (ADR)": ("ADR", "ADR"),
    "Hướng dẫn cách xử trí ADR": ("ADR_MANAGEMENT", "ADRX"),
    "Liều lượng và cách dùng": ("DOSAGE", "LD"),
    "Tương tác thuốc": ("INTERACTION", "TTT"),
    "Tương tác thuốc và các dạng tương tác khác": ("INTERACTION", "TTT"),
    "Tương kỵ": ("INCOMPATIBILITY", "TK"),
    "Độ ổn định và bảo quản": ("STORAGE", "BQ"),
    "Quá liều và xử trí": ("OVERDOSE", "QL"),
}

# --- Trường nội dòng: có dấu hai chấm ngay trên cùng dòng ---
INLINE_FIELDS: Dict[str, str] = {
    "Tên chung quốc tế": "intl_name",
    "Mã ATC": "atc_code",
    "Loại thuốc": "drug_class",
}

MONOGRAPH_END_RE = re.compile(r"^\s*C[âấaậ]p\s+nh[âậa]t\s+l[âầa]n\s+cu[ốôo]i", re.IGNORECASE)
PAGE_MARKER_RE = re.compile(r"^\[Trang\s+(\d+)\]\s*$")

# Dòng tên đồng nghĩa, in ngay dưới tên thuốc và đặt trọn trong ngoặc đơn:
#     ACID ASCORBIC
#     (Vitamin C)
# Dòng này cũng "trông như" tên thuốc (ngắn, không dấu hai chấm), nên nếu không
# nhận diện riêng thì cả chuyên luận sẽ mang tên "(Vitamin C)" thay vì
# "ACID ASCORBIC". Tên đồng nghĩa vẫn được giữ lại: bác sĩ tra "Vitamin C"
# nhiều hơn tra "acid ascorbic".
SYNONYM_LINE_RE = re.compile(r"^\s*\((.+)\)\s*$")

# Ngưỡng khớp mờ cho tiêu đề mục. OCR hay nuốt dấu hoặc đọc nhầm một hai ký tự,
# nên so khớp tuyệt đối sẽ sót rất nhiều mục.
FUZZY_THRESHOLD = 0.86
MAX_HEADING_LEN = 64

# Cắt phụ các mục quá dài (Dược động học thường >3 000 ký tự) để chunk vừa cửa
# sổ embedding mà vẫn giữ đủ ngữ cảnh.
SUBCHUNK_SIZE = 1200
SUBCHUNK_OVERLAP = 180


def _norm(text: str) -> str:
    """Chuẩn hóa để so khớp mờ: NFC, gộp khoảng trắng, bỏ dấu câu ở hai đầu."""
    text = unicodedata.normalize("NFC", text).strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .:;,-–—_|")


def match_block_heading(line: str) -> Optional[Tuple[str, str, str]]:
    """
    Dòng này có phải tiêu đề mục khối không?

    Trả về (tiêu_đề_chuẩn, field_type, mã_ngắn) hoặc None.
    """
    s = _norm(line)
    if not s or len(s) > MAX_HEADING_LEN:
        return None
    # Tiêu đề mục khối không mang dấu hai chấm — đó là dấu hiệu của trường nội dòng
    if ":" in line:
        return None
    low = s.lower()
    best: Optional[Tuple[float, str]] = None
    for canonical in BLOCK_SECTIONS:
        ratio = difflib.SequenceMatcher(None, low, canonical.lower()).ratio()
        if ratio >= FUZZY_THRESHOLD and (best is None or ratio > best[0]):
            best = (ratio, canonical)
    if best is None:
        return None
    field_type, code = BLOCK_SECTIONS[best[1]]
    return best[1], field_type, code


def match_inline_field(line: str) -> Optional[Tuple[str, str]]:
    """Trường nội dòng dạng 'Nhãn: giá trị'. Trả về (khóa, giá trị)."""
    if ":" not in line:
        return None
    label, _, value = line.partition(":")
    label_n = _norm(label).lower()
    if len(label_n) > 40:
        return None
    for canonical, key in INLINE_FIELDS.items():
        if difflib.SequenceMatcher(None, label_n, canonical.lower()).ratio() >= FUZZY_THRESHOLD:
            return key, _norm(value)
    return None


# Mã ATC có khuôn cố định: chữ, số, số, chữ, chữ, số, số (vd. N02CA01).
# OCR hay lẫn O↔0, I/l↔1, S↔5, B↔8, Z↔2. Biết vị trí nào phải là chữ, vị trí nào
# phải là số nên sửa được chắc chắn. Mã ATC chuẩn hóa là khoá nối một hoạt chất
# giữa Dược thư và cuốn Thuốc Biệt Dược.
# Chuỗi đã .upper() trước khi tra bảng, nên phải map cả "L" (từ chữ l thường)
_ATC_TO_DIGIT = str.maketrans({"O": "0", "I": "1", "L": "1",
                               "S": "5", "B": "8", "Z": "2", "G": "6"})
_ATC_TO_ALPHA = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z"})
_ATC_SHAPE = "ADDAADD"  # A = chữ cái, D = chữ số


def normalize_atc(raw: str) -> str:
    """Sửa lỗi OCR trong mã ATC theo khuôn vị trí. Trả về '' nếu không khớp khuôn."""
    s = re.sub(r"[^0-9A-Za-z]", "", unicodedata.normalize("NFC", raw or "")).upper()
    if len(s) < len(_ATC_SHAPE):
        return ""
    s = s[: len(_ATC_SHAPE)]
    out = []
    for ch, kind in zip(s, _ATC_SHAPE):
        if kind == "D":
            ch = ch.translate(_ATC_TO_DIGIT)
            if not ch.isdigit():
                return ""
        else:
            ch = ch.translate(_ATC_TO_ALPHA)
            if not ch.isalpha():
                return ""
        out.append(ch)
    return "".join(out)


def looks_like_drug_name(line: str) -> bool:
    """
    Dòng tên thuốc: ngắn, không dấu hai chấm, có chữ cái.

    Cố tình KHÔNG ràng buộc tỉ lệ chữ hoa — đó chính là heuristic đã trượt 17,9%
    trên cuốn sách trước. Vị trí (đứng ngay trên 'Tên chung quốc tế') mới là tín
    hiệu quyết định.
    """
    s = _norm(line)
    if not s or len(s) > 70 or ":" in line:
        return False
    if not any(c.isalpha() for c in s):
        return False
    # Loại các dòng rõ ràng là câu văn
    if s.endswith((".", ";")) and len(s.split()) > 6:
        return False
    return True


def load_lines(doc_name: str, page_map: Dict[str, Any]) -> List[Tuple[int, str]]:
    """
    Ghép text OCR toàn sách thành danh sách (chỉ_số_trang_pdf, dòng).

    Giữ số trang theo từng dòng thay vì cắt text theo mốc [Trang N]: một mục có
    thể vắt qua ranh giới trang, và chunk cần được gán đúng trang nơi nó BẮT ĐẦU.
    """
    folder = documents.ocr_dir(doc_name)
    pdf_pages = int(page_map.get("pdf_pages") or 0)
    out: List[Tuple[int, str]] = []
    for i in range(1, pdf_pages + 1):
        path = os.path.join(folder, f"page_{i:04d}.txt")
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            for line in f.read().splitlines():
                if PAGE_MARKER_RE.match(line):
                    continue
                out.append((i, line))
    return out


def split_long(text: str) -> List[str]:
    """Cắt mục dài thành nhiều đoạn có chồng lấn, ưu tiên cắt ở ranh giới câu."""
    text = text.strip()
    if len(text) <= SUBCHUNK_SIZE:
        return [text]
    parts: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + SUBCHUNK_SIZE, len(text))
        if end < len(text):
            window = text.rfind(". ", start + SUBCHUNK_SIZE // 2, end)
            if window != -1:
                end = window + 1
        parts.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - SUBCHUNK_OVERLAP, start + 1)
    return [p for p in parts if p]


def parse(doc_name: str) -> List[Dict[str, Any]]:
    map_path = documents.page_map_path(doc_name)
    if not os.path.exists(map_path):
        raise SystemExit(f"[!] Chưa có bản đồ trang: {map_path}. Chạy page_map.py trước.")
    with open(map_path, "r", encoding="utf-8") as f:
        page_map = json.load(f)

    pages_info = page_map.get("pages", {})

    def printed_page(pdf_page: int) -> int:
        info = pages_info.get(str(pdf_page)) or {}
        return info.get("page_num") or pdf_page

    def page_class(pdf_page: int) -> str:
        info = pages_info.get(str(pdf_page)) or {}
        return info.get("page_class") or "body"

    lines = load_lines(doc_name, page_map)
    print(f"  Đọc {len(lines)} dòng text OCR.")

    # --- Bước 1: tìm mọi mốc mở chuyên luận (dòng "Tên chung quốc tế")
    anchors: List[int] = []
    for idx, (_pdf, line) in enumerate(lines):
        hit = match_inline_field(line)
        if hit and hit[0] == "intl_name":
            anchors.append(idx)
    print(f"  Tìm thấy {len(anchors)} mốc 'Tên chung quốc tế'.")

    # --- Bước 2: với mỗi mốc, lùi lên tìm dòng tên thuốc
    monographs: List[Dict[str, Any]] = []
    for a_i, anchor in enumerate(anchors):
        name = None
        name_idx = anchor
        synonyms: List[str] = []
        for back in range(anchor - 1, max(anchor - 6, -1), -1):
            candidate = lines[back][1]
            if not _norm(candidate):
                continue
            if MONOGRAPH_END_RE.match(candidate):
                break
            # Dòng đồng nghĩa nằm CHEN GIỮA tên thuốc và mốc "Tên chung quốc tế",
            # nên gặp nó thì ghi lại rồi lùi tiếp, không dừng.
            syn = SYNONYM_LINE_RE.match(candidate)
            if syn:
                synonyms.insert(0, _norm(syn.group(1)))
                continue
            if looks_like_drug_name(candidate):
                name = _norm(candidate)
                name_idx = back
                break
            break
        if not name:
            continue
        end = anchors[a_i + 1] - 6 if a_i + 1 < len(anchors) else len(lines)
        monographs.append({
            "name": name,
            "synonyms": synonyms,
            "start": name_idx,
            "anchor": anchor,
            "end": max(end, anchor + 1),
            "pdf_page": lines[name_idx][0],
        })
    print(f"  Khoanh vùng {len(monographs)} chuyên luận.")

    # --- Bước 3: bóc tách trường trong từng chuyên luận
    chunks: List[Dict[str, Any]] = []
    for mono in monographs:
        head: Dict[str, str] = {}
        sections: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None

        for idx in range(mono["anchor"], mono["end"]):
            pdf_page, line = lines[idx]

            if MONOGRAPH_END_RE.match(line):
                break

            heading = match_block_heading(line)
            if heading:
                canonical, field_type, code = heading
                current = {
                    "field_name": canonical,
                    "field_type": field_type,
                    "code": code,
                    "pdf_page": pdf_page,
                    "lines": [],
                }
                sections.append(current)
                continue

            inline = match_inline_field(line)
            if inline and current is None:
                head[inline[0]] = inline[1]
                continue

            if current is not None and line.strip():
                current["lines"].append(line.strip())

        counters: Dict[str, int] = {}
        slug = re.sub(r"[^A-Z0-9]", "", mono["name"].upper()) or "DRUG"

        for sec in sections:
            content = "\n".join(sec["lines"]).strip()
            if len(content) < 20:
                continue
            for part in split_long(content):
                counters[sec["code"]] = counters.get(sec["code"], 0) + 1
                pdf_page = sec["pdf_page"]
                chunks.append({
                    "chunk_id": f"{slug}_{sec['code']}_{counters[sec['code']]:02d}",
                    "generic_name": normalize_drug_name(mono["name"]) or mono["name"],
                    "synonyms": mono.get("synonyms") or [],
                    "intl_name": head.get("intl_name", ""),
                    "atc_code": normalize_atc(head.get("atc_code", "")),
                    "drug_class": head.get("drug_class", ""),
                    "brand_names": [],
                    "field_type": sec["field_type"],
                    "field_name": sec["field_name"],
                    "content": part,
                    "source_file": doc_name,
                    "page_in_file": printed_page(pdf_page),
                    "pdf_page": pdf_page,
                    "page_class": page_class(pdf_page),
                })

    return chunks


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    import argparse

    p = argparse.ArgumentParser(description="Bóc tách chuyên luận Dược thư thành chunk")
    p.add_argument("--doc-name", required=True)
    p.add_argument("--out", default=None, help="Mặc định: data/chunks/<doc-name>.json")
    a = p.parse_args()

    print("=" * 66)
    print(f"   BÓC TÁCH CHUYÊN LUẬN — {a.doc_name}")
    print("=" * 66)

    chunks = parse(a.doc_name)

    out = a.out or documents.chunks_path(a.doc_name)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    drugs = {c["generic_name"] for c in chunks}
    by_type: Dict[str, int] = {}
    for c in chunks:
        by_type[c["field_type"]] = by_type.get(c["field_type"], 0) + 1

    print("\n" + "=" * 66)
    print("   HOÀN TẤT")
    print(f"   Chuyên luận : {len(drugs)}")
    print(f"   Chunk       : {len(chunks)}")
    print(f"   Có mã ATC   : {sum(1 for c in chunks if c['atc_code'])}")
    for k, v in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"     {k:20s} {v}")
    print(f"   -> {out}")
    print("=" * 66)


if __name__ == "__main__":
    main()
