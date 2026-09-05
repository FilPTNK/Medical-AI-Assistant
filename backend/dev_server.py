"""Khởi động uvicorn cho môi trường phát triển (có auto-reload).

Dùng API Python thay vì tham số dòng lệnh vì trên Windows các mẫu glob như
"data/*" bị nở thành hàng nghìn đường dẫn trước khi tới uvicorn, khiến nó báo
"Got unexpected extra arguments" rồi thoát với mã 2.
"""
import sys

import uvicorn

import config

# Khi runner chuyển stdout thành pipe, Python dùng mã hoá locale (cp1252 trên
# Windows tiếng Việt) chứ không phải UTF-8, nên mọi dòng log có dấu đều ném
# UnicodeEncodeError. Ép UTF-8 ngay tại đây để không phụ thuộc vào việc tiến
# trình cha có đặt PYTHONIOENCODING hay không; errors="replace" đảm bảo log
# không bao giờ là lý do làm chết một luồng.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Chỉ theo dõi mã nguồn. backend/data/ chứa ~3.400 file / 1,2GB mà chính app
# ghi vào liên tục (chroma.sqlite3, các file .db, ảnh trang, cache). Uvicorn
# chỉ restart khi file .py đổi nên không có vòng lặp restart, nhưng loại nhóm
# này khỏi phạm vi theo dõi vẫn đỡ được I/O vô ích trên Windows.
RELOAD_EXCLUDES = [
    "data/*",
    "data/**/*",
    "__pycache__/*",
    "tessdata/*",
]

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=True,
        reload_excludes=RELOAD_EXCLUDES,
    )
