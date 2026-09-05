"""
Lớp manifest cho tài liệu đã lập chỉ mục.

Mỗi tài liệu (một cuốn sách, hoặc một quyển trong bộ nhiều tập) có đúng một file
JSON mô tả trong backend/data/documents/<doc_name>.json. Manifest là nơi duy nhất
giữ các hằng số theo tài liệu — số trang, cấu hình OCR, dải trang thân sách — thay
cho các giá trị hard-code nằm rải rác trong code trước đây.

doc_name là khóa định danh ổn định, dùng chung cho: tên file PDF trong uploads/,
thư mục text OCR, cache trang, cache ảnh trang, và metadata trong ChromaDB. Đặt
tên theo dạng bền vững (vd. "DTQGVN-2022-Q1") chứ không theo tên file gốc, vì đổi
doc_name sau khi đã index đồng nghĩa phải nạp lại toàn bộ.
"""

import os
import json
from typing import Any, Dict, List, Optional

import config

DOCUMENTS_DIR = os.path.join(config.DATA_DIR, "documents")
OCR_TEXT_DIR = os.path.join(config.DATA_DIR, "ocr_text")
PAGE_MAP_DIR = os.path.join(config.DATA_DIR, "page_map")
PAGE_IMAGES_DIR = os.path.join(config.DATA_DIR, "page_images")
PAGES_CACHE_DIR = os.path.join(config.DATA_DIR, "pages_cache")
CHUNKS_DIR = os.path.join(config.DATA_DIR, "chunks")

for _d in (DOCUMENTS_DIR, OCR_TEXT_DIR, PAGE_MAP_DIR, PAGE_IMAGES_DIR, PAGES_CACHE_DIR, CHUNKS_DIR):
    os.makedirs(_d, exist_ok=True)


def safe_doc_name(doc_name: str) -> str:
    """Chặn directory traversal — doc_name luôn được ghép vào đường dẫn."""
    return os.path.basename(str(doc_name)).replace("..", "")


# --- Đường dẫn dẫn xuất từ doc_name -----------------------------------------

def manifest_path(doc_name: str) -> str:
    return os.path.join(DOCUMENTS_DIR, f"{safe_doc_name(doc_name)}.json")


def ocr_dir(doc_name: str) -> str:
    """Thư mục text OCR riêng của tài liệu (thay cho pdf_text/ phẳng dùng chung)."""
    return os.path.join(OCR_TEXT_DIR, safe_doc_name(doc_name))


def ocr_page_path(doc_name: str, page_num: int) -> str:
    return os.path.join(ocr_dir(doc_name), f"page_{int(page_num):04d}.txt")


def page_images_dir(doc_name: str) -> str:
    return os.path.join(PAGE_IMAGES_DIR, safe_doc_name(doc_name))


def page_map_path(doc_name: str) -> str:
    return os.path.join(PAGE_MAP_DIR, f"{safe_doc_name(doc_name)}.json")


def chunks_path(doc_name: str) -> str:
    """Chunk JSON do parser sinh ra — đầu vào của bước nạp vector."""
    return os.path.join(CHUNKS_DIR, f"{safe_doc_name(doc_name)}.json")


def pages_cache_path(doc_name: str) -> str:
    return os.path.join(PAGES_CACHE_DIR, f"{safe_doc_name(doc_name)}.json")


def upload_path(doc_name: str) -> str:
    """PDF gốc. source_pdf trong manifest cho phép tên file khác doc_name."""
    manifest = load_manifest(doc_name)
    filename = (manifest or {}).get("source_pdf") or safe_doc_name(doc_name)
    return os.path.join(config.UPLOAD_DIR, safe_doc_name(filename))


# --- Đọc / ghi ---------------------------------------------------------------

def new_manifest(
    doc_name: str,
    doc_title: str,
    source_pdf: str,
    pdf_pages: int,
    short_title: Optional[str] = None,
    doc_series: Optional[str] = None,
    volume: Optional[int] = None,
    coverage: Optional[str] = None,
    body_page_range: Optional[List[int]] = None,
    ocr: Optional[Dict[str, Any]] = None,
    parser: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "doc_name": safe_doc_name(doc_name),
        "doc_title": doc_title,
        # Dạng ngắn KHÔNG mang số quyển — display_citation tự ghép số quyển vào.
        # Chip nguồn trong UI rất hẹp, tên đầy đủ sẽ bị cắt mất số trang.
        "short_title": short_title or doc_title,
        "doc_series": doc_series,
        "volume": volume,
        "coverage": coverage,
        "source_pdf": source_pdf,
        "pdf_pages": int(pdf_pages),
        # [trang in đầu, trang in cuối] của phần thân sách — dùng để kẹp biên
        # nút chuyển trang trong reader, vì phần mục lục không đánh số liên tục.
        "body_page_range": body_page_range,
        "ocr": ocr or {},
        "parser": parser,
        "chunk_count": 0,
        "ingested_at": None,
    }


def load_manifest(doc_name: str) -> Optional[Dict[str, Any]]:
    path = manifest_path(doc_name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[documents] Không đọc được manifest {path}: {e}")
        return None


def save_manifest(manifest: Dict[str, Any]) -> str:
    doc_name = manifest.get("doc_name")
    if not doc_name:
        raise ValueError("Manifest thiếu trường 'doc_name'.")
    path = manifest_path(doc_name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return path


def update_manifest(doc_name: str, **fields: Any) -> Optional[Dict[str, Any]]:
    manifest = load_manifest(doc_name)
    if manifest is None:
        return None
    manifest.update(fields)
    save_manifest(manifest)
    return manifest


def list_manifests() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not os.path.isdir(DOCUMENTS_DIR):
        return out
    for name in sorted(os.listdir(DOCUMENTS_DIR)):
        if not name.endswith(".json"):
            continue
        manifest = load_manifest(name[:-5])
        if manifest:
            out.append(manifest)
    return out


_page_map_cache: Dict[str, Dict[str, Any]] = {}


def load_page_map(doc_name: str) -> Optional[Dict[str, Any]]:
    """Bản đồ trang, có cache trong tiến trình — mỗi lần mở là đọc file JSON lớn."""
    key = safe_doc_name(doc_name)
    if key in _page_map_cache:
        return _page_map_cache[key]
    path = page_map_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[documents] Không đọc được page_map {path}: {e}")
        return None
    # Bảng tra ngược trang in -> trang PDF, dựng sẵn một lần.
    #
    # Một số trang in ứng với NHIỀU trang PDF: bản scan Dược thư Quyển 1 có vùng
    # trang bị lặp và đảo thứ tự (vd. trang in 466 xuất hiện ở pdf 469, 470, 473).
    # Khi phải chọn, ưu tiên trang đọc được số trang trực tiếp từ running head —
    # đó là bằng chứng, còn trang "interpolated" chỉ là suy ra từ lân cận.
    reverse: Dict[int, int] = {}
    resolved_by: Dict[int, str] = {}
    for info in (data.get("pages") or {}).values():
        if info.get("page_num") is None:
            continue
        printed = int(info["page_num"])
        pdf_page = int(info["pdf_page"])
        how = info.get("resolved") or "none"
        if printed not in reverse or (
            how == "direct" and resolved_by.get(printed) != "direct"
        ):
            reverse[printed] = pdf_page
            resolved_by[printed] = how
    data["_printed_to_pdf"] = reverse
    _page_map_cache[key] = data
    return data


def printed_to_pdf_page(doc_name: str, page_num: int) -> int:
    """
    Trang in -> trang PDF, để render đúng ảnh scan.

    Không có bản đồ thì coi hai số là một. Đúng với tài liệu upload thường, và
    với sách scan thì bước page_map sẽ dựng bản đồ trước khi endpoint ảnh có ích.
    """
    data = load_page_map(doc_name)
    if not data:
        return int(page_num)
    return data.get("_printed_to_pdf", {}).get(int(page_num), int(page_num))


def display_citation(doc_name: str, page_num: Any) -> str:
    """
    Nhãn trích dẫn cho bác sĩ đối chiếu.

    Số trang đơn lẻ không định danh duy nhất trong một bộ nhiều tập: nếu Quyển 2
    đánh số lại từ 1 thì sẽ có hai trang 298 khác nhau. Nhãn vì vậy luôn mang
    theo số quyển khi tài liệu thuộc một bộ.
    """
    manifest = load_manifest(doc_name)
    if not manifest:
        return f"{doc_name} — tr. {page_num}"

    title = manifest.get("short_title") or manifest.get("doc_title") or manifest.get("doc_name")
    volume = manifest.get("volume")
    if volume:
        return f"{title}, Q.{volume} — tr. {page_num}"
    return f"{title} — tr. {page_num}"
