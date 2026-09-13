# -*- coding: utf-8 -*-
"""
Chỉ mục chữ trong một tài liệu, để tìm kiếm trong trình xem.

Vì sao phải có cache, đo trên Dược thư Quyển 1 (913 trang, 5,3 triệu ký tự):

    đọc 913 tệp OCR rời      8.860 ms
    gấp dấu toàn bộ          1.219 ms
    tìm một lượt trên bản đã gấp  4 ms

Tức là dựng chỉ mục đắt gấp hơn hai nghìn lần một lượt tìm. Dựng lại mỗi lần
gõ thì không dùng được; dựng một lần rồi giữ thì mỗi lượt tìm là 4ms. Đây đúng
là bài học của đợt 2 với việc nạp model: lần đầu sau khi mở app đắt, các lần
sau gần như miễn phí, và một cái trần thời gian chung cho cả hai là sai theo
cả hai chiều.

KHÔNG giữ bảng chỉ số ký tự cho mọi trang: 5,3 triệu số nguyên là hàng chục MB
trên một máy chỉ còn khoảng 1 GB trống. Bảng đó chỉ dựng cho những trang thật
sự khớp, thường là vài trang, ngay lúc cần cắt đoạn trích.

Hai tài liệu trong kho có hai kiểu lưu khác nhau, nên phải đọc được cả hai:
  - pages_cache/<doc>.json  — một JSON, khoá theo số trang IN
  - ocr_text/<doc>/page_NNNN.txt — mỗi trang một tệp, đánh số theo trang PDF
Với sách scan, hai hệ số trang này lệch nhau (Quyển 1 lệch từ +1 tới −10), nên
bản từ tệp rời phải quy đổi qua page_map trước khi trả ra, nếu không bác sĩ
bấm vào kết quả trang 297 sẽ đọc phải trang 301.
"""

import json
import os
import re
import threading
from typing import Dict, Optional, Tuple

import documents
import text_fold

# doc_name -> {trang in: chữ gốc}, và bản đã gấp dấu tương ứng.
_texts: Dict[str, Dict[int, str]] = {}
_folded: Dict[str, Dict[int, str]] = {}
_lock = threading.Lock()

_PAGE_FILE_RE = re.compile(r"^page_(\d+)\.txt$")


def is_warm(doc_name: str) -> bool:
    """Đã dựng chỉ mục chưa — để giao diện biết lượt tìm này sẽ nhanh hay chậm."""
    return documents.safe_doc_name(doc_name) in _folded


def _pdf_to_printed(doc_name: str) -> Dict[int, int]:
    data = documents.load_page_map(doc_name)
    if not data:
        return {}
    out: Dict[int, int] = {}
    for info in (data.get("pages") or {}).values():
        if info.get("page_num") is None:
            continue
        out[int(info["pdf_page"])] = int(info["page_num"])
    return out


def _load_page_texts(doc_name: str) -> Dict[int, str]:
    """{số trang IN: chữ OCR}. Rỗng nghĩa là tài liệu chưa có bản chữ nào."""
    safe = documents.safe_doc_name(doc_name)

    cache_path = documents.pages_cache_path(safe)
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            out: Dict[int, str] = {}
            for k, v in raw.items():
                try:
                    out[int(k)] = v or ""
                except (TypeError, ValueError):
                    continue
            if out:
                return out
        except Exception as e:
            print(f"[doc_index] Không đọc được pages_cache {cache_path}: {e}")

    ocr_dir = documents.ocr_dir(safe)
    if not os.path.isdir(ocr_dir):
        return {}

    mapping = _pdf_to_printed(safe)
    out = {}
    for name in os.listdir(ocr_dir):
        m = _PAGE_FILE_RE.match(name)
        if not m:
            # head_NNNN.txt là chữ của running head, dùng cho page_map chứ
            # không phải nội dung trang — bỏ qua, nếu không mỗi trang bị tính hai lần.
            continue
        pdf_page = int(m.group(1))
        printed = mapping.get(pdf_page, pdf_page)
        try:
            with open(os.path.join(ocr_dir, name), "r", encoding="utf-8") as f:
                text = f.read()
        except Exception:
            continue
        # Một trang in có thể ứng với nhiều trang PDF (vùng bị lặp trong bản
        # scan). Giữ bản dài hơn: bản ngắn thường là trang hỏng hoặc trang trắng.
        if printed not in out or len(text) > len(out[printed]):
            out[printed] = text
    return out


def get_index(doc_name: str) -> Tuple[Dict[int, str], Dict[int, str]]:
    """(chữ gốc theo trang in, chữ đã gấp dấu theo trang in). Dựng một lần."""
    safe = documents.safe_doc_name(doc_name)
    if safe in _folded:
        return _texts[safe], _folded[safe]
    with _lock:
        if safe in _folded:          # một luồng khác vừa dựng xong khi ta chờ khoá
            return _texts[safe], _folded[safe]
        texts = _load_page_texts(safe)
        folded = {p: text_fold.fold(t) for p, t in texts.items() if t}
        _texts[safe] = texts
        _folded[safe] = folded
        return texts, folded


def invalidate(doc_name: Optional[str] = None) -> None:
    """Bỏ chỉ mục khi tài liệu bị xoá hoặc nạp lại."""
    with _lock:
        if doc_name is None:
            _texts.clear()
            _folded.clear()
            return
        safe = documents.safe_doc_name(doc_name)
        _texts.pop(safe, None)
        _folded.pop(safe, None)
