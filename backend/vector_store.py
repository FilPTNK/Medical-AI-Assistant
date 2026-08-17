import os
import uuid
import numpy as np
import json
import pickle
from typing import List, Dict, Any

# Lazy-loaded model
_model = None

def get_embedding_model():
    global _model
    if _model is None:
        print("Loading local embedding model (all-MiniLM-L6-v2)...")
        from sentence_transformers import SentenceTransformer
        import config
        # This will download the model to HF cache on first run (approx 90MB)
        _model = SentenceTransformer(config.EMBEDDING_MODEL)
        print("Embedding model loaded successfully.")
    return _model

class SimpleVectorStore:
    """
    A robust, zero-dependency NumPy-based vector store.
    Saves index to disk using pickle and json.
    This guarantees compatibility on all OS platforms without native compilation issues.
    """
    def __init__(self, db_dir: str):
        self.db_dir = db_dir
        self.index_path = os.path.join(db_dir, "vector_index.pkl")
        self.metadata_path = os.path.join(db_dir, "metadata.json")
        os.makedirs(db_dir, exist_ok=True)
        self.embeddings = [] # List of np.ndarray
        self.documents = []  # List of dicts: {"text": str, "doc_name": str, "page_num": int}
        self.load()

    def load(self):
        if os.path.exists(self.index_path) and os.path.exists(self.metadata_path):
            try:
                with open(self.index_path, "rb") as f:
                    self.embeddings = pickle.load(f)
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    self.documents = json.load(f)
                print(f"Loaded {len(self.documents)} chunks from local vector store.")
            except Exception as e:
                print(f"Error loading vector store: {e}. Starting fresh.")
                self.embeddings = []
                self.documents = []

    def save(self):
        try:
            with open(self.index_path, "wb") as f:
                pickle.dump(self.embeddings, f)
            with open(self.metadata_path, "w", encoding="utf-8") as f:
                json.dump(self.documents, f, ensure_ascii=False, indent=2)
            print(f"Saved {len(self.documents)} chunks to local vector store.")
        except Exception as e:
            print(f"Error saving vector store: {e}")

    def add_chunks(self, chunks: List[Dict[str, Any]]):
        if not chunks:
            return
        
        texts = [c["text"] for c in chunks]
        model = get_embedding_model()
        new_embeddings = model.encode(texts, show_progress_bar=False)

        for chunk, emb in zip(chunks, new_embeddings):
            self.embeddings.append(emb)
            self.documents.append({
                "id": str(uuid.uuid4()),
                "text": chunk["text"],
                "doc_name": chunk["doc_name"],
                "page_num": chunk["page_num"]
            })
        self.save()

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if not self.documents:
            return []

        model = get_embedding_model()
        query_emb = model.encode([query], show_progress_bar=False)[0]

        # Compute cosine similarity
        db_embs = np.array(self.embeddings)
        # Normalize
        query_norm = query_emb / np.linalg.norm(query_emb)
        db_norms = np.linalg.norm(db_embs, axis=1)
        # Handle zero division
        db_norms[db_norms == 0] = 1e-10
        db_embs_norm = db_embs / db_norms[:, np.newaxis]

        similarities = np.dot(db_embs_norm, query_norm)
        
        # Get top-k indices
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            # Only return matches with positive relevance
            if score > 0.05:
                doc = self.documents[idx].copy()
                doc["score"] = score
                results.append(doc)
        return results

    def delete_document(self, doc_name: str):
        indices_to_keep = [i for i, doc in enumerate(self.documents) if doc["doc_name"] != doc_name]
        self.embeddings = [self.embeddings[i] for i in indices_to_keep]
        self.documents = [self.documents[i] for i in indices_to_keep]
        self.save()

    def list_documents(self) -> List[Dict[str, Any]]:
        # Aggregate unique documents
        docs = {}
        for doc in self.documents:
            name = doc["doc_name"]
            if name not in docs:
                docs[name] = {
                    "doc_name": name,
                    "pages": set(),
                    "chunks": 0
                }
            docs[name]["pages"].add(doc["page_num"])
            docs[name]["chunks"] += 1
        
        return [
            {
                "doc_name": name,
                "page_count": len(info["pages"]),
                "chunk_count": info["chunks"]
            }
            for name, info in docs.items()
        ]

# Try to use ChromaDB if installed, otherwise fallback to SimpleVectorStore
try:
    import chromadb
    class ChromaVectorStore:
        def __init__(self, db_dir: str):
            self.db_dir = db_dir
            self.client = chromadb.PersistentClient(path=db_dir)
            self.collection = self.client.get_or_create_collection(
                name="medical_assistant",
                metadata={"hnsw:space": "cosine"}
            )
            print("ChromaDB initialized as vector store.")

        def add_chunks(self, chunks: List[Dict[str, Any]]):
            if not chunks:
                return
            texts = [c["text"] for c in chunks]
            model = get_embedding_model()
            embeddings = model.encode(texts, show_progress_bar=False).tolist()
            
            ids = [str(uuid.uuid4()) for _ in chunks]
            metadatas = [{"doc_name": c["doc_name"], "page_num": c["page_num"]} for c in chunks]

            # Chroma allows adding in batches of up to 40000
            self.collection.add(
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
                ids=ids
            )
            print(f"Added {len(chunks)} chunks to ChromaDB.")

        def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
            model = get_embedding_model()
            query_emb = model.encode([query], show_progress_bar=False).tolist()

            results = self.collection.query(
                query_embeddings=query_emb,
                n_results=top_k
            )

            formatted = []
            if results and results["documents"]:
                for i in range(len(results["documents"][0])):
                    # Chroma returns distance, cosine similarity = 1 - distance
                    dist = results["distances"][0][i] if "distances" in results else 0
                    score = 1.0 - dist
                    
                    formatted.append({
                        "id": results["ids"][0][i],
                        "text": results["documents"][0][i],
                        "doc_name": results["metadatas"][0][i]["doc_name"],
                        "page_num": results["metadatas"][0][i]["page_num"],
                        "score": score
                    })
            return formatted

        def delete_document(self, doc_name: str):
            self.collection.delete(where={"doc_name": doc_name})
            print(f"Deleted document '{doc_name}' from ChromaDB.")

        def list_documents(self) -> List[Dict[str, Any]]:
            # ChromaDB doesn't have a direct "group by" list, so we fetch metadatas
            # To avoid fetching huge data, we fetch only metadatas.
            all_data = self.collection.get(include=["metadatas"])
            docs = {}
            if all_data and all_data["metadatas"]:
                for meta in all_data["metadatas"]:
                    name = meta["doc_name"]
                    page = meta["page_num"]
                    if name not in docs:
                        docs[name] = {"pages": set(), "chunks": 0}
                    docs[name]["pages"].add(page)
                    docs[name]["chunks"] += 1

            return [
                {
                    "doc_name": name,
                    "page_count": len(info["pages"]),
                    "chunk_count": info["chunks"]
                }
                for name, info in docs.items()
            ]

    # Use Chroma
    VectorStore = ChromaVectorStore
except ImportError:
    print("ChromaDB not found. Falling back to NumPy SimpleVectorStore.")
    VectorStore = SimpleVectorStore
