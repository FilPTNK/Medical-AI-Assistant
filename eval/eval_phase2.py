# -*- coding: utf-8 -*-
"""Đo giai đoạn 2: tên thuốc (drug_alias.py) + mục chuyên luận (query_intent.py).

Chạy:
    python eval/eval_phase2.py --persist-dir <bản sao chỉ mục>
    python eval/eval_phase2.py --sweep-focus      # quét trọng số kênh trọng tâm
    python eval/eval_phase2.py --collisions       # bộ gấp INN có gộp nhầm hai chuyên luận không

Ba phép đo, đều chấm bằng METADATA của chunk chứ không bằng chữ — nên không
phụ thuộc vào việc ai viết từ khoá "đúng":

1. ĐÚNG MỤC CỦA ĐÚNG THUỐC. Lấy ngẫu nhiên (hạt cố định) các chuyên luận Dược
   thư có đủ tám mục, hỏi tám ý định bằng hai bộ câu mẫu: bộ A (dùng khi viết
   từ kích hoạt) và bộ B (cách hỏi khác hẳn, viết riêng để kiểm quá khớp). Một
   kết quả đúng khi chunk thuộc đúng thuốc VÀ đúng mục. Báo P@5 và Hit@1.

2. BA CÁCH GỌI MỘT THUỐC. Cùng một chuyên luận, hỏi bằng tên Việt (Dược thư),
   tên quốc tế, và biệt dược. Mục tiêu: P@5 của ba dạng bằng nhau. Kết quả
   đúng khi chunk thuộc đúng thuốc (mọi mục).

3. HỒI QUY. Bộ chính và bộ giữ riêng cũ (eval_set*.py) — không được tụt.

Mỗi phép đo chạy bốn cấu hình: tắt hết / chỉ tên thuốc / chỉ mục / bật cả hai.
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
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(BACKEND_DIR)
warnings.filterwarnings("ignore")

import config          # noqa: E402
import drug_alias      # noqa: E402
import query_intent    # noqa: E402
import vector_store    # noqa: E402

TOP_K = 5
SEED = 7
N_DRUGS = 30

INTENT_FIELDS = {
    "dosage": {"DOSAGE"},
    "contraindication": {"CONTRAINDICATION"},
    "adr": {"ADR", "ADR_MANAGEMENT"},
    "interaction": {"INTERACTION", "INCOMPATIBILITY"},
    "pregnancy": {"PREGNANCY"},
    "lactation": {"LACTATION"},
    "overdose": {"OVERDOSE"},
    "indications": {"INDICATIONS"},
}

TEMPLATES_A = {
    "dosage": ["liều dùng {d}", "{d} liều bao nhiêu"],
    "contraindication": ["chống chỉ định của {d}"],
    "adr": ["tác dụng phụ của {d}"],
    "interaction": ["{d} tương tác với thuốc nào"],
    "pregnancy": ["{d} có dùng được cho phụ nữ có thai không"],
    "lactation": ["{d} khi cho con bú"],
    "overdose": ["quá liều {d}"],
    "indications": ["chỉ định của {d}"],
}

# Viết riêng, không dùng khi chọn từ kích hoạt: cách hỏi đời thường hơn.
TEMPLATES_B = {
    "dosage": ["người lớn uống {d} mấy viên một ngày"],
    "contraindication": ["trường hợp nào không được dùng {d}"],
    "adr": ["{d} có những phản ứng có hại gì"],
    "interaction": ["uống {d} chung với thuốc khác có sao không"],
    "pregnancy": ["bà bầu uống {d} được không"],
    "lactation": ["mẹ đang cho bú có uống {d} được không"],
    "overdose": ["uống nhầm quá nhiều {d} thì xử trí sao"],
    "indications": ["{d} dùng để trị bệnh gì"],
}

CONFIGS = [
    ("tắt hết", False, False),
    ("chỉ tên thuốc", True, False),
    ("chỉ mục", False, True),
    ("bật cả hai", True, True),
]


def set_config(linking, routing):
    vector_store.ENABLE_ENTITY_LINKING = linking
    query_intent.ENABLE_SECTION_ROUTING = routing


def clean_name(name):
    return bool(re.fullmatch(r"[A-Za-zÀ-ỹ\- ]{4,}", name or "")) and len(name.split()) <= 2


def pick_drugs(metas):
    """Chuyên luận Dược thư (tên sạch) có đủ tám mục."""
    sections = {}
    for m in metas:
        if not str(m.get("doc_name", "")).startswith("DTQG") or m.get("name_suspect"):
            continue
        g = m.get("generic_name") or ""
        if not clean_name(g):
            continue
        sections.setdefault(g, set()).add(query_intent.section_of(m))
    need = set().union(*INTENT_FIELDS.values()) - {"ADR_MANAGEMENT", "INCOMPATIBILITY"}
    ok = sorted(g for g, s in sections.items() if need <= s)
    rng = random.Random(SEED)
    return rng.sample(ok, min(N_DRUGS, len(ok))), len(ok)


def meta_of(db, hit):
    idx = db._lookup["by_id"][hit["id"]]
    return db._corpus_cache[1][idx]


def run_queries(db, items, judge, n_relevant=None):
    """items: [(query, target)] -> (P@5 %, Hit@1 %, P@5 chuẩn hoá %).

    P@5 chuẩn hoá chia cho min(5, số chunk đúng có trong kho): mục "Quá liều"
    của một thuốc thường chỉ có 1–2 chunk, nên P@5 thường không bao giờ lên
    được 100% dù xếp hạng hoàn hảo.
    """
    p5, h1, pn = [], [], []
    for query, target in items:
        hits = db.search(query, top_k=TOP_K)[:TOP_K]  # bỏ đoạn bằng chứng chèn thêm (query_plan)
        flags = [judge(meta_of(db, h), target) for h in hits]
        p5.append(sum(flags) / TOP_K)
        h1.append(1.0 if flags and flags[0] else 0.0)
        if n_relevant is not None:
            pn.append(sum(flags) / max(1, min(TOP_K, n_relevant(target))))
    return np.mean(p5) * 100, np.mean(h1) * 100, (np.mean(pn) * 100 if pn else float("nan"))


def section_items(drugs, templates):
    items = []
    for d in drugs:
        for intent, pats in templates.items():
            for pat in pats:
                items.append((pat.format(d=d.lower()), (drug_alias.inn_key(d), intent)))
    return items


def judge_section(meta, target):
    key, intent = target
    return (drug_alias.inn_key(meta.get("generic_name") or "") == key
            and query_intent.section_of(meta) in INTENT_FIELDS[intent])


def relevant_counter(metas):
    counts = {}
    for m in metas:
        key = (drug_alias.inn_key(m.get("generic_name") or ""), query_intent.section_of(m))
        counts[key] = counts.get(key, 0) + 1

    def n_relevant(target):
        key, intent = target
        return sum(counts.get((key, f), 0) for f in INTENT_FIELDS[intent])
    return n_relevant


def judge_entity(meta, target):
    return drug_alias.inn_key(meta.get("generic_name") or "") in target


def name_form_items(db, metas):
    """Ba dạng tên cho cùng chuyên luận Dược thư: Việt / quốc tế / biệt dược."""
    store = db._alias_store
    intl = {}
    for m in metas:
        if str(m.get("doc_name", "")).startswith("DTQG") and m.get("intl_name"):
            g = m["generic_name"]
            if clean_name(g) and clean_name(m["intl_name"]):
                intl[g] = m["intl_name"]
    # chỉ giữ thuốc mà tên quốc tế VIẾT KHÁC tên Việt — chỗ cần bộ gấp INN
    differ = sorted(g for g, n in intl.items()
                    if drug_alias.tokens(g) != drug_alias.tokens(n))
    brands = {}
    for akey, targets in store.alias.items():
        if len(targets) != 1 or len(akey) != 1 or set(targets.values()) != {"brand"}:
            continue
        ent = next(iter(targets))
        brands.setdefault(ent, []).append(akey[0])
    rng = random.Random(SEED)
    vi, en, br = [], [], []
    for g in rng.sample(differ, min(40, len(differ))):
        key = drug_alias.inn_key(g)
        target = {key}
        vi.append((f"liều {g.lower()}", target))
        en.append((f"liều {intl[g].lower()}", target))
        if brands.get(key):
            br.append((f"liều {sorted(brands[key])[0]}", target))
    return vi, en, br, len(differ)


def regression_items():
    import eval_set
    import eval_set_holdout
    return [("bộ chính", eval_set.QUERIES), ("bộ giữ riêng", eval_set_holdout.QUERIES)]


def regression(db, queries):
    p5 = []
    for query, expect, _trap in queries:
        hits = db.search(query, top_k=TOP_K)[:TOP_K]  # bỏ đoạn bằng chứng chèn thêm (query_plan)
        flags = [any(t in (h.get("child_text") or h.get("text", "")).lower() for t in expect) for h in hits]
        p5.append(sum(flags) / TOP_K)
    return np.mean(p5) * 100


def collisions(metas):
    by_key = {}
    for m in metas:
        if str(m.get("doc_name", "")).startswith("DTQG"):
            by_key.setdefault(drug_alias.inn_key(m["generic_name"]), set()).add(m["generic_name"])
    bad = [sorted(v) for v in by_key.values() if len(v) > 1]
    print(f"khoá INN: {len(by_key)} chuyên luận Dược thư, {len(bad)} khoá gộp nhiều chuyên luận")
    for b in bad:
        print("   ", b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--persist-dir", default=None)
    ap.add_argument("--sweep-focus", action="store_true")
    ap.add_argument("--collisions", action="store_true")
    ap.add_argument("--skip-regression", action="store_true")
    ap.add_argument("--focus-weight", type=float, default=None, help="đặt RRF_W_FOCUS cho cả lần chạy")
    args = ap.parse_args()
    if args.focus_weight is not None:
        vector_store.RRF_W_FOCUS = args.focus_weight
        print(f"RRF_W_FOCUS = {args.focus_weight}")

    db = vector_store.VectorStore(args.persist_dir or config.VECTOR_DB_DIR)
    db._get_corpus_and_bm25()
    metas = db._corpus_cache[1]
    print(f"chỉ mục: {db.persist_dir}  ({len(metas)} chunk)\n")

    if args.collisions:
        collisions(metas)
        return

    drugs, pool = pick_drugs(metas)
    print(f"1. ĐÚNG MỤC CỦA ĐÚNG THUỐC — {len(drugs)}/{pool} chuyên luận Dược thư có đủ tám mục")
    sets = [("bộ A", section_items(drugs, TEMPLATES_A)), ("bộ B (cách hỏi khác)", section_items(drugs, TEMPLATES_B))]
    n_rel = relevant_counter(metas)
    for name, items in sets:
        print(f"   {name}: {len(items)} câu")
        for label, linking, routing in CONFIGS:
            set_config(linking, routing)
            p, h, pn = run_queries(db, items, judge_section, n_rel)
            print(f"     {label:<14} P@5 {p:5.1f}%   P@5 chuẩn hoá {pn:5.1f}%   Hit@1 {h:5.1f}%")
    set_config(True, True)

    if args.sweep_focus:
        print("\n   quét trọng số kênh trọng tâm (bật cả hai):")
        for w in [0.5, 1.0, 1.5, 2.0, 3.0]:
            vector_store.RRF_W_FOCUS = w
            row = []
            for name, items in sets:
                p, h, pn = run_queries(db, items, judge_section, n_rel)
                row.append(f"{name.split()[1]}: P@5cH {pn:5.1f}% Hit@1 {h:5.1f}%")
            print(f"     w={w:<4} " + "   ".join(row))
        vector_store.RRF_W_FOCUS = args.focus_weight or 2.0

    vi, en, br, n_differ = name_form_items(db, metas)
    print(f"\n2. BA CÁCH GỌI MỘT THUỐC — {len(vi)} chuyên luận có tên quốc tế viết khác ({n_differ} trong kho), "
          f"{len(br)} có biệt dược trong sách")
    for label, linking, routing in CONFIGS:
        set_config(linking, routing)
        cells = []
        for form, items in (("tên Việt", vi), ("tên quốc tế", en), ("biệt dược", br)):
            if items:
                p, h, _ = run_queries(db, items, judge_entity)
                cells.append(f"{form} {p:5.1f}%")
        print(f"     {label:<14} " + "   ".join(cells))
    set_config(True, True)

    if not args.skip_regression:
        print("\n3. HỒI QUY — bộ truy vấn cũ (P@5 theo từ khoá)")
        for name, queries in regression_items():
            cells = []
            for label, linking, routing in (CONFIGS[0], CONFIGS[3]):
                set_config(linking, routing)
                cells.append(f"{label} {regression(db, queries):5.1f}%")
            print(f"     {name:<13} " + "   ".join(cells))
        set_config(True, True)


if __name__ == "__main__":
    main()
