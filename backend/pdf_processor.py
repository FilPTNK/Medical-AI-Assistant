import os
import re
import glob
import unicodedata
from typing import List, Dict, Any
from tqdm import tqdm
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

# 1. Clean Vietnamese text as shown in Image 2
def clean_vietnamese_text(text: str) -> str:
    # Chuẩn hóa Unicode về dạng NFC cho tiếng Việt
    text = unicodedata.normalize('NFC', text)
    text = "".join(
        char for char in text
        if not unicodedata.category(char).startswith('C') or char in '\n\t'
    )
    
    # Gộp khoảng trắng thừa và dòng trống
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n', text)
    return text.strip()

# 2. SimpleLoader as shown in Image 3
class SimpleLoader:
    # Tải một file PDF và gọi hàm làm sạch nội dung văn bản
    def load_pdf(self, pdf_file: str) -> List[Document]:
        # Set extract_images=False by default to avoid slow tesseract calls unless needed
        # We can try to load with extract_images=True but if it fails or runs slow, we fall back
        try:
            loader = PyPDFLoader(pdf_file, extract_images=False)
            docs = loader.load()
        except Exception:
            loader = PyPDFLoader(pdf_file, extract_images=True)
            docs = loader.load()

        for doc in docs:
            doc.page_content = clean_vietnamese_text(doc.page_content)
        return docs
        
    # Tải tất cả file PDF trong một thư mục
    def load_dir(self, dir_path: str) -> List[Document]:
        pdf_files = glob.glob(os.path.join(dir_path, "*.pdf"))
        if not pdf_files:
            raise ValueError(f"No PDF files found in {dir_path}")
            
        all_docs = []
        for pdf_file in tqdm(pdf_files, desc="Loading PDFs"):
            try:
                all_docs.extend(self.load_pdf(pdf_file))
            except Exception as e:
                print(f"Error loading {pdf_file}: {e}")
        return all_docs

# 3. TextSplitter as shown in Image 3
class TextSplitter:
    # Khởi tạo với chunk_size và chunk_overlap phù hợp cho tiếng Việt
    def __init__(
        self,
        chunk_size: int = 400,
        chunk_overlap: int = 120,
    ):
        self.splitter = RecursiveCharacterTextSplitter(
            separators=["\n\n", "\n", " ", ""],
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
        )
        
    # Chia danh sách documents thành các chunk nhỏ hơn
    def split(self, documents: List[Document]) -> List[Document]:
        return self.splitter.split_documents(documents)

# 4. Extractive sentence summarizer (fully open-source and local)
def extract_page_summary(text: str, max_sentences: int = 3) -> str:
    """
    Creates an extractive summary of the page content using a local TF-IDF ranking of sentences.
    Ensures that summary indexing runs offline without requiring external API calls.
    """
    if not text or len(text) < 150:
        return text

    # Simple sentence splitting on Vietnamese punctuation
    sentences = re.split(r'(?<=[.!?])\s+', text)
    if len(sentences) <= max_sentences:
        return text

    # Simple TF-IDF term frequency calculation
    words = re.findall(r'\w+', text.lower())
    if not words:
        return text

    tf = {}
    for w in words:
        tf[w] = tf.get(w, 0) + 1

    # Score sentences based on word frequencies
    sentence_scores = []
    for idx, sentence in enumerate(sentences):
        s_words = re.findall(r'\w+', sentence.lower())
        if not s_words:
            sentence_scores.append((0, idx))
            continue
        # Average term frequency score
        score = sum(tf.get(w, 0) for w in s_words) / len(s_words)
        sentence_scores.append((score, idx))

    # Pick the top scoring sentences
    sentence_scores.sort(key=lambda x: x[0], reverse=True)
    top_indices = [x[1] for x in sentence_scores[:max_sentences]]
    top_indices.sort()  # Keep chronological order

    summary_sentences = [sentences[i] for i in top_indices]
    return " ".join(summary_sentences)

# 5. Pipeline orchestrator for Parent-Child & Summary Indexing
def process_pdf_parent_child_summary(pdf_file_path: str) -> List[Document]:
    """
    Loads PDF, cleans text, and generates three index components:
    1. Parent chunks mapped to child chunks (stored as child chunks with parent text in metadata)
    2. Summary chunks (summaries of each page indexed for high-level retrieval)
    
    Returns a unified list of LangChain Document objects ready to be added to Chroma.
    """
    doc_name = os.path.basename(pdf_file_path)
    
    # Load and clean document
    loader = SimpleLoader()
    raw_pages = loader.load_pdf(pdf_file_path)
    
    parent_splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", " ", ""],
        chunk_size=1500,
        chunk_overlap=300,
        length_function=len
    )
    
    child_splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", " ", ""],
        chunk_size=400,
        chunk_overlap=120,
        length_function=len
    )
    
    processed_documents = []
    
    for page in raw_pages:
        # Extract page number (PyPDFLoader is 0-indexed in metadata 'page')
        page_num = page.metadata.get("page", 0) + 1
        page_text = page.page_content
        
        if not page_text:
            continue
            
        # A. Create Summary Chunk for this page
        page_summary = extract_page_summary(page_text, max_sentences=3)
        summary_doc = Document(
            page_content=page_summary,
            metadata={
                "doc_name": doc_name,
                "page_num": page_num,
                "doc_type": "summary",
                "parent_text": page_text  # Page text is the parent for page summaries
            }
        )
        processed_documents.append(summary_doc)
        
        # B. Create Parent Chunks
        parent_docs = parent_splitter.split_documents([page])
        for p_idx, p_doc in enumerate(parent_docs):
            p_text = p_doc.page_content
            parent_id = f"{doc_name}_p{page_num}_{p_idx}"
            
            # C. Create Child Chunks from this Parent Chunk
            child_docs = child_splitter.split_documents([p_doc])
            for c_doc in child_docs:
                child_doc = Document(
                    page_content=c_doc.page_content,
                    metadata={
                        "doc_name": doc_name,
                        "page_num": page_num,
                        "doc_type": "child",
                        "parent_id": parent_id,
                        "parent_text": p_text
                    }
                )
                processed_documents.append(child_doc)
                
    return processed_documents
