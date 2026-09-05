"""
OCR toàn bộ một cuốn sách scan, có tham số và chạy tiếp được sau khi ngắt.

Thay cho batch_process_book.py (đường dẫn hard-code, luôn cắt 2 cột, mở lại file
PDF cho từng trang).

Khác biệt đáng kể:

* Cắt cột là tuỳ chọn. Thuốc Biệt Dược in 2 cột; Dược thư Quốc gia in 1 cột, ép
  cắt đôi sẽ xé ngang từng câu.
* Tách riêng running head. Dải 6% trên cùng chứa số trang in và tên chạy đầu
  trang — Bước 02 cần nó để dựng bản đồ trang. Thân trang được OCR từ dưới dải
  này trở xuống, nên không bị dòng "DTQGVN 3 Bezafibrat 297" lẫn vào giữa nội
  dung và làm rối parser.
* Mỗi luồng mở PDF đúng một lần. Script cũ gọi fitz.open() cho từng trang —
  chấp nhận được với file 65 MB, phí phạm với file 835 MB.
* Ghi cache theo từng trang, nên ngắt giữa chừng rồi chạy lại không mất công.

Dùng:
    python backend/ocr_book.py --doc-name DTQGVN-2022-Q1
    python backend/ocr_book.py --doc-name DTQGVN-2022-Q1 --start 100 --end 200
"""

import os
import io
import sys
import time
import argparse
import threading
from typing import List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from tqdm import tqdm
from PIL import Image

try:
    import pymupdf as fitz
except ImportError:
    import fitz

import pytesseract

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import documents

# Cấu hình Tesseract. TESSDATA_PREFIX trỏ vào tessdata/ cạnh file này để dùng
# đúng bộ dữ liệu tiếng Việt đi kèm dự án.
pytesseract.pytesseract.tesseract_cmd = os.environ.get(
    "TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)
os.environ.setdefault(
    "TESSDATA_PREFIX", os.path.join(os.path.dirname(os.path.abspath(__file__)), "tessdata")
)

# Mặc định Tesseract tự đa luồng bằng OpenMP, nên nhiều worker sẽ giành nhau lõi
# CPU. Ép mỗi tiến trình chạy một luồng rồi để ThreadPoolExecutor lo song song:
# đo trên máy 6 nhân, 2,6 s/trang thay vì 3,8 s/trang.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")

# Chiều cao dải running head, tính theo tỉ lệ chiều cao trang.
HEAD_BAND = 0.06

_local = threading.local()


def _doc_for_thread(pdf_path: str):
    """Một handle PDF cho mỗi luồng — Document của PyMuPDF không dùng chung được."""
    if getattr(_local, "path", None) != pdf_path:
        old = getattr(_local, "doc", None)
        if old is not None:
            try:
                old.close()
            except Exception:
                pass
        _local.doc = fitz.open(pdf_path)
        _local.path = pdf_path
    return _local.doc


def _render(page, dpi: int, clip=None) -> Image.Image:
    pix = page.get_pixmap(dpi=dpi, clip=clip)
    return Image.open(io.BytesIO(pix.tobytes("png")))


def ocr_page(
    pdf_path: str,
    page_idx: int,
    doc_name: str,
    dpi: int,
    columns: int,
    lang: str,
) -> Tuple[int, int, int]:
    """
    OCR một trang, ghi ra hai file: thân trang và running head.

    Trả về (page_idx, số ký tự thân trang, đã dùng cache hay chưa).
    """
    page_num = page_idx + 1
    body_file = documents.ocr_page_path(doc_name, page_num)
    head_file = os.path.join(documents.ocr_dir(doc_name), f"head_{page_num:04d}.txt")

    if os.path.exists(body_file) and os.path.exists(head_file):
        with open(body_file, "r", encoding="utf-8") as f:
            return page_idx, len(f.read()), 1

    doc = _doc_for_thread(pdf_path)
    page = doc[page_idx]
    rect = page.rect
    cut = rect.height * HEAD_BAND

    # 1. Running head — dải trên cùng, OCR riêng
    head_img = _render(page, dpi, fitz.Rect(0, 0, rect.width, cut))
    head_text = pytesseract.image_to_string(head_img, lang=lang).strip()

    # 2. Thân trang — từ dưới dải head trở xuống
    body_clip = fitz.Rect(0, cut, rect.width, rect.height)
    body_img = _render(page, dpi, body_clip)

    if columns >= 2:
        w, h = body_img.size
        left = pytesseract.image_to_string(
            body_img.crop((0, 0, int(w * 0.49), h)), lang=lang
        ).strip()
        right = pytesseract.image_to_string(
            body_img.crop((int(w * 0.49), 0, w, h)), lang=lang
        ).strip()
        body_text = f"{left}\n\n{right}".strip()
    else:
        body_text = pytesseract.image_to_string(body_img, lang=lang).strip()

    os.makedirs(documents.ocr_dir(doc_name), exist_ok=True)
    with open(body_file, "w", encoding="utf-8") as f:
        f.write(f"[Trang {page_num}]\n{body_text}")
    with open(head_file, "w", encoding="utf-8") as f:
        f.write(head_text)

    return page_idx, len(body_text), 0


def run(
    doc_name: str,
    pdf_path: Optional[str],
    start: int,
    end: Optional[int],
    workers: int,
    dpi: Optional[int],
    columns: Optional[int],
    lang: Optional[str],
) -> None:
    manifest = documents.load_manifest(doc_name)
    if not manifest:
        print(f"[!] Chưa có manifest cho '{doc_name}'. Chạy migrate_phase0.py trước.")
        return

    pdf_path = pdf_path or documents.upload_path(doc_name)
    if not os.path.exists(pdf_path):
        print(f"[!] Không thấy PDF: {pdf_path}")
        return

    ocr_cfg = manifest.get("ocr") or {}
    dpi = dpi or ocr_cfg.get("dpi", 300)
    columns = columns if columns is not None else ocr_cfg.get("columns", 1)
    lang = lang or ocr_cfg.get("lang", "vie+eng")

    with fitz.open(pdf_path) as d:
        total_pages = len(d)

    if end is None or end > total_pages:
        end = total_pages
    page_indices = list(range(start - 1, end))

    print("=" * 66)
    print("   OCR TOÀN BỘ SÁCH")
    print(f"   Tài liệu : {manifest.get('doc_title')}  [{doc_name}]")
    print(f"   Nguồn    : {os.path.basename(pdf_path)}  ({os.path.getsize(pdf_path)/1048576:.0f} MB)")
    print(f"   Phạm vi  : trang {start} – {end} / {total_pages}")
    print(f"   Cấu hình : {dpi} DPI · {columns} cột · {lang} · {workers} luồng")
    print(f"   Đầu ra   : {documents.ocr_dir(doc_name)}")
    print("=" * 66)

    os.makedirs(documents.ocr_dir(doc_name), exist_ok=True)

    cached = 0
    short_pages: List[int] = []
    failed: List[int] = []
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(ocr_page, pdf_path, i, doc_name, dpi, columns, lang): i
            for i in page_indices
        }
        pbar = tqdm(total=len(page_indices), desc="  OCR", unit="trang")
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                _, n_chars, was_cached = fut.result()
                cached += was_cached
                # Trang gần như trống thường là trang trắng, hoặc scan lỗi cần
                # OCR lại ở DPI cao hơn. Ghi lại để rà tay.
                if n_chars < 200:
                    short_pages.append(idx + 1)
            except Exception as e:
                failed.append(idx + 1)
                pbar.write(f"  [!] Lỗi trang {idx + 1}: {e}")
            pbar.update(1)
        pbar.close()

    elapsed = time.time() - t0
    done = len(page_indices) - len(failed)

    print("\n" + "=" * 66)
    print("   OCR HOÀN TẤT")
    print(f"   Thời gian     : {elapsed/60:.1f} phút  ({elapsed/max(done,1):.1f} s/trang)")
    print(f"   Đã xử lý      : {done}/{len(page_indices)} trang")
    if cached:
        print(f"   Dùng lại cache: {cached} trang")
    if failed:
        print(f"   LỖI           : {len(failed)} trang -> {failed[:20]}")
    if short_pages:
        preview = sorted(short_pages)[:20]
        print(f"   Trang < 200 ký tự: {len(short_pages)} -> {preview}{' ...' if len(short_pages) > 20 else ''}")
        print("   (thường là trang trắng; nếu là trang có chữ thì cần OCR lại DPI cao hơn)")
    print("=" * 66)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="OCR toàn bộ một cuốn sách scan")
    p.add_argument("--doc-name", required=True, help="ID tài liệu, vd. DTQGVN-2022-Q1")
    p.add_argument("--pdf", default=None, help="Ghi đè đường dẫn PDF (mặc định lấy từ manifest)")
    p.add_argument("--start", type=int, default=1, help="Trang PDF bắt đầu (1-based)")
    p.add_argument("--end", type=int, default=None, help="Trang PDF kết thúc")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--dpi", type=int, default=None, help="Mặc định lấy từ manifest")
    p.add_argument("--columns", type=int, default=None, choices=[1, 2], help="Mặc định lấy từ manifest")
    p.add_argument("--lang", default=None, help="Mặc định lấy từ manifest, vd. vie+eng")
    a = p.parse_args()

    run(a.doc_name, a.pdf, a.start, a.end, a.workers, a.dpi, a.columns, a.lang)


if __name__ == "__main__":
    main()
