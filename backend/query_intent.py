"""Hiểu câu hỏi của bác sĩ: ý định -> mục chuyên luận, điều kiện bệnh nhân, viết tắt."""
import json
import os
import re
import unicodedata

# Bật/tắt duy nhất cho phép đo trước/sau; không đổi công thức hay trọng số RRF.
ENABLE_INDICATION_RANKING = True

# CẦN DƯỢC SĨ DUYỆT: đây là ứng viên, không tự áp dụng vì hai cụm có thể khác nghĩa lâm sàng.
CANDIDATE_EXPANSIONS = {
    "đau bụng": {"terms": ("co thắt", "đau quặn", "đau dạ dày"), "approved": False},
}
# CẦN DƯỢC SĨ DUYỆT: không có quy tắc loại trừ drug_class đã duyệt trong ZIP.
APPROVED_CLASS_EXCLUSIONS = {}


def fold(text):
    text = text.lower().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", text)
                   if unicodedata.category(c) != "Mn")


def indication_subject(query):
    """Chỉ nhận mẫu yêu cầu thuốc rõ ràng, không suy diễn câu hỏi phủ định hoặc thận trọng."""
    match = re.fullmatch(r"thuốc\s+(?:cho|điều trị|giảm|chữa|trị)\s+(.+)",
                         query.strip().lower(), flags=re.IGNORECASE)
    if not match:
        return None
    subject = match.group(1).strip(" ?.,;:")
    return subject if len(subject) >= 3 else None


def expanded_terms(subject):
    entry = CANDIDATE_EXPANSIONS.get(subject.lower())
    return entry["terms"] if entry and entry["approved"] else ()


def adjusted_score(score, meta, child_text, subject, enabled=None):
    if enabled is None:
        enabled = ENABLE_INDICATION_RANKING
    if not enabled or not subject or not score:
        return score
    if meta.get("field_type") == "INDICATIONS":
        content = fold(child_text)
        if any(fold(term) in content for term in (subject, *expanded_terms(subject))):
            score += min(score * 0.18, 0.003)
    denied = APPROVED_CLASS_EXCLUSIONS.get(subject.lower(), ())
    if meta.get("drug_class") in denied:
        score *= 0.5
    return score


# ---------------------------------------------------------------------------
# Ý định của bác sĩ -> mục chuyên luận, và khe điều kiện bệnh nhân
# ---------------------------------------------------------------------------
#
# Dược thư và sách Thuốc Biệt Dược chia mọi chuyên luận theo cùng một bộ tiêu
# đề cố định (field_type trong metadata chunk). Câu hỏi của bác sĩ hầu như
# luôn nhắm đúng MỘT tiêu đề: "liều" -> Liều lượng và cách dùng, "bà bầu" ->
# Thời kỳ mang thai. Nên bộ ý định được giữ thô, ánh xạ một-một vào tiêu đề —
# phân loại câu hỏi lâm sàng chi tiết (Ely, 64 loại) chỉ đạt κ = 0,53 giữa
# người mã hoá với nhau, không đáng để máy đoán.
#
# Ý định KHÔNG lọc kết quả. vector_store chạy thêm một kênh truy xuất giới hạn
# trong các mục này và hợp nhất bằng RRF: đoán sai thì bảng xếp hạng gốc vẫn
# còn nguyên.
#
# Từ kích hoạt viết có dấu và so trên câu ĐÃ chuẩn hoá (query_normalize khôi
# phục dấu trước), nên "lieu dung" cũng khớp. Từ tiếng Anh / viết tắt so trên
# dạng đã bỏ dấu.

ENABLE_SECTION_ROUTING = True

INTENTS = [
    # (id, nhãn hiển thị, field_type, từ kích hoạt tiếng Việt, từ ASCII / tiếng Anh)
    ("overdose", "Quá liều", ("OVERDOSE",),
     ("quá liều", "ngộ độc", "uống quá nhiều", "uống nhầm", "dùng quá nhiều"),
     ("overdose", "overdosage", "poisoning")),
    ("contraindication", "Chống chỉ định", ("CONTRAINDICATION",),
     ("chống chỉ định", "không được dùng", "không được sử dụng", "cấm dùng", "ccđ"),
     ("contraindication", "contraindications", "contraindicated", "ccd")),
    ("adr", "Tác dụng không mong muốn", ("ADR", "ADR_MANAGEMENT"),
     ("tác dụng phụ", "tác dụng không mong muốn", "phản ứng có hại", "phản ứng phụ",
      "tác dụng ngoại ý", "tdkmm", "biến cố bất lợi"),
     ("adr", "adrs", "side effect", "side effects", "adverse", "tdkmm")),
    ("interaction", "Tương tác thuốc", ("INTERACTION", "INCOMPATIBILITY"),
     ("tương tác", "tương kỵ", "dùng chung", "dùng cùng", "uống chung", "uống cùng",
      "phối hợp với", "kết hợp với", "dùng kèm"),
     ("interaction", "interactions", "incompatibility")),
    ("pregnancy", "Thời kỳ mang thai", ("PREGNANCY",),
     ("có thai", "mang thai", "thai kỳ", "thai phụ", "bà bầu", "có bầu", "mang bầu",
      "đang bầu", "thai nhi", "phụ nữ mang thai"),
     ("pregnancy", "pregnant")),
    ("lactation", "Thời kỳ cho con bú", ("LACTATION",),
     ("cho con bú", "cho bú", "sữa mẹ", "nuôi con bằng sữa", "đang bú"),
     ("lactation", "breastfeeding", "breast feeding")),
    ("dosage", "Liều dùng", ("DOSAGE",),
     ("liều", "liều dùng", "liều lượng", "cách dùng", "cách uống", "dùng bao nhiêu",
      "uống bao nhiêu", "uống mấy", "mấy viên", "mấy lần", "bao nhiêu mg", "hiệu chỉnh liều",
      "chỉnh liều"),
     ("dose", "doses", "dosage", "dosing", "posology")),
    ("warnings", "Thận trọng", ("WARNINGS",),
     ("thận trọng", "lưu ý", "cảnh báo", "chú ý khi dùng", "cẩn thận"),
     ("precaution", "precautions", "warning", "warnings")),
    ("indications", "Chỉ định", ("INDICATIONS",),
     ("chỉ định", "công dụng", "dùng để làm gì", "dùng để trị", "dùng để chữa",
      "trị bệnh gì", "chữa bệnh gì", "điều trị bệnh gì", "tác dụng gì"),
     ("indication", "indications", "indicated")),
    ("mechanism", "Dược lý", ("PHARMACODYNAMICS", "PHARMACOKINETICS", "TARGET_ACTION"),
     ("cơ chế", "dược lực học", "dược lý", "dược động học", "bán thải", "thải trừ",
      "hấp thu", "chuyển hóa", "sinh khả dụng"),
     ("mechanism", "pharmacokinetics", "pharmacodynamics", "half life")),
    ("dosage_form", "Dạng thuốc - hàm lượng", ("DOSAGE_FORM",),
     ("dạng bào chế", "dạng thuốc", "hàm lượng", "biệt dược", "tên thương mại",
      "quy cách", "trình bày"),
     ("formulation", "brand", "brands")),
]

INTENT_LABEL = {i[0]: i[1] for i in INTENTS}
INTENT_FIELDS = {i[0]: i[2] for i in INTENTS}
_INTENT_BY_ID = {i[0]: i for i in INTENTS}

# Khe điều kiện bệnh nhân. Không phải bộ lọc: lọc cứng theo "suy thận" sẽ loại
# mất chính bảng liều trả lời câu hỏi. Khe chỉ (1) chỉ ra mục cần tra khi câu
# hỏi không nói rõ ý định, và (2) được báo lại cho bác sĩ để thấy máy đã hiểu
# đủ điều kiện chưa.
SLOTS = [
    ("neonate", "trẻ sơ sinh", ("sơ sinh", "trẻ đẻ non", "đẻ non"), ("neonate", "neonatal", "newborn")),
    ("child", "trẻ em", ("trẻ em", "trẻ nhỏ", "trẻ", "nhi", "em bé"), ("child", "children", "pediatric", "paediatric")),
    ("elderly", "người cao tuổi", ("người cao tuổi", "cao tuổi", "người già", "lớn tuổi"), ("elderly", "geriatric")),
    ("pregnancy", "có thai", _INTENT_BY_ID["pregnancy"][3], _INTENT_BY_ID["pregnancy"][4]),
    ("lactation", "cho con bú", _INTENT_BY_ID["lactation"][3], _INTENT_BY_ID["lactation"][4]),
    ("renal", "suy thận", ("suy thận", "bệnh thận", "lọc máu", "chạy thận", "thẩm phân",
                           "thanh thải creatinin", "mức lọc cầu thận"),
     ("clcr", "egfr", "gfr", "renal", "dialysis", "hemodialysis")),
    ("hepatic", "suy gan", ("suy gan", "bệnh gan", "xơ gan", "men gan"),
     ("hepatic", "child pugh", "cirrhosis")),
]

# Khe -> mục cần tra, chỉ dùng khi câu hỏi không có ý định rõ.
_SLOT_FIELDS = {
    "neonate": ("DOSAGE",), "child": ("DOSAGE",), "elderly": ("DOSAGE", "WARNINGS"),
    "pregnancy": ("PREGNANCY",), "lactation": ("LACTATION",),
    "renal": ("DOSAGE", "WARNINGS", "CONTRAINDICATION"),
    "hepatic": ("DOSAGE", "WARNINGS", "CONTRAINDICATION"),
}

# "có dùng được … không", "uống … được không": hỏi được hay không được dùng.
_POLARITY_RE = re.compile(
    r"\b(?:có\s+(?:được\s+|nên\s+)?(?:dùng|uống|sử\s+dụng|tiêm|kê|cho)\b.*\bkhông|được\s+(?:không|ko)|"
    r"có\s+an\s+toàn\b.*\bkhông)\b"
)
_AGE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(tháng tuổi|ngày tuổi|tuổi|tháng)")
_WEIGHT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:kg|ký|kí|cân)\b")


def _word_tokens(text):
    return re.findall(r"\w+", (text or "").lower())


def _phrase_tokens(phrases, folded):
    out = []
    for p in phrases:
        toks = _word_tokens(fold(p) if folded else p)
        if toks:
            out.append(tuple(toks))
    return out


def _phrase_table(rows):
    """[(id, cụm có dấu, cụm ASCII)] -> ứng viên sắp theo độ dài giảm dần."""
    cands = []
    for rid, vi, en in rows:
        cands += [(p, rid, False) for p in _phrase_tokens(vi, False)]
        cands += [(p, rid, True) for p in _phrase_tokens(en, True)]
    cands.sort(key=lambda c: -len(c[0]))
    return cands


_INTENT_CANDS = _phrase_table([(i[0], i[3], i[4]) for i in INTENTS])
_SLOT_CANDS = _phrase_table([(s[0], s[2], s[3]) for s in SLOTS])
_SLOT_LABEL = {s[0]: s[1] for s in SLOTS}


def _scan(toks, ftoks, cands):
    """Các id khớp, theo thứ tự xuất hiện. Cụm dài chiếm chỗ trước: "tác dụng
    phụ" không để lại "tác dụng" cho ý định khác, "quá liều" không để lại "liều"."""
    used = [False] * len(toks)
    hits = []
    for phrase, rid, folded in cands:
        seq = ftoks if folded else toks
        n = len(phrase)
        for i in range(len(seq) - n + 1):
            if tuple(seq[i:i + n]) == phrase and not any(used[i:i + n]):
                for j in range(i, i + n):
                    used[j] = True
                hits.append((i, rid))
    out = []
    for _pos, rid in sorted(hits):
        if rid not in out:
            out.append(rid)
    return out


class QueryUnderstanding:
    """Máy đã hiểu câu hỏi thế nào: ý định, mục cần tra, điều kiện bệnh nhân."""

    def __init__(self, intents, sections, slots, polarity, age=None, weight=None):
        self.intents = intents        # ["dosage", ...] theo thứ tự xuất hiện
        self.sections = sections      # set field_type cần tra
        self.slots = slots            # ["child", "renal", ...]
        self.polarity = polarity      # hỏi "có được dùng … không"
        self.age = age
        self.weight = weight

    @property
    def empty(self):
        return not (self.intents or self.slots or self.polarity)

    def labels(self):
        out = [INTENT_LABEL[i] for i in self.intents]
        for s in self.slots:
            if s in self.intents:
                continue  # "Thời kỳ mang thai" đã nói thay "có thai"
            label = _SLOT_LABEL[s]
            if s in ("child", "neonate", "elderly") and self.age:
                label += f" ({self.age})"
            out.append(label)
        if self.weight:
            out.append(self.weight)
        return out

    def as_dict(self):
        return {"intents": self.intents, "sections": sorted(self.sections),
                "slots": self.slots, "polarity": self.polarity,
                "age": self.age, "weight": self.weight, "labels": self.labels()}


def understand(query):
    """Đọc ý định và điều kiện bệnh nhân từ câu hỏi (đã chuẩn hoá dấu)."""
    q = (query or "").lower()
    toks = _word_tokens(q)
    ftoks = [fold(t) for t in toks]

    intents = _scan(toks, ftoks, _INTENT_CANDS)
    slots = _scan(toks, ftoks, _SLOT_CANDS)
    if "neonate" in slots and "child" in slots:
        slots.remove("child")

    age = weight = None
    m = _AGE_RE.search(q)
    if m:
        age = f"{m.group(1)} {m.group(2)}"
        try:
            years = float(m.group(1).replace(",", "."))
        except ValueError:
            years = None
        if m.group(2) == "tuổi" and years is not None:
            if years < 16 and "child" not in slots and "neonate" not in slots:
                slots.append("child")
            elif years >= 65 and "elderly" not in slots:
                slots.append("elderly")
        elif m.group(2) != "tuổi" and "child" not in slots and "neonate" not in slots:
            slots.append("child")
    m = _WEIGHT_RE.search(q)
    if m:
        weight = f"{m.group(1)} kg"

    polarity = bool(_POLARITY_RE.search(q))

    # "thuốc hạ sốt", "trẻ bị ho dùng thuốc gì": hỏi THUỐC NÀO dùng cho một bệnh —
    # tức mục Chỉ định, dù không có chữ "chỉ định".
    if not intents and (re.match(r"^thuốc\s", q) or re.search(r"\bthuốc\s+(?:gì|nào)\b", q)):
        intents.append("indications")

    sections = set()
    for iid in intents:
        sections.update(INTENT_FIELDS[iid])
    if not intents:
        for s in slots:
            sections.update(_SLOT_FIELDS.get(s, ()))
        if polarity:
            sections.update(("CONTRAINDICATION", "WARNINGS"))
    return QueryUnderstanding(intents, sections, slots, polarity, age, weight)


def section_of(meta):
    """Mục của một chunk, theo cùng bộ field_type mà ý định dùng.

    Sách Thuốc Biệt Dược gắn đoạn "Tương tác thuốc" vào field_type WARNINGS
    (cùng mục "Lưu ý - Thận trọng" trong sách in); ở đây trả về đúng INTERACTION
    để ý định tương tác tìm thấy nó.
    """
    ft = meta.get("field_type") or ""
    if ft == "WARNINGS" and (meta.get("field_name") or "").startswith("Tương tác"):
        return "INTERACTION"
    return ft


# ---------------------------------------------------------------------------
# Chữ viết tắt đã duyệt (lexicon/abbreviations.json)
# ---------------------------------------------------------------------------
#
# Mở rộng THÊM vào câu tra, không thay: "metformin ĐTĐ" vẫn còn chữ "ĐTĐ" cho
# những đoạn sách viết tắt. Chỉ dòng approved mới được dùng — ứng viên khai
# thác từ sách (lexicon_mine.py) phải qua người duyệt trước.

ABBREVIATIONS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lexicon", "abbreviations.json")
_abbreviations = None


def _load_abbreviations():
    global _abbreviations
    if _abbreviations is None:
        table = {}
        try:
            with open(ABBREVIATIONS_PATH, encoding="utf-8") as f:
                for row in json.load(f).get("entries", []):
                    if row.get("approved"):
                        table[fold(row["abbr"])] = (row["abbr"], row["expansion"])
        except (OSError, ValueError) as e:
            print(f"[abbr] Không đọc được {ABBREVIATIONS_PATH}: {e}")
        _abbreviations = table
    return _abbreviations


def expand_abbreviations(query):
    """[(viết tắt, cụm đầy đủ)] có trong câu hỏi GỐC (trước khi khôi phục dấu).

    Nhận chữ viết HOA ("THA") hoặc chữ thường từ 4 ký tự ("copd"). Chữ thường
    ngắn thì bỏ: "tha", "stm" quá dễ là âm tiết tiếng Việt gõ không dấu.
    """
    table = _load_abbreviations()
    out = []
    for tok in re.findall(r"\w+", query or ""):
        if not (tok.isupper() and len(tok) >= 2) and not (tok.islower() and len(tok) >= 4):
            continue
        hit = table.get(fold(tok))
        if hit and hit not in out:
            out.append(hit)
    return out
