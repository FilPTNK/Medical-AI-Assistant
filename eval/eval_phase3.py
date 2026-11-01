# -*- coding: utf-8 -*-
"""Đo giai đoạn 3: câu hỏi nhiều điều kiện (query_plan.py).

Chạy:
    python eval/eval_phase3.py --persist-dir <bản sao chỉ mục>

Câu hỏi dựng từ chuyên luận Dược thư thật, mỗi câu hai điều kiện bệnh nhân:

    "liều {thuốc} cho trẻ em suy thận"                 trẻ em + suy thận
    "{thuốc} cho phụ nữ có thai và cho con bú"          có thai + cho con bú
    "{thuốc} cho người cao tuổi suy gan"               cao tuổi + suy gan

Một điều kiện CÓ TRONG SÁCH khi kho có chunk của đúng thuốc, ở một trong các
mục của điều kiện, nhắc tới chính điều kiện đó (cùng phép kiểm chữ với
query_plan.mentions_any). Chỉ chấm các điều kiện có trong sách.

Báo, với kế hoạch TẮT và BẬT:
- recall theo điều kiện:  điều kiện có bằng chứng nằm trong danh sách nguồn
- recall đủ cả hai:       MỌI điều kiện của câu đều có bằng chứng — con số
                          tương ứng 0,54 của GMDS 2025 (cần đủ hai tài liệu)
- số nguồn trung bình:    giá phải trả (mỗi nguồn là một [n] phải đọc)
và, khi BẬT, bảng kiểm báo "thư viện không có" đúng bao nhiêu điều kiện.
"""

import argparse
import os
import random
import re
import sys
import warnings

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))
os.chdir(os.path.join(BASE_DIR, "backend"))
warnings.filterwarnings("ignore")

import config        # noqa: E402
import drug_alias    # noqa: E402
import query_intent  # noqa: E402
import query_plan    # noqa: E402
import vector_store  # noqa: E402

SEED = 5
N_DRUGS = 25
TEMPLATES = [
    ("liều {d} cho trẻ em suy thận", ("child", "renal")),
    ("{d} cho phụ nữ có thai và cho con bú", ("pregnancy", "lactation")),
    ("{d} cho người cao tuổi suy gan", ("elderly", "hepatic")),
]


def supports(meta, text, key, cond):
    _label, sections, terms = query_plan.CONDITIONS[cond]
    return (drug_alias.inn_key(meta.get("generic_name") or "") == key
            and query_intent.section_of(meta) in sections
            and query_plan.mentions_any(query_plan.body_of(text), terms) > 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--persist-dir", default=None)
    args = ap.parse_args()

    db = vector_store.VectorStore(args.persist_dir or config.VECTOR_DB_DIR)
    texts, metas, ids, _ = db._get_corpus_and_bm25()
    by_id = db._lookup["by_id"]

    names = sorted({m["generic_name"] for m in metas
                    if str(m.get("doc_name", "")).startswith("DTQG") and not m.get("name_suspect")
                    and re.fullmatch(r"[A-Za-zÀ-ỹ\- ]{4,}", m.get("generic_name") or "")
                    and len(m["generic_name"].split()) <= 2})
    drugs = random.Random(SEED).sample(names, min(N_DRUGS, len(names)))
    # Điều kiện nào thật sự có trong sách, cho từng thuốc.
    exists = {}
    for t, m in zip(texts, metas):
        key = drug_alias.inn_key(m.get("generic_name") or "")
        for cond in query_plan.CONDITIONS:
            if supports(m, t, key, cond):
                exists[(key, cond)] = True

    cases = []
    for d in drugs:
        key = drug_alias.inn_key(d)
        for pat, conds in TEMPLATES:
            cases.append((pat.format(d=d.lower()), key, conds))
    print(f"{len(cases)} câu hỏi hai điều kiện ({len(drugs)} chuyên luận Dược thư)")

    for label, on in (("kế hoạch TẮT", False), ("kế hoạch BẬT", True)):
        query_plan.ENABLE_QUERY_PLAN = on
        per_cond, all_ok, n_src = [], [], []
        flagged_missing, truly_missing, wrong_missing = 0, 0, 0
        for q, key, conds in cases:
            hits = db.search(q, top_k=5)
            n_src.append(len(hits))
            answerable = [c for c in conds if exists.get((key, c))]
            got = []
            for c in answerable:
                ok = any(supports(metas[by_id[h["id"]]], texts[by_id[h["id"]]], key, c) for h in hits)
                got.append(ok)
                per_cond.append(ok)
            if len(answerable) == len(conds):
                all_ok.append(all(got))
            if on:
                for item in hits.coverage or []:
                    if item["condition"] not in query_plan.CONDITIONS:
                        continue
                    really = exists.get((key, item["condition"]), False)
                    truly_missing += not really
                    if not item["found"]:
                        flagged_missing += 1
                        wrong_missing += really
        print(f"  {label}:  recall theo điều kiện {np.mean(per_cond):6.1%} ({len(per_cond)})   "
              f"đủ cả hai {np.mean(all_ok):6.1%} ({len(all_ok)} câu)   nguồn TB {np.mean(n_src):.1f}")
        if on:
            print(f"     bảng kiểm báo 'thư viện không có': {flagged_missing} điều kiện "
                  f"(thật sự không có: {truly_missing}; báo nhầm: {wrong_missing})")
    query_plan.ENABLE_QUERY_PLAN = True


if __name__ == "__main__":
    main()
