# -*- coding: utf-8 -*-
r"""Câu hỏi có điều kiện -> từng cặp (thuốc, điều kiện) -> bằng chứng từng cặp.

"Liều amoxicilin cho trẻ suy thận" là MỘT câu nhưng cần HAI bằng chứng: đoạn
liều trẻ em và đoạn hiệu chỉnh liều khi suy thận. Một lượt truy xuất chung
thường mang về đủ đoạn cho điều kiện này mà bỏ sót điều kiện kia — trên câu hỏi
hướng dẫn lâm sàng, tỉ lệ trúng là 0,92 khi chỉ cần một tài liệu nhưng 0,54
khi cần đủ cả hai (GMDS 2025). Và khi thiếu, mô hình hay trả lời luôn thay vì
nói thiếu.

Với kho chuyên luận, việc tách này TẤT ĐỊNH, không cần LLM lập kế hoạch: mỗi
điều kiện bệnh nhân chỉ thẳng tới mục sách (mang thai -> "Thời kỳ mang thai",
suy thận -> Liều / Thận trọng / Chống chỉ định), và tên thuốc đã được
drug_alias nhận ra. Mỗi cặp là một truy xuất phụ trong đúng thuốc ∩ đúng mục,
kèm một phép kiểm chữ: đoạn được nhận là bằng chứng khi có nhắc tới chính điều
kiện đó ("suy thận", "ClCr", "lọc máu"…).

Đầu ra là BẢNG KIỂM: mỗi điều kiện "có trong sách, trang N" hoặc "thư viện
không có". Điều kiện thiếu được báo cho bác sĩ và cho mô hình — bỏ sót lặng lẽ
thành từ chối hiện rõ.

Kèm theo mỗi điều kiện tìm thấy là các CÂU NGUYÊN VĂN trong sách (chép đúng
từng chữ từ chunk, không qua LLM) — giao diện vẽ khối liều thẳng từ đó, bấm
vào thì mở trang và tô đúng câu.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from text_fold import fold

ENABLE_QUERY_PLAN = True

MAX_DRUGS = 2
MAX_QUOTES = 2
MAX_QUOTE_CHARS = 320

# id điều kiện -> (nhãn, mục ưu tiên theo thứ tự, từ chứng cứ)
# Từ chứng cứ so trên dạng gấp dấu, theo ranh giới từ: OCR hay rụng dấu
# ("suy than"), còn vị trí chữ thì không đổi. Vì gấp dấu nên KHÔNG dùng một
# âm tiết trơ trọi dễ trùng: "thận" gấp ra "than" khớp cả "thận trọng"; "thai"
# khớp "thải trừ"; "gan" khớp "gần"; "nhi" khớp "nhĩ".
# "tuổi" gấp ra "tuoi" trùng "tươi" ("sữa tươi"), nên chỉ tính khi đứng sau
# một con số: "12 tuổi", "3 tháng tuổi". Từ chứng cứ dạng regex chạy trên
# chuỗi từ đã gấp dấu (mỗi từ có một khoảng trắng hai bên).
AGE_TERM = re.compile(r" \d+ (?:thang )?tuoi ")

CONDITIONS: Dict[str, Tuple[str, Tuple[str, ...], tuple]] = {
    "pregnancy": ("Phụ nữ có thai", ("PREGNANCY", "CONTRAINDICATION", "WARNINGS"),
                  ("mang thai", "có thai", "thai kỳ", "thai nhi", "thai phụ", "bà bầu")),
    "lactation": ("Cho con bú", ("LACTATION", "CONTRAINDICATION", "WARNINGS"),
                  ("cho con bú", "cho bú", "sữa mẹ", "bú mẹ")),
    "renal": ("Suy thận", ("DOSAGE", "CONTRAINDICATION", "WARNINGS"),
              ("suy thận", "chức năng thận", "bệnh thận", "clcr", "thanh thải creatinin",
               "lọc máu", "thẩm phân", "lọc cầu thận")),
    "hepatic": ("Suy gan", ("DOSAGE", "CONTRAINDICATION", "WARNINGS"),
                ("suy gan", "bệnh gan", "xơ gan", "child pugh", "chức năng gan", "tổn thương gan")),
    "neonate": ("Trẻ sơ sinh", ("DOSAGE", "CONTRAINDICATION", "WARNINGS"),
                ("sơ sinh", "đẻ non")),
    "child": ("Trẻ em", ("DOSAGE", "CONTRAINDICATION", "WARNINGS"),
              ("trẻ em", "trẻ", "trẻ nhỏ", AGE_TERM)),
    "elderly": ("Người cao tuổi", ("DOSAGE", "WARNINGS", "CONTRAINDICATION"),
                ("người cao tuổi", "cao tuổi", "người già", "lớn tuổi")),
}

# Ý định không đi kèm điều kiện nào: bằng chứng là bất kỳ đoạn nào của mục.
INTENT_LABEL = {
    "dosage": "Liều dùng", "contraindication": "Chống chỉ định",
    "adr": "Tác dụng không mong muốn", "interaction": "Tương tác thuốc",
    "pregnancy": "Phụ nữ có thai", "lactation": "Cho con bú", "overdose": "Quá liều",
    "warnings": "Thận trọng", "indications": "Chỉ định", "mechanism": "Dược lý",
    "dosage_form": "Dạng thuốc - hàm lượng",
}

# Ý định mà bác sĩ cần đọc NGUYÊN VĂN (sai một chữ là sai lâm sàng).
VERBATIM_INTENTS = {"dosage", "contraindication", "adr", "interaction", "pregnancy",
                    "lactation", "overdose", "warnings"}

# Ý định -> mục ưu tiên cho điều kiện khi ý định đã nói rõ mục.
# "Liều … suy thận": tìm ở mục Liều trước, chỉ khi không có mới sang Thận trọng.
_INTENT_FIRST = {"dosage": "DOSAGE", "contraindication": "CONTRAINDICATION", "warnings": "WARNINGS"}

_DOSE_NUM = re.compile(r"\d")


@dataclass
class Condition:
    drug_keys: List[Tuple[str, ...]]
    drug_name: str
    cid: str                       # id điều kiện hoặc ý định
    label: str
    sections: Tuple[str, ...]      # thứ tự ưu tiên
    terms: Tuple[str, ...] = ()    # rỗng = mọi đoạn của mục đều là chứng cứ
    verbatim: bool = False
    # Khối liều: ưu tiên câu có con số. Chỉ là ưu tiên — "Chống chỉ định: suy
    # thận nặng" không có số nào mà vẫn là câu trả lời đúng cho "liều … suy thận".
    need_number: bool = False
    # Cặp tương tác: (khoá thuốc A, tên A, khoá thuốc B, tên B). Chứng cứ là
    # đoạn Tương tác của A có nhắc B, hoặc của B có nhắc A.
    pair: Optional[tuple] = None


@dataclass
class Evidence:
    condition: Condition
    idx: Optional[int] = None      # chỉ số chunk trong corpus, None = không có
    quotes: List[str] = field(default_factory=list)


def plan(intents: Sequence[str], slots: Sequence[str],
         drugs: Sequence[Tuple[List[Tuple[str, ...]], str, List[str]]]) -> List[Condition]:
    """Tách câu hỏi thành các điều kiện cần bằng chứng riêng.

    `drugs`: [(khoá thực thể, tên hiển thị, các tên dùng để dò chữ)] theo thứ
    tự xuất hiện. Không nhận ra thuốc nào thì không lập kế hoạch: mục quá rộng,
    kênh trọng tâm của vector_store đã lo phần đó.
    """
    drugs = list(drugs)[:MAX_DRUGS]
    if not drugs:
        return []
    out: List[Condition] = []
    first_intent = next((i for i in intents if i in _INTENT_FIRST), None)
    cond_slots = [s for s in slots if s in CONDITIONS]
    if "interaction" in intents and len(drugs) == 2:
        # Hai thuốc + ý định tương tác -> một điều kiện duy nhất cho cả cặp.
        (ka, na, ta), (kb, nb, tb) = drugs
        return [Condition(ka + kb, na, "interaction_pair", f"Tương tác {na} – {nb}",
                          ("INTERACTION", "INCOMPATIBILITY", "WARNINGS"),
                          verbatim=True, pair=(ka, ta, kb, tb))]
    for keys, name, _terms in drugs:
        for s in cond_slots:
            label, sections, terms = CONDITIONS[s]
            if first_intent:
                first = _INTENT_FIRST[first_intent]
                sections = (first,) + tuple(x for x in sections if x != first)
            out.append(Condition(keys, name, s, label, sections, terms, verbatim=True,
                                 need_number=first_intent == "dosage"))
        for i in intents:
            if i in ("pregnancy", "lactation") and i in cond_slots:
                continue  # đã có điều kiện cùng tên ở trên
            if i in ("dosage", "contraindication", "warnings") and cond_slots:
                continue  # "liều cho trẻ suy thận": hai điều kiện trên đã là câu hỏi
            if i not in INTENT_LABEL:
                continue
            out.append(Condition(keys, name, i, INTENT_LABEL[i], _INTENT_SECTIONS.get(i, ()),
                                 verbatim=i in VERBATIM_INTENTS, need_number=i == "dosage"))
    return out


_INTENT_SECTIONS = {
    "dosage": ("DOSAGE",), "contraindication": ("CONTRAINDICATION",),
    "adr": ("ADR", "ADR_MANAGEMENT"), "interaction": ("INTERACTION", "INCOMPATIBILITY"),
    "pregnancy": ("PREGNANCY",), "lactation": ("LACTATION",), "overdose": ("OVERDOSE",),
    "warnings": ("WARNINGS",), "indications": ("INDICATIONS",),
    "mechanism": ("PHARMACODYNAMICS", "TARGET_ACTION", "PHARMACOKINETICS"),
    "dosage_form": ("DOSAGE_FORM",),
}


# ---------------------------------------------------------------------------
# Kiểm chữ và trích nguyên văn
# ---------------------------------------------------------------------------

def _folded_words(text: str) -> str:
    return " " + " ".join(re.findall(r"\w+", fold(text or ""))) + " "


def mentions_any(text: str, terms: Sequence[str]) -> int:
    """Số từ chứng cứ (khác nhau) có trong đoạn, so theo ranh giới từ trên dạng gấp dấu."""
    if not terms:
        return 1
    hay = _folded_words(text)
    return sum(1 for t in terms
               if (t.search(hay) if isinstance(t, re.Pattern) else _folded_words(t) in hay))


def body_of(chunk_text: str) -> str:
    """Bỏ dòng định danh "【THUỐC: …】 (…) [Mục]" ở đầu chunk — đó là nhãn do
    parser ghép, không phải chữ in trên trang, nên không được trích làm nguyên văn."""
    text = chunk_text or ""
    text = re.sub(r"^\s*【[^】]*】[^\n\[]*", "", text)
    text = re.sub(r"^\s*\[[^\]\n]{1,60}\]\s*", "", text.strip())
    # Mã mục của sách Biệt Dược ("LD:", "CĐ:", "CCĐ:") ở đầu thân đoạn.
    text = re.sub(r"^\s*[A-ZĐ]{1,4}\s*:\s*", "", text)
    return text.strip()


def sentences(text: str) -> List[str]:
    flat = re.sub(r"-\n(?=\w)", "", text)          # nối chữ bị ngắt dòng
    flat = re.sub(r"\s*\|\s*", " ", flat)            # dấu | là chỗ xuống dòng trong chunk
    flat = re.sub(r"\s+", " ", flat).strip()
    parts = re.split(r"(?<=[.;!?])\s+(?=[A-ZÀ-Ỹ0-9(\-•–])", flat)
    return [p.strip() for p in parts if len(p.strip()) >= 12]


def pick_quotes(chunk_text: str, cond: Condition) -> List[str]:
    """Các câu nguyên văn trong đoạn trả lời điều kiện này.

    Chép đúng từng chữ (sau khi gộp khoảng trắng) — kể cả lỗi OCR — vì đây là
    chỗ bác sĩ đối chiếu với trang sách. Khối liều ưu tiên câu có con số.
    """
    sents = sentences(body_of(chunk_text))
    if not sents:
        return []
    scored = []
    for pos, s in enumerate(sents):
        hit = mentions_any(s, cond.terms) if cond.terms else 1
        if cond.terms and not hit:
            continue
        no_number = cond.need_number and not _DOSE_NUM.search(s)
        scored.append((no_number, -hit, pos, s))
    scored.sort()
    chosen = sorted(scored[:MAX_QUOTES], key=lambda x: x[2])
    out = []
    for _n, _h, _p, s in chosen:
        out.append(s if len(s) <= MAX_QUOTE_CHARS else s[:MAX_QUOTE_CHARS].rsplit(" ", 1)[0] + " …")
    return out
