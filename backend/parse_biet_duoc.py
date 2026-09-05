"""
Bóc tách 'Thuốc Biệt Dược & Cách Sử Dụng' thành chunk — CLI dùng lại được.

Thay cho batch_process_book.py: kịch bản đó gộp OCR + bóc tách + nạp làm một,
ghi thẳng ra metadata.json bằng đường dẫn hard-code không còn tồn tại. Ở đây chỉ
làm đúng một việc — đọc text OCR đã có, bóc thành chunk, ghi ra
data/chunks/<doc-name>.json — rồi để ingest_book.py lo phần nạp, giống hệt luồng
của Dược thư.

Dùng:
    python backend/parse_biet_duoc.py --doc-name THUOC-BIET-DUOC-VA-CACH-SU-DUNG.pdf
"""

import os
import sys
import json
import collections
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import documents
from drug_parser import DrugChunkParser


def load_pages(doc_name: str) -> str:
    """Ghép text OCR của mọi trang, mỗi trang mở đầu bằng mốc [Trang N].

    drug_parser cắt tài liệu theo chính các mốc này, nên trang nào thiếu mốc thì
    nội dung của nó bị gán nhầm sang số trang của trang trước — trích dẫn sai
    trang là hỏng đúng cái mục đích fact-check.
    """
    ocr_dir = documents.ocr_dir(doc_name)
    if not os.path.isdir(ocr_dir):
        raise SystemExit(f"[!] Chưa có text OCR: {ocr_dir}")

    parts: List[str] = []
    for name in sorted(f for f in os.listdir(ocr_dir) if f.startswith("page_")):
        page_num = int(name[5:9])
        text = open(os.path.join(ocr_dir, name), encoding="utf-8").read()
        parts.append(text if text.lstrip().startswith("[Trang") else f"[Trang {page_num}]\n{text}")
    return "\n".join(parts)


def parse(doc_name: str, monograph_page_range: Optional[Tuple[int, int]]) -> List[Dict[str, Any]]:
    chunks = DrugChunkParser.parse_pdf_text_to_chunks(
        load_pages(doc_name), doc_name, monograph_page_range
    )
    # Chuẩn hoá về đúng schema mà ingest_book.py mong đợi: nó đọc pdf_page để
    # dựng liên kết tới ảnh scan. Sách này đánh số trang in trùng số trang PDF
    # (body_page_range [1, 1555]) nên hai giá trị bằng nhau.
    for c in chunks:
        c.setdefault("pdf_page", c.get("page_in_file"))
    return chunks


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    import argparse

    p = argparse.ArgumentParser(description="Bóc tách Thuốc Biệt Dược thành chunk")
    p.add_argument("--doc-name", required=True)
    p.add_argument("--out", default=None, help="Mặc định: data/chunks/<doc-name>.json")
    p.add_argument(
        "--monograph-pages", default=None, metavar="ĐẦU-CUỐI",
        help="Dải trang chuyên luận, vd. 5-1031. Mặc định lấy từ manifest.",
    )
    a = p.parse_args()

    manifest = documents.load_manifest(a.doc_name) or {}
    if a.monograph_pages:
        lo, hi = (int(x) for x in a.monograph_pages.split("-"))
        rng: Optional[Tuple[int, int]] = (lo, hi)
    else:
        saved = manifest.get("monograph_page_range")
        rng = (int(saved[0]), int(saved[1])) if saved else None

    print("=" * 66)
    print(f"   BÓC TÁCH — {a.doc_name}")
    print(f"   Dải chuyên luận: {rng if rng else 'toàn bộ sách'}")
    print("=" * 66)

    chunks = parse(a.doc_name, rng)

    out = a.out or documents.chunks_path(a.doc_name)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    drugs = {c["generic_name"] for c in chunks}
    unknown = sum(1 for c in chunks if c["generic_name"] == "UNKNOWN_DRUG")
    by_type = collections.Counter(c["field_type"] for c in chunks)

    print("\n" + "=" * 66)
    print("   HOÀN TẤT")
    print(f"   Mục thuốc    : {len(drugs)}")
    print(f"   Chunk        : {len(chunks)}")
    print(f"   UNKNOWN_DRUG : {unknown} ({100 * unknown / max(len(chunks), 1):.2f}%)")
    for k, v in by_type.most_common():
        print(f"     {k:22s} {v}")
    print(f"   -> {out}")
    print("=" * 66)


if __name__ == "__main__":
    main()
