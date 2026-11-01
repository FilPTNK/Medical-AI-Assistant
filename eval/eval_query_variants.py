# -*- coding: utf-8 -*-
"""Đo tra cứu khi bác sĩ gõ KHÔNG DẤU hoặc gõ nhầm TELEX (query_normalize.py).

Chạy:
    python eval/eval_query_variants.py --persist-dir <bản sao chỉ mục>
    python eval/eval_query_variants.py --sweep-folded   # quét trọng số trường gấp dấu

Mỗi truy vấn của bộ chính và bộ giữ riêng được sinh thêm hai biến thể tự động:

- không dấu:  "thuốc hạ sốt"  -> "thuoc ha sot"
- Telex:      "thuốc hạ sốt"  -> "thuoocs haj soots"  (quên bật bộ gõ)

rồi chấm P@5 và MRR qua đúng `VectorStore.search()` mà app dùng, với chuẩn hoá
TẮT và BẬT. Mục tiêu đặt trong báo cáo kỹ thuật: biến thể đạt ≥95% P@5 của bản
có dấu. Bản có dấu thì phải KHÔNG đổi — chuẩn hoá không được làm hỏng truy vấn
vốn đã đúng.

Chấm như eval_run.py: chia cho K, không chia cho số kết quả trả về.
"""

import argparse
import os
import sys
import unicodedata
import warnings

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(BACKEND_DIR)
warnings.filterwarnings("ignore")

import config                # noqa: E402
import vector_store          # noqa: E402
from text_fold import fold   # noqa: E402

TOP_K = 5

_TONE_KEY = {"́": "s", "̀": "f", "̉": "r", "̃": "x", "̣": "j"}
_MARK_KEY = {"̂": None, "̆": "w", "̛": "w"}  # mũ: gấp đôi nguyên âm


def to_telex(text: str) -> str:
    """Gõ lại một câu có dấu theo kiểu Telex khi quên bật bộ gõ."""
    out = []
    for word in text.split(" "):
        tone = ""
        letters = []
        for ch in unicodedata.normalize("NFD", word.lower()):
            if ch in _TONE_KEY:
                tone = _TONE_KEY[ch]
            elif ch in _MARK_KEY:
                key = _MARK_KEY[ch]
                if key is None:
                    letters.append(letters[-1] if letters else "")
                elif not (letters and letters[-1] == "w"):
                    # "ươ" chỉ cần một chữ w sau cụm
                    letters.append(key)
            elif ch == "đ":
                letters.append("dd")
            else:
                letters.append(ch)
        out.append("".join(letters).replace("uwow", "uow") + tone)
    return " ".join(out)


def hit(text, terms):
    low = text.lower()
    return any(t in low for t in terms)


def score(db, queries, transform):
    p5, rr = [], []
    for query, expect, _trap in queries:
        hits = db.search(transform(query), top_k=TOP_K)[:TOP_K]  # bỏ đoạn bằng chứng chèn thêm (query_plan)
        flags = [hit(h.get("child_text") or h.get("text", ""), expect) for h in hits]
        p5.append(sum(flags) / TOP_K)
        rr.append(next((1.0 / (i + 1) for i, f in enumerate(flags) if f), 0.0))
    return np.mean(p5) * 100, np.mean(rr), p5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--persist-dir", default=None)
    ap.add_argument("--sweep-folded", action="store_true")
    ap.add_argument("--show", action="store_true", help="in câu đã chuẩn hoá của từng biến thể")
    args = ap.parse_args()

    import eval_set
    import eval_set_holdout
    sets = [("BỘ CHÍNH", eval_set.QUERIES), ("BỘ GIỮ RIÊNG", eval_set_holdout.QUERIES)]

    db = vector_store.VectorStore(args.persist_dir or config.VECTOR_DB_DIR)
    db._get_corpus_and_bm25()
    print(f"chỉ mục: {db.persist_dir}\n")

    variants = [("có dấu", lambda q: q), ("không dấu", fold), ("Telex", to_telex)]

    for name, queries in sets:
        print("=" * 72)
        print(f"{name} ({len(queries)} truy vấn)")
        print("=" * 72)
        print(f"  {'biến thể':<10} {'chuẩn hoá':<10} {'P@5':>7} {'MRR':>6}")
        base = None
        for label, fn in variants:
            for on in (False, True):
                vector_store.ENABLE_QUERY_NORMALIZATION = on
                p, mrr, _ = score(db, queries, fn)
                if label == "có dấu" and on:
                    base = p
                rel = f"  ({p / base:.0%} bản có dấu)" if base and label != "có dấu" and on else ""
                print(f"  {label:<10} {'BẬT' if on else 'tắt':<10} {p:6.1f}% {mrr:6.3f}{rel}")
        vector_store.ENABLE_QUERY_NORMALIZATION = True

        if args.show:
            for query, _, _ in queries:
                for label, fn in variants[1:]:
                    n = db._lexicon.normalize(fn(query))
                    mark = "" if fold(n.text) == fold(query) and n.text.lower() == query.lower() else "  ≠"
                    print(f"    {label:<9} {fn(query)!r:42} -> {n.text!r}{mark}")

        if args.sweep_folded:
            print("\n  quét trọng số trường gấp dấu (biến thể không dấu, chuẩn hoá BẬT):")
            for w in [0.0, 0.5, 1.0, 1.5]:
                vector_store.RRF_W_FOLDED = w
                p, mrr, _ = score(db, queries, fold)
                print(f"    w_folded={w:<4} P@5={p:5.1f}%  MRR={mrr:.3f}")
            vector_store.RRF_W_FOLDED = 1.0
        print()


if __name__ == "__main__":
    main()
