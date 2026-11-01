"""Khoá liên tiến trình cho mọi thao tác ghi chỉ mục Chroma."""
import os
from contextlib import contextmanager


@contextmanager
def writer_lock(persist_dir):
    os.makedirs(persist_dir, exist_ok=True)
    path = os.path.join(persist_dir, ".writer.lock")
    handle = open(path, "a+b")
    try:
        # Byte đầu chỉ được khởi tạo một lần; ghi lại khi đã bị khóa sẽ lỗi trên Windows.
        if os.path.getsize(path) == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError) as exc:
            raise RuntimeError(
                "Chỉ mục đang được máy chủ hoặc tiến trình nạp khác sử dụng; "
                "hãy tắt máy chủ trước khi chạy CLI ghi chỉ mục."
            ) from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()
