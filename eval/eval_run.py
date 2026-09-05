# -*- coding: utf-8 -*-
"""Chấm P@5 cho ba nhánh truy xuất: BM25, DENSE, RRF.

Chạy:
    python eval/eval_run.py                 # cả hai bộ truy vấn
    python eval/eval_run.py --set main      # chỉ bộ chính
    python eval/eval_run.py --sweep         # quét trọng số RRF

Đo cả ba nhánh vì một thay đổi có thể cải thiện nhánh này mà làm hỏng nhánh kia —
đúng như trường hợp tách từ pyvi: nó nâng BM25 nhưng không đụng gì tới dense.

CHIA CHO K, KHÔNG CHIA CHO SỐ KẾT QUẢ TRẢ VỀ. BM25 có thể trả ít hơn 5 chunk khi
truy vấn được tách thành một từ ghép hiếm ("thuốc ho" -> "thuốc_ho" chỉ khớp 1
chunk). Chia cho len(kết quả) sẽ chấm 1/1 = 100% cho đúng cái trường hợp tệ nhất,
tức là thưởng cho việc không tìm ra gì. Một phiên trước đã dính đúng lỗi này.
"""

import argparse
import os
import sys
import time
import warnings

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(BACKEND_DIR)

warnings.filterwarnings("ignore")

import config                                    # noqa: E402
from vector_store import (  # noqa: E402
    VectorStore,
    tokenize_text,
    expand_rare_compounds,
    RRF_K,
    RRF_W_SPARSE,
    RRF_W_DENSE,
)

TOP_K = 5
K_CAND = TOP_K * 4


def hit(text: str, terms) -> bool:
    low = text.lower()
    return any(t in low for t in terms)


class Harness:
    """Lấy ranking dense/sparse thô một lần cho mỗi truy vấn, rồi trộn lại nhiều kiểu.

    Tách hẳn phần lấy ứng viên khỏi phần hợp nhất để quét tham số không phải
    gọi lại Chroma — quét 40 cấu hình mất vài giây thay vì vài phút.
    """

    def __init__(self, persist_dir=None):
        self.db = VectorStore(persist_dir or config.VECTOR_DB_DIR)
        print(f"chỉ mục: {self.db.persist_dir}")
        print(f"model  : {self.db.embedding_model}")
        t0 = time.perf_counter()
        self.texts, self.metas, self.ids, self.bm25 = self.db._get_corpus_and_bm25()
        print(f"nạp corpus: {time.perf_counter() - t0:.1f}s | {len(self.texts)} chunk\n")
        self.by_id = {d: i for i, d in enumerate(self.ids)}
        self.by_chunk_id = {
            m.get("chunk_id"): i for i, m in enumerate(self.metas) if m.get("chunk_id")
        }
        self.by_text = {t: i for i, t in enumerate(self.texts)}
        self._cache = {}

    def rankings(self, query: str):
        if query in self._cache:
            return self._cache[query]

        dense = []
        for doc, _ in self.db.db.similarity_search_with_relevance_scores(query, k=K_CAND):
            cid = doc.metadata.get("chunk_id") if doc.metadata else None
            idx = self.by_chunk_id.get(cid, -1) if cid else -1
            if idx == -1:
                idx = self.by_text.get(doc.page_content, -1)
            if idx != -1:
                dense.append(self.ids[idx])

        # Đi đúng đường mà search() đi, kể cả bước mở rộng từ ghép hiếm —
        # nếu không thì bộ đo chấm một hệ thống khác với hệ thống chạy thật.
        query_tokens = expand_rare_compounds(tokenize_text(query), self.db._doc_freq or {})
        scores = self.bm25.get_scores(query_tokens)
        sparse = []
        for idx in np.argsort(scores)[::-1]:
            if scores[idx] <= 0.0:
                break
            sparse.append(self.ids[idx])
            if len(sparse) >= K_CAND:
                break

        self._cache[query] = (dense, sparse)
        return dense, sparse

    def top(self, query, mode, w_sparse=RRF_W_SPARSE, w_dense=RRF_W_DENSE, k=RRF_K):
        dense, sparse = self.rankings(query)
        if mode == "bm25":
            ranked = sparse[:TOP_K]
        elif mode == "dense":
            ranked = dense[:TOP_K]
        else:
            fused = {}
            for rank, doc_id in enumerate(dense):
                fused[doc_id] = fused.get(doc_id, 0.0) + w_dense / (k + rank + 1)
            for rank, doc_id in enumerate(sparse):
                fused[doc_id] = fused.get(doc_id, 0.0) + w_sparse / (k + rank + 1)
            ranked = [i for i, _ in sorted(fused.items(), key=lambda x: -x[1])[:TOP_K]]
        return [self.texts[self.by_id[i]] for i in ranked]

    def score(self, queries, mode, **kw):
        precision, traps = [], []
        for query, expect, trap in queries:
            top = self.top(query, mode, **kw)
            # Chia cho TOP_K: trả về ít hơn 5 chunk là một thất bại, không phải
            # một mẫu số nhỏ hơn.
            precision.append(sum(hit(t, expect) for t in top) / TOP_K)
            traps.append(sum(hit(t, trap) for t in top) / TOP_K if trap else 0.0)
        return np.mean(precision) * 100, np.mean(traps) * 100, precision


def load_sets(which):
    import eval_set
    import eval_set_holdout

    sets = []
    if which in ("main", "both"):
        sets.append(("BỘ CHÍNH — truy vấn từ khoá", eval_set.QUERIES))
    if which in ("holdout", "both"):
        sets.append(("BỘ GIỮ RIÊNG — câu hỏi tự nhiên", eval_set_holdout.QUERIES))
    return sets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["main", "holdout", "both"], default="both")
    ap.add_argument("--sweep", action="store_true", help="quét trọng số RRF")
    ap.add_argument(
        "--persist-dir",
        default=None,
        help="Chỉ mục cần chấm (mặc định: chỉ mục đang chạy). Dùng để đối chiếu "
             "một chỉ mục dựng thử với chỉ mục hiện hành.",
    )
    args = ap.parse_args()

    h = Harness(args.persist_dir)

    for name, queries in load_sets(args.set):
        print("=" * 64)
        print(name)
        print("=" * 64)
        rows = []
        for label, mode in [("BM25", "bm25"), ("DENSE", "dense"), ("RRF", "rrf")]:
            p, t, per = h.score(queries, mode)
            rows.append((label, per))
            print(f"  {label:<6} P@5 = {p:5.1f}%   bẫy-nhầm = {t:4.1f}%")

        print(f"\n  chi tiết RRF (w_bm25={RRF_W_SPARSE}, k={RRF_K}):")
        per = dict(rows)["RRF"]
        for (query, _, _), v in zip(queries, per):
            print(f"    {v * 100:5.1f}%  {query}")

        if args.sweep:
            print(f"\n  quét trọng số BM25 (w_dense=1.0, k={RRF_K}):")
            print(f"    {'w_bm25':>7} {'P@5':>7} {'bẫy':>6}")
            for w in [1.0, 1.2, 1.5, 2.0, 3.0]:
                p, t, _ = h.score(queries, "rrf", w_sparse=w)
                print(f"    {w:7.2f} {p:6.1f}% {t:5.1f}%")
        print()


if __name__ == "__main__":
    main()
