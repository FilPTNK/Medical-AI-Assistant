"""ĐÃ THAY THẾ — đừng chạy. Dùng: ocr_book.py rồi parse_biet_duoc.py.

Gộp OCR + bóc tách + ghi metadata.json làm một, bằng đường dẫn hard-code
(BASE_DIR/data/THUOC-...pdf) không còn tồn tại sau khi PDF chuyển vào
backend/data/uploads/. OCR giờ nằm ở ocr_book.py (có thể dừng giữa chừng rồi
chạy tiếp, dùng chung cho mọi sách).

Giữ lại để tham chiếu, không nằm trong luồng nào đang dùng.
"""

import os
import sys
import json
import time
import io
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from PIL import Image

try:
    import pymupdf as fitz
except ImportError:
    import fitz

import pytesseract
from drug_parser import parse_pdf_text_to_chunks

# Cấu hình Tesseract OCR & Tessdata
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSDATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tessdata")
os.environ["TESSDATA_PREFIX"] = TESSDATA_DIR

# Cấu hình đường dẫn dự án
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_PATH = os.path.join(BASE_DIR, "data", "THUOC-BIET-DUOC-VA-CACH-SU-DUNG.pdf")
PDF_TEXT_DIR = os.path.join(BASE_DIR, "pdf_text")
OUTPUT_METADATA_PATH = os.path.join(BASE_DIR, "backend", "data", "vector_db", "metadata.json")

os.makedirs(PDF_TEXT_DIR, exist_ok=True)
os.makedirs(os.path.dirname(OUTPUT_METADATA_PATH), exist_ok=True)


def ocr_single_page(page_idx: int, pdf_path: str = PDF_PATH) -> str:
    """
    Xử lý OCR cho 1 trang duy nhất:
    - Kiểm tra nếu đã có file cache trong pdf_text/ thì đọc ngay.
    - Cắt trang thành 2 cột dọc (Trái / Phải) và nhận diện bằng Tesseract vie+eng.
    - Lưu kết quả vào pdf_text/page_XXXX.txt.
    """
    page_num = page_idx + 1
    cache_file = os.path.join(PDF_TEXT_DIR, f"page_{page_num:04d}.txt")

    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            return f.read()

    doc = fitz.open(pdf_path)
    try:
        page = doc[page_idx]
        pix = page.get_pixmap(dpi=200)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        w, h = img.size

        # Cắt 2 cột dọc
        left_col = img.crop((0, 0, int(w * 0.49), h))
        right_col = img.crop((int(w * 0.49), 0, w, h))

        # Nhận diện chữ tiếng Việt + Tiếng Anh
        left_text = pytesseract.image_to_string(left_col, lang="vie+eng")
        right_text = pytesseract.image_to_string(right_col, lang="vie+eng")

        page_text = f"[Trang {page_num}]\n{left_text.strip()}\n\n{right_text.strip()}".strip()

        # Lưu file cache
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(page_text)

        return page_text
    finally:
        doc.close()


def run_full_book_indexing(
    start_page: int = 1,
    end_page: Optional[int] = None,
    max_workers: int = 4,
    save_interval: int = 25
):
    """
    Tiến trình OCR song song đa luồng và bóc tách Field-Centric Chunks toàn bộ sách.
    """
    sys.stdout.reconfigure(encoding="utf-8")

    doc = fitz.open(PDF_PATH)
    total_pages = len(doc)
    doc.close()

    if end_page is None or end_page > total_pages:
        end_page = total_pages

    page_indices = list(range(start_page - 1, end_page))
    num_to_process = len(page_indices)

    print("=" * 65)
    print("      TIẾN TRÌNH OCR & FIELD-CENTRIC CHUNK INDEXING TOÀN BỘ SÁCH")
    print(f"  • File nguồn: {os.path.basename(PDF_PATH)}")
    print(f"  • Tổng số trang xử lý: {num_to_process} trang (Trang {start_page} -> {end_page})")
    print(f"  • Số luồng song song (Threads): {max_workers}")
    print(f"  • File đầu ra: {OUTPUT_METADATA_PATH}")
    print("=" * 65)

    all_chunks: List[Dict[str, Any]] = []
    page_texts: Dict[int, str] = {}
    completed_count = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_page = {
            executor.submit(ocr_single_page, idx, PDF_PATH): idx for idx in page_indices
        }

        pbar = tqdm(total=num_to_process, desc="OCR & Parsing Pages", unit="page")

        for future in as_completed(future_to_page):
            idx = future_to_page[future]
            try:
                text = future.result()
                page_texts[idx] = text
            except Exception as e:
                print(f"\n[!] Lỗi tại trang {idx + 1}: {e}")
                page_texts[idx] = f"[Trang {idx + 1}]\n"

            completed_count += 1
            pbar.update(1)

            # Định kỳ bóc tách và lưu checkpoint
            if completed_count % save_interval == 0 or completed_count == num_to_process:
                # Sắp xếp lại văn bản theo thứ tự trang
                sorted_pages = [page_texts[i] for i in sorted(page_texts.keys())]
                combined_text = "\n\n".join(sorted_pages)
                current_chunks = parse_pdf_text_to_chunks(
                    combined_text,
                    source_file_name=os.path.basename(PDF_PATH)
                )
                with open(OUTPUT_METADATA_PATH, "w", encoding="utf-8") as f:
                    json.dump(current_chunks, f, ensure_ascii=False, indent=2)
                pbar.set_postfix({"chunks": len(current_chunks)})

        pbar.close()

    total_time = time.time() - t0
    # Tổng kết và ghi dữ liệu cuối cùng
    sorted_pages = [page_texts[i] for i in sorted(page_texts.keys())]
    combined_text = "\n\n".join(sorted_pages)
    final_chunks = parse_pdf_text_to_chunks(
        combined_text,
        source_file_name=os.path.basename(PDF_PATH)
    )

    with open(OUTPUT_METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(final_chunks, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 65)
    print("                  XỬ LÝ HOÀN TẤT THÀNH CÔNG!")
    print(f"  • Thời gian chạy: {total_time:.2f} giây ({total_time / 60:.2f} phút)")
    print(f"  • Tổng số trang đã xử lý: {len(page_texts)}")
    print(f"  • Tổng số Chunks tạo thành: {len(final_chunks)}")
    print(f"  • File kết quả: {OUTPUT_METADATA_PATH} ({os.path.getsize(OUTPUT_METADATA_PATH) / 1024:.2f} KB)")
    print("=" * 65)

    return final_chunks


if __name__ == "__main__":
    # Chạy tiến trình với 4 workers
    run_full_book_indexing(start_page=1, end_page=1555, max_workers=4)
