r"""Đo thời gian từng khâu của đường tìm kiếm chính.

Chạy::

    python eval/timing_run.py                  # cả hai khâu, cần khoá DeepSeek
    python eval/timing_run.py --no-llm          # chỉ khâu tìm, không cần khoá
    python eval/timing_run.py --repeat 3        # lặp để thấy chênh lệch giữa các lần

Gọi THẲNG vào hàm trong tiến trình, không qua HTTP: mọi `/api/*` đều đòi đăng
nhập nên curl trần trả 401, và dựng phiên đăng nhập chỉ để đo thời gian là thêm
một biến không liên quan.

Lần tra ĐẦU TIÊN luôn chậm hơn hẳn vì nó nạp model embedding và dựng chỉ mục
BM25. Đó là con số thật mà bác sĩ gặp sau khi mở app, nên script in riêng nó ra
thay vì bỏ đi như một lần "làm nóng".
"""

import argparse
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

# Câu hỏi đo: một tra theo tên thuốc, một đặt theo lời người bệnh. Hai dạng này
# đi qua hai nhánh khác nhau của truy xuất lai, nên thời gian có thể lệch nhau.
QUERIES = [
    "paracetamol liều dùng",
    "bị đau đầu thì uống thuốc gì",
    "thuốc hạ sốt",
]


def fmt(ms: float) -> str:
    return f"{ms/1000:.2f}s" if ms >= 1000 else f"{ms:.0f}ms"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true",
                    help="Chỉ đo khâu tìm. Dùng khi không có khoá DeepSeek.")
    ap.add_argument("--repeat", type=int, default=1,
                    help="Số lần lặp mỗi câu hỏi, sau lần nạp model.")
    ap.add_argument("--stream", action="store_true",
                    help="Đo thời gian tới CHỮ ĐẦU TIÊN thay vì chờ sinh xong. "
                         "Đây là con số quyết định ngưỡng timeout khi đã chuyển "
                         "sang luồng SSE, vì lúc đó bác sĩ đã đọc được trước khi "
                         "mô hình sinh xong.")
    args = ap.parse_args()

    import config
    from vector_store import VectorStore
    from llm_client import generate_answer, stream_answer

    key = config.DEEPSEEK_API_KEY
    use_llm = not args.no_llm
    if use_llm and not key:
        print("Không có DEEPSEEK_API_KEY, chỉ đo khâu tìm.")
        use_llm = False

    # PHẢI truyền đường dẫn. Constructor không tham số đặt persist_dir thành
    # "/content/chroma_data" — đường dẫn Google Colab còn sót lại. Trên máy này
    # nó trỏ vào chỗ không có gì, và search() chỉ in "Vector store is empty"
    # rồi trả về danh sách rỗng thay vì báo lỗi. Đo kiểu đó ra 14ms một lần tìm,
    # trông như một kết quả tốt trong khi thật ra không tìm gì cả.
    db = VectorStore(config.VECTOR_DB_DIR)

    print("\n=== Lần nạp đầu tiên (model embedding + chỉ mục BM25) ===")
    t0 = time.perf_counter()
    db.search(QUERIES[0], top_k=5)
    cold_ms = (time.perf_counter() - t0) * 1000
    print(f"tìm lần đầu: {fmt(cold_ms)}   <- bác sĩ gặp con số này sau khi mở app")

    print("\n=== Sau khi đã nạp ===")
    header = f"{'câu hỏi':<34} {'tìm':>9}"
    if use_llm:
        header += f" {'chữ đầu':>9} {'sinh xong':>10}" if args.stream else f" {'mô hình':>9} {'tổng':>9}"
    print(header)
    print("-" * len(header))

    retrieval_all: list[float] = []
    llm_all: list[float] = []
    ttft_all: list[float] = []

    for q in QUERIES:
        for _ in range(max(1, args.repeat)):
            t = time.perf_counter()
            sources = db.search(q, top_k=5)
            r_ms = (time.perf_counter() - t) * 1000
            retrieval_all.append(r_ms)

            row = f"{q[:33]:<34} {fmt(r_ms):>9}"
            if use_llm and args.stream:
                t = time.perf_counter()
                first_ms = None
                err = None
                for kind, payload in stream_answer(q, sources, key):
                    if kind == "error":
                        err = payload
                        break
                    if first_ms is None:
                        first_ms = (time.perf_counter() - t) * 1000
                l_ms = (time.perf_counter() - t) * 1000
                if err:
                    row += f" {'LỖI':>9} {fmt(l_ms):>10}   {err}"
                else:
                    ttft_all.append(first_ms)
                    llm_all.append(l_ms)
                    row += f" {fmt(first_ms):>9} {fmt(l_ms):>10}"
            elif use_llm:
                t = time.perf_counter()
                try:
                    generate_answer(q, sources, key)
                    l_ms = (time.perf_counter() - t) * 1000
                    llm_all.append(l_ms)
                    row += f" {fmt(l_ms):>9} {fmt(r_ms + l_ms):>9}"
                except Exception as e:
                    l_ms = (time.perf_counter() - t) * 1000
                    row += f" {'LỖI':>9} {fmt(r_ms + l_ms):>9}   {type(e).__name__}: {e}"
            print(row)

    print("\n=== Tóm lại ===")
    print(f"tìm:        trung vị {fmt(statistics.median(retrieval_all))}, "
          f"chậm nhất {fmt(max(retrieval_all))}, {len(retrieval_all)} lần")
    if ttft_all:
        print(f"chữ đầu:    trung vị {fmt(statistics.median(ttft_all))}, "
              f"chậm nhất {fmt(max(ttft_all))}, {len(ttft_all)} lần")
    if llm_all:
        print(f"sinh xong:  trung vị {fmt(statistics.median(llm_all))}, "
              f"chậm nhất {fmt(max(llm_all))}, {len(llm_all)} lần")
        share = statistics.median(llm_all) / (statistics.median(llm_all) + statistics.median(retrieval_all))
        print(f"\nMô hình ngôn ngữ chiếm {share*100:.0f}% thời gian chờ. "
              f"Timeout và nút hủy phải đặt ở đó trước.")
    else:
        print("mô hình:    không đo (thiếu khoá hoặc --no-llm)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
