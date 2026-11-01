import os
import re
import math
import time
import threading
import hashlib
import pickle
from datetime import datetime, timezone
import numpy as np
from typing import List, Dict, Any, Optional
from collections import Counter

import config  # phải đứng trước langchain_huggingface: config đặt HF_HOME
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document

import config
import documents
import drug_alias
import query_intent
import query_normalize
import query_plan
from text_fold import fold

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
# Trọng số 1:1 — công thức RRF nguyên bản. Có một quãng đã đặt w_sparse = 1,5
# để nghiêng về BM25, và ghi lại ở đây vì bài học đáng giá hơn con số:
#
#   Hồi model embedding còn là paraphrase-multilingual-MiniLM-L12-v2, dense chỉ
#   đạt P@5 78% so với 92% của BM25, nên trộn 1:1 kéo kết quả xuống dưới cả
#   BM25 đứng một mình. Nghiêng về BM25 chữa được triệu chứng đó (bộ giữ riêng
#   80% -> 92%).
#
#   Đổi sang multilingual-e5-small thì dense lên 90%/94% và VƯỢT BM25 trên bộ
#   câu hỏi tự nhiên. Lúc này chính cái nghiêng ấy quay ra làm hỏng: đo lại
#   trên bộ giữ riêng, w=1,0 cho 98% còn w>=1,2 chỉ còn 94%.
#
# Tức là trọng số kia là miếng vá cho một nhánh dense yếu, không phải một tính
# chất của bài toán. Sửa đúng gốc rồi thì phải gỡ miếng vá ra. Ai đổi model lần
# nữa thì quét lại: python eval/eval_run.py --sweep
RRF_K = 60.0
RRF_W_SPARSE = 1.0
RRF_W_DENSE = 1.0

# 1c. Câu hỏi gõ không dấu / gõ nhầm Telex (query_normalize.py)
#
# Bật thì câu hỏi được gỡ Telex và khôi phục dấu theo từ vựng của chính kho
# trước khi vào cả hai nhánh. Câu không dấu còn được tra thêm trên một trường
# BM25 thứ ba đã gấp dấu ("đái_tháo_đường" -> "dai_thao_duong"), hợp nhất bằng
# RRF với trọng số dưới đây. Trường gấp dấu cứu cả hai phía: bác sĩ gõ không
# dấu, và chữ OCR bị rụng dấu ("Giảm dau"). Đo bằng eval/eval_query_variants.py.
ENABLE_QUERY_NORMALIZATION = True
RRF_W_FOLDED = 1.0

# 1d. Sách làm chỉ mục: tên thuốc + mục chuyên luận (drug_alias.py, query_intent.py)
#
# Câu hỏi nhắc tên một thuốc (dưới bất kỳ tên nào: INN Việt/Anh, tên khác,
# biệt dược) và/hoặc hỏi về một mục (liều, chống chỉ định, thai kỳ…) thì chạy
# thêm một kênh "trọng tâm": BM25 chỉ trong các chunk thuộc đúng thuốc đó và
# đúng mục đó, hợp nhất bằng RRF. Là kênh THÊM, không phải bộ lọc — nhận sai
# thuốc hay đoán sai ý định thì hai kênh gốc vẫn còn nguyên.
#
# Tên nhận ra mà khác chữ trong sách ("amoxicillin" -> Amoxicilin, "Mucodyne"
# -> Carbocistein) được viết thêm vào câu tra cho cả dense lẫn BM25: BM25 không
# có cách nào biết hai chuỗi đó là một thuốc. Đo bằng eval/eval_phase2.py
# (30 chuyên luận x 8 ý định, chấm theo metadata "đúng thuốc + đúng mục"):
#   Hit@1  37% -> 99,6% (bộ A), 41% -> 95% (bộ B, cách hỏi khác)
#   tra bằng biệt dược: P@5 50% -> 100%; bộ chính / giữ riêng cũ: không đổi.
#
# Hai trọng số vì hai kênh khác hẳn độ rộng. Có tên thuốc: kênh chỉ còn vài
# chunk của đúng thuốc đó, rất chính xác — w=2,0 đưa Hit@1 lên 99,6% / 95%.
# Không có tên thuốc ("thuốc hạ sốt" -> mục Chỉ định): kênh là cả nghìn chunk
# Chỉ định của mọi thuốc; w=2,0 kéo bộ chính cũ từ 100% xuống 98%, nên giữ 1,0.
ENABLE_ENTITY_LINKING = True
RRF_W_FOCUS = 2.0
RRF_W_FOCUS_SECTION_ONLY = 1.0

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

# 3. Reranker: tắt mặc định, bật lại được bằng model ĐA NGỮ (xem rerank()).
#
# Trước đây bước xếp hạng cuối dùng cross-encoder/ms-marco-MiniLM-L-6-v2 —
# model huấn luyện trên MS MARCO thuần tiếng Anh, chấm điểm ngữ liệu tiếng
# Việt. Giá phải trả đo được: 11,7s nạp model ở truy vấn đầu và 0,93s mỗi
# truy vấn (4,48s khi lọc theo doc_names vì k_candidates lên 60). Không có
# bằng chứng định lượng nào cho thấy nó cải thiện thứ hạng tiếng Việt, nên
# kết quả nay lấy thẳng theo điểm RRF. Muốn rerank lại thì dùng model đa
# ngữ (mmarco-mMiniLMv2) hoặc reranker qua API, đừng quay lại model Anh.

_reranker = None
_reranker_failed = False
_reranker_lock = threading.Lock()


def _get_reranker():
    global _reranker, _reranker_failed
    if not getattr(config, "RERANKER_MODEL", "") or _reranker_failed:
        return None
    with _reranker_lock:
        if _reranker is None and not _reranker_failed:
            try:
                from sentence_transformers import CrossEncoder
                _reranker = CrossEncoder(config.RERANKER_MODEL, max_length=512)
            except Exception as e:  # thiếu model/mạng: tìm vẫn chạy theo RRF
                _reranker_failed = True
                print(f"Không nạp được reranker {config.RERANKER_MODEL}: {e}")
    return _reranker


def rerank(query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Chấm lại RERANK_TOP_N ứng viên đầu bằng cross-encoder đa ngữ, nếu đã bật."""
    model = _get_reranker()
    if model is None or len(candidates) < 2:
        return candidates
    head, tail = candidates[:config.RERANK_TOP_N], candidates[config.RERANK_TOP_N:]
    try:
        scores = model.predict([(query, c["text"]) for c in head])
    except Exception as e:
        print(f"Rerank lỗi, giữ thứ tự RRF: {e}")
        return candidates
    order = sorted(range(len(head)), key=lambda i: -float(scores[i]))
    return [head[i] for i in order] + tail


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
class IndexUnavailable(RuntimeError):
    code = "INDEX_UNAVAILABLE"


class EmptyIndex(IndexUnavailable):
    code = "EMPTY_INDEX"


class EmbeddingUnavailable(IndexUnavailable):
    code = "EMBEDDING_UNAVAILABLE"


class SearchHits(list):
    def __init__(self, values=(), *, degraded=False, reason=None, status="OK", normalized=None,
                 understood=None, coverage=None):
        super().__init__(values)
        self.degraded = degraded
        self.reason = reason
        self.status = status
        # query_normalize.NormalizedQuery khi câu hỏi đã được sửa (gỡ Telex /
        # khôi phục dấu) — giao diện báo cho bác sĩ "đã tra theo: …".
        self.normalized = normalized
        # Máy đã hiểu câu hỏi thế nào: thuốc nào, mục nào, điều kiện bệnh nhân
        # nào (dict, xem VectorDB._understand). None nếu không nhận ra gì.
        self.understood = understood
        # Bảng kiểm điều kiện (query_plan.py): mỗi cặp (thuốc, điều kiện) có
        # trong sách ở nguồn nào, kèm câu nguyên văn — hoặc thư viện không có.
        self.coverage = coverage


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
        self._last_build_at = None
        self._last_build_seconds = None
        self._embedding_error = None
        self._index_error = None

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
        self._bm25_folded = None
        self._folded_df = None
        self._lexicon = None
        self._alias_store = None
        self._entity_idx = None
        self._section_idx = None

    def is_warm(self) -> bool:
        """Đã nạp xong model embedding và corpus/BM25 chưa.

        Dùng để chọn trần thời gian cho khâu tìm: lần tìm khi còn phải nạp mất
        khoảng 21,7s, còn khi đã nạp chỉ 65ms. Một trần chung cho cả hai thì
        hoặc giết lần tra đầu tiên sau khi mở app, hoặc lỏng đến mức vô dụng.

        Chỉ ĐỌC trạng thái, không nạp gì và không giữ khoá — gọi được từ đường
        request mà không làm nó phải chờ.
        """
        return self._embedding is not None and self._corpus_cache is not None

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
                        self._embedding_error = str(e)
        return self._embedding

    @property
    def db(self):
        # Khoá giống hệt property `embedding` ở trên — và lý do thật đo được,
        # không phải phòng xa: hai request đồng thời lúc mới mở server (vd.
        # /api/documents và /api/drugs/report chạy song song trên threadpool
        # của FastAPI) cùng thấy self._db is None, cùng tự dựng Chroma(...)
        # riêng, và tầng Rust bindings bên dưới không chịu được hai lần khởi
        # tạo chồng lên nhau trên cùng một thư mục persist — ném
        # "'RustBindingsAPI' object has no attribute 'bindings'". Tệ hơn nữa:
        # kết quả là self._db bị gán đè bởi bất cứ thread nào chạy xong SAU
        # cùng, có thể là bản hỏng — và vì nó không phải None nữa, mọi request
        # sau đó dùng luôn bản hỏng, không bao giờ tự thử dựng lại. Khoá đảm
        # bảo chỉ một thread dựng Chroma một lần.
        if self._db is None:
            with self._build_lock:
                if self._db is None:
                    try:
                        # Đọc get() không cần mô hình; chỉ similarity_search cần embedding.
                        self._db = Chroma(
                            collection_name=self.collection_name,
                            embedding_function=None,
                            persist_directory=self.persist_dir,
                            collection_metadata={"hnsw:space": "cosine"},
                        )
                        self._index_error = None
                    except Exception as e:
                        self._index_error = str(e)
                        print(f"Warning: Chroma init error: {e}")
                        self._db = None
        return self._db

    # Get retriever as shown in Image 1
    def get_retriever(self, search_kwargs: dict = None):
        if search_kwargs is None:
            search_kwargs = {"k": 4} # Mặc định lấy 4 document gần nhất
        if not self.db or not self.embedding:
            return None
        self.db._embedding_function = self.embedding
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
            raise IndexUnavailable("Không mở được chỉ mục tra cứu y văn.")

        if self._corpus_cache is None:
            # Khoá: preload lúc khởi động chạy ở thread nền, nên một request
            # đến đúng lúc đó sẽ gọi vào đây song song. Không khoá thì cả hai
            # cùng kéo 25.861 chunk ra RAM và cùng dựng BM25.
            with self._build_lock:
                if self._corpus_cache is None:
                    self._build_corpus_cache()

        if self._corpus_cache is None:
            raise EmptyIndex("Chỉ mục chưa có đoạn y văn nào để tra cứu.")
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

    # Chroma lọc theo `where` xong thì lấy nội dung các id khớp bằng một câu
    # SQLite "id IN (?, ?, …)", một tham số cho mỗi id. Gọi get() một lượt cho
    # TOÀN BỘ corpus thì số tham số bằng đúng số chunk — 33 490 chunk trên cả
    # ba cuốn (đo lúc nạp xong Quyển 2) đã vượt trần biến của SQLite, ném lỗi
    # "too many SQL variables" và làm hỏng luôn cả Thư viện lẫn tra cứu. Ngưỡng
    # 999 là mức SQLite mặc định thấp nhất từng gặp — chọn thấp hơn hẳn để an
    # toàn trên mọi bản dựng SQLite, không chỉ vừa đủ cho kho hiện tại.
    _GET_BATCH_SIZE = 500

    def _get_batched(self, where: Optional[dict] = None, include: Optional[list] = None) -> Dict[str, List[Any]]:
        """self.db.get(...) nhưng chia lô theo _GET_BATCH_SIZE — xem chú thích trên _GET_BATCH_SIZE.

        Dùng cho MỌI self.db.get() có thể khớp hàng nghìn chunk trở lên (liệt
        kê thư viện, xoá tài liệu): một cuốn sách đơn lẻ đã tới 18 708 chunk,
        đủ gần trần để một cuốn dày hơn hoặc kho nhiều sách hơn lại vỡ lần nữa
        nếu gọi get() một lượt không chia lô.
        """
        if self.db is None:
            raise IndexUnavailable("Không mở được chỉ mục tra cứu y văn.")
        keys = list(include) if include is not None else ["metadatas", "documents"]
        all_ids: List[Any] = []
        collected: Dict[str, List[Any]] = {k: [] for k in keys}
        offset = 0
        while True:
            batch = self.db.get(where=where, include=keys, limit=self._GET_BATCH_SIZE, offset=offset)
            batch_ids = batch.get("ids") or []
            if not batch_ids:
                break
            all_ids.extend(batch_ids)
            for k in keys:
                collected[k].extend(batch.get(k) or [])
            if len(batch_ids) < self._GET_BATCH_SIZE:
                break
            offset += self._GET_BATCH_SIZE
        collected["ids"] = all_ids
        return collected

    def _get_all_child_chunks(self) -> Optional[Dict[str, List[Any]]]:
        """self.db.get(where={"doc_type": "child"}) nhưng chia lô — xem _GET_BATCH_SIZE."""
        result = self._get_batched(where={"doc_type": "child"}, include=["metadatas", "documents"])
        if not result["documents"]:
            return None
        return result

    def _corpus_fingerprint(self):
        """Đếm và băm ID theo lô, không tải văn bản/metadata chỉ để kiểm cache.

        KHÔNG lấy mtime của chroma.sqlite3/-wal: đo được là chính việc MỞ
        Chroma để đọc (bước ngay trên, self.db.get()) đã đổi mtime của các tệp
        này, nên fingerprint không bao giờ khớp giữa hai lần khởi động — cache
        bị coi là cũ và bị dựng lại từ đầu mỗi lần, dù corpus không đổi (đo
        trên kho 33.490 chunk thật: vẫn ~38s ở lần "khôi phục" thứ hai, y hệt
        lần dựng đầu). Số lượng + băm danh sách id đã đủ phát hiện corpus đổi
        (thêm/bớt/thay tài liệu đổi id) mà không dính hiệu ứng phụ của mtime.
        """
        digest = hashlib.sha1()
        count = 0
        offset = 0
        while True:
            ids = (self.db.get(where={"doc_type": "child"}, include=[],
                               limit=self._GET_BATCH_SIZE, offset=offset).get("ids") or [])
            for doc_id in ids:
                raw = str(doc_id).encode("utf-8", "replace")
                digest.update(len(raw).to_bytes(4, "big"))
                digest.update(raw)
            count += len(ids)
            if len(ids) < self._GET_BATCH_SIZE:
                break
            offset += self._GET_BATCH_SIZE
        return (count, digest.hexdigest(), SEGMENTER_VERSION, query_normalize.LEXICON_VERSION)

    def _build_corpus_cache(self):
        """Dựng hoặc khôi phục corpus/BM25 khi dấu vân tay chỉ mục khớp."""
        t0 = time.perf_counter()
        try:
            fingerprint = self._corpus_fingerprint()
            cache_path = os.path.join(self.persist_dir, "bm25_corpus.pkl")
            try:
                with open(cache_path, "rb") as f:
                    blob = pickle.load(f)
                if blob.get("fingerprint") == fingerprint:
                    # _corpus_cache gán SAU CÙNG — nó là cờ "đã dựng xong" mà
                    # thread khác đọc (is_warm(), search() đang chờ khoá). Bản
                    # vá trước gán nó đầu tiên, nên một request đến đúng lúc có
                    # thể thấy corpus có nhưng _bm25_model vẫn None.
                    self._bm25_model = blob["bm25"]
                    self._doc_freq = blob["doc_freq"]
                    self._bm25_folded = blob["bm25_folded"]
                    self._folded_df = blob["folded_df"]
                    self._lexicon = blob["lexicon"]
                    self._lookup = blob["lookup"]
                    self._build_query_aids(blob["corpus"][1], blob["lexicon"])
                    self._corpus_cache = blob["corpus"]
                    self._last_build_at = datetime.now(timezone.utc).isoformat()
                    self._last_build_seconds = round(time.perf_counter() - t0, 2)
                    return
            except (OSError, ValueError, KeyError, EOFError, pickle.UnpicklingError):
                pass
            db_content = self._get_all_child_chunks()
            if not db_content:
                return
            all_texts = db_content["documents"]
            all_metadatas = db_content["metadatas"]
            all_ids = db_content["ids"]
            tokenized_corpus = self._tokenized_corpus(all_texts, all_ids)
            try:
                from rank_bm25 import BM25Okapi
                bm25_model = BM25Okapi(tokenized_corpus)
            except ImportError:
                bm25_model = FallbackBM25(tokenized_corpus)
            doc_freq = {}
            for tokens in tokenized_corpus:
                for token in set(tokens):
                    doc_freq[token] = doc_freq.get(token, 0) + 1

            # Trường thứ hai: cùng token pyvi nhưng đã gấp dấu. Gấp SAU khi tách
            # từ, vì pyvi cần dấu để nhận ra từ ghép.
            folded_corpus = [[fold(t) for t in tokens] for tokens in tokenized_corpus]
            try:
                from rank_bm25 import BM25Okapi
                bm25_folded = BM25Okapi(folded_corpus)
            except ImportError:
                bm25_folded = FallbackBM25(folded_corpus)
            folded_df = {}
            for tokens in folded_corpus:
                for token in set(tokens):
                    folded_df[token] = folded_df.get(token, 0) + 1
            lexicon = query_normalize.QueryLexicon.build(all_texts)
            lookup = {
                "by_chunk_id": {meta.get("chunk_id"): idx for idx, meta in enumerate(all_metadatas) if meta.get("chunk_id")},
                "by_text": {text: idx for idx, text in enumerate(all_texts)},
                "by_id": {doc_id: idx for idx, doc_id in enumerate(all_ids)},
            }
            corpus = (all_texts, all_metadatas, all_ids)
            self._doc_freq = doc_freq
            self._bm25_model = bm25_model
            self._bm25_folded = bm25_folded
            self._folded_df = folded_df
            self._lexicon = lexicon
            self._lookup = lookup
            self._build_query_aids(all_metadatas, lexicon)
            self._corpus_cache = corpus
            self._last_build_at = datetime.now(timezone.utc).isoformat()
            self._last_build_seconds = round(time.perf_counter() - t0, 2)
            try:
                with open(cache_path + ".tmp", "wb") as f:
                    pickle.dump({"fingerprint": fingerprint, "corpus": corpus,
                                 "bm25": bm25_model, "doc_freq": doc_freq,
                                 "bm25_folded": bm25_folded, "folded_df": folded_df,
                                 "lexicon": lexicon,
                                 "lookup": lookup}, f, protocol=pickle.HIGHEST_PROTOCOL)
                os.replace(cache_path + ".tmp", cache_path)
            except (OSError, pickle.PicklingError) as e:
                print(f"[BM25] Không ghi được cache corpus: {e}")
        except Exception as e:
            self._index_error = str(e)
            raise IndexUnavailable("Không đọc được chỉ mục tra cứu y văn.") from e

    def _build_query_aids(self, metadatas, lexicon):
        """Kho bí danh thuốc + chỉ mục chunk theo thuốc và theo mục.

        Không ghi vào pickle: dựng lại mất ~1,5s, và nhờ vậy sửa tệp
        lexicon/drug_synonyms.json là có hiệu lực ở lần khởi động sau mà không
        phải đổi dấu vân tay chỉ mục.
        """
        try:
            vn = drug_alias.vietnamese_syllables(lexicon.unigrams) if lexicon is not None else set()
            store = drug_alias.DrugAliasStore.build(metadatas, vn)
        except Exception as e:  # kho bí danh hỏng không được làm hỏng tra cứu
            print(f"[alias] Không dựng được kho bí danh thuốc: {e}")
            store = None
        entity_idx, section_idx = {}, {}
        for idx, meta in enumerate(metadatas):
            key = drug_alias.inn_key(meta.get("generic_name") or "")
            if key:
                entity_idx.setdefault(key, []).append(idx)
            section_idx.setdefault(query_intent.section_of(meta), []).append(idx)
        self._entity_idx = {k: np.array(v, dtype=np.int64) for k, v in entity_idx.items()}
        self._section_idx = {k: np.array(v, dtype=np.int64) for k, v in section_idx.items()}
        self._alias_store = store
        drug_alias.set_current(store)

    def _understand(self, query: str):
        """(thuốc nhận ra, hiểu biết về ý định, đoạn viết thêm vào câu tra)."""
        understanding = query_intent.understand(query) if query_intent.ENABLE_SECTION_ROUTING else None
        mentions = []
        if ENABLE_ENTITY_LINKING and self._alias_store is not None:
            mentions = self._alias_store.link(query)
        extra = []
        drugs = []
        for m in mentions:
            names = self._alias_store.canonical_names(m)
            drugs.append({"text": m.text, "names": names, "kind": m.kind})
            for name in names:
                # Chỉ viết thêm khi chữ trong sách khác chữ bác sĩ gõ.
                if drug_alias.tokens(name) != drug_alias.tokens(m.text) and name.lower() not in extra:
                    extra.append(name.lower())
        return mentions, understanding, extra, drugs

    # Không chèn quá ngần này đoạn bằng chứng vào danh sách nguồn: mỗi đoạn là
    # một [n] mà mô hình và bác sĩ phải đọc.
    MAX_EVIDENCE_INJECT = 3

    def _drug_terms(self, mention, names):
        """Các cách viết tên một thuốc để dò trong chữ sách: chữ bác sĩ gõ, tên
        chuyên luận, và tên bỏ hậu tố muối ("Warfarin Natri" -> "warfarin")."""
        terms = [mention.text]
        for n in names:
            terms.append(n)
            base = [t for t in drug_alias.tokens(n) if drug_alias._token_key(t) not in drug_alias._SALTS]
            if base:
                terms.append(" ".join(base))
        out = []
        for t in terms:
            t = t.lower().strip()
            if len(t) >= 4 and t not in out:
                out.append(t)
        return out

    def _find_evidence(self, cond, scores, allowed_ids, all_ids, all_texts):
        """Đoạn tốt nhất cho một điều kiện: đúng thuốc, mục theo thứ tự ưu tiên,
        có nhắc chính điều kiện đó. Không có thì trả về None — thư viện không có."""
        def pool_of(keys):
            parts = [self._entity_idx[k] for k in keys if k in (self._entity_idx or {})]
            return np.unique(np.concatenate(parts)) if parts else np.array([], dtype=np.int64)

        if cond.pair:
            ka, ta, kb, tb = cond.pair
            tries = [(pool_of(ka), tuple(tb)), (pool_of(kb), tuple(ta))]
        else:
            tries = [(pool_of(cond.drug_keys), cond.terms)]
        for section in cond.sections:
            sec = (self._section_idx or {}).get(section)
            if sec is None:
                continue
            best = None
            for pool, terms in tries:
                cand = np.intersect1d(pool, sec, assume_unique=True)
                for idx in cand:
                    if allowed_ids is not None and all_ids[idx] not in allowed_ids:
                        continue
                    text = all_texts[idx]
                    hits = query_plan.mentions_any(query_plan.body_of(text), terms)
                    if terms and not hits:
                        continue
                    quotes = query_plan.pick_quotes(text, query_plan.Condition(
                        cond.drug_keys, cond.drug_name, cond.cid, cond.label, cond.sections,
                        terms, cond.verbatim, cond.need_number))
                    has_number = any(query_plan._DOSE_NUM.search(q) for q in quotes)
                    key = (hits, has_number if cond.need_number else True, float(scores[idx]))
                    if best is None or key > best[0]:
                        best = (key, int(idx), quotes)
            if best is not None:
                return query_plan.Evidence(cond, best[1], best[2] if cond.verbatim else [])
        return query_plan.Evidence(cond, None, [])

    def _coverage(self, evidence, results, all_ids):
        position = {r["id"]: i for i, r in enumerate(results)}
        metas = self._corpus_cache[1] if self._corpus_cache else None
        items = []
        for ev in evidence:
            c = ev.condition
            item = {"drug": c.drug_name, "condition": c.cid, "label": c.label, "found": ev.idx is not None}
            if ev.idx is not None:
                meta = metas[ev.idx] if metas is not None else {}
                # Bằng chứng nằm ở mục nào. "Liều cho người suy gan" mà chỉ tìm
                # thấy ở mục Thận trọng nghĩa là sách KHÔNG ghi liều riêng — giao
                # diện phải nói rõ thay vì để bác sĩ tưởng đó là liều.
                item["section"] = meta.get("field_name") or meta.get("field_type")
                item["in_preferred_section"] = (
                    query_intent.section_of(meta) == c.sections[0] if c.sections else True)
                rid = all_ids[ev.idx]
                item["source_index"] = position.get(rid)
                if item["source_index"] is not None:
                    r = results[item["source_index"]]
                    item["doc_name"], item["page_num"] = r["doc_name"], r["page_num"]
                item["quotes"] = ev.quotes
            items.append(item)
        return items

    def _focus_ranking(self, mentions, understanding, scores, allowed_ids, all_ids, limit):
        """Kênh trọng tâm: chunk của đúng thuốc ∩ đúng mục, xếp theo BM25."""
        pool = None
        if mentions and self._entity_idx:
            keys = {k for m in mentions for k in m.entities}
            parts = [self._entity_idx[k] for k in keys if k in self._entity_idx]
            if parts:
                pool = np.unique(np.concatenate(parts))
        # Mục suy từ điều kiện bệnh nhân ("trẻ em" -> Liều dùng) chỉ có nghĩa
        # khi biết đang hỏi thuốc nào; "trẻ em bị tiêu chảy dùng thuốc nào"
        # không được kéo về các đoạn liều trẻ em của thuốc bất kỳ.
        slot_only = understanding is not None and not understanding.intents
        if slot_only and not mentions:
            return []
        if understanding is not None and understanding.sections and self._section_idx:
            parts = [self._section_idx[f] for f in understanding.sections if f in self._section_idx]
            if parts:
                sec = np.unique(np.concatenate(parts))
                pool = sec if pool is None else np.intersect1d(pool, sec, assume_unique=True)
        if pool is None or not len(pool):
            return []
        has_entity = bool(mentions)
        ranking = []
        for idx in pool[np.argsort(-scores[pool], kind="stable")]:
            # Không có tên thuốc thì mục quá rộng (cả nghìn chunk "Liều dùng"),
            # chỉ nhận chunk có khớp chữ. Có tên thuốc thì mọi chunk của thuốc
            # đó ở đúng mục đều là ứng viên thật, kể cả khi điểm BM25 bằng 0.
            if not has_entity and scores[idx] <= 0.0:
                break
            if allowed_ids is not None and all_ids[idx] not in allowed_ids:
                continue
            ranking.append(all_ids[idx])
            if len(ranking) >= limit:
                break
        return ranking

    def health(self):
        corpus = self._corpus_cache
        counts = {}
        if corpus:
            for meta in corpus[1]:
                name = meta.get("doc_name", "")
                counts[name] = counts.get(name, 0) + 1
        return {
            "embedding_loaded": self._embedding is not None,
            "corpus_chunks": len(corpus[0]) if corpus else 0,
            "bm25_ready": self._bm25_model is not None,
            "docs": [{"doc_name": name, "chunks": count} for name, count in sorted(counts.items())],
            "degraded": bool(self._embedding_error or self._index_error),
            "reason": self._index_error or self._embedding_error,
            "last_build_at": self._last_build_at,
            "last_build_seconds": self._last_build_seconds,
        }

    def add_chunks(self, documents: List[Document], ids: Optional[List[str]] = None):
        """
        Thêm chunk vào vector store.

        Truyền `ids` tất định để lần nạp lại ghi đè thay vì nhân bản: Chroma
        dùng upsert theo id, còn nếu để trống thì mỗi lần chạy sinh UUID mới và
        cùng một nội dung sẽ nằm nhiều lần trong index.
        """
        if not documents:
            return
        embedding = self.embedding
        if embedding is None:
            raise EmbeddingUnavailable("Không có mô hình embedding để ghi chỉ mục.")
        db = self.db
        if db is None:
            raise IndexUnavailable("Không mở được chỉ mục để ghi.")
        db._embedding_function = embedding
        if ids is not None:
            if len(ids) != len(documents):
                raise ValueError(
                    f"Số ids ({len(ids)}) không khớp số documents ({len(documents)})."
                )
            db.add_documents(documents, ids=ids)
        else:
            db.add_documents(documents)
        self._invalidate_caches()
        print(f"Added {len(documents)} documents to vector store.")

    def delete_document(self, doc_name: str):
        if self.db is None:
            raise IndexUnavailable("Không mở được chỉ mục để xoá.")
        res = self._get_batched(where={"doc_name": doc_name}, include=[])
        if res and res["ids"]:
            self.db.delete(ids=res["ids"])
            self._invalidate_caches()
            print(f"Deleted document '{doc_name}' ({len(res['ids'])} chunks) from vector database.")

    def list_documents(self) -> List[Dict[str, Any]]:
        all_metadatas = self._corpus_cache[1] if self._corpus_cache else None
        if all_metadatas is None:
            res = self._get_batched(include=["metadatas"])
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

    # Hybrid search: dense (cosine) + BM25, hợp nhất bằng RRF. KHÔNG có bước
    # rerank — cross-encoder đã gỡ, xem chú thích "3." ở đầu tệp.
    def search(self, query: str, top_k: int = 5, doc_names: Optional[List[str]] = None,
               exclude_doc_names: Optional[set] = None) -> List[Dict[str, Any]]:
        """Hybrid search over the indexed chunks.

        `doc_names` restricts the search to a subset of documents — used by the
        multi-source comparison feature, which needs the best passages *per
        document* rather than the globally best passages.

        `exclude_doc_names` loại tài liệu riêng của bác sĩ khác. Lọc ở CẢ HAI
        nhánh trước khi cắt top-k (dense lọc ngay trong Chroma bằng $nin, BM25
        bỏ qua trước khi đếm), nên tài liệu bị ẩn không chiếm chỗ của kết quả
        thật. Tập rỗng thì đường tìm y hệt trước đây — P@5 đo cũ vẫn còn giá trị.
        """
        all_texts, all_metadatas, all_ids, bm25_model = self._get_corpus_and_bm25()

        # Gỡ Telex + khôi phục dấu theo kho. Mọi bước sau dùng câu đã chuẩn hoá;
        # câu gốc chỉ còn dùng để quyết định có tra thêm trường gấp dấu không.
        normalized = None
        original_query = query
        if ENABLE_QUERY_NORMALIZATION and self._lexicon is not None:
            normalized = self._lexicon.normalize(query)
            query = normalized.text
        use_folded = bool(normalized and normalized.unaccented and self._bm25_folded is not None)

        # Thuốc nào, mục nào. Tên thuốc mà sách viết khác được viết thêm vào câu
        # tra; câu hiển thị cho bác sĩ thì giữ nguyên.
        mentions, understanding, extra_names, drugs = self._understand(query)
        conditions = []
        if query_plan.ENABLE_QUERY_PLAN and understanding is not None and mentions:
            conditions = query_plan.plan(
                understanding.intents, understanding.slots,
                [(m.entities, (d["names"] or [m.text])[0], self._drug_terms(m, d["names"]))
                 for m, d in zip(mentions, drugs)],
            )
        abbreviations = query_intent.expand_abbreviations(original_query) if ENABLE_ENTITY_LINKING else []
        extra_names += [exp.lower() for _abbr, exp in abbreviations]
        search_query = f"{query} ({', '.join(extra_names)})" if extra_names else query
        understood = None
        if drugs or abbreviations or (understanding is not None and not understanding.empty):
            understood = {"drugs": drugs,
                          "abbreviations": [{"abbr": a, "expansion": e} for a, e in abbreviations],
                          **(understanding.as_dict() if understanding else {})}

        excluded = set(exclude_doc_names or ())
        if doc_names and excluded:
            doc_names = [d for d in doc_names if d not in excluded]
            if not doc_names:
                return SearchHits(status="NO_MATCH", degraded=self.embedding is None,
                                  reason=self._embedding_error)

        allowed_ids = None
        if doc_names:
            allowed_ids = {
                all_ids[idx] for idx, meta in enumerate(all_metadatas)
                if meta.get("doc_name") in set(doc_names)
            }
            if not allowed_ids:
                return SearchHits(status="NO_MATCH", degraded=self.embedding is None,
                                  reason=self._embedding_error)
        elif excluded:
            allowed_ids = {
                all_ids[idx] for idx, meta in enumerate(all_metadatas)
                if meta.get("doc_name") not in excluded
            }

        # A. DENSE RETRIEVAL: Query similarity from ChromaDB
        # Widen the candidate pool when filtering so enough of them survive the filter.
        k_candidates = min(top_k * (12 if doc_names else 4), len(all_texts))
        dense_filter = None
        if doc_names:
            dense_filter = (
                {"doc_name": doc_names[0]} if len(doc_names) == 1
                else {"doc_name": {"$in": list(doc_names)}}
            )
        elif excluded:
            dense_filter = {"doc_name": {"$nin": sorted(excluded)}}
        embedding = self.embedding
        dense_results_with_scores = []
        degraded = embedding is None
        reason = self._embedding_error if degraded else None
        if embedding is not None:
            try:
                # Không đổi client đọc metadata: embedding được dùng trực tiếp
                # cho truy vấn, tránh dựng thêm Chroma trong lúc đang phục vụ.
                dense_results_with_scores = self.db.similarity_search_by_vector_with_relevance_scores(
                    embedding.embed_query(search_query), k=k_candidates, filter=dense_filter
                )
            except Exception as e:
                degraded = True
                reason = f"Dense search lỗi: {e}"
                self._embedding_error = reason
                print(reason)

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
        subject = query_intent.indication_subject(query) if query_intent.ENABLE_INDICATION_RANKING else None
        tokenized_query = expand_rare_compounds(tokenize_text(search_query), self._doc_freq or {})
        if subject:
            for term in query_intent.expanded_terms(subject):
                tokenized_query.extend(expand_rare_compounds(tokenize_text(term), self._doc_freq or {}))
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

        # B2. Trường gấp dấu — chỉ khi bác sĩ gõ không dấu. Tách từ ghép bằng
        # chính từ điển của trường gấp, vì pyvi không tách được chữ không dấu.
        folded_ranking = []
        if use_folded:
            syllables = re.findall(r"\w+", fold(query))
            folded_query = expand_rare_compounds(
                query_normalize.segment_folded(syllables, self._folded_df or {}),
                self._folded_df or {},
            )
            folded_scores = self._bm25_folded.get_scores(folded_query)
            for idx in np.argsort(folded_scores)[::-1]:
                if folded_scores[idx] <= 0.0:
                    break
                if allowed_ids is not None and all_ids[idx] not in allowed_ids:
                    continue
                folded_ranking.append(all_ids[idx])
                if len(folded_ranking) >= k_candidates:
                    break

        # B3. Kênh trọng tâm: đúng thuốc ∩ đúng mục (xem 1d ở đầu tệp).
        focus_ranking = []
        if mentions or (understanding is not None and understanding.sections):
            focus_ranking = self._focus_ranking(
                mentions, understanding, bm25_scores, allowed_ids, all_ids, k_candidates
            )

        # C. RECIPROCAL RANK FUSION (RRF)
        # Combine rankings — công thức và lý do chọn trọng số ở đầu file.
        rrf_scores = {}

        # Score dense rank
        for rank, doc_id in enumerate(dense_ranking):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + RRF_W_DENSE / (RRF_K + rank + 1)

        # Score sparse rank
        for rank, doc_id in enumerate(sparse_ranking):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + RRF_W_SPARSE / (RRF_K + rank + 1)

        for rank, doc_id in enumerate(folded_ranking):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + RRF_W_FOLDED / (RRF_K + rank + 1)

        w_focus = RRF_W_FOCUS if mentions else RRF_W_FOCUS_SECTION_ONLY
        for rank, doc_id in enumerate(focus_ranking):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + w_focus / (RRF_K + rank + 1)

        # Sort candidate IDs by RRF score descending
        adjusted_scores = {
            doc_id: query_intent.adjusted_score(
                score, all_metadatas[by_id[doc_id]], all_texts[by_id[doc_id]], subject
            ) for doc_id, score in rrf_scores.items()
        }
        sorted_rrf_candidates = sorted(
            rrf_scores.items(), key=lambda item: -adjusted_scores[item[0]]
        )
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
                "generic_name": all_metadatas[idx].get("generic_name", ""),
                "name_suspect": bool(all_metadatas[idx].get("name_suspect", False)),
                "score": adjusted_scores[doc_id]
            })

        # D. Rerank tuỳ chọn (config.RERANKER_MODEL) — mặc định tắt, candidates
        # giữ thứ tự RRF giảm dần.
        candidates = rerank(query, candidates)

        # Return top_k search results
        # Under Parent-Child Indexing, the RAG assistant returns the PARENT_TEXT (richer context)
        # as the primary text, but keeps details of the document and page.
        results = []
        chosen = candidates[:top_k]

        # E. Bảng kiểm điều kiện: mỗi cặp (thuốc, điều kiện) phải có đoạn bằng
        # chứng trong danh sách nguồn; đoạn nào chưa có thì chèn thêm vào cuối.
        evidence = [self._find_evidence(c, bm25_scores, allowed_ids, all_ids, all_texts)
                    for c in conditions]
        have = {c["id"] for c in chosen}
        injected = 0
        for ev in evidence:
            if ev.idx is None or all_ids[ev.idx] in have or injected >= self.MAX_EVIDENCE_INJECT:
                continue
            idx = ev.idx
            meta = all_metadatas[idx]
            chosen.append({
                "id": all_ids[idx], "text": all_texts[idx],
                "doc_name": meta.get("doc_name", ""), "page_num": meta.get("page_num", 1),
                "parent_text": meta.get("parent_text", all_texts[idx]),
                "generic_name": meta.get("generic_name", ""),
                "name_suspect": bool(meta.get("name_suspect", False)),
                "score": 0.0,
            })
            have.add(all_ids[idx])
            injected += 1

        for c in chosen:
            results.append({
                "id": c["id"],
                "text": c["parent_text"],  # Parent text for the doctor/LLM to read
                "child_text": c["text"],   # Child text for matching highlights
                "doc_name": c["doc_name"],
                "page_num": c["page_num"],
                "generic_name": c["generic_name"],
                # Tên thuốc của chunk này do OCR đọc hỏng (xem drug_name.py).
                # Nội dung vẫn dùng được, chỉ cái nhãn là không đáng tin — nơi
                # nào hiển thị hoặc đưa cho LLM thì đừng khẳng định đó là tên
                # thuốc. Chunk KHÔNG bị loại vì nội dung là dữ liệu thuốc thật.
                "name_suspect": c["name_suspect"],
                "score": c["score"]
            })
            
        return SearchHits(results, degraded=degraded, reason=reason,
                          status="EMBEDDING_UNAVAILABLE" if degraded else
                          ("NO_MATCH" if not results else "OK"),
                          normalized=normalized if normalized and normalized.changed else None,
                          understood=understood,
                          coverage=self._coverage(evidence, results, all_ids) if evidence else None)

# Establish compatibility alias
VectorStore = VectorDB
