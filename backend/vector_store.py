import os
import re
import math
import numpy as np
from typing import List, Dict, Any, Optional
from collections import Counter

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document

# 1. Helper function for Vietnamese / English tokenisation
def tokenize_text(text: str) -> List[str]:
    text = text.lower()
    # Matches words, numbers
    return re.findall(r'\w+', text)

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

# 3. Lazy loaded Cross-Encoder Reranker
_cross_encoder = None

def get_cross_encoder():
    global _cross_encoder
    if _cross_encoder is None:
        model_name = "cross-encoder/ms-marco-MiniLM-L-6-v2"
        print(f"Loading local Cross-Encoder reranker ({model_name})...")
        try:
            from sentence_transformers import CrossEncoder
            _cross_encoder = CrossEncoder(model_name)
            print("Cross-Encoder loaded successfully.")
        except Exception as e:
            print(f"Failed to load sentence-transformers CrossEncoder: {e}. Running search without reranker.")
    return _cross_encoder

# 4. Upgraded VectorDB class matching the requirements & visual screenshots
class VectorDB:
    def __init__(
        self,
        documents_or_persist_dir=None,
        embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
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
        
        print(f"Initializing HuggingFaceEmbeddings with model: {embedding_model}")
        self.embedding = HuggingFaceEmbeddings(model_name=embedding_model)
        self.db = self._build_db(documents)

    # Building or loading database as shown in Image 1
    def _build_db(self, documents):
        # Trường hợp tải database đã có từ persist_dir
        if documents is None or len(documents) == 0:
            db = Chroma(
                collection_name=self.collection_name,
                embedding_function=self.embedding,
                persist_directory=self.persist_dir,
            )
        # Trường hợp tạo mới database từ documents
        else:
            db = Chroma.from_documents(
                documents=documents,
                embedding=self.embedding,
                collection_name=self.collection_name,
                persist_directory=self.persist_dir,
            )
        return db

    # Get retriever as shown in Image 1
    def get_retriever(self, search_kwargs: dict = None):
        if search_kwargs is None:
            search_kwargs = {"k": 4} # Mặc định lấy 4 document gần nhất
            
        return self.db.as_retriever(
            search_type="similarity",
            search_kwargs=search_kwargs,
        )

    # Unified methods for FastAPI interaction
    def add_chunks(self, documents: List[Document]):
        if not documents:
            return
        self.db.add_documents(documents)
        print(f"Added {len(documents)} documents to vector store.")

    def delete_document(self, doc_name: str):
        res = self.db.get(where={"doc_name": doc_name})
        if res and res["ids"]:
            self.db.delete(ids=res["ids"])
            print(f"Deleted document '{doc_name}' ({len(res['ids'])} chunks) from vector database.")

    def list_documents(self) -> List[Dict[str, Any]]:
        res = self.db.get(include=["metadatas"])
        docs = {}
        if res and res["metadatas"]:
            for meta in res["metadatas"]:
                name = meta.get("doc_name")
                page = meta.get("page_num", 1)
                doc_type = meta.get("doc_type", "child")
                if not name:
                    continue
                if name not in docs:
                    docs[name] = {"pages": set(), "chunks": 0}
                docs[name]["pages"].add(page)
                if doc_type == "child":
                    docs[name]["chunks"] += 1
                    
        return [
            {
                "doc_name": name,
                "page_count": len(info["pages"]),
                "chunk_count": info["chunks"]
            }
            for name, info in docs.items()
        ]

    # Advanced Hybrid Search with BM25, RRF, and Cross-Encoder Reranking
    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        # Fetch child documents to run sparse BM25 indexing
        db_content = self.db.get(where={"doc_type": "child"}, include=["metadatas", "documents"])
        
        if not db_content or not db_content["documents"]:
            print("Vector store is empty or has no child chunks. Skipping search.")
            return []
            
        all_texts = db_content["documents"]
        all_metadatas = db_content["metadatas"]
        all_ids = db_content["ids"]
        
        # A. DENSE RETRIEVAL: Query similarity from ChromaDB
        # We search with a wider margin (top_k * 4) to ensure good candidates for RRF and Reranking
        k_candidates = min(top_k * 4, len(all_texts))
        dense_results_with_scores = self.db.similarity_search_with_relevance_scores(
            query, k=k_candidates, filter={"doc_type": "child"}
        )
        
        dense_ranking = []
        for doc, score in dense_results_with_scores:
            # Try to match the retrieved doc with the db_content list to find the ID
            match_idx = -1
            for idx, text in enumerate(all_texts):
                if text == doc.page_content and all_metadatas[idx].get("page_num") == doc.metadata.get("page_num"):
                    match_idx = idx
                    break
            if match_idx != -1:
                dense_ranking.append(all_ids[match_idx])
                
        # B. SPARSE RETRIEVAL: BM25 score calculation
        tokenized_corpus = [tokenize_text(text) for text in all_texts]
        
        # Load rank-bm25 if available, otherwise fallback
        bm25_model = None
        try:
            from rank_bm25 import BM25Okapi
            bm25_model = BM25Okapi(tokenized_corpus)
        except Exception:
            bm25_model = FallbackBM25(tokenized_corpus)
            
        tokenized_query = tokenize_text(query)
        bm25_scores = bm25_model.get_scores(tokenized_query)
        
        # Sort indices by BM25 score descending
        sparse_indices = np.argsort(bm25_scores)[::-1][:k_candidates]
        sparse_ranking = [all_ids[idx] for idx in sparse_indices if bm25_scores[idx] > 0.0]

        # C. RECIPROCAL RANK FUSION (RRF)
        # Combine rankings: RRF_Score = 1/(60 + dense_rank) + 1/(60 + sparse_rank)
        rrf_scores = {}
        
        # Score dense rank
        for rank, doc_id in enumerate(dense_ranking):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (60.0 + rank + 1)
            
        # Score sparse rank
        for rank, doc_id in enumerate(sparse_ranking):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (60.0 + rank + 1)

        # Sort candidate IDs by RRF score descending
        sorted_rrf_candidates = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        top_rrf_ids = [doc_id for doc_id, rrf_score in sorted_rrf_candidates[:k_candidates]]

        # Gather actual documents for Reranking
        candidates = []
        for doc_id in top_rrf_ids:
            idx = all_ids.index(doc_id)
            candidates.append({
                "id": doc_id,
                "text": all_texts[idx],
                "doc_name": all_metadatas[idx].get("doc_name", ""),
                "page_num": all_metadatas[idx].get("page_num", 1),
                "parent_text": all_metadatas[idx].get("parent_text", all_texts[idx]),
                "score": rrf_scores[doc_id]  # Default score is RRF
            })

        # D. CROSS-ENCODER RERANKING
        cross_encoder = get_cross_encoder()
        if cross_encoder and candidates:
            try:
                # Format candidate inputs: [[query, context], [query, context], ...]
                # We use parent_text as the context for richer sentence similarity matching
                rerank_inputs = [[query, c["parent_text"]] for c in candidates]
                reranker_scores = cross_encoder.predict(rerank_inputs)
                
                # Update scores with cross-encoder outputs
                for idx, c in enumerate(candidates):
                    # Normalize raw logits to 0-1 range using sigmoid approximation
                    raw_score = reranker_scores[idx]
                    prob_score = 1.0 / (1.0 + math.exp(-raw_score))
                    c["score"] = float(prob_score)
                    
                # Sort by reranked scores
                candidates.sort(key=lambda x: x["score"], reverse=True)
            except Exception as e:
                print(f"Reranking failed with error: {e}. Falling back to RRF rankings.")

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
