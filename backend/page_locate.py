"""
Tìm VỊ TRÍ của một đoạn trích dẫn trên trang sách, để tô sáng ngay trên ảnh scan.

Trước đây bấm vào trích dẫn chỉ mở đúng trang; tô sáng chỉ làm được ở cột chữ
OCR, vì kho chỉ có chữ ở mức TRANG, không có toạ độ từng từ. Bác sĩ phải tự dò
bằng mắt trên một trang sách đầy chữ.

Cách làm ở đây:

1. Lấy danh sách TỪ kèm hộp bao của trang.
   - PDF có lớp chữ thật: PyMuPDF ``get_text("words")``, gần như tức thì.
   - Sách scan (cả ba cuốn hiện có): OCR lại trang bằng Tesseract
     ``image_to_data`` — cùng bộ tessdata, cùng cách cắt dải running head và
     cắt cột như ``ocr_book.py`` để chuỗi từ ra gần giống chữ đã chỉ mục.
   Kết quả cache theo trang trong ``data/page_words/``: chỉ trang nào bác sĩ
   thật sự mở mới tốn công OCR (~3–6 s), lần sau đọc file.
2. Gấp dấu cả hai phía (text_fold) rồi dóng chuỗi từ của đoạn trích với chuỗi
   từ của trang bằng difflib. Gấp dấu vì hai lượt OCR của cùng một trang có
   thể khác nhau ở dấu thanh; vị trí thì không đổi.
3. Lấy cụm từ khớp dày nhất làm vùng trích dẫn, gộp các từ thành hộp theo
   dòng. Toạ độ chuẩn hoá về 0–1 theo khổ trang, nên giao diện vẽ được trên ảnh
   ở bất kỳ độ phân giải nào.

Không neo được thì trả về rects rỗng kèm độ tin cậy thấp — giao diện nói thật là
không tìm thấy vị trí chính xác, thay vì tô nhầm chỗ.
"""

import os
import io
import json
import re
import threading
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

import config
import documents
import text_fold

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover - bản PyMuPDF cũ
    import fitz

PAGE_WORDS_DIR = os.path.join(config.DATA_DIR, "page_words")

# Cùng giá trị với ocr_book.HEAD_BAND: dải running head không thuộc thân trang.
HEAD_BAND = 0.06
OCR_DPI = 200
# Trang có ít hơn ngần này từ ở lớp chữ thì coi là trang scan.
MIN_TEXT_LAYER_WORDS = 25
# Hai từ khớp cách nhau quá ngần này từ của trang thì coi là hai cụm riêng.
MAX_GAP = 12
# Cần tối thiểu ngần này từ khớp mới dám tô.
MIN_MATCHED = 5

# Neo bằng con số. Trên sách scan tiếng Việt, chữ số và đơn vị sống sót qua
# OCR tốt hơn dấu thanh: hai lượt OCR của cùng trang hay lệch "liều"/"liêu"
# nhưng gần như không lệch "500 mg". Nên khi chọn giữa các cụm khớp, mỗi con
# số của câu trích khớp được trong cụm tính bằng NUM_WEIGHT từ thường — câu
# liều ngắn "500 mg x 3 lần/ngày" không bị một cụm chữ thường dài hơn ở chỗ
# khác trên trang cướp mất. Và câu trích ngắn có con số khớp thì được tô với
# ít từ khớp hơn MIN_MATCHED (nhưng không dưới MIN_MATCHED_ANCHORED).
ANCHOR_NUMBERS = True
NUM_WEIGHT = 3
MIN_MATCHED_ANCHORED = 3

_ocr_lock = threading.Lock()


def _cache_path(doc_name: str, pdf_page: int) -> str:
    return os.path.join(PAGE_WORDS_DIR, documents.safe_doc_name(doc_name), f"{pdf_page:04d}.json")


def _words_from_text_layer(page) -> List[Dict[str, Any]]:
    w, h = page.rect.width, page.rect.height
    out = []
    for x0, y0, x1, y1, text, block, line, _ in page.get_text("words"):
        out.append({"t": text, "x0": x0 / w, "y0": y0 / h, "x1": x1 / w, "y1": y1 / h,
                    "line": f"{block}-{line}"})
    return out


def _ocr_region(img, lang: str, x_off: float, y_off: float, full_w: float, full_h: float,
                tag: str) -> List[Dict[str, Any]]:
    import pytesseract
    data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
    out = []
    for i, text in enumerate(data["text"]):
        text = (text or "").strip()
        if not text:
            continue
        left, top = data["left"][i] + x_off, data["top"][i] + y_off
        out.append({
            "t": text,
            "x0": left / full_w, "y0": top / full_h,
            "x1": (left + data["width"][i]) / full_w, "y1": (top + data["height"][i]) / full_h,
            "line": f"{tag}{data['block_num'][i]}-{data['par_num'][i]}-{data['line_num'][i]}",
        })
    return out


def _words_from_ocr(page, columns: int, lang: str) -> List[Dict[str, Any]]:
    # Dùng chung cấu hình Tesseract với ocr_book (đường dẫn exe, tessdata, 1 luồng).
    import ocr_book  # noqa: F401 — import để chạy phần cấu hình ở đầu module
    from PIL import Image

    pix = page.get_pixmap(dpi=OCR_DPI)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    full_w, full_h = img.size
    cut = int(full_h * HEAD_BAND)
    body = img.crop((0, cut, full_w, full_h))
    if columns >= 2:
        split = int(full_w * 0.49)
        return (_ocr_region(body.crop((0, 0, split, body.height)), lang, 0, cut, full_w, full_h, "L")
                + _ocr_region(body.crop((split, 0, full_w, body.height)), lang, split, cut, full_w, full_h, "R"))
    return _ocr_region(body, lang, 0, cut, full_w, full_h, "B")


def page_words(doc_name: str, pdf_page: int) -> Dict[str, Any]:
    """Từ + hộp bao của một trang PDF (1-based), có cache."""
    path = _cache_path(doc_name, pdf_page)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    pdf_path = documents.upload_path(doc_name)
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(pdf_path)
    manifest = documents.load_manifest(doc_name) or {}
    ocr_cfg = manifest.get("ocr") or {}

    with fitz.open(pdf_path) as doc:
        if not (1 <= pdf_page <= len(doc)):
            raise IndexError(pdf_page)
        page = doc[pdf_page - 1]
        words = _words_from_text_layer(page)
        method = "text_layer"
        if len(words) < MIN_TEXT_LAYER_WORDS:
            # Tesseract nặng CPU; một lượt một lúc là đủ cho một phòng khám.
            with _ocr_lock:
                words = _words_from_ocr(page, int(ocr_cfg.get("columns", 1) or 1),
                                        ocr_cfg.get("lang") or "vie+eng")
            method = "ocr"

    result = {"method": method, "words": words}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    return result


def _tokens(text: str) -> List[str]:
    return [t for t in text_fold.fold(text).split() if any(c.isalnum() for c in t)]


def _strip(tok: str) -> str:
    return "".join(c for c in tok if c.isalnum())


_FINE_RE = re.compile(r"[a-z]+|\d+(?:[.,]\d+)*")


def _fine(text: str) -> List[str]:
    """Token mịn: tách chữ khỏi số. "500mg" và "500 mg" cùng ra ["500", "mg"];
    "10-15" ra ["10", "15"] chứ không dính thành "1015" như khi chỉ bỏ dấu câu."""
    return _FINE_RE.findall(text_fold.fold(text))


def locate(words: List[Dict[str, Any]], quote: str) -> Dict[str, Any]:
    """Dóng đoạn trích với chuỗi từ của trang; trả về các hộp theo dòng."""
    if ANCHOR_NUMBERS:
        # Mỗi từ của trang có thể ra nhiều token mịn; giữ ánh xạ token -> từ
        # để cuối cùng vẫn tô theo hộp của TỪ.
        page_toks, owner = [], []
        for wi, w in enumerate(words):
            for t in _fine(w["t"]):
                page_toks.append(t)
                owner.append(wi)
        quote_toks = _fine(quote)
    else:
        page_toks = [_strip(text_fold.fold(w["t"])) for w in words]
        owner = list(range(len(words)))
        quote_toks = [_strip(t) for t in _tokens(quote)]
        quote_toks = [t for t in quote_toks if t]
    if not quote_toks or not words or not page_toks:
        return {"rects": [], "confidence": 0.0, "matched": 0}

    sm = SequenceMatcher(None, page_toks, quote_toks, autojunk=False)
    hits = sorted(i for blk in sm.get_matching_blocks() for i in range(blk.a, blk.a + blk.size))
    if not hits:
        return {"rects": [], "confidence": 0.0, "matched": 0}

    # Cụm dày nhất: các chỉ số khớp nối nhau với khoảng hở <= MAX_GAP.
    clusters, cur = [], [hits[0]]
    for i in hits[1:]:
        if i - cur[-1] <= MAX_GAP:
            cur.append(i)
        else:
            clusters.append(cur)
            cur = [i]
    clusters.append(cur)

    quote_nums = {t for t in quote_toks if any(c.isdigit() for c in t)}

    def numbers_in(cluster):
        return len({page_toks[i] for i in cluster} & quote_nums)

    if ANCHOR_NUMBERS and quote_nums:
        best = max(clusters, key=lambda c: len(c) + NUM_WEIGHT * numbers_in(c))
        anchored = numbers_in(best) > 0
        need = (min(MIN_MATCHED, max(MIN_MATCHED_ANCHORED, (len(quote_toks) + 1) // 2))
                if anchored else MIN_MATCHED)
    else:
        best = max(clusters, key=len)
        need = MIN_MATCHED
    if len(best) < need:
        return {"rects": [], "confidence": 0.0, "matched": len(best)}
    # Câu liều mà vùng tô thiếu quá nửa con số của nó là tô nhầm sang câu khác
    # có chữ giống ("suy thận … 30 ml/phút" thay cho bảng 10–30 ml/phút, 500 mg…).
    # Tô sai tệ hơn không tô. Chỉ đòi một nửa vì câu có thể tràn sang trang sau.
    if ANCHOR_NUMBERS and len(quote_nums) >= 2 and 2 * numbers_in(best) < len(quote_nums):
        return {"rects": [], "confidence": 0.0, "matched": len(best)}

    start, end = owner[best[0]], owner[best[-1]]
    span = best[-1] - best[0] + 1
    # Đoạn trích có thể tràn sang trang sau, nên chia cho phần đoạn trích có thể
    # nằm trên trang này chứ không chia cho toàn bộ đoạn trích.
    confidence = len(best) / max(1, min(len(quote_toks), span))

    rects: List[Dict[str, float]] = []
    by_line: Dict[str, Dict[str, float]] = {}
    order: List[str] = []
    for w in words[start:end + 1]:
        r = by_line.get(w["line"])
        if r is None:
            by_line[w["line"]] = dict(x0=w["x0"], y0=w["y0"], x1=w["x1"], y1=w["y1"])
            order.append(w["line"])
        else:
            r["x0"], r["y0"] = min(r["x0"], w["x0"]), min(r["y0"], w["y0"])
            r["x1"], r["y1"] = max(r["x1"], w["x1"]), max(r["y1"], w["y1"])
    for key in order:
        r = by_line[key]
        rects.append({"x": round(r["x0"], 5), "y": round(r["y0"], 5),
                      "w": round(r["x1"] - r["x0"], 5), "h": round(r["y1"] - r["y0"], 5)})
    return {"rects": rects, "confidence": round(min(confidence, 1.0), 3), "matched": len(best),
            "span": [start, end]}


def locate_on_page(doc_name: str, pdf_page: int, quote: str) -> Dict[str, Any]:
    data = page_words(doc_name, pdf_page)
    result = locate(data["words"], quote)
    result["method"] = data["method"]
    return result
