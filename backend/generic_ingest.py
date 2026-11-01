"""
Nạp một PDF BẤT KỲ do bác sĩ tự tải lên — không cần parser viết riêng cho
từng cuốn sách như dtqg_parser.py / drug_parser.py.

Khác với hai parser đó (bóc theo cấu trúc chuyên luận: tên thuốc, mục "Chỉ
định", "Chống chỉ định"...), tài liệu tự nạp có thể là bất cứ thứ gì — quyết
định, hướng dẫn điều trị, công văn — nên không có cấu trúc cố định để bám
vào. Cách nạp ở đây vì vậy cố tình "nông": cắt theo TRANG rồi cắt tiếp theo độ
dài, không cố đoán tiêu đề mục hay tên thuốc.

Mỗi trang được xử lý ĐỘC LẬP để quyết định đọc chữ trực tiếp hay phải OCR:
PDF lai (đa số có lớp chữ, vài trang phụ lục là ảnh scan) rất thường gặp
trong hồ sơ hành chính, nên phân loại "cả cuốn scan hay không" sẽ xử sai một
nửa số trang của đúng loại tài liệu này.

Đầu ra chunk cố tình CHỈ mang đúng những key mà
`ingest_book.py::build_documents` đã biết đọc (chunk_id, field_name, content,
page_in_file, pdf_page) — không có `generic_name`, để nhánh gắn nhãn
"【THUỐC: ...】" ở đó tự bỏ qua (xem chú thích trong build_documents). Nhờ vậy
toàn bộ phần còn lại của pipeline — nạp Chroma, liệt kê trong Thư viện, tải
xuống, xoá, tô sáng, Đối chiếu, trình đọc trang — dùng lại y nguyên, không
cần sửa gì thêm.
"""

import json
import os
import re
import unicodedata
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import pymupdf as fitz
except ImportError:
    import fitz

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import documents
import config
import ingest_book
import ocr_book
from dtqg_parser import split_long

# Trang có ít hơn ngần này ký tự chữ (sau khi strip) bị coi là ảnh scan và đưa
# đi OCR, bất kể các trang khác trong CÙNG tài liệu đọc chữ trực tiếp được hay
# không — đo nhanh trên vài PDF hành chính mẫu: trang bìa/trang trắng thật sự
# thường dưới 10 ký tự, còn trang có nội dung luôn vượt xa mốc này.
DIGITAL_TEXT_MIN_CHARS = 40
OCR_WORKERS = 1
MAX_PDF_BYTES = 64 * 1024 * 1024
MAX_PDF_PAGES = 300
MAX_OCR_PIXELS = 9_000_000
DEFAULT_OCR = {"dpi": 300, "columns": 1, "lang": "vie+eng"}

_PAGE_MARKER_RE = re.compile(r"^\[Trang\s+\d+\]\n?")

ProgressCb = Callable[[str, int, int], None]


def _noop_progress(stage: str, current: int, total: int) -> None:
    pass


def slugify_doc_name(filename: str, reserved=()) -> str:
    """
    doc_name ổn định từ tên tệp gốc — giữ nguyên tiếng Việt có dấu, chỉ chặn
    những ký tự Windows cấm trong tên tệp và đụng hàng với tài liệu đã có.

    Không ép về ASCII: doc_name khác các sách Dược thư (ID nhân tạo kiểu
    "DTQGVN-2022-Q1") ở chỗ nó CHÍNH LÀ tên hiển thị trong thẻ Thư viện, nên
    giữ tên gốc dễ nhận ra hơn một slug không dấu.
    """
    base = unicodedata.normalize("NFKC", str(filename).replace("\\", "/").split("/")[-1])
    base = documents.safe_doc_name(base)
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base).strip() or "tai-lieu"
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    stem, ext = os.path.splitext(base)
    stem = stem[:115].rstrip(" .") or "tai-lieu"
    base = stem + ext
    taken = {name.casefold() for name in reserved}
    taken.update(name.casefold() for name in os.listdir(config.UPLOAD_DIR))
    taken.update((m.get("doc_name") or "").casefold() for m in documents.list_manifests())
    candidate = base
    n = 2
    while candidate.casefold() in taken:
        candidate = f"{stem[:110]} ({n}){ext}"
        n += 1
    return candidate


def validate_pdf(pdf_path: str) -> int:
    with open(pdf_path, "rb") as source:
        if not source.read(5) == b"%PDF-":
            raise ValueError("Tệp không có chữ ký PDF hợp lệ.")
    try:
        with fitz.open(pdf_path) as doc:
            if not doc.is_pdf or doc.needs_pass:
                raise ValueError("PDF mã hoá hoặc không đúng định dạng PDF.")
            pages = len(doc)
            if any(doc[i].rect.width * doc[i].rect.height * (120 / 72) ** 2 > MAX_OCR_PIXELS
                   for i in range(pages)):
                raise ValueError("PDF có trang quá lớn để OCR an toàn trên máy này.")
    except ValueError:
        raise
    except Exception as e:
        raise ValueError("PDF hỏng hoặc không đọc được.") from e
    if not 1 <= pages <= MAX_PDF_PAGES:
        raise ValueError(f"PDF phải có từ 1 đến {MAX_PDF_PAGES} trang.")
    return pages


def ocr_dpi_for_page(rect, requested=300):
    # A4 300 DPI gần 9 triệu pixel; tài liệu khổ lớn giảm DPI để tránh vỡ RAM.
    pixels = rect.width * rect.height * (requested / 72) ** 2
    return min(requested, max(120, int(requested * (MAX_OCR_PIXELS / max(pixels, 1)) ** 0.5)))


def low_quality_ocr(text):
    stripped = (text or "").strip()
    if not stripped:
        return True
    printable = sum(ch.isalnum() or ch.isspace() or ch in ".,;:!?-()" for ch in stripped)
    return len(stripped) < 40 or printable / len(stripped) < 0.65


def cleanup_orphans(vector_store):
    """Chỉ dọn manifest generic chưa hoàn tất; giữ nguyên mọi tài liệu đã nạp."""
    import ingest_jobs
    for manifest in documents.list_manifests():
        name = manifest.get("doc_name", "")
        if manifest.get("parser") != "generic" or manifest.get("ingested_at") is not None:
            continue
        if ingest_jobs.is_active(name):
            continue
        # Nếu xóa index lỗi, giữ file để có thể khôi phục thay vì mồ côi im lặng.
        vector_store.delete_document(name)
        paths = (documents.upload_path(name), documents.manifest_path(name),
                 documents.pages_cache_path(name), documents.chunks_path(name),
                 documents.page_map_path(name))
        for path in paths:
            if os.path.exists(path):
                os.remove(path)
        for folder in (documents.ocr_dir(name), documents.page_images_dir(name)):
            if os.path.isdir(folder):
                shutil.rmtree(folder)


def needs_ocr_by_page(pdf_path: str) -> Tuple[Dict[int, str], List[int], int]:
    """Đọc chữ trực tiếp từng trang; trang nào quá ít chữ thì xếp vào danh sách OCR."""
    with fitz.open(pdf_path) as doc:
        total_pages = len(doc)
        digital: Dict[int, str] = {}
        ocr_needed: List[int] = []
        for i in range(total_pages):
            text = doc[i].get_text().strip()
            if len(text) >= DIGITAL_TEXT_MIN_CHARS:
                digital[i + 1] = text
            else:
                ocr_needed.append(i)
    return digital, ocr_needed, total_pages


def ocr_page_at_safe_dpi(pdf_path, idx, doc_name, dpi, lang):
    with fitz.open(pdf_path) as doc:
        safe_dpi = ocr_dpi_for_page(doc[idx].rect, dpi)
    return ocr_book.ocr_page(pdf_path, idx, doc_name, safe_dpi, 1, lang)


def iter_page_texts(
    pdf_path: str,
    doc_name: str,
    dpi: int = 300,
    lang: str = "vie+eng",
    progress_cb: Optional[ProgressCb] = None,
) -> Tuple[Dict[int, str], int, int]:
    """{trang: chữ}, tổng số trang, số trang phải OCR."""
    progress_cb = progress_cb or _noop_progress

    digital, ocr_needed, total_pages = needs_ocr_by_page(pdf_path)
    progress_cb("Đang đọc lớp chữ của PDF", total_pages, total_pages)

    ocr_text: Dict[int, str] = {}
    if ocr_needed:
        done = 0
        progress_cb(f"Đang OCR trang quét (0/{len(ocr_needed)})", 0, len(ocr_needed))
        with ThreadPoolExecutor(max_workers=OCR_WORKERS) as pool:
            futures = {
                pool.submit(ocr_page_at_safe_dpi, pdf_path, idx, doc_name, dpi, lang): idx
                for idx in ocr_needed
            }
            for fut in as_completed(futures):
                idx = futures[fut]
                page_num = idx + 1
                try:
                    fut.result()
                    body_path = documents.ocr_page_path(doc_name, page_num)
                    with open(body_path, "r", encoding="utf-8") as f:
                        raw = f.read()
                    ocr_text[page_num] = _PAGE_MARKER_RE.sub("", raw, count=1).strip()
                except Exception as e:
                    print(f"[generic_ingest] Lỗi OCR trang {page_num}: {e}")
                    ocr_text[page_num] = ""
                done += 1
                progress_cb(f"Đang OCR trang quét ({done}/{len(ocr_needed)})", done, len(ocr_needed))

    pages: Dict[int, str] = {}
    pages.update(digital)
    pages.update(ocr_text)
    return pages, total_pages, len(ocr_needed)


def chunk_generic_pages(page_texts: Dict[int, str]) -> List[Dict[str, Any]]:
    """Cắt theo trang rồi cắt tiếp theo độ dài — tái dùng split_long của dtqg_parser
    (cùng SUBCHUNK_SIZE/OVERLAP, ưu tiên cắt ở ranh giới câu) để giữ chung một
    triết lý chunk trên toàn dự án thay vì thêm một bộ cắt khác."""
    chunks: List[Dict[str, Any]] = []
    for page_num in sorted(page_texts):
        text = (page_texts[page_num] or "").strip()
        if len(text) < 3:
            continue
        for i, part in enumerate(split_long(text)):
            part = part.strip()
            if not part:
                continue
            chunks.append({
                "chunk_id": f"p{page_num:04d}_{i}",
                "field_name": "Nội dung",
                "content": part,
                "page_in_file": page_num,
                "pdf_page": page_num,
            })
    return chunks


def ingest_generic_pdf(
    doc_name: str,
    pdf_path: str,
    doc_title: str,
    progress_cb: Optional[ProgressCb] = None,
    vector_store: Any = None,
    uploaded_by: Optional[str] = None,
    warning_cb: Optional[Callable[[int], None]] = None,
    owner_id: Optional[str] = None,
    visibility: str = "private",
) -> Dict[str, Any]:
    """Toàn bộ đường đi: manifest -> đọc/OCR từng trang -> cắt đoạn -> nạp Chroma.

    `vector_store`: truyền vào đúng singleton `db` của main.py khi gọi từ máy
    chủ đang chạy — xem chú thích trong ingest_book.ingest() vì sao bỏ qua
    tham số này sẽ làm tài liệu mới nạp không tìm thấy được cho tới khi
    khởi động lại server.

    Trả về {"doc_name", "pages", "chunks", "ocr_pages"}. Ném lỗi (ValueError /
    Exception khác) nếu không đọc được chữ nào — bên gọi (main.py) chịu trách
    nhiệm dọn PDF + manifest khi việc nạp thất bại giữa chừng.
    """
    progress_cb = progress_cb or _noop_progress

    pdf_pages = validate_pdf(pdf_path)

    manifest = documents.new_manifest(
        doc_name=doc_name,
        doc_title=doc_title,
        source_pdf=doc_name,
        pdf_pages=pdf_pages,
        ocr=dict(DEFAULT_OCR),
        parser="generic",
    )
    manifest["uploaded_by"] = uploaded_by
    # Ghi quyền NGAY lúc tạo manifest, trước khi có chunk nào vào chỉ mục: nếu
    # ghi sau bước nạp thì trong vài giây đó tài liệu riêng lộ ra cho mọi người.
    manifest["owner_id"] = owner_id
    manifest["visibility"] = visibility
    documents.save_manifest(manifest)

    progress_cb("Đang đọc PDF", 0, pdf_pages)
    page_texts, total_pages, ocr_count = iter_page_texts(
        pdf_path, doc_name,
        dpi=DEFAULT_OCR["dpi"], lang=DEFAULT_OCR["lang"],
        progress_cb=progress_cb,
    )

    for page_num in range(1, total_pages + 1):
        if page_num not in page_texts or low_quality_ocr(page_texts.get(page_num)):
            if warning_cb:
                warning_cb(page_num)
    progress_cb("Đang lưu bản chữ đầy đủ", 0, 1)
    with open(documents.pages_cache_path(doc_name), "w", encoding="utf-8") as f:
        json.dump({str(p): t for p, t in page_texts.items()}, f, ensure_ascii=False)

    progress_cb("Đang bóc đoạn để lập chỉ mục", 0, 1)
    chunks = chunk_generic_pages(page_texts)
    if not chunks:
        raise ValueError(
            "Không đọc được chữ nào trong tệp PDF này, kể cả sau khi OCR — "
            "có thể là tệp trắng, ảnh chất lượng quá thấp, hoặc file hỏng."
        )

    chunks_file = documents.chunks_path(doc_name)
    with open(chunks_file, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    progress_cb("Đang nạp vào chỉ mục tìm kiếm", 0, 1)
    ingest_book.ingest(doc_name, chunks_file, replace=True, batch_size=500, vector_store=vector_store)

    progress_cb("Hoàn tất", 1, 1)
    return {
        "doc_name": doc_name,
        "pages": pdf_pages,
        "chunks": len(chunks),
        "ocr_pages": ocr_count,
    }
