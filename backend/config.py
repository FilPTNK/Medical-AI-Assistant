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

# Directories relative to workspace or specified
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
VECTOR_DB_DIR = os.path.join(DATA_DIR, "vector_db")

# Create directories if they do not exist
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(VECTOR_DB_DIR, exist_ok=True)

PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "127.0.0.1")
