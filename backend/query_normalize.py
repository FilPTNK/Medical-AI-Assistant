# -*- coding: utf-8 -*-
"""
Chuẩn hoá câu hỏi gõ không dấu hoặc gõ nhầm Telex, CHỈ bằng từ vựng của chính kho sách.

Bác sĩ lớn tuổi hay gõ "thuoc ha huyet ap cho tre em" (không dấu), hoặc quên bật
bộ gõ nên ra "thuoocs" thay vì "thuốc". Cả hai đều làm hỏng tra cứu:

- BM25 so token nguyên dạng, "thuoc" không khớp "thuốc".
- e5 nhạy dấu: vector của câu không dấu lệch khỏi vector của đoạn văn có dấu.

Ở đây có hai phép biến đổi, cả hai đều TẤT ĐỊNH và bị ràng buộc bởi kho:

1. Gỡ Telex — một token chỉ được đổi khi (a) nó không có trong kho ở bất kỳ
   dạng nào, và (b) dạng sau khi đổi CÓ trong kho. Nhờ vậy "aspirin", "virus",
   "cefixime" không bao giờ bị đụng tới.

2. Khôi phục dấu theo kho — lúc dựng chỉ mục, đếm mọi âm tiết và mọi cặp âm
   tiết liền nhau trong sách. Câu không dấu được khôi phục về chuỗi có dấu có
   điểm cao nhất theo hai bảng đếm đó (quy hoạch động kiểu Viterbi). Không có
   mô hình nào đoán thêm: một âm tiết không có trong sách thì giữ nguyên.

Vì sao không dùng mô hình khôi phục dấu có sẵn (ViT5…): chúng học trên báo chí
và Wikipedia, chưa ai đo trên văn bản y dược, và chúng không biết "dai thao
duong" trong sách này luôn là "đái tháo đường" chứ không phải "dài tháo đường".
Bảng đếm của chính kho biết điều đó.

Cái giá: kho có lỗi OCR ("huyét", "thuóc"), nên các biến thể lỗi cũng nằm trong
bảng đếm. Chúng hiếm hơn hẳn dạng đúng (huyết 17.632 lần, huyét 300 lần), nên
ứng viên được lọc theo tần suất tương đối trước khi vào quy hoạch động.

Đo trên 100 truy vấn của eval (bỏ dấu rồi khôi phục): 85/100 câu ra đúng nguyên
văn; mọi câu có dấu đều giữ nguyên. Phần sai là từ đồng âm mà sách thuốc không
phân xử được — "thuốc chữa" gặp 12 lần còn "thuốc chưa" 100 lần, "trị nấm" 9 lần
còn "trị nam" 20 lần. Đã thử gộp số đếm của dạng rụng dấu vào dạng đủ dấu (vì
OCR làm rụng dấu chứ ít khi thêm: "da dày" 444 lần là "dạ dày" bị rụng dấu) —
KHÔNG đỡ: 84/100, và đẻ lỗi mới ("thuốc ho" -> "thuốc hỗ"). Nên đừng thử lại.
Những câu khôi phục sai vẫn tra đúng nhờ trường gấp dấu trong vector_store, và
giao diện hiện câu đã hiểu để bác sĩ thấy.
"""

import math
import re
import unicodedata
from collections import Counter
from typing import Dict, List, Optional, Tuple

from text_fold import fold

# Đổi khi đổi cách dựng bảng đếm — cache corpus trên đĩa sẽ tự dựng lại.
LEXICON_VERSION = "lex-1"

# Chữ cái (kể cả chữ có dấu), không số, không gạch dưới.
WORD_RE = re.compile(r"[^\W\d_]+")

# Một câu được coi là "gõ không dấu" khi ít hơn tỉ lệ này số âm tiết có dấu.
# Văn tiếng Việt viết đủ dấu có khoảng 70–80% âm tiết mang dấu; ngưỡng thấp để
# câu có dấu bình thường (vốn có "cho", "ho", "gan", "tim"…) không bị đụng tới.
UNACCENTED_RATIO = 0.2

# Ứng viên khôi phục: tối đa ngần này dạng có dấu cho mỗi dạng gấp, và chỉ những
# dạng xuất hiện ít nhất bằng tỉ lệ này so với dạng phổ biến nhất. Bỏ được phần
# lớn biến thể lỗi OCR ("thuóc" 81 lần so với "thuốc" 78.263 lần).
MAX_CANDIDATES = 6
MIN_RELATIVE_FREQ = 0.002

# Cặp âm tiết chỉ được giữ trong bảng đếm khi gặp ít nhất ngần này lần — cặp gặp
# một lần phần lớn là nhiễu, và bỏ đi giảm bảng từ ~430k xuống ~190k cặp.
MIN_BIGRAM_COUNT = 2

# Trọng số của cặp so với âm tiết đơn trong điểm Viterbi. Cặp mang ngữ cảnh
# ("đái tháo" vs "dài tháo") nên được nặng gấp đôi.
BIGRAM_WEIGHT = 2.0

# Token trông như Telex được đổi khi dạng đã đổi gặp nhiều hơn ít nhất ngần này
# lần so với chính token đó trong kho (xem QueryLexicon.fix_telex).
TELEX_MIN_RATIO = 20


def has_diacritic(word: str) -> bool:
    return fold(word) != word.lower()


def is_unaccented_query(query: str) -> bool:
    """Câu gần như không có dấu (bác sĩ gõ không bật bộ gõ, hoặc cố ý gõ nhanh)."""
    words = WORD_RE.findall(query)
    if not words:
        return False
    accented = sum(1 for w in words if has_diacritic(w))
    return accented / len(words) < UNACCENTED_RATIO


# ---------------------------------------------------------------- Telex

_TELEX_TONES = {"s": "́", "f": "̀", "r": "̉", "x": "̃", "j": "̣"}
_TELEX_DOUBLE = (("dd", "đ"), ("aa", "â"), ("ee", "ê"), ("oo", "ô"))
_VOWELS = set("aăâeêioôơuưy")
_ASCII_WORD = re.compile(r"^[a-z]+$")


def _apply_modifiers(core: str) -> Optional[str]:
    """Đổi phím mũ/móc Telex trong một âm tiết: dd→đ, aa→â, aw→ă, ow→ơ, uw→ư…

    Chữ "w" có thể nằm sau phụ âm cuối ("tangw" = "tăng"), nên w được gỡ ra
    trước rồi áp vào nguyên âm thích hợp.
    """
    s = core
    for src, dst in _TELEX_DOUBLE:
        s = s.replace(src, dst)
    # w đứng ngay sau nguyên âm của nó trước: "chuwa" = "chưa", không phải "chuă".
    for src, dst in (("uwow", "ươ"), ("uow", "ươ"), ("uw", "ư"), ("ow", "ơ"), ("aw", "ă")):
        s = s.replace(src, dst)
    if "w" in s:
        if s.count("w") > 1:
            return None
        s = s.replace("w", "")
        if "uo" in s:
            s = s.replace("uo", "ươ", 1)
        elif "a" in s:
            s = s.replace("a", "ă", 1)
        elif "o" in s:
            s = s.replace("o", "ơ", 1)
        elif "u" in s:
            s = s.replace("u", "ư", 1)
        else:
            return None
    return s


def telex_candidates(token: str) -> List[str]:
    """Mọi cách đọc token như một âm tiết Telex. Chưa kiểm với kho."""
    t = token.lower()
    if not _ASCII_WORD.match(t) or len(t) < 2:
        return []
    tone = None
    core = t
    if t[-1] in _TELEX_TONES and any(c in "aeiouy" for c in t[:-1]):
        tone = _TELEX_TONES[t[-1]]
        core = t[:-1]
    base = _apply_modifiers(core)
    if base is None or (base == t and tone is None):
        return []
    if tone is None:
        return [base]
    # Đặt dấu thanh lên từng nguyên âm một; kho sẽ quyết định cách nào đúng.
    # Làm vậy thay vì cài quy tắc đặt dấu vì sách dùng cả kiểu cũ lẫn kiểu mới
    # ("hoà"/"hòa").
    out = []
    for i, ch in enumerate(base):
        if ch in _VOWELS:
            out.append(unicodedata.normalize("NFC", base[:i + 1] + tone + base[i + 1:]))
    return out


# ---------------------------------------------------------------- Lexicon

class QueryLexicon:
    """Bảng đếm âm tiết và cặp âm tiết của kho, dùng để chuẩn hoá câu hỏi."""

    def __init__(self, unigrams: Dict[str, int], bigrams: Dict[str, int]):
        self.unigrams = unigrams
        self.bigrams = bigrams
        by_fold: Dict[str, List[Tuple[int, str]]] = {}
        for word, count in unigrams.items():
            by_fold.setdefault(fold(word), []).append((count, word))
        self.candidates: Dict[str, List[str]] = {}
        for key, forms in by_fold.items():
            forms.sort(reverse=True)
            top = forms[0][0]
            self.candidates[key] = [
                w for c, w in forms[:MAX_CANDIDATES] if c >= top * MIN_RELATIVE_FREQ
            ]

    @classmethod
    def build(cls, texts: List[str]) -> "QueryLexicon":
        uni: Counter = Counter()
        bi: Counter = Counter()
        for text in texts:
            words = WORD_RE.findall(text.lower())
            uni.update(words)
            bi.update(f"{a} {b}" for a, b in zip(words, words[1:]))
        bigrams = {k: v for k, v in bi.items() if v >= MIN_BIGRAM_COUNT}
        return cls(dict(uni), bigrams)

    # -- từng bước --

    def fix_telex(self, word: str) -> str:
        """Gỡ Telex cho một token, chỉ khi kho xác nhận.

        Không thể chỉ đòi "token không có trong kho": rác OCR của kho có đúng
        những chuỗi trông như Telex ("gif", "trer", "ngur"). Nên token CÓ trong
        kho vẫn được đổi, miễn dạng sau khi đổi phổ biến hơn hẳn — "gì" gặp hàng
        nghìn lần còn "gif" vài lần. Âm tiết tiếng Việt thật không bao giờ tận
        cùng bằng s/f/r/x/j hay chứa dd/aa/ee/w, nên ngưỡng này gần như không
        thể đổi nhầm một từ đúng.
        """
        low = word.lower()
        own = self.unigrams.get(low, 0)
        options = [c for c in telex_candidates(low)
                   if self.unigrams.get(c, 0) >= max(1, own * TELEX_MIN_RATIO)]
        if not options:
            return word
        return max(options, key=lambda c: self.unigrams[c])

    def restore(self, words: List[str]) -> List[str]:
        """Viterbi trên các dạng có dấu của từng âm tiết.

        Âm tiết đã có dấu được giữ nguyên làm mỏ neo; âm tiết không có trong kho
        cũng giữ nguyên (tên thuốc, từ tiếng Anh…).
        """
        lattice: List[List[str]] = []
        for w in words:
            low = w.lower()
            if has_diacritic(low):
                lattice.append([low])
            else:
                lattice.append(self.candidates.get(low) or [low])

        def emit(word: str) -> float:
            return math.log(self.unigrams.get(word, 0) + 1)

        def trans(prev: str, cur: str) -> float:
            return BIGRAM_WEIGHT * math.log(self.bigrams.get(f"{prev} {cur}", 0) + 1)

        scores = [emit(c) for c in lattice[0]]
        back: List[List[int]] = [[-1] * len(lattice[0])]
        for i in range(1, len(lattice)):
            row_scores, row_back = [], []
            for cur in lattice[i]:
                best, arg = -math.inf, 0
                for j, prev in enumerate(lattice[i - 1]):
                    s = scores[j] + trans(prev, cur)
                    if s > best:
                        best, arg = s, j
                row_scores.append(best + emit(cur))
                row_back.append(arg)
            scores, back = row_scores, back + [row_back]

        idx = max(range(len(scores)), key=lambda k: scores[k])
        out = []
        for i in range(len(lattice) - 1, -1, -1):
            out.append(lattice[i][idx])
            idx = back[i][idx]
        return out[::-1]

    # -- cả câu --

    def normalize(self, query: str) -> "NormalizedQuery":
        pieces = re.split(r"(\W+)", query)
        telex_fixed = []
        for i, piece in enumerate(pieces):
            if WORD_RE.fullmatch(piece or ""):
                fixed = self.fix_telex(piece)
                if fixed != piece:
                    telex_fixed.append((piece, fixed))
                    pieces[i] = fixed
        text = "".join(pieces)

        unaccented = is_unaccented_query(text)
        restored = False
        if unaccented:
            word_idx = [i for i, p in enumerate(pieces) if WORD_RE.fullmatch(p or "")]
            if word_idx:
                new_words = self.restore([pieces[i] for i in word_idx])
                for i, w in zip(word_idx, new_words):
                    if w != pieces[i].lower():
                        pieces[i] = w
                        restored = True
                text = "".join(pieces)
        return NormalizedQuery(original=query, text=text, unaccented=unaccented,
                               restored=restored, telex_fixed=telex_fixed)


class NormalizedQuery:
    __slots__ = ("original", "text", "unaccented", "restored", "telex_fixed")

    def __init__(self, original, text, unaccented, restored, telex_fixed):
        self.original = original
        self.text = text
        self.unaccented = unaccented
        self.restored = restored
        self.telex_fixed = telex_fixed

    @property
    def changed(self) -> bool:
        return self.text != self.original

    def as_dict(self):
        return {"original": self.original, "text": self.text,
                "unaccented": self.unaccented, "restored": self.restored,
                "telex_fixed": [list(p) for p in self.telex_fixed]}


# ---------------------------------------------------------------- tách từ ghép trên chữ gấp

MAX_COMPOUND_SYLLABLES = 4


def segment_folded(syllables: List[str], folded_df: Dict[str, int]) -> List[str]:
    """Ghép các âm tiết đã gấp dấu thành từ ghép theo đúng từ điển của trường gấp.

    pyvi tách từ ghép rất kém trên chữ không dấu, nên câu không dấu không thể đưa
    qua pyvi rồi đem so với token "dai_thao_duong" của kho. Thay vào đó, lấy
    chính tập token đã gấp của kho làm từ điển và ghép tham lam theo cụm dài nhất
    có trong đó.
    """
    out, i = [], 0
    while i < len(syllables):
        for n in range(min(MAX_COMPOUND_SYLLABLES, len(syllables) - i), 1, -1):
            cand = "_".join(syllables[i:i + n])
            if folded_df.get(cand, 0) > 0:
                out.append(cand)
                i += n
                break
        else:
            out.append(syllables[i])
            i += 1
    return out
