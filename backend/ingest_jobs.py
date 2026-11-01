"""Job nạp PDF trong RAM: một worker, tối đa ba job đang chạy/đang chờ."""
import queue
import threading
import uuid
from typing import Any, Callable, Dict, Optional

MAX_ACTIVE_JOBS = 3
_jobs: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()
_queue = queue.Queue()
_worker = None


def reserve(file_name: str, allocate_name: Callable[[set], str]) -> Dict[str, Any]:
    with _lock:
        active = {j["doc_name"] for j in _jobs.values() if j["status"] in ("queued", "running")}
        if len(active) >= MAX_ACTIVE_JOBS:
            raise ValueError("Đang có 3 tài liệu chờ hoặc đang nạp; hãy thử lại khi một tài liệu xong.")
        doc_name = allocate_name(active)
        job_id = uuid.uuid4().hex
        job = {"job_id": job_id, "doc_name": doc_name, "file_name": file_name,
               "status": "queued", "stage": "Đang chờ xử lý...", "current": 0,
               "total": 0, "error": None, "warnings": []}
        _jobs[job_id] = job
        return dict(job)


def discard(job_id: str) -> None:
    with _lock:
        _jobs.pop(job_id, None)


def is_active(doc_name: str) -> bool:
    with _lock:
        return any(j["doc_name"].casefold() == doc_name.casefold() and
                   j["status"] in ("queued", "running") for j in _jobs.values())


def _work():
    while True:
        job_id, task = _queue.get()
        try:
            update(job_id, status="running")
            task()
        finally:
            _queue.task_done()


def submit(job_id: str, task: Callable[[], None]) -> None:
    global _worker
    with _lock:
        if job_id not in _jobs:
            raise ValueError("Không tìm thấy job nạp tài liệu.")
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_work, name="pdf-ingest", daemon=True)
            _worker.start()
        _queue.put((job_id, task))


def update(job_id: str, **fields: Any) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is not None:
            job.update(fields)


def get(job_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def make_progress_cb(job_id: str) -> Callable[[str, int, int], None]:
    def _cb(stage: str, current: int, total: int) -> None:
        update(job_id, status="running", stage=stage, current=current, total=total)
    return _cb
