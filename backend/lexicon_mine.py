# -*- coding: utf-8 -*-
r"""Khai thác chữ viết tắt từ chính kho sách -> hàng chờ bác sĩ duyệt.

    python lexicon_mine.py [--persist-dir <chỉ mục>] [--min-count 2]

Không có từ điển viết tắt lâm sàng tiếng Việt nào có giấy phép để dùng. Nhưng
sách y Việt định nghĩa viết tắt rất đều theo mẫu "cụm đầy đủ (VIẾT TẮT)":
"bệnh phổi tắc nghẽn mạn tính (BPTNMT)", "thuốc chống viêm không steroid
(NSAID)". Và viết tắt tiếng Việt được tạo theo CHỮ CÁI ĐẦU CỦA TỪNG ÂM TIẾT
(Bệnh Phổi Tắc Nghẽn Mạn Tính -> BPTNMT, Đ viết là Đ hoặc D). Tiếng Việt viết
rời từng âm tiết, nên phép khớp chữ đầu ở đây chặt hơn hẳn tiếng Anh, nơi
chữ viết tắt hay lấy chữ ở giữa từ ("CYP" = CYtochrome P450).

Đầu ra: lexicon/abbreviation_candidates.csv (viết tắt, cụm đầy đủ, số lần
gặp, câu ví dụ, sách, trang). Bộ mở rộng truy vấn KHÔNG đọc tệp này — nó chỉ
đọc lexicon/abbreviations.json, nơi mỗi dòng phải được người duyệt đánh dấu
"approved": true. Viết tắt đa nghĩa ("HC" = hội chứng / hồng cầu) sẽ hiện
thành nhiều dòng ứng viên; người duyệt chọn.
"""

import argparse
import csv
import os
import re
import sys
from collections import defaultdict

from text_fold import fold

HERE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES_PATH = os.path.join(HERE, "lexicon", "abbreviation_candidates.csv")

# Từ nối được phép bỏ qua khi khớp chữ đầu ("hội chứng tiết ADH không thích
# hợp" -> SIADH thì không, nhưng "tắc nghẽn của phổi" vẫn được).
_SKIP = {"và", "của", "các", "những", "do", "ở", "the", "of", "and", "in", "to", "for", "by", "with"}

_ABBR_RE = re.compile(r"\(([A-ZĐ][A-ZĐa-z0-9]{1,9})\)")
_WORD_RE = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*|\d+")


def _letters(abbr):
    """Chữ cái của viết tắt, đã fold: 'ĐTĐ' -> 'dtd'. Bỏ chữ số ('COX2')."""
    return [c for c in fold(abbr).lower() if c.isalpha()]


def _initial(word):
    return fold(word[0]).lower() if word else ""


def match_long_form(words, abbr):
    """Tìm cụm cuối cùng của `words` mà chữ đầu từng từ khớp `abbr`.

    Duyệt ngược từ từ gần dấu ngoặc nhất. Trả về cụm (list từ) hoặc None.
    """
    letters = _letters(abbr)
    if len(letters) < 2 or sum(c.isupper() for c in abbr) < 2:
        return None
    i = len(words) - 1
    j = len(letters) - 1
    out = []
    skipped = 0
    while j >= 0 and i >= 0:
        w = words[i]
        if _initial(w) == letters[j]:
            out.append(w)
            j -= 1
        elif w.lower() in _SKIP and out and skipped < 2:
            out.append(w)
            skipped += 1
        else:
            return None
        i -= 1
    if j >= 0:
        return None
    long_form = list(reversed(out))
    if long_form[0].lower() in _SKIP:
        return None
    return long_form


def mine(texts, metas):
    found = defaultdict(lambda: {"count": 0, "example": "", "doc": "", "page": ""})
    for text, meta in zip(texts, metas):
        flat = re.sub(r"\s+", " ", text)
        for m in _ABBR_RE.finditer(flat):
            abbr = m.group(1)
            before = flat[max(0, m.start() - 160):m.start()]
            words = _WORD_RE.findall(before)[-(len(abbr) + 4):]
            long_form = match_long_form(words, abbr)
            if not long_form:
                continue
            key = (abbr, " ".join(long_form).lower())
            row = found[key]
            row["count"] += 1
            if not row["example"]:
                row["example"] = flat[max(0, m.start() - 100):m.end() + 20]
                row["doc"] = meta.get("doc_name", "")
                row["page"] = meta.get("page_num", "")
    return found


def write_candidates(found, min_count, path=CANDIDATES_PATH):
    rows = sorted(((k, v) for k, v in found.items() if v["count"] >= min_count),
                  key=lambda kv: (-kv[1]["count"], kv[0]))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["viet_tat", "cum_day_du", "so_lan", "vi_du", "sach", "trang"])
        for (abbr, long_form), v in rows:
            w.writerow([abbr, long_form, v["count"], v["example"], v["doc"], v["page"]])
    return rows


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--persist-dir", default=None)
    ap.add_argument("--min-count", type=int, default=2)
    args = ap.parse_args()
    import config
    import vector_store
    db = vector_store.VectorStore(args.persist_dir or config.VECTOR_DB_DIR)
    texts, metas, _ids, _bm25 = db._get_corpus_and_bm25()
    rows = write_candidates(mine(texts, metas), args.min_count)
    print(f"{len(rows)} ứng viên -> {CANDIDATES_PATH}")
    for (abbr, long_form), v in rows[:40]:
        print(f"  {abbr:<8} {long_form:<50} x{v['count']}")


if __name__ == "__main__":
    main()
