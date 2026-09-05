"""
Dựng bản đồ trang in ↔ trang PDF từ running head đã OCR ở Bước 01.

Vì sao cần bước riêng: độ lệch giữa số trang in và chỉ số PDF KHÔNG cố định. Đo
trên Dược thư Quyển 1, nó trôi từ +1 xuống −10 dọc theo sách (pdf 102 → trang in
103, nhưng pdf 851 → trang in 841). Dùng một offset cố định sẽ trích dẫn sai tới
10 trang — đủ để bác sĩ mở nhầm sang thuốc khác khi kiểm chứng.

Thuật toán không cố làm sạch chuỗi head. OCR trả về đủ biến thể nhiễu của chuỗi
hằng "DTQGVN 3" (DIQGVNg, pTQGVN 3, PIQGYN, DTQGVN ạ), lọc bằng regex sẽ luôn
sót. Thay vào đó:

  1. Lấy MỌI số nguyên trong head làm ứng viên.
  2. Với mỗi ứng viên tính offset = số − chỉ_số_pdf.
  3. Offset của số trang thật bám cụm chặt qua hàng trăm trang. Offset sinh ra
     từ số "3" của DTQGVN là 3 − pdf, khác nhau ở mỗi trang nên không thành cụm.
     Lọc theo tần suất là loại sạch nhiễu.
  4. Chọn ứng viên có offset gần offset của các trang lân cận nhất.
  5. Trang không đọc được số thì nội suy từ offset lân cận.

Dùng: python backend/page_map.py --doc-name DTQGVN-2022-Q1
"""

import os
import re
import sys
import json
import argparse
import statistics
import unicodedata
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import documents

# Số trang dạng mục lục tra cứu: ML-6, ML–18
INDEX_LABEL_RE = re.compile(r"\bML\s*[-–—]\s*([0-9lIi]{1,3})\b", re.IGNORECASE)

# Số trang hay bị OCR đọc lẫn chữ: "2l6" = 216, "I4" = 14, "60]" = 601, "88I" = 881.
# Nên bắt cả token pha chữ-số rồi quy về chữ số, thay vì đòi \d{1,4} thuần — kiểu
# cứng đó bỏ sót hàng trăm trang và đẩy hết sang nội suy.
TOKEN_RE = re.compile(r"(?<![0-9A-Za-z])([0-9lIiOoSBZ\]\|]{1,4})(?![0-9A-Za-z])")
_DIGITISE = str.maketrans({"l": "1", "I": "1", "i": "1", "]": "1", "|": "1",
                           "O": "0", "o": "0", "S": "5", "B": "8", "Z": "2"})

# Offset hợp lệ: chênh lệch giữa trang in và chỉ số PDF chỉ do vài trang bìa/phụ
# bản chèn vào, không bao giờ lớn. Ngưỡng rộng rãi để không cắt nhầm.
MAX_PLAUSIBLE_OFFSET = 60
# Một mức offset phải xuất hiện ở ít nhất ngần này trang mới coi là thật.
MIN_LEVEL_SUPPORT = 4
# Bán kính cửa sổ lấy offset lân cận khi nội suy.
NEIGHBOUR_RADIUS = 20


def read_heads(doc_name: str, pdf_pages: int) -> Dict[int, str]:
    heads: Dict[int, str] = {}
    folder = documents.ocr_dir(doc_name)
    for i in range(1, pdf_pages + 1):
        path = os.path.join(folder, f"head_{i:04d}.txt")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    heads[i] = f.read().strip()
            except Exception:
                heads[i] = ""
    return heads


def candidates_for(head: str) -> List[Tuple[int, float]]:
    """
    Ứng viên số trang trong một running head.

    Trả về (giá trị, vị_trí_tương_đối) với vị trí 0.0 = đầu chuỗi, 1.0 = cuối.
    Vị trí dùng để kiểm tra quy luật chẵn/lẻ: sách in số trang chẵn ở mép trái,
    số lẻ ở mép phải.
    """
    if not head:
        return []
    # Bỏ dấu tiếng Việt trước khi dò, để "85Ì" hay "88Í" cũng quy được về số
    flat = "".join(
        c for c in unicodedata.normalize("NFD", head)
        if not unicodedata.combining(c)
    )
    out: List[Tuple[int, float]] = []
    span = max(len(flat) - 1, 1)
    for m in TOKEN_RE.finditer(flat):
        tok = m.group(1)
        # Phải có ít nhất một chữ số thật, nếu không "Ill" hay "SOS" cũng thành số
        if not any(ch.isdigit() for ch in tok):
            continue
        digits = tok.translate(_DIGITISE)
        if not digits.isdigit():
            continue
        val = int(digits)
        if val <= 0:
            continue
        out.append((val, m.start() / span))
    return out


def build_map(doc_name: str) -> Optional[Dict[str, Any]]:
    manifest = documents.load_manifest(doc_name)
    if not manifest:
        print(f"[!] Chưa có manifest cho '{doc_name}'.")
        return None

    pdf_pages = int(manifest.get("pdf_pages") or 0)
    heads = read_heads(doc_name, pdf_pages)
    if not heads:
        print(f"[!] Chưa có file head_*.txt trong {documents.ocr_dir(doc_name)}. Chạy ocr_book.py trước.")
        return None

    print(f"[1/5] Đọc {len(heads)}/{pdf_pages} running head.")

    # --- Trang mục lục tra cứu (ML-xx) tách riêng, không tham gia đánh số thân sách
    index_pages: Dict[int, str] = {}
    for pdf_page, head in heads.items():
        m = INDEX_LABEL_RE.search(head)
        if m:
            digits = m.group(1).translate(_DIGITISE)
            if digits.isdigit():
                index_pages[pdf_page] = f"ML-{int(digits)}"
    print(f"[2/5] Nhận diện {len(index_pages)} trang mục lục tra cứu (ML-xx).")

    # --- Tìm các mức offset thật bằng tần suất
    offset_counter: Counter = Counter()
    page_candidates: Dict[int, List[Tuple[int, float]]] = {}
    for pdf_page, head in heads.items():
        if pdf_page in index_pages:
            continue
        cands = candidates_for(head)
        page_candidates[pdf_page] = cands
        for val, _pos in cands:
            off = val - pdf_page
            if abs(off) <= MAX_PLAUSIBLE_OFFSET:
                offset_counter[off] += 1

    levels = {off for off, n in offset_counter.items() if n >= MIN_LEVEL_SUPPORT}
    print(f"[3/5] Mức offset thật: {sorted(levels)}")
    if not levels:
        print("    [!] Không tìm được mức offset nào — head có thể OCR hỏng.")
        return None

    # --- Chọn ứng viên bằng quy hoạch động, ràng buộc offset GIẢM DẦN
    #
    # Ràng buộc này là thứ mạnh nhất có được: những trang thừa trong PDF (bìa,
    # trang phân mục, trang trắng) không được đánh số in, nên càng về sau chỉ số
    # PDF càng chạy nhanh hơn số trang in. offset = trang_in − pdf vì thế chỉ đi
    # xuống, không bao giờ đi lên.
    #
    # Chọn tham lam từng trang sẽ sinh ra số trùng (pdf 146 và 147 cùng ra 147).
    # Ở đây tìm dãy con có tổng điểm lớn nhất mà offset không tăng — đúng một
    # ứng viên cho mỗi trang, và tự loại các số đọc nhầm không nằm trong dãy.
    items: List[Tuple[int, int, int]] = []  # (pdf_page, offset, điểm)
    for pdf_page in sorted(page_candidates):
        for val, pos in page_candidates[pdf_page]:
            off = val - pdf_page
            if off not in levels:
                continue
            # Sách in số trang chẵn ở mép trái, số lẻ ở mép phải
            score = 10 + min(offset_counter[off], 60) // 10
            if (val % 2 == 0) == (pos < 0.5):
                score += 6
            items.append((pdf_page, off, score))

    n = len(items)
    best_score = [0] * n
    parent = [-1] * n
    for i in range(n):
        best_score[i] = items[i][2]
        for j in range(i):
            # pdf tăng, offset không tăng, VÀ số trang in tăng thật sự.
            # Thiếu điều kiện cuối thì cặp (pdf+1, offset−1) vẫn lọt, cho ra hai
            # trang PDF khác nhau cùng mang một số trang in.
            if (
                items[j][0] < items[i][0]
                and items[j][1] >= items[i][1]
                and items[j][0] + items[j][1] < items[i][0] + items[i][1]
            ):
                if best_score[j] + items[i][2] > best_score[i]:
                    best_score[i] = best_score[j] + items[i][2]
                    parent[i] = j

    chosen: Dict[int, Tuple[int, int, bool]] = {}  # pdf -> (trang in, offset, đọc trực tiếp)
    if n:
        k = max(range(n), key=lambda i: best_score[i])
        while k != -1:
            pdf_page, off, _ = items[k]
            chosen[pdf_page] = (pdf_page + off, off, True)
            k = parent[k]

    direct = len(chosen)
    print(f"[4/5] Đọc trực tiếp được số trang của {direct}/{len(page_candidates)} trang.")

    # --- Nội suy giữa hai trang neo
    #
    # Khi offset đổi giữa neo A và neo B, có nghĩa vài trang PDF trong khoảng đó
    # KHÔNG mang số trang in — trang trắng hoặc trang phân mục. Dùng offset của A
    # cho cả khoảng sẽ sinh số trùng ở đúng những chỗ này.
    #
    # Số trang không đánh số đếm được chính xác: (số trang PDF trong khoảng) trừ
    # (số trang in cần gán). Còn chọn ĐÚNG trang nào thì dựa vào lượng chữ: trang
    # trắng cho text OCR gần rỗng.
    body_len: Dict[int, int] = {}
    for pdf_page in page_candidates:
        try:
            body_len[pdf_page] = os.path.getsize(
                documents.ocr_page_path(doc_name, pdf_page)
            )
        except OSError:
            body_len[pdf_page] = 0

    anchors_sorted = sorted(chosen)
    for a, b in zip(anchors_sorted, anchors_sorted[1:]):
        gap = [p for p in range(a + 1, b) if p in page_candidates]
        if not gap:
            continue
        printed_a = chosen[a][0]
        printed_b = chosen[b][0]
        slots = printed_b - printed_a - 1  # số trang in cần gán trong khoảng
        unnumbered = len(gap) - slots

        skip: set = set()
        if unnumbered > 0:
            # Trang ít chữ nhất là trang trắng -> không đánh số
            skip = set(sorted(gap, key=lambda p: body_len.get(p, 0))[:unnumbered])

        nxt = printed_a + 1
        for p in gap:
            if p in skip or nxt >= printed_b:
                continue
            chosen[p] = (nxt, nxt - p, False)
            nxt += 1

    # Đuôi sách sau neo cuối: giữ nguyên offset của neo cuối
    if anchors_sorted:
        last = anchors_sorted[-1]
        last_off = chosen[last][1]
        for pdf_page in sorted(page_candidates):
            if pdf_page > last and pdf_page not in chosen:
                chosen[pdf_page] = (pdf_page + last_off, last_off, False)

    # --- Dựng kết quả
    pages: Dict[str, Dict[str, Any]] = {}
    body_numbers: List[int] = []
    for pdf_page in range(1, pdf_pages + 1):
        head = heads.get(pdf_page, "")
        if pdf_page in index_pages:
            pages[str(pdf_page)] = {
                "pdf_page": pdf_page,
                "page_label": index_pages[pdf_page],
                "page_num": None,
                "page_class": "index",
                "resolved": "direct",
            }
            continue
        if pdf_page in chosen:
            printed, off, is_direct = chosen[pdf_page]
            pages[str(pdf_page)] = {
                "pdf_page": pdf_page,
                "page_label": str(printed),
                "page_num": printed,
                "offset": off,
                "page_class": "body",
                "resolved": "direct" if is_direct else "interpolated",
            }
            body_numbers.append(printed)
        else:
            # Không số, không lân cận -> bìa / trang trắng đầu sách
            pages[str(pdf_page)] = {
                "pdf_page": pdf_page,
                "page_label": None,
                "page_num": None,
                "page_class": "front_matter",
                "resolved": "none",
            }

    # --- Kiểm tra tính đơn điệu: trang in phải tăng đều 1 đơn vị
    anomalies: List[Dict[str, Any]] = []
    prev: Optional[Tuple[int, int]] = None
    for pdf_page in range(1, pdf_pages + 1):
        info = pages[str(pdf_page)]
        if info["page_num"] is None:
            continue
        if prev is not None:
            gap = info["page_num"] - prev[1]
            step = pdf_page - prev[0]
            if gap != step:
                anomalies.append({
                    "pdf_page": pdf_page,
                    "page_num": info["page_num"],
                    "prev_pdf_page": prev[0],
                    "prev_page_num": prev[1],
                    "head": heads.get(pdf_page, ""),
                })
        prev = (pdf_page, info["page_num"])

    body_range = [min(body_numbers), max(body_numbers)] if body_numbers else None
    interpolated = sum(1 for p in pages.values() if p["resolved"] == "interpolated")

    print(f"[5/5] Nội suy thêm {interpolated} trang. Bất thường còn lại: {len(anomalies)}.")

    return {
        "doc_name": doc_name,
        "pdf_pages": pdf_pages,
        "body_page_range": body_range,
        "counts": {
            "direct": direct,
            "interpolated": interpolated,
            "index": len(index_pages),
            "front_matter": sum(1 for p in pages.values() if p["page_class"] == "front_matter"),
            "anomalies": len(anomalies),
        },
        "offset_levels": sorted(levels),
        "anomalies": anomalies[:100],
        "pages": pages,
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Dựng bản đồ trang in ↔ trang PDF")
    p.add_argument("--doc-name", required=True)
    a = p.parse_args()

    print("=" * 66)
    print(f"   BẢN ĐỒ TRANG — {a.doc_name}")
    print("=" * 66)

    result = build_map(a.doc_name)
    if not result:
        return

    path = documents.page_map_path(a.doc_name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    documents.update_manifest(a.doc_name, body_page_range=result["body_page_range"])

    c = result["counts"]
    print("\n" + "=" * 66)
    print("   HOÀN TẤT")
    print(f"   Dải trang thân sách : {result['body_page_range']}")
    print(f"   Đọc trực tiếp       : {c['direct']}")
    print(f"   Nội suy             : {c['interpolated']}")
    print(f"   Mục lục tra cứu     : {c['index']}")
    print(f"   Bìa / trang đầu     : {c['front_matter']}")
    print(f"   Bất thường cần rà   : {c['anomalies']}")
    print(f"   -> {path}")
    print("=" * 66)


if __name__ == "__main__":
    main()
