"""
Migration Bước 00 — dọn nền cho pipeline nhiều tập.

Chạy được nhiều lần, không hỏng nếu chạy lại (idempotent).

1. Tách text OCR ra khỏi namespace phẳng pdf_text/ về ocr_text/<doc_name>/.
   Trước đây main.py fallback về pdf_text/page_XXXX.txt cho MỌI doc_name, nên
   sau khi nạp cuốn thứ hai, mở trang của cuốn này sẽ ra nội dung cuốn kia.
2. Sinh manifest cho cuốn đã index sẵn.
3. Di chuyển + đổi tên PDF Dược thư về uploads/<doc_name>.pdf và sinh manifest.

Dùng: python backend/migrate_phase0.py [--dry-run]
"""

import os
import sys
import json
import shutil
import sqlite3
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import documents

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEGACY_PDF_TEXT_DIR = os.path.join(PROJECT_ROOT, "pdf_text")

OLD_BOOK = "THUOC-BIET-DUOC-VA-CACH-SU-DUNG.pdf"

NEW_BOOK_SOURCE = os.path.join(
    PROJECT_ROOT, "835733515-Duoc-Thu-Quoc-Gia-Viet-Nam-2022-Quyen-1-11-2023-1.pdf"
)
NEW_BOOK_DOC_NAME = "DTQGVN-2022-Q1"


def count_chunks(doc_name: str) -> int:
    """
    Đếm child chunk của một tài liệu bằng SQL trực tiếp trên chroma.sqlite3.

    Đi đường SQL thay vì qua Chroma client để khỏi phải nạp model embedding
    (mất vài chục giây) chỉ để lấy một con số.
    """
    db_path = os.path.join(config.VECTOR_DB_DIR, "chroma.sqlite3")
    if not os.path.exists(db_path):
        return 0
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        row = con.execute(
            """
            SELECT COUNT(*) FROM embedding_metadata m
            WHERE m.key = 'doc_name' AND m.string_value = ?
              AND m.id IN (
                  SELECT id FROM embedding_metadata
                  WHERE key = 'doc_type' AND string_value = 'child'
              )
            """,
            (doc_name,),
        ).fetchone()
        con.close()
        return int(row[0]) if row else 0
    except Exception as e:
        print(f"    [!] Không đếm được chunk: {e}")
        return 0


def step_migrate_ocr_text(dry_run: bool) -> int:
    print("\n[1/3] Tách text OCR về namespace riêng của tài liệu")

    if not os.path.isdir(LEGACY_PDF_TEXT_DIR):
        print(f"    Không có {LEGACY_PDF_TEXT_DIR} — bỏ qua.")
        return 0

    target_dir = documents.ocr_dir(OLD_BOOK)
    files = sorted(
        f for f in os.listdir(LEGACY_PDF_TEXT_DIR)
        if f.startswith("page_") and f.endswith(".txt")
    )
    if not files:
        print("    Không có file page_*.txt nào — bỏ qua.")
        return 0

    print(f"    {len(files)} file  ->  {target_dir}")
    if dry_run:
        return len(files)

    os.makedirs(target_dir, exist_ok=True)
    copied = 0
    for name in files:
        src = os.path.join(LEGACY_PDF_TEXT_DIR, name)
        dst = os.path.join(target_dir, name)
        # Sao chép chứ không di chuyển: giữ nguyên pdf_text/ làm bản dự phòng
        # cho tới khi xác nhận reader chạy đúng trên đường dẫn mới.
        if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
            shutil.copy2(src, dst)
        copied += 1

    print(f"    -> Đã đặt {copied} file. Giữ nguyên pdf_text/ làm bản dự phòng.")
    return copied


def step_manifest_old_book(dry_run: bool) -> None:
    print("\n[2/3] Manifest cho cuốn đã index sẵn")

    pdf_path = os.path.join(config.UPLOAD_DIR, OLD_BOOK)
    if not os.path.exists(pdf_path):
        print(f"    [!] Không thấy {pdf_path} — vẫn sinh manifest, chỉ thiếu file gốc.")

    existing = documents.load_manifest(OLD_BOOK)
    chunks = count_chunks(OLD_BOOK)

    manifest = documents.new_manifest(
        doc_name=OLD_BOOK,
        doc_title="Thuốc Biệt Dược và Cách Sử Dụng",
        short_title="Thuốc Biệt Dược",
        source_pdf=OLD_BOOK,
        pdf_pages=1555,
        # Sách một tập, số trang in = chỉ số PDF + 1 trên toàn bộ sách.
        body_page_range=[1, 1555],
        ocr={"dpi": 200, "columns": 2, "lang": "vie+eng"},
        parser="drug_parser",
    )
    manifest["chunk_count"] = chunks
    if existing:
        manifest["ingested_at"] = existing.get("ingested_at")

    print(f"    doc_name    : {OLD_BOOK}")
    print(f"    pdf_pages   : 1555  (thay cho hard-code trong vector_store.py)")
    print(f"    chunk_count : {chunks}")

    if not dry_run:
        path = documents.save_manifest(manifest)
        print(f"    -> {path}")


def step_place_new_book(dry_run: bool) -> None:
    print("\n[3/3] Đưa PDF Dược thư vào uploads/ và sinh manifest")

    target = os.path.join(config.UPLOAD_DIR, f"{NEW_BOOK_DOC_NAME}.pdf")

    if os.path.exists(target):
        size_mb = os.path.getsize(target) / 1024 / 1024
        print(f"    Đã có sẵn {target} ({size_mb:.0f} MB) — bỏ qua bước di chuyển.")
    elif not os.path.exists(NEW_BOOK_SOURCE):
        print(f"    [!] Không thấy file nguồn: {NEW_BOOK_SOURCE}")
        return
    else:
        size_mb = os.path.getsize(NEW_BOOK_SOURCE) / 1024 / 1024
        print(f"    {os.path.basename(NEW_BOOK_SOURCE)}  ({size_mb:.0f} MB)")
        print(f"    ->  {target}")
        print("    (move, không copy — ổ C: chỉ còn ~24 GB trống)")
        if not dry_run:
            shutil.move(NEW_BOOK_SOURCE, target)

    pdf_pages = 913
    if not dry_run and os.path.exists(target):
        try:
            try:
                import pymupdf as fitz
            except ImportError:
                import fitz
            with fitz.open(target) as d:
                pdf_pages = len(d)
        except Exception as e:
            print(f"    [!] Không đọc được số trang, dùng mặc định 913: {e}")

    existing = documents.load_manifest(NEW_BOOK_DOC_NAME)
    manifest = documents.new_manifest(
        doc_name=NEW_BOOK_DOC_NAME,
        doc_title="Dược thư Quốc gia Việt Nam 2022 — Quyển 1",
        short_title="Dược thư QGVN 2022",
        doc_series="DTQGVN-2022",
        volume=1,
        coverage="A – Hydroxyzin",
        source_pdf=f"{NEW_BOOK_DOC_NAME}.pdf",
        pdf_pages=pdf_pages,
        # Chưa đo chính xác — Bước 02 (page_map) sẽ điền sau khi OCR running head
        # toàn bộ 913 trang. Ước lượng từ 17 trang mẫu: khoảng [105, 881].
        body_page_range=None,
        ocr={"dpi": 300, "columns": 1, "lang": "vie+eng"},
        parser="dtqg_parser",
    )
    if existing:
        manifest["chunk_count"] = existing.get("chunk_count", 0)
        manifest["ingested_at"] = existing.get("ingested_at")
        manifest["body_page_range"] = existing.get("body_page_range")

    print(f"    doc_name  : {NEW_BOOK_DOC_NAME}   (ID ổn định, không theo tên file)")
    print(f"    pdf_pages : {pdf_pages}")

    if not dry_run:
        path = documents.save_manifest(manifest)
        print(f"    -> {path}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Migration Bước 00")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ in ra, không ghi gì")
    args = parser.parse_args()

    print("=" * 66)
    print("   MIGRATION BƯỚC 00 — DỌN NỀN CHO PIPELINE NHIỀU TẬP")
    if args.dry_run:
        print("   (DRY RUN — không ghi gì lên đĩa)")
    print("=" * 66)

    step_migrate_ocr_text(args.dry_run)
    step_manifest_old_book(args.dry_run)
    step_place_new_book(args.dry_run)

    print("\n" + "=" * 66)
    print("   HOÀN TẤT" if not args.dry_run else "   DRY RUN HOÀN TẤT")
    print("=" * 66)


if __name__ == "__main__":
    main()
