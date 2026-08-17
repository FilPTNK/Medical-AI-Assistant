import os
from pypdf import PdfReader

def extract_pdf_pages(file_path: str):
    """
    Extracts text from a PDF file page by page.
    Returns a list of dictionaries with page number, text content, and document name.
    """
    doc_name = os.path.basename(file_path)
    reader = PdfReader(file_path)
    pages_data = []

    for page_idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        text = text.strip()
        if text:
            pages_data.append({
                "doc_name": doc_name,
                "page_num": page_idx + 1,  # 1-indexed for reader display
                "text": text
            })
    return pages_data

def chunk_text(pages_data, chunk_size: int = 800, overlap: int = 150):
    """
    Chunks text from each page to ensure optimal vector database search.
    Each chunk retains its source document name and page number.
    """
    chunks = []
    for page in pages_data:
        text = page["text"]
        page_num = page["page_num"]
        doc_name = page["doc_name"]

        # Simple sliding window chunker
        if len(text) <= chunk_size:
            chunks.append({
                "doc_name": doc_name,
                "page_num": page_num,
                "text": text
            })
            continue

        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append({
                "doc_name": doc_name,
                "page_num": page_num,
                "text": chunk
            })
            start += (chunk_size - overlap)
            
    return chunks
