import os
import re
import math
import time
import threading
import numpy as np
from typing import List, Dict, Any, Optional
from collections import Counter

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document

import config
import documents

# 1. Tách token cho BM25 (dùng chung cho corpus và truy vấn)

# Đổi chuỗi này khi thay cách tách từ — cache token trên đĩa sẽ tự dựng lại.
SEGMENTER_VERSION = "pyvi-1"

try:
    from pyvi import ViTokenizer as _ViTokenizer
except Exception:  # pyvi chưa cài -> vẫn chạy được, chỉ kém chính xác hơn
    _ViTokenizer = None


def tokenize_text(text: str) -> List[str]:
    r"""Tách văn bản thành token cho BM25, có gộp từ ghép tiếng Việt.

    Tiếng Việt phân tách theo âm tiết, nên cắt theo khoảng trắng sẽ xé từ ghép:
    "hạ sốt" -> ["hạ", "sốt"] và "sốt rét" -> ["sốt", "rét"]. Hai khái niệm
    khác hẳn nhau lại dùng chung token "sốt", nên truy vấn "thuốc hạ sốt" kéo
    lên toàn thuốc sốt rét — đo được P@5 chỉ 40% cho truy vấn đó.

    pyvi nối từ ghép bằng dấu gạch dưới ("hạ_sốt", "sốt_rét"), mà `\w+` coi
    "_" là ký tự chữ nên hai từ thành hai token riêng biệt, không còn trùng.

    Chọn pyvi thay vì underthesea vì underthesea vẫn tách "hạ sốt" thành hai
    âm tiết — tức là không sửa được đúng lỗi này — và chậm hơn 2,7 lần.
    """
    if _ViTokenizer is not None:
        try:
            text = _ViTokenizer.tokenize(text)
        except Exception:
            # Văn bản OCR lỗi có thể làm model tách từ ngã; thà mất phần gộp
            # từ ghép của một chunk còn hơn hỏng cả lần dựng chỉ mục.
            pass
    return re.findall(r'\w+', text.lower())

# Ngưỡng "từ ghép hiếm": token ghép xuất hiện ở ít hơn ngần này chunk thì
# truy vấn được bổ sung thêm các âm tiết của nó.
#
# Phải thấp hơn hẳn df của những từ ghép mà #3 cần giữ nguyên — "hạ_sốt" có
# df=22, "sốt_rét" df=107. Đo được: ngưỡng 5–20 đều cho P@5 100% trên bộ chính;
# từ 50 trở lên thì "hạ_sốt" cũng bị tách và va chạm "sốt" quay lại, tụt còn 96%.
RARE_COMPOUND_MIN_DF = 10


def expand_rare_compounds(tokens: List[str], doc_freq: Dict[str, int]) -> List[str]:
    """Bổ sung âm tiết cho những token ghép gần như không khớp chunk nào.

    pyvi gộp từ ghép để "hạ_sốt" và "sốt_rét" không dùng chung token "sốt" — đó
    là điều #3 cần. Nhưng nó cũng gộp cả những cụm mà sách không bao giờ viết
    liền: "thuốc ho" thành "thuốc_ho", df = 1 trên 25.852 chunk. Cả truy vấn thu
    về đúng một token hiếm, nên BM25 chỉ trả nổi 1 chunk thay vì 5 — đo được
    P@5 của riêng truy vấn đó là 20%.

    Chỉ mở rộng phía TRUY VẤN, và chỉ với token đã hiếm sẵn: corpus vẫn giữ token
    ghép nên các cặp dễ nhầm vẫn tách bạch. Token hiếm thì idf cao, nên bản ghép
    (nếu khớp được chunk nào) vẫn xếp trên các âm tiết vừa thêm.
    """
    expanded = list(tokens)
    for token in tokens:
        if "_" in token and doc_freq.get(token, 0) < RARE_COMPOUND_MIN_DF:
            expanded.extend(part for part in token.split("_") if part)
    return expanded


# 1b. Tham số hợp nhất RRF
#
# RRF_Score(d) = w_sparse/(k + rank_bm25) + w_dense/(k + rank_dense)
#
# Đo trên hai bộ truy vấn (xem eval/): BM25 đạt P@5 96%, dense chỉ 76%. Trộn
# 1:1 nên kéo chất lượng xuống 90% — mỗi kết quả đúng của BM25 lại bị kèm một
# kết quả sai từ nhánh dense. Truy vấn "thuốc hạ sốt" là ví dụ rõ nhất: BM25
# đúng cả 5/5, dense trả 4/5 thuốc sốt rét, RRF 1:1 trộn ra 2/5.
#
# Nghiêng về BM25 thay vì bỏ hẳn dense: dense vẫn là nhánh duy nhất tìm được
# chunk không trùng từ vựng với câu hỏi, và ở w=1.5 nó vẫn giữ khoảng 10% số
# suất trong top-5.
RRF_K = 60.0
RRF_W_SPARSE = 1.5
RRF_W_DENSE = 1.0

# 2. Local Fallback BM25 implementation for maximum robustness
class FallbackBM25:
    def __init__(self, corpus: List[List[str]]):
        self.corpus_size = len(corpus)
        self.avgdl = sum(len(doc) for doc in corpus) / self.corpus_size if self.corpus_size > 0 else 0.0
        self.doc_freqs = []
        self.doc_len = []
        self.df = {}
        self.k1 = 1.5
        self.b = 0.75
        
        for doc in corpus:
            frequencies = Counter(doc)
            self.doc_freqs.append(frequencies)
            self.doc_len.append(len(doc))
            for word in frequencies:
                self.df[word] = self.df.get(word, 0) + 1
                
        self.idf = {}
        for word, freq in self.df.items():
            self.idf[word] = math.log(1 + (self.corpus_size - freq + 0.5) / (freq + 0.5))

    def get_scores(self, query: List[str]) -> List[float]:
        scores = [0.0] * self.corpus_size
        for q in query:
            if q not in self.idf:
                continue
            idf = self.idf[q]
            for idx in range(self.corpus_size):
                tf = self.doc_freqs[idx].get(q, 0)
                dl = self.doc_len[idx]
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * (dl / self.avgdl)) if self.avgdl > 0 else 1.0
                scores[idx] += idf * (numerator / denominator)
        return scores

# 3. Không còn Cross-Encoder reranker.
#
# Trước đây bước xếp hạng cuối dùng cross-encoder/ms-marco-MiniLM-L-6-v2 —
# model huấn luyện trên MS MARCO thuần tiếng Anh, chấm điểm ngữ liệu tiếng
# Việt. Giá phải trả đo được: 11,7s nạp model ở truy vấn đầu và 0,93s mỗi
# truy vấn (4,48s khi lọc theo doc_names vì k_candidates lên 60). Không có
# bằng chứng định lượng nào cho thấy nó cải thiện thứ hạng tiếng Việt, nên
# kết quả nay lấy thẳng theo điểm RRF. Muốn rerank lại thì dùng model đa
# ngữ (mmarco-mMiniLMv2) hoặc reranker qua API, đừng quay lại model Anh.

# 3b. Model embedding: multilingual-e5-small, cosine, vector đã chuẩn hoá
#
# Thay cho paraphrase-multilingual-MiniLM-L12-v2. Vẫn 384 chiều nên schema và
# kích thước chỉ mục không đổi, nhưng max_seq_length 512 thay vì 128 — đo trên
# chính tokenizer của model cũ thì 35,9% chunk bị cắt và 35,1% token bị bỏ.
#
# Họ e5 BẮT BUỘC có tiền tố: "query: " cho câu hỏi và "passage: " cho tài liệu.
# Thiếu tiền tố thì chất lượng tụt hẳn — model được huấn luyện bất đối xứng, hai
# vế nằm ở hai vùng khác nhau của không gian vector. HuggingFaceEmbeddings không
# tự thêm, nên phải bọc lại.
DEFAULT_EMBEDDING_MODEL = config.EMBEDDING_MODEL
E5_QUERY_PREFIX = "query: "
E5_PASSAGE_PREFIX = "passage: "
MAX_SEQ_LENGTH = 512


class PrefixedEmbeddings(HuggingFaceEmbeddings):
    """HuggingFaceEmbeddings có thêm tiền tố bất đối xứng của họ e5.

    Chỉ thêm tiền tố cho model thật sự cần (tên có "e5"), để đổi ngược về model
    cũ vẫn chạy đúng mà không phải sửa gì thêm.
    """

    _needs_prefix: bool = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        object.__setattr__(self, "_needs_prefix", "e5" in self.model_name.lower())
        # Ép độ dài chuỗi tối đa: bản cấu hình sẵn của model có thể thấp hơn, mà
        # cắt ngắn ở đây thì mất hẳn phần đuôi của chunk chứ không báo lỗi gì.
        try:
            self._client.max_seq_length = MAX_SEQ_LENGTH
        except Exception as e:
            print(f"Warning: không đặt được max_seq_length: {e}")

    def embed_documents(self, texts):
        if self._needs_prefix:
            texts = [E5_PASSAGE_PREFIX + t for t in texts]
        return super().embed_documents(texts)

    def embed_query(self, text):
        if self._needs_prefix:
            text = E5_QUERY_PREFIX + text
        return super().embed_query(text)


# 4. Upgraded VectorDB class matching the requirements & visual screenshots
class VectorDB:
    def __init__(
        self,
        documents_or_persist_dir=None,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        collection_name: str = "vietnamese_docs",
        persist_dir: str = None,
    ):
        # Flexible signature to support both standard initialization and Image 1 constructor
        if isinstance(documents_or_persist_dir, str):
            self.persist_dir = documents_or_persist_dir
            documents = None
        else:
            self.persist_dir = persist_dir if persist_dir else "/content/chroma_data"
            documents = documents_or_persist_dir

        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self._embedding = None
        self._db = None
        self._invalidate_caches()
        # Nạp model và dựng BM25 đều tốn kém và đều có thể bị gọi từ nhiều
        # thread cùng lúc (preload chạy nền + request của người dùng). Khoá lại
        # để chỉ làm một lần, thay vì nạp hai bản model 470MB trên máy 7,3GB.
        self._build_lock = threading.RLock()

    def _invalidate_caches(self):
        """Xoá mọi thứ dẫn xuất từ nội dung index.

        Gom lại một chỗ vì bốn nơi cần reset (khởi tạo, add, delete, reload) và
        chúng đã từng lệch nhau — thêm một cache mới mà quên một nhánh thì nó
        sống sót qua lần nạp lại và trả kết quả theo corpus cũ.
        """
        self._corpus_cache = None
        self._bm25_model = None
        self._lookup = None
        self._doc_freq = None

    @property
    def embedding(self):
        if self._embedding is None:
            with self._build_lock:
                if self._embedding is None:
                    print(f"Lazy loading HuggingFaceEmbeddings with model: {self.embedding_model}")
                    try:
                        # normalize_embeddings: vector chuẩn hoá về độ dài 1 thì
                        # khoảng cách L2 và cosine xếp hạng như nhau — không còn
                        # phụ thuộc vào chuyện chỉ mục được tạo với space nào.
                        self._embedding = PrefixedEmbeddings(
                            model_name=self.embedding_model,
                            model_kwargs={'device': 'cpu'},
                            encode_kwargs={'normalize_embeddings': True},
                        )
                    except Exception as e:
                        print(f"Warning: HuggingFaceEmbeddings init error: {e}. Falling back to keyword search.")
                        self._embedding = None
        return self._embedding

    @property
    def db(self):
        if self._db is None:
            if self.embedding:
                try:
                    self._db = Chroma(
                        collection_name=self.collection_name,
                        embedding_function=self.embedding,
                        persist_directory=self.persist_dir,
                        # Không đặt thì Chroma mặc định L2. Model huấn luyện cho
                        # cosine, và similarity_search_with_relevance_scores quy
                        # đổi điểm theo giả định cosine — với L2 nó trả điểm âm
                        # (đo được -3,9 … -6,3) kèm cảnh báo.
                        # Chỉ có tác dụng khi TẠO collection; đổi giá trị này
                        # trên chỉ mục đã có thì phải index lại.
                        collection_metadata={"hnsw:space": "cosine"},
                    )
                except Exception as e:
                    print(f"Warning: Chroma init error: {e}")
                    self._db = None
        return self._db

    # Get retriever as shown in Image 1
    def get_retriever(self, search_kwargs: dict = None):
        if search_kwargs is None:
            search_kwargs = {"k": 4} # Mặc định lấy 4 document gần nhất
        if not self.db:
            return None
            
        return self.db.as_retriever(
            search_type="similarity",
            search_kwargs=search_kwargs,
        )

    def embed_text(self, text: str) -> Optional[List[float]]:
        """Embeds a free-text string with the same model the index uses.

        Used to store a vector alongside each logged question so "câu hỏi tương
        tự đã hỏi trước đây" can match by meaning, not just by keyword. Returns
        None whenever the embedding model is unavailable — callers fall back to
        keyword matching.
        """
        if not (text or "").strip():
            return None
        try:
            embedding = self.embedding
            if embedding is None:
                return None
            return [float(x) for x in embedding.embed_query(text)]
        except Exception as e:
            print(f"Warning: embed_text failed: {e}")
            return None

    def _get_corpus_and_bm25(self):
        if not self.db:
            return None, None, None, None

        if self._corpus_cache is None:
            # Khoá: preload lúc khởi động chạy ở thread nền, nên một request
            # đến đúng lúc đó sẽ gọi vào đây song song. Không khoá thì cả hai
            # cùng kéo 25.861 chunk ra RAM và cùng dựng BM25.
            with self._build_lock:
                if self._corpus_cache is None:
                    self._build_corpus_cache()

        if self._corpus_cache is None:
            return None, None, None, None
        return self._corpus_cache[0], self._corpus_cache[1], self._corpus_cache[2], self._bm25_model

    def _tokenized_corpus(self, all_texts, all_ids):
        """Token của toàn corpus, đọc từ cache đĩa nếu còn khớp.

        Tách từ bằng pyvi tốn ~4ms/chunk, tức khoảng 110s cho 25.852 chunk —
        quá lâu để làm lại mỗi lần khởi động (trước đây chỉ mất ~11s). Cache
        lại và chỉ dựng lại khi corpus hoặc cách tách từ thay đổi.
        """
        import hashlib, pickle

        # Khoá cache phải phủ cả NỘI DUNG, không chỉ danh sách id. Id của chunk
        # dẫn xuất từ chunk_id/field/trang/content — KHÔNG từ tên thuốc. Nên khi
        # chuẩn hoá tên (#5) thì parent_text đổi mà id giữ nguyên: khoá chỉ theo
        # id sẽ báo "còn khớp" và trả về token của corpus cũ, im lặng và sai.
        digest = hashlib.sha1()
        digest.update(SEGMENTER_VERSION.encode("utf-8"))
        for doc_id, text in zip(all_ids, all_texts):
            # Kèm độ dài trước mỗi phần: không cần ký tự ngăn cách, mà cũng
            # không có cách nào ghép hai bộ (id, text) khác nhau ra cùng chuỗi.
            for part in (str(doc_id), text):
                raw = part.encode("utf-8", "replace")
                digest.update(str(len(raw)).encode("ascii"))
                digest.update(b":")
                digest.update(raw)
        key = digest.hexdigest()
        cache_path = os.path.join(self.persist_dir, "bm25_tokens.pkl")

        try:
            with open(cache_path, "rb") as f:
                blob = pickle.load(f)
            if blob.get("key") == key:
                return blob["tokens"]
        except Exception:
            pass  # không có cache, hỏng, hoặc lệch phiên bản -> dựng lại

        print(f"[BM25] Đang tách từ {len(all_texts)} chunk (chỉ chạy lại khi corpus đổi)...")
        t0 = time.perf_counter()
        tokens = [tokenize_text(text) for text in all_texts]
        print(f"[BM25] Tách từ xong sau {time.perf_counter() - t0:.0f}s.")

        try:
            os.makedirs(self.persist_dir, exist_ok=True)
            tmp = cache_path + ".tmp"
            with open(tmp, "wb") as f:
                pickle.dump({"key": key, "tokens": tokens}, f, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, cache_path)   # thay nguyên tử: không để lại file dở
        except Exception as e:
            print(f"[BM25] Không ghi được cache token ({e}); lần sau sẽ tách lại.")

        return tokens

    def _build_corpus_cache(self):
        """Kéo toàn bộ child chunk ra RAM, dựng BM25 và các bảng tra ngược.

        Luôn gọi bên trong `self._build_lock`.
        """
        try:
            db_content = self.db.get(where={"doc_type": "child"}, include=["metadatas", "documents"])
        except Exception:
            db_content = None
        if not db_content or not db_content["documents"]:
            return

        all_texts = db_content["documents"]
        all_metadatas = db_content["metadatas"]
        all_ids = db_content["ids"]

        tokenized_corpus = self._tokenized_corpus(all_texts, all_ids)
        try:
            from rank_bm25 import BM25Okapi
            bm25_model = BM25Okapi(tokenized_corpus)
        except Exception:
            bm25_model = FallbackBM25(tokenized_corpus)

        # Document frequency dùng cho expand_rare_compounds(). Tự đếm thay vì
        # đọc thuộc tính nội bộ của BM25Okapi — hai lớp BM25 ở trên không có
        # chung API, còn đếm lại chỉ tốn dưới một giây.
        doc_freq: Dict[str, int] = {}
        for tokens in tokenized_corpus:
            for token in set(tokens):
                doc_freq[token] = doc_freq.get(token, 0) + 1
        self._doc_freq = doc_freq

        self._bm25_model = bm25_model
        # Bảng tra ngược dựng một lần. Trước đây search() quét tuyến tính toàn
        # bộ metadata cho MỖI kết quả dense, rồi gọi all_ids.index() thêm một
        # lần nữa cho mỗi ứng viên — O(k×N) thuần Python, đo được ~1,5s mỗi
        # truy vấn trên 25.861 chunk.
        self._lookup = {
            "by_chunk_id": {
                meta.get("chunk_id"): idx
                for idx, meta in enumerate(all_metadatas)
                if meta.get("chunk_id")
            },
            "by_text": {text: idx for idx, text in enumerate(all_texts)},
            "by_id": {doc_id: idx for idx, doc_id in enumerate(all_ids)},
        }
        # Gán cuối cùng: các thread khác dùng biến này làm cờ "đã xong", nên
        # nó chỉ được set khi mọi thứ ở trên đã dựng đủ.
        self._corpus_cache = (all_texts, all_metadatas, all_ids)

    def add_chunks(self, documents: List[Document], ids: Optional[List[str]] = None):
        """
        Thêm chunk vào vector store.

        Truyền `ids` tất định để lần nạp lại ghi đè thay vì nhân bản: Chroma
        dùng upsert theo id, còn nếu để trống thì mỗi lần chạy sinh UUID mới và
        cùng một nội dung sẽ nằm nhiều lần trong index.
        """
        if not documents:
            return
        if ids is not None:
            if len(ids) != len(documents):
                raise ValueError(
                    f"Số ids ({len(ids)}) không khớp số documents ({len(documents)})."
                )
            self.db.add_documents(documents, ids=ids)
        else:
            self.db.add_documents(documents)
        self._invalidate_caches()
        print(f"Added {len(documents)} documents to vector store.")

    def delete_document(self, doc_name: str):
        res = self.db.get(where={"doc_name": doc_name})
        if res and res["ids"]:
            self.db.delete(ids=res["ids"])
            self._invalidate_caches()
            print(f"Deleted document '{doc_name}' ({len(res['ids'])} chunks) from vector database.")

    def list_documents(self) -> List[Dict[str, Any]]:
        all_texts, all_metadatas, all_ids, _ = self._get_corpus_and_bm25()
        if not all_metadatas:
            res = self.db.get(include=["metadatas"])
            all_metadatas = res.get("metadatas", [])

        docs = {}
        if all_metadatas:
            for meta in all_metadatas:
                name = meta.get("doc_name")
                page = meta.get("page_num", 1)
                doc_type = meta.get("doc_type", "child")
                if not name:
                    continue
                if name not in docs:
                    docs[name] = {"pages": set(), "max_page": 0, "chunks": 0}
                docs[name]["pages"].add(page)
                if isinstance(page, int) and page > docs[name]["max_page"]:
                    docs[name]["max_page"] = page
                if doc_type == "child":
                    docs[name]["chunks"] += 1
                    
        # Số trang lấy từ manifest của tài liệu. Trước đây giá trị này được
        # hard-code theo tên sách, nên mọi tài liệu khác đều báo 1 trang và làm
        # hỏng nút chuyển trang trong reader.
        results = []
        for name, info in docs.items():
            manifest = documents.load_manifest(name) or {}
            page_count = manifest.get("pdf_pages") or max(
                len(info["pages"]), info["max_page"], 1
            )
            results.append({
                "doc_name": name,
                "doc_title": manifest.get("doc_title") or name,
                "doc_series": manifest.get("doc_series"),
                "volume": manifest.get("volume"),
                "coverage": manifest.get("coverage"),
                "body_page_range": manifest.get("body_page_range"),
                "page_count": page_count,
                "chunk_count": info["chunks"],
            })
        return results

    def _reload_db(self):
        try:
            self._db = None
            self._invalidate_caches()
        except Exception as e:
            print(f"Error reloading db: {e}")

    # Advanced Hybrid Search with BM25, RRF, and Cross-Encoder Reranking
    def search(self, query: str, top_k: int = 5, doc_names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Hybrid search over the indexed chunks.

        `doc_names` restricts the search to a subset of documents — used by the
        multi-source comparison feature, which needs the best passages *per
        document* rather than the globally best passages.
        """
        all_texts, all_metadatas, all_ids, bm25_model = self._get_corpus_and_bm25()

        if not all_texts or not bm25_model:
            self._reload_db()
            all_texts, all_metadatas, all_ids, bm25_model = self._get_corpus_and_bm25()
            if not all_texts or not bm25_model:
                print("Vector store is empty or has no child chunks. Skipping search.")
                return []

        allowed_ids = None
        if doc_names:
            allowed_ids = {
                all_ids[idx] for idx, meta in enumerate(all_metadatas)
                if meta.get("doc_name") in set(doc_names)
            }
            if not allowed_ids:
                return []

        # A. DENSE RETRIEVAL: Query similarity from ChromaDB
        # Widen the candidate pool when filtering so enough of them survive the filter.
        k_candidates = min(top_k * (12 if doc_names else 4), len(all_texts))
        dense_filter = None
        if doc_names:
            dense_filter = (
                {"doc_name": doc_names[0]} if len(doc_names) == 1
                else {"doc_name": {"$in": list(doc_names)}}
            )
        try:
            dense_results_with_scores = self.db.similarity_search_with_relevance_scores(
                query, k=k_candidates, filter=dense_filter
            )
        except Exception as e:
            print(f"Dense search error ({e}). Reloading Chroma and retrying...")
            self._reload_db()
            all_texts, all_metadatas, all_ids, bm25_model = self._get_corpus_and_bm25()
            try:
                dense_results_with_scores = self.db.similarity_search_with_relevance_scores(
                    query, k=k_candidates, filter=dense_filter
                )
            except Exception as e2:
                print(f"Dense search fallback failed: {e2}")
                dense_results_with_scores = []
        
        lookup = self._lookup or {}
        by_chunk_id = lookup.get("by_chunk_id", {})
        by_text = lookup.get("by_text", {})
        by_id = lookup.get("by_id", {})

        dense_ranking = []
        for doc, score in dense_results_with_scores:
            cid = doc.metadata.get("chunk_id") if doc.metadata else None
            match_idx = by_chunk_id.get(cid, -1) if cid else -1
            if match_idx == -1:
                match_idx = by_text.get(doc.page_content, -1)
            if match_idx != -1 and (allowed_ids is None or all_ids[match_idx] in allowed_ids):
                dense_ranking.append(all_ids[match_idx])

        # B. SPARSE RETRIEVAL: BM25 score calculation
        tokenized_query = expand_rare_compounds(tokenize_text(query), self._doc_freq or {})
        bm25_scores = bm25_model.get_scores(tokenized_query)

        # Sort indices by BM25 score descending, dropping filtered-out documents
        # *before* trimming to k_candidates so a small document still gets its hits.
        sparse_ranking = []
        for idx in np.argsort(bm25_scores)[::-1]:
            if bm25_scores[idx] <= 0.0:
                break
            if allowed_ids is not None and all_ids[idx] not in allowed_ids:
                continue
            sparse_ranking.append(all_ids[idx])
            if len(sparse_ranking) >= k_candidates:
                break

        # C. RECIPROCAL RANK FUSION (RRF)
        # Combine rankings — công thức và lý do chọn trọng số ở đầu file.
        rrf_scores = {}

        # Score dense rank
        for rank, doc_id in enumerate(dense_ranking):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + RRF_W_DENSE / (RRF_K + rank + 1)

        # Score sparse rank
        for rank, doc_id in enumerate(sparse_ranking):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + RRF_W_SPARSE / (RRF_K + rank + 1)

        # Sort candidate IDs by RRF score descending
        sorted_rrf_candidates = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        top_rrf_ids = [doc_id for doc_id, rrf_score in sorted_rrf_candidates[:k_candidates]]

        # Gather actual documents for Reranking
        candidates = []
        for doc_id in top_rrf_ids:
            idx = by_id.get(doc_id, -1)
            if idx == -1:
                continue
            candidates.append({
                "id": doc_id,
                "text": all_texts[idx],
                "doc_name": all_metadatas[idx].get("doc_name", ""),
                "page_num": all_metadatas[idx].get("page_num", 1),
                "parent_text": all_metadatas[idx].get("parent_text", all_texts[idx]),
                "score": rrf_scores[doc_id]  # Default score is RRF
            })

        # D. Không rerank nữa — candidates đã theo thứ tự RRF giảm dần.

        # Return top_k search results
        # Under Parent-Child Indexing, the RAG assistant returns the PARENT_TEXT (richer context)
        # as the primary text, but keeps details of the document and page.
        results = []
        for c in candidates[:top_k]:
            results.append({
                "id": c["id"],
                "text": c["parent_text"],  # Parent text for the doctor/LLM to read
                "child_text": c["text"],   # Child text for matching highlights
                "doc_name": c["doc_name"],
                "page_num": c["page_num"],
                "score": c["score"]
            })
            
        return results

# Establish compatibility alias
VectorStore = VectorDB
