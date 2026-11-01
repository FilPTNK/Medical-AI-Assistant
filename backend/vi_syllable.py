# -*- coding: utf-8 -*-
"""Kiểm âm tiết tiếng Việt hợp lệ — điểm chất lượng OCR theo từng trang.

Mỗi âm tiết là (phụ âm đầu) + vần + thanh, với tập phụ âm đầu và vần đóng, và
một ràng buộc mạnh: vần tận cùng bằng p/t/c/ch chỉ mang thanh sắc hoặc nặng.
OCR gốc Latin làm hỏng chữ Việt theo những cách phá vỡ khuôn này — mất mũ
("thuôc"), lệch dấu, hai dấu thanh, ghép chữ lạ ("nhỉêm") — nên tỉ lệ âm tiết
không hợp lệ trên một trang là thước đo chất lượng OCR riêng cho tiếng Việt,
không cần mô hình hay từ điển.

Giới hạn đã biết: rụng HẾT dấu thường vẫn ra âm tiết hợp lệ ("thận" -> "than"),
nên điểm này đánh giá thấp loại lỗi đó. Tên thuốc ngoại, đơn vị ("mg",
"Augmentin") không phải âm tiết Việt: từ toàn chữ ASCII mà không ghép được thành
âm tiết thì bị bỏ qua, không tính là lỗi.
"""

import re
import unicodedata
from typing import Dict, Iterable, Optional, Tuple

# Dấu thanh (dấu kết hợp sau NFD). Mũ/trăng/móc (0302, 0306, 031B) là một phần
# của nguyên âm, không phải thanh.
_TONES = {"̀": "huyen", "́": "sac", "̃": "nga", "̉": "hoi", "̣": "nang"}

_ONSETS = ("ngh", "ch", "gh", "gi", "kh", "ng", "nh", "ph", "qu", "th", "tr",
           "b", "c", "d", "đ", "g", "h", "k", "l", "m", "n", "p", "r", "s", "t", "v", "x", "")

_RHYMES = set("""
a ac ach ai am an ang anh ao ap at au ay
ăc ăm ăn ăng ăp ăt
âc âm ân âng âp ât âu ây
e ec em en eng eo ep et
ê êch êm ên ênh êp êt êu
i ich im in inh ip it iu ia iêc iêm iên iêng iêp iêt iêu
y yêm yên yêng yêt yêu
o oc oi om on ong ooc oong op ot
ô ôc ôi ôm ôn ông ôp ôt
ơ ơi ơm ơn ơp ơt
u uc ui um un ung up ut ua uôc uôi uôm uôn uông uôt
ư ưc ưi ưm ưn ưng ưt ưu ưa ươc ươi ươm ươn ương ươp ươt ươu
oa oac oach oai oan oang oanh oao oap oat oay oăc oăm oăn oăng oăt oe oen oeo oet
uân uâng uât uây uê uêch uênh uy uych uyên uyêt uynh uyp uyt uyu uya uơ
""".split())

_STOP_CODA = ("p", "t", "c", "ch")

_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


_MARKED = set("âăêôơư")


def _split_tone(word: str) -> Tuple[str, Optional[str], int, int]:
    """Bỏ dấu thanh; trả (chữ không thanh, thanh, số dấu thanh, vị trí chữ mang thanh)."""
    tone, n, at = None, 0, -1
    letters = []  # mỗi phần tử là một chữ cái (chữ gốc + dấu mũ/móc), đã bỏ thanh
    for ch in unicodedata.normalize("NFD", word):
        if ch in _TONES:
            tone, n, at = _TONES[ch], n + 1, len(letters) - 1
        elif unicodedata.combining(ch) and letters:
            letters[-1] += ch
        else:
            letters.append(ch)
    letters = [unicodedata.normalize("NFC", x) for x in letters]
    return "".join(letters), tone, n, at


def _tone_on_right_vowel(w: str, at: int) -> bool:
    """Vần có nguyên âm mũ/móc/trăng thì thanh phải nằm trên nguyên âm đó
    ("nhiễm", không phải "nhĩêm"). Kiểu bỏ dấu cũ/mới cho oa, uy… đều nhận."""
    if at < 0:
        return True
    if w[at] not in "aăâeêioôơuưy":
        return False
    return not (_MARKED & set(w)) or w[at] in _MARKED


def is_valid(word: str) -> bool:
    """Một từ (một âm tiết) có đúng khuôn âm tiết tiếng Việt không."""
    w, tone, n, at = _split_tone(word.lower())
    if n > 1 or not w or not _tone_on_right_vowel(w, at):
        return False
    for onset in _ONSETS:
        if not w.startswith(onset):
            continue
        rhyme = w[len(onset):]
        if onset == "qu" and rhyme and rhyme[0] not in "aăâeêiyoơ":
            continue
        if onset == "gi" and not rhyme:
            rhyme = "i"  # "gì" = gi + ì
        if rhyme in _RHYMES:
            if rhyme.endswith(_STOP_CODA) and tone not in ("sac", "nang"):
                continue
            return True
    return False


def _has_vietnamese_letter(word: str) -> bool:
    return any(ord(c) > 127 for c in word)


def page_score(text: str) -> Dict[str, float]:
    """Điểm OCR của một đoạn/trang.

    - judged:  số từ được chấm (từ có chữ Việt có dấu, hoặc từ ASCII hợp lệ)
    - invalid: số từ có dấu tiếng Việt mà không hợp lệ
    - invalid_rate = invalid / judged — càng cao trang càng xấu.
    """
    judged = invalid = 0
    for word in _WORD_RE.findall(text or ""):
        if len(word) > 7:  # âm tiết Việt dài nhất "nghiêng" = 7 chữ
            if _has_vietnamese_letter(word):
                judged += 1
                invalid += 1
            continue
        if is_valid(word):
            judged += 1
        elif _has_vietnamese_letter(word):
            judged += 1
            invalid += 1
    return {"judged": judged, "invalid": invalid,
            "invalid_rate": invalid / judged if judged else 0.0}


def score_pages(items: Iterable[Tuple[tuple, str]]) -> Dict[tuple, float]:
    """Gộp các đoạn theo khoá trang (vd. (doc_name, pdf_page)) -> invalid_rate."""
    tally: Dict[tuple, list] = {}
    for key, text in items:
        s = page_score(text)
        t = tally.setdefault(key, [0, 0])
        t[0] += s["judged"]
        t[1] += s["invalid"]
    return {k: (inv / j if j else 0.0) for k, (j, inv) in tally.items()}
