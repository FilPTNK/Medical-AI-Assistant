# -*- coding: utf-8 -*-
"""Đo tô sáng câu trích trên ảnh trang (page_locate.py): có neo bằng con số hay không.

Chạy:
    python eval/eval_locate.py --cache-dir <thư mục nháp> [--pages 30]

Lấy ngẫu nhiên (hạt cố định) các chunk "Liều lượng và cách dùng" của Dược
thư, OCR lại trang của chúng thành từ + hộp bao (cache vào --cache-dir, KHÔNG
ghi vào data/page_words), rồi tô từng câu có con số của chunk — đúng loại câu
mà khối trích nguyên văn (query_plan.py) đưa cho bác sĩ bấm.

Chấm, cho từng câu:
- tô được:        trả về ít nhất một hộp
- neo đúng số:    vùng tô chứa MỌI con số của câu trích (dạng đã gấp dấu).
                  Đây là thước đo chính: tô ra mà lệch sang câu khác có chữ
                  giống nhưng số khác là tô SAI, tệ hơn không tô.
- tô lệch:        tô được nhưng không chứa đủ số.
"""

import argparse
import os
import random
import re
import sys
import warnings

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))
os.chdir(os.path.join(BASE_DIR, "backend"))
warnings.filterwarnings("ignore")

import config        # noqa: E402
import page_locate   # noqa: E402
import query_plan    # noqa: E402
import text_fold     # noqa: E402
import vector_store  # noqa: E402
import vi_syllable   # noqa: E402

SEED = 11


_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def numbers(text):
    """Các con số của một đoạn — không phụ thuộc cách tách token của page_locate,
    để hai cách tô được chấm bằng cùng một thước."""
    return set(_NUM.findall(text))


def judge(words, sentence, result):
    if not result["rects"]:
        return "miss"
    a, b = result["span"]
    span_nums = numbers(" ".join(w["t"] for w in words[a:b + 1]))
    return "ok" if numbers(sentence) <= span_nums else "wrong"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--persist-dir", default=None)
    ap.add_argument("--pages", type=int, default=30)
    args = ap.parse_args()
    page_locate.PAGE_WORDS_DIR = args.cache_dir

    db = vector_store.VectorStore(args.persist_dir or config.VECTOR_DB_DIR)
    texts, metas, _ids, _ = db._get_corpus_and_bm25()
    by_page, page_text = {}, {}
    for t, m in zip(texts, metas):
        page_text.setdefault((m.get("doc_name"), int(m.get("pdf_page") or 0)), []).append(t)
        if str(m.get("doc_name", "")).startswith("DTQG") and m.get("field_type") == "DOSAGE":
            by_page.setdefault((m["doc_name"], int(m.get("pdf_page") or 0)), []).append(t)
    pages = sorted(k for k in by_page if k[1] > 0)
    pages = random.Random(SEED).sample(pages, min(args.pages, len(pages)))

    cases = []
    for n, (doc, pdf_page) in enumerate(pages, 1):
        try:
            words = page_locate.page_words(doc, pdf_page)["words"]
        except Exception as e:  # thiếu PDF gốc, trang ngoài khổ…
            print(f"  bỏ {doc} tr.{pdf_page}: {e}")
            continue
        for chunk in by_page[(doc, pdf_page)]:
            for s in query_plan.sentences(query_plan.body_of(chunk)):
                if numbers(s) and len(s) <= 320:
                    cases.append((words, s, (doc, pdf_page)))
        print(f"\r  OCR {n}/{len(pages)} trang, {len(cases)} câu", end="", flush=True)
    print()

    for label, on in (("chỉ chữ (cũ)", False), ("neo bằng số", True)):
        page_locate.ANCHOR_NUMBERS = on
        tally = {"ok": 0, "wrong": 0, "miss": 0}
        per_page = {}
        for words, s, key in cases:
            verdict = judge(words, s, page_locate.locate(words, s))
            tally[verdict] += 1
            per_page.setdefault(key, []).append(verdict == "ok")
        n = max(1, len(cases))
        print(f"  {label:<14} neo đúng số {tally['ok'] / n:6.1%}   tô lệch {tally['wrong'] / n:6.1%}   "
              f"không tô {tally['miss'] / n:6.1%}   ({len(cases)} câu)")
    page_locate.ANCHOR_NUMBERS = True
    quality_report(per_page, page_text)


def _ranks(x):
    order = sorted(range(len(x)), key=lambda i: x[i])
    r = [0.0] * len(x)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and x[order[j + 1]] == x[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2
        i = j + 1
    return r


def quality_report(per_page, page_text):
    """Điểm âm tiết của trang (vi_syllable, tính trên chữ OCR đã lập chỉ mục) có
    dự báo được trang nào tô câu hỏng không."""
    keys = [k for k in per_page if k in page_text]
    rate = [vi_syllable.page_score(" ".join(page_text[k]))["invalid_rate"] for k in keys]
    ok = [sum(per_page[k]) / len(per_page[k]) for k in keys]
    ra, rb = _ranks(rate), _ranks(ok)
    n = len(keys)
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((a - ma) * (b - mb) for a, b in zip(ra, rb))
    sd = (sum((a - ma) ** 2 for a in ra) * sum((b - mb) ** 2 for b in rb)) ** 0.5
    rho = cov / sd if sd else 0.0
    cut = sorted(rate)[n // 2]
    hi = [o for r, o in zip(rate, ok) if r > cut]
    lo = [o for r, o in zip(rate, ok) if r <= cut]
    print(f"  điểm âm tiết ↔ tô đúng theo trang: Spearman ρ = {rho:+.2f} ({n} trang)")
    print(f"     nửa trang âm tiết tốt: tô đúng {sum(lo) / max(1, len(lo)):6.1%} ({len(lo)} trang)   "
          f"nửa xấu: {sum(hi) / max(1, len(hi)):6.1%} ({len(hi)} trang)")


if __name__ == "__main__":
    main()
