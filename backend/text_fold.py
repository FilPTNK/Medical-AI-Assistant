# -*- coding: utf-8 -*-
"""
Gấp dấu tiếng Việt để tìm chữ trong tài liệu.

Hai việc, theo đúng thứ tự này:

1. đ/Đ -> d/D bằng bảng tra. BẮT BUỘC phải làm riêng: đ (U+0111) và Đ (U+0110)
   là CHỮ CÁI riêng, không phải d có dấu, nên unicodedata.decomposition() trả về
   chuỗi RỖNG và NFD không hề đụng tới chúng.

2. NFD rồi bỏ mọi dấu phụ (category 'Mn'). Bước này xử đúng toàn bộ nguyên âm
   tiếng Việt, kể cả dấu móc (U+031B của ư/ơ) và các chữ chồng hai dấu — ộ tách
   ra thành o + dấu chấm dưới + dấu mũ.

Vì sao bước 1 đáng giá hơn vẻ ngoài của nó: OCR của kho này làm rụng nét ngang
của đ, sinh ra "Giảm dau" thay vì "Giảm đau". Chỉ gấp dấu thanh thì KHÔNG cứu
được — "giam đau" vẫn không khớp "giam dau". Có bảng đ->d thì cả hai cùng về
"giam dau" và khớp. Đo trên đúng những chuỗi hỏng đã thấy trong kho:

    'Giảm dau'   vs bác sĩ gõ 'giảm đau'    — không có đ->d: trượt · có: KHỚP
    'bị dau dầu' vs bác sĩ gõ 'bị đau đầu'  — không có đ->d: trượt · có: KHỚP
    'Ha nhiệt'   vs bác sĩ gõ 'hạ nhiệt'    — cả hai cách đều KHỚP

CỐ Ý KHÔNG dùng so khớp mờ (khoảng cách sửa đổi). Trên 913 trang văn bản vốn
đã nhiễu, so khớp mờ đẻ ra dương tính giả mà bác sĩ phải tự đi bác bỏ — và
trong app này một trang sai trông y hệt một trang đúng. Gấp dấu là phép biến
đổi tất định: nó chỉ bỏ thông tin, không đoán thêm gì.
"""

import unicodedata
from typing import List, Tuple

# đ U+0111 · Đ U+0110 — NFD không đụng tới, phải tự thay.
_D_STROKE = str.maketrans({"đ": "d", "Đ": "D"})


def fold(s: str) -> str:
    """Chuỗi đã bỏ dấu, hạ chữ thường và gộp khoảng trắng, để so khớp."""
    return fold_with_map(s)[0]


def fold_with_map(s: str) -> Tuple[str, List[int]]:
    """
    Chuỗi đã gấp, kèm bảng chỉ số: ký tự thứ i của chuỗi đã gấp nằm ở đâu trong
    chuỗi GỐC.

    Cần bảng này vì đoạn trích phải cắt ra từ chữ GỐC còn nguyên dấu — bác sĩ
    đọc kết quả chứ không đọc chuỗi đã bỏ dấu. Gấp từng ký tự một thay vì gấp cả
    chuỗi rồi suy ngược theo độ dài: một ký tự có thể nở ra hoặc biến mất khi
    chuẩn hoá, nên suy theo độ dài sai đúng ở những chỗ khó nhất.

    GỘP KHOẢNG TRẮNG: mọi chuỗi dấu cách/xuống dòng liên tiếp thành đúng một
    dấu cách. Bắt buộc phải có, đo mới thấy: chữ OCR xuống dòng giữa câu, nên
    một đoạn trích liền mạch như "Thường gặp TKTW" không khớp được với trang
    ghi "Thường gặp
TKTW". Không gộp thì cứ chỗ nào vắt dòng là trượt, mà
    trang sách thì vắt dòng liên tục.
    """
    folded_parts: List[str] = []
    index_map: List[int] = []
    prev_space = False
    for i, ch in enumerate(s):
        if ch.isspace():
            if not prev_space and folded_parts:
                folded_parts.append(" ")
                index_map.append(i)
                prev_space = True
            continue
        piece = "".join(
            c for c in unicodedata.normalize("NFD", ch.translate(_D_STROKE))
            if unicodedata.category(c) != "Mn"
        ).lower()
        for c in piece:
            folded_parts.append(c)
            index_map.append(i)
        prev_space = False
    # dấu cách thừa ở cuối không mang thông tin
    if folded_parts and folded_parts[-1] == " ":
        folded_parts.pop()
        index_map.pop()
    return "".join(folded_parts), index_map
