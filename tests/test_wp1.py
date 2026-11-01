"""Kiểm tra WP1 bằng giả lập; chạy được với pytest hoặc unittest, không cần Chroma/torch."""
import importlib
import sys
import tempfile
import threading
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import numpy

ROOT = str(Path(__file__).resolve().parents[1] / "backend")


class FakeChroma:
    instances = 0
    rows = []

    def __init__(self, **kwargs):
        type(self).instances += 1
        self._embedding_function = kwargs.get("embedding_function")

    def get(self, where=None, include=None, limit=500, offset=0):
        rows = self.rows
        if where:
            rows = [r for r in rows if all(r[2].get(k) == v for k, v in where.items())]
        rows = rows[offset:offset + limit]
        return {"ids": [r[0] for r in rows],
                "documents": [r[1] for r in rows] if "documents" in (include or []) else [],
                "metadatas": [r[2] for r in rows] if "metadatas" in (include or []) else []}

    def similarity_search_by_vector_with_relevance_scores(self, *args, **kwargs):
        return []


class FakeEmbedding:
    def __init__(self, **kwargs):
        raise RuntimeError("model absent")


class WP1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, ROOT)
        cls.modules = {
            "config": types.SimpleNamespace(EMBEDDING_MODEL="fake"),
            "documents": types.SimpleNamespace(load_manifest=lambda name: {}),
            "langchain_chroma": types.SimpleNamespace(Chroma=FakeChroma),
            "langchain_huggingface": types.SimpleNamespace(HuggingFaceEmbeddings=FakeEmbedding),
            "langchain_core": types.ModuleType("langchain_core"),
            "langchain_core.documents": types.SimpleNamespace(Document=object),
        }
        cls.patcher = patch.dict(sys.modules, cls.modules)
        cls.patcher.start()
        cls.vs = importlib.import_module("vector_store")

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()
        sys.modules.pop("vector_store", None)
        sys.path.remove(ROOT)

    def setUp(self):
        FakeChroma.instances = 0
        FakeChroma.rows = []
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = self.vs.VectorStore(self.tmp.name)

    def seed(self, n):
        FakeChroma.rows = [(f"id{i}", "thuoc abc" if i == 0 else f"van ban {i}",
                            {"doc_type": "child", "doc_name": "sach", "page_num": i + 1,
                             "chunk_id": f"chunk{i}"}) for i in range(n)]

    def test_bm25_when_embedding_missing(self):
        # 30, không phải 2: rank_bm25 thật (không phải FallbackBM25 dự phòng)
        # tính điểm bằng IDF — với kho chỉ 2 tài liệu mà 1 tài liệu chứa từ
        # khoá, IDF của chính từ đó suýt bằng 0 nên get_scores() trả toàn số
        # ~0 và get_scores <= 0.0 bị lọc mất ở search(), ra kết quả rỗng dù
        # logic suy giảm (degraded/status) đúng. Không phải lỗi của search().
        self.seed(30)
        hits = self.db.search("thuoc abc")
        self.assertTrue(hits)
        self.assertTrue(hits.degraded)
        self.assertEqual(hits.status, "EMBEDDING_UNAVAILABLE")
        self.assertEqual(hits[0]["id"], "id0")

    def test_excluded_docs_never_returned(self):
        # Hai tài liệu cùng chứa từ khoá; tài liệu riêng của người khác phải
        # biến mất ở cả nhánh BM25 lẫn bộ lọc gửi xuống Chroma.
        self.seed(30)
        FakeChroma.rows.append(("rieng0", "thuoc abc rieng",
                                {"doc_type": "child", "doc_name": "rieng-b.pdf", "page_num": 1,
                                 "chunk_id": "rieng0"}))
        self.assertIn("rieng-b.pdf", {h["doc_name"] for h in self.db.search("thuoc abc")})
        hits = self.db.search("thuoc abc", exclude_doc_names={"rieng-b.pdf"})
        self.assertTrue(hits)
        self.assertNotIn("rieng-b.pdf", {h["doc_name"] for h in hits})
        seen = {}
        self.db._embedding = types.SimpleNamespace(embed_query=lambda q: [0.1])
        with patch.object(FakeChroma, "similarity_search_by_vector_with_relevance_scores",
                          lambda _self, *a, **kw: seen.update(kw) or []):
            self.db.search("thuoc abc", exclude_doc_names={"rieng-b.pdf"})
        self.assertEqual(seen["filter"], {"doc_name": {"$nin": ["rieng-b.pdf"]}})
        # Đối chiếu trỏ thẳng vào tài liệu bị ẩn thì không trả gì.
        self.assertEqual(self.db.search("thuoc abc", doc_names=["rieng-b.pdf"],
                                        exclude_doc_names={"rieng-b.pdf"}), [])

    def test_empty_index_and_no_match_are_distinct(self):
        with self.assertRaises(self.vs.EmptyIndex) as err:
            self.db.search("abc")
        self.assertEqual(err.exception.code, "EMPTY_INDEX")
        self.seed(1)
        hits = self.db.search("zzzzzz")
        self.assertEqual(hits.status, "EMBEDDING_UNAVAILABLE")
        self.assertEqual(hits, [])
        # NO_MATCH khi dense sẵn sàng nhưng cả hai nhánh đều không có kết quả.
        self.db._embedding = types.SimpleNamespace(embed_query=lambda q: [0.1])
        hits = self.db.search("zzzzzz")
        self.assertEqual(hits.status, "NO_MATCH")

    def test_db_init_once_under_threads(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            handles = list(pool.map(lambda _: self.db.db, range(2)))
        self.assertIs(handles[0], handles[1])
        self.assertEqual(FakeChroma.instances, 1)

    def test_batches_have_all_ids_at_boundaries(self):
        for n in (0, 499, 500, 501, 1000):
            self.seed(n)
            rows = self.db._get_batched(include=["documents", "metadatas"])
            self.assertEqual(rows["ids"], [f"id{i}" for i in range(n)])
            self.assertEqual(len(rows["documents"]), n)
            self.assertEqual(len(rows["metadatas"]), n)

    def test_cache_roundtrip_and_changed_corpus(self):
        self.seed(2)
        self.db._get_corpus_and_bm25()
        other = self.vs.VectorStore(self.tmp.name)
        with patch.object(other, "_get_all_child_chunks", side_effect=AssertionError("cache miss")):
            texts, _, ids, _ = other._get_corpus_and_bm25()
        self.assertEqual(ids, ["id0", "id1"])
        self.seed(3)
        changed = self.vs.VectorStore(self.tmp.name)
        self.assertEqual(len(changed._get_corpus_and_bm25()[0]), 3)


if __name__ == "__main__":
    unittest.main()
