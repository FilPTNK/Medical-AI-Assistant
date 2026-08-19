import os
import shutil
import json
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

import config
from pdf_processor import process_pdf_parent_child_summary, SimpleLoader
from vector_store import VectorStore
from llm_client import generate_answer

app = FastAPI(title="Medical RAG Assistant API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For local development, allow all
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize vector store
db = VectorStore(config.VECTOR_DB_DIR)

# Path to store full page texts for the reader
PAGES_CACHE_DIR = os.path.join(config.DATA_DIR, "pages_cache")
os.makedirs(PAGES_CACHE_DIR, exist_ok=True)

class QueryRequest(BaseModel):
    query: str

class SearchResultItem(BaseModel):
    id: Optional[str] = None
    text: str
    doc_name: str
    page_num: int
    score: float

class QueryResponse(BaseModel):
    answer: str
    sources: List[SearchResultItem]

# Storage configuration for patients (Medications is removed)
PATIENTS_FILE = os.path.join(config.DATA_DIR, "patients.json")

class PatientModel(BaseModel):
    id: Optional[str] = None
    name: str
    age: int
    gender: str
    diagnosis: str
    notes: Optional[str] = ""

def read_json_data(file_path: str) -> list:
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return []

def write_json_data(file_path: str, data: list):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error writing {file_path}: {e}")

@app.get("/api/patients")
def get_patients():
    return read_json_data(PATIENTS_FILE)

@app.post("/api/patients")
def add_patient(patient: PatientModel):
    patients = read_json_data(PATIENTS_FILE)
    import uuid
    new_patient = patient.dict()
    new_patient["id"] = str(uuid.uuid4())
    patients.append(new_patient)
    write_json_data(PATIENTS_FILE, patients)
    return new_patient

@app.delete("/api/patients/{patient_id}")
def delete_patient(patient_id: str):
    patients = read_json_data(PATIENTS_FILE)
    updated_patients = [p for p in patients if p.get("id") != patient_id]
    write_json_data(PATIENTS_FILE, updated_patients)
    return {"status": "success"}

def get_safe_filename(filename: str) -> str:
    """Sanitizes filename to prevent directory traversal."""
    return os.path.basename(filename).replace("..", "")

@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    safe_name = get_safe_filename(file.filename)
    save_path = os.path.join(config.UPLOAD_DIR, safe_name)

    # Save PDF locally
    try:
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {str(e)}")

    try:
        # 1. Process document through Parent-Child & Summary Indexer
        processed_docs = process_pdf_parent_child_summary(save_path)
        if not processed_docs:
            if os.path.exists(save_path):
                os.remove(save_path)
            raise HTTPException(status_code=400, detail="No readable text found in the PDF.")

        # 2. Cache full page text on disk for reader lookup
        loader = SimpleLoader()
        raw_pages = loader.load_pdf(save_path)
        
        cache_file = os.path.join(PAGES_CACHE_DIR, f"{safe_name}.json")
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({str(p.metadata.get("page", 0) + 1): p.page_content for p in raw_pages}, f, ensure_ascii=False, indent=2)

        # 3. Add chunks to vector index
        db.add_chunks(processed_docs)

        return {
            "status": "success",
            "filename": safe_name,
            "pages": len(raw_pages),
            "chunks": len(processed_docs)
        }

    except Exception as e:
        # Cleanup file if indexing failed
        if os.path.exists(save_path):
            os.remove(save_path)
        raise HTTPException(status_code=500, detail=f"Error indexing document: {str(e)}")

@app.get("/api/documents")
def list_documents():
    try:
        return db.list_documents()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/documents/{doc_name}")
def delete_document(doc_name: str):
    safe_name = get_safe_filename(doc_name)
    pdf_path = os.path.join(config.UPLOAD_DIR, safe_name)
    cache_path = os.path.join(PAGES_CACHE_DIR, f"{safe_name}.json")

    # Delete from vector store
    try:
        db.delete_document(safe_name)
    except Exception as e:
        print(f"Error removing from vector index: {e}")

    # Delete local files
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    if os.path.exists(cache_path):
        os.remove(cache_path)

    return {"status": "success", "message": f"Document '{safe_name}' deleted."}

# Chat Tab Search & Answer endpoint (uses LLM)
@app.post("/api/search", response_model=QueryResponse)
def search_and_answer(request: QueryRequest, x_deepseek_key: Optional[str] = Header(None)):
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    try:
        # Retrieve matching document contexts using advanced hybrid search + reranking
        sources = db.search(query, top_k=5)

        # Generate contextualized answer from LLM
        answer = generate_answer(query, sources, x_deepseek_key or "")

        # Map to Pydantic structure
        formatted_sources = [
            SearchResultItem(
                id=s.get("id"),
                text=s["text"],
                doc_name=s["doc_name"],
                page_num=s["page_num"],
                score=s["score"]
            )
            for s in sources
        ]

        return QueryResponse(answer=answer, sources=formatted_sources)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search and generation failed: {str(e)}")

# Literature Search Tab endpoint (local retrieval only, NO LLM)
@app.post("/api/literature-search", response_model=QueryResponse)
def literature_search(request: QueryRequest):
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    try:
        # Retrieve matching document contexts using advanced hybrid search + reranking
        sources = db.search(query, top_k=10)

        # Map to Pydantic structure
        formatted_sources = [
            SearchResultItem(
                id=s.get("id"),
                text=s["text"],
                doc_name=s["doc_name"],
                page_num=s["page_num"],
                score=s["score"]
            )
            for s in sources
        ]

        # No LLM answer returned.
        return QueryResponse(
            answer="Kết quả tìm kiếm y văn (Xếp hạng bởi RRF & Cross-Encoder Reranking):",
            sources=formatted_sources
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Literature search failed: {str(e)}")

@app.get("/api/documents/{doc_name}/pages/{page_num}")
def get_page_content(doc_name: str, page_num: int):
    safe_name = get_safe_filename(doc_name)
    cache_path = os.path.join(PAGES_CACHE_DIR, f"{safe_name}.json")

    if not os.path.exists(cache_path):
        raise HTTPException(status_code=404, detail="Document pages cache not found.")

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            pages = json.load(f)
        
        # page keys are stringified in JSON
        page_str = str(page_num)
        if page_str not in pages:
            raise HTTPException(status_code=404, detail=f"Page {page_num} not found in this document.")

        return {
            "doc_name": safe_name,
            "page_num": page_num,
            "text": pages[page_str]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=True)
