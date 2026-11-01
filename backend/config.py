import os
from dotenv import load_dotenv

# Load env variables from a .env file if it exists
load_dotenv()

# Không đặt khoá mặc định trong mã nguồn. Bản trước hard-code một khoá thật
# ở đây, và khoá đó đã bị commit vào lịch sử git — phải thu hồi trên dashboard
# DeepSeek, xoá dòng code không gỡ được nó khỏi history.
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL") or "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"

# Model embedding của vector store. Giá trị mặc định cũ ở đây là
# "all-MiniLM-L6-v2" — một model THUẦN TIẾNG ANH mà không chỗ nào đọc tới, vì
# vector_store.py tự hard-code model riêng. Đặt EMBEDDING_MODEL trong .env vì
# thế không có tác dụng gì. Nay đây là nguồn duy nhất.
#
# ĐỔI GIÁ TRỊ NÀY LÀ PHẢI INDEX LẠI: vector cũ sinh bởi model khác không so
# sánh được với vector mới, và số chiều cũng có thể khác.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")

# Reranker cross-encoder đa ngữ, TẮT mặc định. Bật bằng biến môi trường, ví dụ
#   RERANKER_MODEL=BAAI/bge-reranker-v2-m3
#   RERANKER_MODEL=AITeamVN/Vietnamese_Reranker
# Chỉ chấm lại RERANK_TOP_N ứng viên đầu của RRF. Model ~0,6B tham số: phải đo độ
# trễ trên CPU của máy phòng khám trước khi bật (xem RUNBOOK.md).
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "").strip()
RERANK_TOP_N = int(os.getenv("RERANK_TOP_N", "20"))

# Directories relative to workspace or specified
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
VECTOR_DB_DIR = os.path.join(DATA_DIR, "vector_db")

# Cache model HuggingFace nằm TRONG dự án, không theo biến môi trường của máy.
#
# Máy phát triển có HF_HOME cấp hệ thống trỏ sang ổ D: (ổ rời). Khi ổ đó không
# cắm, mô hình embedding không nạp được, VectorStore.db thành None, corpus rỗng
# và search() trả [] — giao diện báo "Không tìm thấy đoạn y văn nào khớp" cho
# MỌI câu hỏi, dù dữ liệu vẫn nguyên vẹn. Lỗi hạ tầng bị đọc thành "không có
# kết quả". Gán cứng (không setdefault) vì chính biến hệ thống mới là thủ phạm.
#
# Phải chạy trước mọi `import huggingface_hub / sentence_transformers /
# langchain_huggingface`: các thư viện này đọc HF_HOME lúc import.
HF_HOME_DIR = os.path.join(DATA_DIR, "hf_cache")
os.makedirs(HF_HOME_DIR, exist_ok=True)
os.environ["HF_HOME"] = HF_HOME_DIR
os.environ.pop("HF_HUB_CACHE", None)
os.environ.pop("TRANSFORMERS_CACHE", None)
# Windows không cho tạo symlink nếu không bật Developer Mode; cache vẫn chạy
# đúng nhưng in cảnh báo dài mỗi lần nạp.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def _hf_model_cached() -> bool:
    hub = os.path.join(HF_HOME_DIR, "hub")
    if not os.path.isdir(hub):
        return False
    for entry in os.listdir(hub):
        snaps = os.path.join(hub, entry, "snapshots")
        if entry.startswith("models--") and os.path.isdir(snaps) and os.listdir(snaps):
            return True
    return False


# Đã có model trong cache thì chạy offline hẳn: khỏi gọi mạng lúc khởi động,
# khỏi cảnh báo "unauthenticated requests to the HF Hub". Chưa có (lần đầu) thì
# để mặc định để nó tự tải.
if _hf_model_cached():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

# Create directories if they do not exist
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(VECTOR_DB_DIR, exist_ok=True)

PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "127.0.0.1")

# Chế độ phát triển. Chỉ khi bật thì chi tiết kỹ thuật của lỗi mới được gửi ra
# giao diện. Ở chế độ thường bác sĩ chỉ thấy câu tiếng Việt nói rõ phải làm gì:
# một chuỗi như "AuthenticationError: Error code: 401 …" giữa lúc đang khám
# không giúp được gì, mà lại lộ cấu hình máy chủ cho bất cứ ai xem màn hình.
#
# Bật bằng biến môi trường, không phải bằng cách sửa mã:
#     MEDICAL_ASSISTANT_DEV=1 python run.py
DEV_MODE = os.getenv("MEDICAL_ASSISTANT_DEV", "").strip().lower() in ("1", "true", "yes", "on")

# Tìm thêm trên web (tab Tra y văn, nút "Tìm thêm trên web"). Xem web_tools.py.
#
# PubMed, openFDA và ClinicalTrials.gov là API công khai, chạy được không cần
# khoá. Khoá chỉ nâng hạn mức: NCBI 3 -> 10 lượt/giây, openFDA 1.000 ->
# 120.000 lượt/ngày. Riêng tìm web chung cần khoá Tavily (miễn phí 1.000
# lượt/tháng tại tavily.com); không có khoá thì công cụ đó tự ẩn đi.
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
NCBI_API_KEY = os.getenv("NCBI_API_KEY", "")
OPENFDA_API_KEY = os.getenv("OPENFDA_API_KEY", "")
# Tắt hẳn tính năng (vd. phòng khám không cho dữ liệu câu hỏi ra ngoài).
WEB_SEARCH_ENABLED = os.getenv("WEB_SEARCH_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")
# Tavily chỉ tìm trong các tên miền này. Để trống biến môi trường thì dùng danh
# sách mặc định trong web_tools.DEFAULT_DOMAINS.
WEB_SEARCH_DOMAINS = [d.strip() for d in os.getenv("WEB_SEARCH_DOMAINS", "").split(",") if d.strip()]
