"""
Nạp chunk của một tài liệu vào ChromaDB — idempotent, dùng chung cho mọi sách.

Thay cho ingest_metadata_to_vectordb.py (đường dẫn hard-code, không xoá trước khi
nạp nên chạy lại là nhân bản dữ liệu).

Điểm khác cốt lõi: mỗi chunk mang một id TẤT ĐỊNH, dẫn xuất từ nội dung. Chroma
upsert theo id, nên chạy lại script này ghi đè đúng chỗ thay vì tạo bản mới. Hai
entry có cùng chunk_id và cùng nội dung sẽ tự gộp làm một — đó đúng là định nghĩa
của bản trùng.

Dùng:
    python backend/ingest_book.py --doc-name DTQGVN-2022-Q1
    python backend/ingest_book.py --doc-name <sách cũ> --chunks <đường dẫn> --replace
"""

import os
import sys
import json
import time
import hashlib
import argparse
import datetime
import sqlite3
from typing import Any, Dict, List, Tuple

from tqdm import tqdm
from langchain_core.documents import Document

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import documents
from drug_name import is_suspect_name, normalize_drug_name
from vector_store import VectorStore
import config


def chunk_uid(doc_name: str, chunk: Dict[str, Any]) -> str:
    """
    Id tất định, định địa chỉ theo nội dung.

    chunk_id do parser sinh KHÔNG duy nhất — trên cuốn Thuốc Biệt Dược có 18 717
    chunk nhưng chỉ 15 371 chunk_id phân biệt, riêng UNKNOWNDRUG_LD_01 lặp 792
    lần. Vì vậy phải thêm hash nội dung, nếu không các chunk khác nhau sẽ ghi đè
    lẫn nhau khi upsert.

    Tiền tố doc_name giữ cho hai quyển trong cùng bộ sách không đụng nhau khi một
    hoạt chất xuất hiện ở cả hai.
    """
    payload = "\x1f".join([
        str(chunk.get("chunk_id", "")),
        str(chunk.get("field_name", "")),
        str(chunk.get("page_in_file", "")),
        str(chunk.get("content", "")),
    ])
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"{doc_name}::{chunk.get('chunk_id', 'CHUNK')}::{digest}"


def count_indexed_chunks(doc_name: str) -> int:
    """Số chunk của một tài liệu đang có trong ChromaDB.

    Đọc trực tiếp bằng SQL để không phải nạp lại mô hình embedding chỉ để đếm.
    """
    db_file = os.path.join(config.VECTOR_DB_DIR, "chroma.sqlite3")
    if not os.path.exists(db_file):
        return 0
    try:
        conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM embedding_metadata WHERE key = 'doc_name' AND string_value = ?",
                (doc_name,),
            ).fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()
    except Exception as e:
        print(f"  [!] Không đếm được chunk trong chỉ mục: {e}")
        return 0


def build_documents(
    doc_name: str, raw_chunks: List[Dict[str, Any]]
) -> Tuple[List[Document], List[str]]:
    """Chuyển chunk JSON của parser thành LangChain Document + id tất định."""
    manifest = documents.load_manifest(doc_name) or {}

    seen: Dict[str, int] = {}
    docs: List[Document] = []
    ids: List[str] = []

    suspect_count = 0
    for c in raw_chunks:
        # Chuẩn hoá tên ở đây chứ không ở parser: chỗ này chạy cho MỌI cuốn sách
        # và cho cả những tệp chunk đã bóc từ trước, nên không phải OCR lại sách
        # chỉ để sửa cái nhãn. Hàm này idempotent nên parser có gọi sẵn cũng
        # không sao.
        raw_name = c.get("generic_name", "UNKNOWN")
        generic_name = normalize_drug_name(raw_name) or "UNKNOWN"
        suspect, suspect_reason = is_suspect_name(raw_name)
        field_name = c.get("field_name", "Thông tin")
        content = c.get("content", "")
        if not content.strip():
            continue

        brand_list = c.get("brand_names", [])
        brand_str = ", ".join(brand_list) if isinstance(brand_list, list) else str(brand_list)
        page_num = c.get("page_in_file", 1)

        uid = chunk_uid(doc_name, c)
        if uid in seen:
            # Cùng id ⇒ cùng nội dung ⇒ đúng là bản trùng, bỏ qua bản sau.
            seen[uid] += 1
            continue
        seen[uid] = 1

        # Ngữ cảnh parent giàu thông tin cho LLM đọc và cho embedding.
        # Dòng định danh ghép từ những gì tài liệu thực sự có: Thuốc Biệt Dược
        # cho biệt dược, Dược thư cho tên quốc tế và mã ATC. Nhồi "Biệt dược:
        # Không" vào mọi chunk Dược thư chỉ làm loãng vector embedding.
        syn_list = c.get("synonyms", [])
        syn_str = ", ".join(syn_list) if isinstance(syn_list, list) else str(syn_list)

        ident: List[str] = [f"【THUỐC: {generic_name}】"]
        if brand_str:
            ident.append(f"(Biệt dược: {brand_str})")
        # Dược thư in tên đồng nghĩa ngay dưới tên chuyên luận. Đưa vào đây thì
        # câu hỏi "Vitamin C" mới tìm ra chuyên luận ACID ASCORBIC — cả BM25 lẫn
        # embedding đều chỉ nhìn thấy chuỗi này.
        if syn_str:
            ident.append(f"(Tên khác: {syn_str})")
        if c.get("intl_name"):
            ident.append(f"(Tên quốc tế: {c['intl_name']})")
        if c.get("atc_code"):
            ident.append(f"(ATC: {c['atc_code']})")
        parent_text = f"{' '.join(ident)}\n[{field_name}]\n{content}"

        metadata = {
            "doc_name": doc_name,
            "chunk_id": c.get("chunk_id", ""),
            "generic_name": generic_name,
            "brand_names": brand_str,
            "field_type": c.get("field_type", "GENERAL"),
            "field_name": field_name,
            "page_num": page_num,
            "doc_type": "child",
            "parent_text": parent_text,
            "source": doc_name,
            "page": page_num,
        }

        # Trường phục vụ trích dẫn & lọc phạm vi trong bộ nhiều tập. Chroma chỉ
        # nhận str/int/float/bool nên bỏ mọi giá trị None.
        for key in ("doc_series", "volume"):
            if manifest.get(key) is not None:
                metadata[key] = manifest[key]
        if c.get("pdf_page") is not None:
            metadata["pdf_page"] = c["pdf_page"]
        if c.get("page_class"):
            metadata["page_class"] = c["page_class"]
        # Định danh chuẩn hóa của Dược thư. atc_code là khoá nối một hoạt chất
        # giữa hai cuốn sách, nên đáng đưa vào metadata để lọc và đối chiếu.
        for key in ("intl_name", "atc_code", "drug_class"):
            if c.get(key):
                metadata[key] = c[key]
        # Chroma chỉ nhận str/int/float/bool nên list phải nối thành chuỗi.
        if syn_str:
            metadata["synonyms"] = syn_str
        # Cờ cảnh báo tên hỏng do OCR. Chỉ để giao diện và LLM biết đường không
        # khẳng định chuỗi này là tên thuốc — KHÔNG dùng để lọc bỏ chunk: nội
        # dung của chúng là dữ liệu thuốc thật (xem backend/drug_name.py).
        if suspect:
            metadata["name_suspect"] = True
            metadata["name_suspect_reason"] = suspect_reason
            suspect_count += 1

        docs.append(Document(page_content=parent_text, metadata=metadata))
        ids.append(uid)

    collapsed = sum(v - 1 for v in seen.values() if v > 1)
    if collapsed:
        print(f"  [i] Gộp {collapsed} entry trùng khít trong file chunk nguồn.")
    if suspect_count:
        pct = suspect_count / max(len(docs), 1) * 100
        print(f"  [i] {suspect_count} chunk ({pct:.1f}%) có tên thuốc đáng ngờ — "
              f"đã gắn cờ name_suspect, KHÔNG loại bỏ.")

    return docs, ids


def ingest(doc_name: str, chunks_file: str, replace: bool, batch_size: int) -> None:
    manifest = documents.load_manifest(doc_name)
    if not manifest:
        print(f"[!] Chưa có manifest cho '{doc_name}'. Chạy migrate_phase0.py trước.")
        return

    if not os.path.exists(chunks_file):
        print(f"[!] Không thấy file chunk: {chunks_file}")
        return

    print("=" * 66)
    print("   NẠP CHUNK VÀO VECTOR DATABASE")
    print(f"   Tài liệu : {manifest.get('doc_title')}  [{doc_name}]")
    print(f"   Nguồn    : {chunks_file}")
    print("=" * 66)

    with open(chunks_file, "r", encoding="utf-8") as f:
        raw_chunks = json.load(f)
    print(f"\n[1/4] Đọc {len(raw_chunks)} chunk từ file nguồn.")

    print("[2/4] Dựng Document + id tất định...")
    docs, ids = build_documents(doc_name, raw_chunks)
    print(f"  -> {len(docs)} chunk duy nhất, {len(set(ids))} id phân biệt.")
    if len(set(ids)) != len(ids):
        print("  [!] Id bị trùng — dừng để tránh mất dữ liệu.")
        return

    db = VectorStore(config.VECTOR_DB_DIR)

    if replace:
        print(f"[3/4] Xoá toàn bộ chunk cũ của '{doc_name}' khỏi index...")
        try:
            db.delete_document(doc_name)
        except Exception as e:
            print(f"  [!] Lỗi khi xoá: {e}")
    else:
        print("[3/4] Bỏ qua bước xoá (upsert theo id).")

    print(f"[4/4] Nạp {len(docs)} chunk, mỗi đợt {batch_size}...")
    t0 = time.time()
    for i in tqdm(range(0, len(docs), batch_size), desc="  ChromaDB", unit="batch"):
        db.add_chunks(docs[i : i + batch_size], ids=ids[i : i + batch_size])
    elapsed = time.time() - t0

    # Đếm từ chính chỉ mục, không lấy len(docs): nạp một tệp chunk RIÊNG PHẦN
    # (vd. để thử tính bất biến) mà ghi len(docs) vào manifest thì số chunk của
    # cả cuốn sách bị thay bằng số chunk của phần vừa nạp — vector_store
    # .list_documents() đọc đúng trường này để hiện ra giao diện.
    documents.update_manifest(
        doc_name,
        chunk_count=count_indexed_chunks(doc_name),
        ingested_at=datetime.datetime.now().isoformat(timespec="seconds"),
    )

    print("\n" + "=" * 66)
    print(f"   HOÀN TẤT — {len(docs)} chunk trong {elapsed / 60:.1f} phút")
    print("=" * 66)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Nạp chunk của một tài liệu vào ChromaDB")
    p.add_argument("--doc-name", required=True, help="ID tài liệu, vd. DTQGVN-2022-Q1")
    p.add_argument("--chunks", default=None, help="File chunk JSON (mặc định: data/chunks/<doc-name>.json)")
    p.add_argument("--replace", action="store_true", help="Xoá sạch chunk cũ của tài liệu trước khi nạp")
    p.add_argument("--batch-size", type=int, default=500)
    args = p.parse_args()

    chunks_file = args.chunks or documents.chunks_path(args.doc_name)
    ingest(args.doc_name, chunks_file, args.replace, args.batch_size)


if __name__ == "__main__":
    main()
