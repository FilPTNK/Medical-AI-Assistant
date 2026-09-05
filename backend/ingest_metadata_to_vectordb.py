"""ĐÃ THAY THẾ — đừng chạy. Dùng: python backend/ingest_book.py --doc-name <ID> --replace

Kịch bản này gọi add_documents() mà KHÔNG truyền ids, nên Chroma sinh UUID mới
mỗi lần chạy: chạy lại là nhân bản toàn bộ chỉ mục. Đúng việc đó đã xảy ra —
27 909 embedding cho 18 717 chunk, phải xoá và nạp lại mới sạch. ingest_book.py
sinh id tất định theo nội dung nên chạy bao nhiêu lần cũng cho một kết quả.

Giữ lại để tham chiếu, không nằm trong luồng nào đang dùng.
"""

import os
import sys
import json
import shutil
from typing import List
from tqdm import tqdm
from langchain_core.documents import Document

# Cấu hình đường dẫn
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGINAL_PDF = os.path.join(BASE_DIR, "data", "THUOC-BIET-DUOC-VA-CACH-SU-DUNG.pdf")
UPLOADS_DIR = os.path.join(BASE_DIR, "backend", "data", "uploads")
PAGES_CACHE_DIR = os.path.join(BASE_DIR, "backend", "data", "pages_cache")
METADATA_JSON_PATH = os.path.join(BASE_DIR, "backend", "data", "vector_db", "metadata.json")
VECTOR_DB_DIR = os.path.join(BASE_DIR, "backend", "data", "vector_db")
PDF_TEXT_DIR = os.path.join(BASE_DIR, "pdf_text")

sys.path.append(os.path.join(BASE_DIR, "backend"))
from vector_store import VectorStore
import config

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(PAGES_CACHE_DIR, exist_ok=True)
os.makedirs(VECTOR_DB_DIR, exist_ok=True)


def ingest_book_to_vector_db(batch_size: int = 500):
    """
    Quy trình lưu trữ hoàn chỉnh:
    1. Sao chép file PDF gốc vào backend/data/uploads để phục vụ xem trước (Preview/Download).
    2. Gom các trang text OCR vào backend/data/pages_cache phục vụ tìm kiếm nguyên trang.
    3. Đọc metadata.json, chuyển thành LangChain Documents và nạp vào ChromaDB theo từng batch.
    """
    sys.stdout.reconfigure(encoding="utf-8")
    doc_name = os.path.basename(ORIGINAL_PDF)

    print("=" * 65)
    print("      TIẾN TRÌNH NẠP DỮ LIỆU SÁCH VÀO VECTOR DATABASE (CHROMADB)")
    print(f"  • File PDF gốc: {ORIGINAL_PDF}")
    print(f"  • File Metadata: {METADATA_JSON_PATH}")
    print(f"  • Vector DB: {VECTOR_DB_DIR}")
    print("=" * 65)

    # 1. Lưu file PDF gốc vào thư mục uploads
    target_upload_path = os.path.join(UPLOADS_DIR, doc_name)
    if os.path.exists(ORIGINAL_PDF):
        if not os.path.exists(target_upload_path) or os.path.getsize(target_upload_path) != os.path.getsize(ORIGINAL_PDF):
            print(f"\n[1/3] Đang sao chép file PDF gốc vào uploads/...")
            shutil.copy2(ORIGINAL_PDF, target_upload_path)
            print(f"  -> Đã lưu PDF gốc tại: {target_upload_path}")
        else:
            print(f"\n[1/3] File PDF gốc đã có sẵn trong uploads/ ({os.path.getsize(target_upload_path) / 1024 / 1024:.2f} MB).")
    else:
        print(f"\n[!] Cảnh báo: Không tìm thấy file PDF gốc tại {ORIGINAL_PDF}")

    # 2. Xây dựng bộ nhớ đệm trang (pages_cache) cho Reader UI
    cache_file = os.path.join(PAGES_CACHE_DIR, f"{doc_name}.json")
    print(f"\n[2/3] Đang tổng hợp bộ nhớ đệm trang (pages_cache)...")
    pages_data = {}
    if os.path.exists(PDF_TEXT_DIR):
        txt_files = sorted(os.listdir(PDF_TEXT_DIR))
        for f in txt_files:
            if f.startswith("page_") and f.endswith(".txt"):
                try:
                    page_num = str(int(f.replace("page_", "").replace(".txt", "")))
                    with open(os.path.join(PDF_TEXT_DIR, f), "r", encoding="utf-8") as tf:
                        pages_data[page_num] = tf.read()
                except Exception:
                    continue

    if pages_data:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(pages_data, f, ensure_ascii=False, indent=2)
        print(f"  -> Đã lưu cache {len(pages_data)} trang vào: {cache_file}")

    # 3. Đọc metadata.json và nạp vào ChromaDB
    print(f"\n[3/3] Đang đọc metadata.json và nạp vào Vector Store (ChromaDB)...")
    if not os.path.exists(METADATA_JSON_PATH):
        print(f"[!] Lỗi: Không tìm thấy file {METADATA_JSON_PATH}")
        return

    with open(METADATA_JSON_PATH, "r", encoding="utf-8") as f:
        raw_chunks = json.load(f)

    print(f"  -> Tìm thấy {len(raw_chunks)} chunks trong metadata.json.")
    if not raw_chunks:
        print("[!] metadata.json đang trống.")
        return

    # Chuyển đổi thành LangChain Document objects
    documents: List[Document] = []
    for c in raw_chunks:
        generic_name = c.get("generic_name", "UNKNOWN")
        field_name = c.get("field_name", "Thông tin")
        content = c.get("content", "")
        brand_list = c.get("brand_names", [])
        brand_str = ", ".join(brand_list) if isinstance(brand_list, list) else str(brand_list)
        page_num = c.get("page_in_file", 1)

        # Tạo ngữ cảnh Parent-Text giàu thông tin cho LLM & Vector Embeddings
        parent_text = f"【THUỐC: {generic_name}】(Biệt dược: {brand_str if brand_str else 'Không'})\n[{field_name}]\n{content}"

        doc = Document(
            page_content=parent_text,
            metadata={
                "doc_name": doc_name,
                "chunk_id": c.get("chunk_id", ""),
                "generic_name": generic_name,
                "brand_names": brand_str,
                "field_type": c.get("field_type", "GENERAL"),
                "field_name": field_name,
                "page_num": page_num,
                "doc_type": "child",
                "parent_text": parent_text,
                "source": doc_name,
                "page": page_num,
            }
        )
        documents.append(doc)

    # Khởi tạo VectorStore và thêm chunks theo batch
    print(f"[*] Khởi tạo VectorStore tại: {VECTOR_DB_DIR}...")
    db = VectorStore(VECTOR_DB_DIR)

    print(f"[*] Bắt đầu nạp {len(documents)} chunks theo từng đợt ({batch_size} chunks/lần)...")
    for i in tqdm(range(0, len(documents), batch_size), desc="Đang nạp vào ChromaDB"):
        batch = documents[i : i + batch_size]
        db.add_chunks(batch)

    print("\n" + "=" * 65)
    print("            NẠP VECTOR DATABASE HOÀN TẤT THÀNH CÔNG!")
    print(f"  • Đã lưu PDF gốc vào: {target_upload_path}")
    print(f"  • Đã lập chỉ mục {len(documents)} chunks vào ChromaDB")
    print("=" * 65)


if __name__ == "__main__":
    ingest_book_to_vector_db(batch_size=500)
