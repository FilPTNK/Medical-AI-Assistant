# -*- coding: utf-8 -*-
"""
Cổng số liệu: mọi con số liều trong câu trả lời phải TÌM THẤY trong trang được trích.

Liều là chỗ mô hình ngôn ngữ sai nhiều nhất và nguy hiểm nhất. Có ngữ cảnh rồi
mà nó vẫn có thể chép lệch một con số, đổi mg thành mcg, hay gán liều người lớn
cho trẻ em. Bác sĩ đọc câu trả lời trôi chảy thì khó nhận ra.

Ở đây không có mô hình nào cả — chỉ là so khớp tất định, chạy ngay sau khi câu
trả lời chảy xong:

1. Bóc mọi cặp (số, đơn vị) ra khỏi câu trả lời: "500 mg", "0,5 g", "10–15
   mg/kg", "4 g/ngày", "40 kg", "12 tuổi", "mỗi 8 giờ".
2. Với từng câu, xem nó trích [n] nào. Cặp (số, đơn vị) phải có trong chính các
   đoạn [n] ấy; không có thì tìm trong các đoạn khác; vẫn không có thì gắn cờ.
3. Cùng con số mà khác đơn vị khối lượng (sách ghi mg, câu trả lời ghi mcg) là
   LỖI CỨNG — sai gấp nghìn lần.

So theo GIÁ TRỊ chứ không theo chuỗi, sau khi quy khối lượng về mg: "1 g" khớp
"1000 mg" và "1.000 mg" (sách Việt dùng dấu chấm phân nghìn, dấu phẩy thập phân).
Phần "/kg" và "/m²" là một phần của liều nên phải khớp; còn "/ngày", "/lần" thì
không, vì mô hình hay viết lại thành "mỗi ngày", "chia 2 lần".

Cờ KHÔNG xoá chữ nào trong câu trả lời. Nó chỉ nói thật với bác sĩ con số nào
chưa đối chiếu được với sách — quyết định vẫn là của bác sĩ.

Dùng chung với eval/wp6_grade.py để chấm ngoại tuyến và kiểm lúc chạy không lệch
nhau.
"""

import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# Đơn vị -> (khoá chuẩn, hệ số quy về mg nếu là khối lượng)
_UNITS: Dict[str, Tuple[str, Optional[float]]] = {
    "mcg": ("mass", 0.001), "µg": ("mass", 0.001), "μg": ("mass", 0.001),
    "microgam": ("mass", 0.001), "microgram": ("mass", 0.001),
    "mg": ("mass", 1.0),
    "g": ("mass", 1000.0), "gam": ("mass", 1000.0), "gram": ("mass", 1000.0),
    "kg": ("kg", None),
    "ml": ("ml", None),
    "iu": ("iu", None), "ui": ("iu", None), "đvqt": ("iu", None),
    "mmol": ("mmol", None), "meq": ("meq", None),
    "%": ("%", None),
    "viên": ("viên", None), "giọt": ("giọt", None), "ống": ("ống", None), "gói": ("gói", None),
    "lần": ("lần", None),
    "giờ": ("giờ", None), "tuổi": ("tuổi", None), "tháng": ("tháng", None),
}

_NUM = r"\d+(?:[.,]\d+)*"
_UNIT_ALT = "|".join(sorted((re.escape(u) for u in _UNITS), key=len, reverse=True))
# "10–15 mg/kg/ngày", "0,5 g", "mỗi 8 giờ", "2 lần/ngày"
DOSE_RE = re.compile(
    rf"(?<![\w.,])(?P<a>{_NUM})(?:\s*(?:-|–|—|đến|tới)\s*(?P<b>{_NUM}))?\s*"
    rf"(?P<unit>{_UNIT_ALT})(?![\w])(?P<per>(?:\s*/\s*(?:kg|m2|m²|ngày|lần|giờ|24\s*giờ|liều))*)",
    re.IGNORECASE,
)
CITE_RE = re.compile(r"\[(\d+)\]")
# Câu: cắt ở dấu chấm/hỏi/than CÓ khoảng trắng sau (không cắt "0.5"), và ở xuống dòng.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;])\s+|\n+")


def _to_float(raw: str) -> Optional[float]:
    s = raw.strip()
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", s):        # 1.000 / 12.500 -> phân nghìn
        s = s.replace(".", "")
    elif re.fullmatch(r"\d{1,3}(?:,\d{3})+", s) and "." not in s and len(s.split(",")[-1]) == 3 \
            and s.count(",") > 1:                         # 1,000,000 kiểu Anh
        s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


class Dose:
    __slots__ = ("raw", "values", "kind", "factor", "per_kg", "start", "end")

    def __init__(self, raw, values, kind, factor, per_kg, start, end):
        self.raw, self.values, self.kind, self.factor = raw, values, kind, factor
        self.per_kg, self.start, self.end = per_kg, start, end

    def keys(self) -> List[Tuple[str, float, str]]:
        """Khoá so khớp cho từng con số: (loại đơn vị, giá trị đã quy đổi, mẫu số)."""
        scale = self.factor or 1.0
        return [(self.kind, round(v * scale, 6), self.per_kg) for v in self.values]


def extract_doses(text: str) -> List[Dose]:
    out = []
    for m in DOSE_RE.finditer(text or ""):
        unit = m.group("unit").lower()
        kind, factor = _UNITS.get(unit, (unit, None))
        values = [v for v in (_to_float(m.group("a")), _to_float(m.group("b")) if m.group("b") else None)
                  if v is not None]
        if not values:
            continue
        per = re.sub(r"\s+", "", (m.group("per") or "").lower())
        per_kg = "/m2" if ("/m2" in per or "/m²" in per) else ("/kg" if "/kg" in per else "")
        out.append(Dose(m.group(0).strip(), values, kind, factor, per_kg, m.start(), m.end()))
    return out


def _index(texts: Iterable[str]) -> Tuple[set, set]:
    """(khoá đầy đủ, khoá chỉ theo con số thô của khối lượng) của một tập đoạn văn."""
    full, raw_mass = set(), set()
    for t in texts:
        for d in extract_doses(t):
            full.update(d.keys())
            if d.kind == "mass":
                raw_mass.update((v, d.per_kg) for v in d.values)
    return full, raw_mass


def verify_answer(answer: str, sources: Sequence[dict],
                  page_text: Optional[callable] = None) -> Dict[str, object]:
    """Đối chiếu số liệu của câu trả lời với các nguồn đã trích.

    `sources` theo đúng thứ tự [1], [2]… đã đưa cho mô hình. `page_text(source)`
    (tuỳ chọn) trả văn bản OCR của CẢ TRANG — dùng khi con số nằm ngoài đoạn
    được cắt làm ngữ cảnh nhưng vẫn trên cùng trang sách.
    """
    texts = [str(s.get("text") or "") + "\n" + str(s.get("quote") or s.get("child_text") or "")
             for s in sources]
    per_source = [_index([t]) for t in texts]
    page_cache: Dict[int, Tuple[set, set]] = {}

    def page_index(i: int):
        if page_text is None:
            return set(), set()
        if i not in page_cache:
            try:
                page_cache[i] = _index([page_text(sources[i]) or ""])
            except Exception:
                page_cache[i] = (set(), set())
        return page_cache[i]

    flags, checked = [], 0
    for sentence in _SENTENCE_SPLIT.split(answer or ""):
        doses = extract_doses(sentence)
        if not doses:
            continue
        cited = [int(n) - 1 for n in CITE_RE.findall(sentence) if 0 < int(n) <= len(sources)]
        scope = cited or list(range(len(sources)))
        others = [i for i in range(len(sources)) if i not in scope]
        for d in doses:
            checked += 1
            keys = d.keys()

            def found(idx_list, use_page=False):
                hits = []
                for i in idx_list:
                    full, _ = page_index(i) if use_page else per_source[i]
                    if all(k in full for k in keys):
                        hits.append(i)
                return hits

            if found(scope) or found(scope, use_page=True):
                continue
            elsewhere = found(others) or found(others, use_page=True)
            status = "other_source" if elsewhere else "ungrounded"
            if d.kind == "mass" and not elsewhere:
                # Cùng con số, khác đơn vị khối lượng: sai gấp nghìn lần.
                for i in scope:
                    _, raw_mass = per_source[i]
                    if all((v, d.per_kg) in raw_mass for v in d.values):
                        status = "unit_mismatch"
                        break
            flags.append({
                "text": d.raw,
                "status": status,
                "cited": [i + 1 for i in cited],
                "found_in": [i + 1 for i in elsewhere],
                "sentence": sentence.strip()[:240],
            })
    return {"checked": checked, "flags": flags}
