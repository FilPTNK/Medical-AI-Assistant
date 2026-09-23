import os
import re
import asyncio
import shutil
import json
import uuid
import time
import sqlite3
import secrets
import threading
from contextlib import asynccontextmanager, contextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Header, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Any, Dict

import config
import documents
import google_login
import mailer
import patient_db
import patient_context
import drug_allergy
import text_fold
import doc_index
import profile_db
import auth_db
import reminder_db
import stats_db
import pdf_export
import library_db
import agent
from pdf_processor import process_pdf_parent_child_summary, SimpleLoader
from vector_store import VectorStore
from llm_client import generate_answer, stream_answer, generate_diagnosis_tree, suggest_endoscopy_exam, generate_final_diagnosis, generate_treatment_suggestion, generate_drug_report, stream_drug_report, generate_document_comparison

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Nạp sẵn model embedding và chỉ mục BM25 ở một thread nền.

    Phải chạy nền chứ không chặn: nếu chặn, uvicorn chưa bind cổng 8000 cho
    tới khi nạp xong (~35s), nên Vite proxy trả ECONNREFUSED và giao diện hiện
    "không kết nối được với máy chủ".

    Chạy nền thì cổng mở ngay, màn hình đăng nhập dùng được luôn (các endpoint
    xác thực không đụng tới vector store), và tới lúc bác sĩ gõ câu hỏi đầu
    tiên thì model thường đã sẵn sàng. Nếu chưa, search() vẫn tự nạp lười —
    VectorDB có khoá riêng nên hai đường này không dựng trùng nhau.
    """
    def _warm():
        t0 = time.perf_counter()
        print("[STARTUP] Đang nạp model embedding và chỉ mục BM25 ở nền...")
        try:
            db._get_corpus_and_bm25()
            print(f"[STARTUP] Sẵn sàng phục vụ tìm kiếm sau {time.perf_counter() - t0:.1f}s.")
        except Exception as e:
            print(f"[STARTUP] Cảnh báo: nạp trước thất bại ({e}). Sẽ nạp lười khi có truy vấn.")

    threading.Thread(target=_warm, name="warmup", daemon=True).start()
    yield

app = FastAPI(title="Medical RAG Assistant API", lifespan=lifespan)

# Initialize patient records database (SQLite)
patient_db.init_db()

# Initialize doctor profile database (SQLite) + xác thực/phân quyền trên cùng bảng
profile_db.init_db()
auth_db.init_db()

# Initialize document research database: highlights, notes, search history (SQLite)
library_db.init_db()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For local development, allow all
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize vector store
db = VectorStore(config.VECTOR_DB_DIR)

# Path to store full page texts for the reader. Đường dẫn theo tài liệu do
# documents.py quản lý — mọi thứ khóa theo doc_name để hai cuốn sách không đè nhau.
PAGES_CACHE_DIR = documents.PAGES_CACHE_DIR

class QueryRequest(BaseModel):
    query: str
    created_by: Optional[str] = None

class SearchResultItem(BaseModel):
    id: Optional[str] = None
    text: str
    doc_name: str
    page_num: int
    score: float
    # Nhãn để bác sĩ đối chiếu. doc_name là ID kỹ thuật ("DTQGVN-2022-Q1"),
    # không đọc được trên chip nguồn; citation là dạng người đọc, có kèm số
    # quyển vì trong bộ nhiều tập một số trang không định danh duy nhất.
    doc_title: Optional[str] = None
    citation: Optional[str] = None
    # Tên thuốc của chunk này do OCR đọc hỏng (xem drug_name.py). Nội dung vẫn
    # là dữ liệu thuốc thật nên chunk KHÔNG bị loại, nhưng giao diện phải nói
    # rõ cái nhãn không đáng tin. Trước đây cờ này dừng lại ở backend: llm_client
    # có nhận, còn model trả về cho UI thì không có trường nào để chở nó đi.
    name_suspect: bool = False

class QueryResponse(BaseModel):
    answer: str
    sources: List[SearchResultItem]


def enrich_sources(sources: List[dict]) -> List[dict]:
    """
    Gắn nhãn trích dẫn vào kết quả thô của vector store, tại chỗ.

    Chạy TRƯỚC khi gọi LLM để mô hình cũng thấy tên sách thật thay vì ID kỹ
    thuật, và chính danh sách đã gắn nhãn đó được trả về cho UI — hai bên vì
    thế luôn nói về cùng một nguồn.
    """
    for s in sources:
        doc_name = s.get("doc_name", "")
        manifest = documents.load_manifest(doc_name) or {}
        s["doc_title"] = manifest.get("doc_title") or doc_name
        s["citation"] = documents.display_citation(doc_name, s.get("page_num", 1))
    return sources


def to_search_result(s: dict) -> SearchResultItem:
    """Kết quả thô từ vector store -> item có kèm nhãn trích dẫn cho UI."""
    doc_name = s["doc_name"]
    return SearchResultItem(
        id=s.get("id"),
        text=s["text"],
        doc_name=doc_name,
        page_num=s["page_num"],
        score=s["score"],
        doc_title=s.get("doc_title") or doc_name,
        citation=s.get("citation") or documents.display_citation(doc_name, s["page_num"]),
        name_suspect=bool(s.get("name_suspect", False)),
    )

def read_json_data(file_path: str) -> list:
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return []

def write_json_data(file_path: str, data: list):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error writing {file_path}: {e}")


# =============================================================================
# Đo thời gian từng khâu
# =============================================================================

class StageTimer:
    r"""Đo thời gian từng khâu của một request và in ra ĐÚNG MỘT dòng log.

    Một dòng cho cả request, không phải một dòng mỗi khâu: backend chạy nhiều
    request song song, nên log từng khâu của các request khác nhau sẽ xen vào
    nhau và không còn ghép lại được để biết một lần tra mất bao lâu.

    Dùng như sau::

        t = StageTimer("search")
        with t.stage("retrieval"):
            sources = db.search(query)
        with t.stage("llm"):
            answer = generate_answer(...)
        t.log(f"q={len(query)}c")

    In ra::

        [TIMING] search retrieval=412ms llm=8310ms total=8724ms q=17c

    Khâu nào ném lỗi thì thời gian của nó VẪN được ghi, rồi lỗi bay tiếp ra
    ngoài — nếu không thì đúng những lần chậm nhất lại là những lần không có
    số liệu. Gọi ``log()`` trong ``finally`` để mọi lần tra đều để lại một dòng.
    """

    def __init__(self, label: str):
        self.label = label
        self.stages: Dict[str, int] = {}
        self._t0 = time.perf_counter()

    @contextmanager
    def stage(self, name: str):
        t = time.perf_counter()
        try:
            yield
        finally:
            self.stages[name] = round((time.perf_counter() - t) * 1000)

    @property
    def total_ms(self) -> int:
        return round((time.perf_counter() - self._t0) * 1000)

    def timings(self) -> Dict[str, int]:
        """Số đo của từng khâu, cộng tổng. Khâu chưa chạy thì không có mặt."""
        return dict(self.stages, total=self.total_ms)

    def log(self, note: str = "") -> Dict[str, int]:
        result = self.timings()
        parts = " ".join(f"{k}={v}ms" for k, v in result.items())
        # flush=True vì stdout của tiến trình con bị buffer khi run.py pipe nó,
        # và log đo thời gian mà đến muộn thì mất hẳn tác dụng.
        print(f"[TIMING] {self.label} {parts}" + (f" {note}" if note else ""), flush=True)
        return result

# =============================================================================
# XÁC THỰC & PHÂN QUYỀN
# =============================================================================
# Đường dẫn không cần đăng nhập: bản thân luồng đăng nhập, kiểm tra cấu hình, và
# link chia sẻ hội thoại (người nhận link không có tài khoản trong phòng khám).
PUBLIC_PATHS = {
    "/api/config", "/api/auth/status", "/api/auth/login", "/api/auth/setup",
    # Luồng đăng ký tự phục vụ: người dùng chưa có tài khoản nên chưa có token.
    "/api/auth/register", "/api/auth/register/verify",
    "/api/auth/register/resend", "/api/auth/google",
}
PUBLIC_PREFIXES = ("/api/share/",)

# PDF sách gốc nặng tới ~835 MB. Giao diện không thể fetch về blob rồi
# createObjectURL như với ảnh và tệp đính kèm nhỏ: cả tệp sẽ nằm trong RAM của tab.
# Thẻ <a download> thì stream thẳng xuống đĩa nhưng không mang được header
# Authorization. Lối ra là một "vé" dùng đúng một lần, sống rất ngắn, đi trong query
# string — như vậy session token của phiên không lọt vào lịch sử trình duyệt hay
# access log của máy chủ.
DOWNLOAD_TICKET_TTL_SECONDS = 60.0
DOWNLOAD_TICKET_PATH_RE = re.compile(r"^/api/documents/[^/]+/download$")
_download_tickets: Dict[str, Dict[str, Any]] = {}


def _issue_download_ticket(doc_name: str, session_token: str) -> str:
    now = time.time()
    for key in [k for k, v in _download_tickets.items() if v["expires_at"] < now]:
        del _download_tickets[key]
    ticket = secrets.token_urlsafe(32)
    _download_tickets[ticket] = {
        "doc_name": doc_name,
        # Vé gắn với phiên đã phát ra nó, không phải với tài khoản: bấm đăng xuất
        # phải vô hiệu hoá ngay cả vé vừa phát, không để nó sống hết TTL.
        "session_token": session_token,
        "expires_at": now + DOWNLOAD_TICKET_TTL_SECONDS,
    }
    return ticket


def _redeem_download_ticket(ticket: Optional[str], doc_name: str) -> bool:
    """Dùng một lần: pop trước khi kiểm tra nên vé rạch dù hợp lệ hay không."""
    if not ticket:
        return False
    info = _download_tickets.pop(ticket, None)
    if not info:
        return False
    if info["expires_at"] < time.time() or info["doc_name"] != doc_name:
        return False
    return auth_db.resolve_session(info["session_token"]) is not None


def _is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


@app.middleware("http")
async def authenticate(request: Request, call_next):
    """Gắn tài khoản đang đăng nhập vào request.state.user.

    Chỉ chặn các đường dẫn /api/; tệp tĩnh của giao diện vẫn phục vụ bình thường
    để trình duyệt tải được màn hình đăng nhập.
    """
    path = request.url.path
    request.state.user = None
    request.state.token = None

    if request.method == "OPTIONS" or not path.startswith("/api/"):
        return await call_next(request)

    header = request.headers.get("authorization") or ""
    token = header[7:].strip() if header.lower().startswith("bearer ") else None
    if token:
        request.state.token = token
        request.state.user = auth_db.resolve_session(token)

    if not _is_public(path) and request.state.user is None:
        # Tải PDF sách bằng vé một lần thay cho header — chính route sẽ đối chiếu vé,
        # ở đây chỉ ngừng trả 401 sớm để request đến được đó.
        has_ticket = bool(
            request.method == "GET"
            and DOWNLOAD_TICKET_PATH_RE.match(path)
            and request.query_params.get("ticket")
        )
        if not has_ticket:
            return JSONResponse(
                status_code=401,
                content={"detail": "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại."},
            )

    return await call_next(request)


def current_user(request: Request) -> Dict[str, Any]:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập.")
    return user


def require_admin(request: Request) -> Dict[str, Any]:
    user = current_user(request)
    if not auth_db.is_admin(user):
        raise HTTPException(status_code=403, detail="Chỉ quản trị phòng khám mới thực hiện được thao tác này.")
    return user


def require_write(request: Request) -> Dict[str, Any]:
    """Chặn vai trò chỉ đọc (điều dưỡng/trợ lý) khi ghi lên hồ sơ bệnh nhân."""
    user = current_user(request)
    if auth_db.is_read_only(user):
        raise HTTPException(status_code=403, detail="Tài khoản của bạn chỉ có quyền xem hồ sơ bệnh nhân.")
    return user


def scope_owner_id(user: Dict[str, Any]) -> Optional[str]:
    """None = xem toàn phòng khám; ngược lại giới hạn theo bác sĩ phụ trách."""
    return None if auth_db.can_see_all_patients(user) else user["id"]


def ensure_patient_access(patient_id: str, user: Dict[str, Any], write: bool = False) -> None:
    """Ném 404/403 nếu tài khoản không được phép chạm vào hồ sơ này.

    Bệnh nhân không thuộc quyền quản lý trả về 404 chứ không phải 403: bác sĩ
    khác không nên biết mã hồ sơ nào đang tồn tại trong phòng khám.
    """
    if not patient_db.patient_exists(patient_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ bệnh nhân.")
    if write and auth_db.is_read_only(user):
        raise HTTPException(status_code=403, detail="Tài khoản của bạn chỉ có quyền xem hồ sơ bệnh nhân.")
    if auth_db.can_see_all_patients(user):
        return
    owner = patient_db.get_patient_owner(patient_id)
    if owner is not None and owner != user["id"]:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ bệnh nhân.")


class LoginRequest(BaseModel):
    username: str
    password: str


class SetupRequest(BaseModel):
    password: str
    display_name: Optional[str] = None
    username: Optional[str] = None


class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str


class VerifyRegistrationRequest(BaseModel):
    pending_id: str
    code: str


class ResendCodeRequest(BaseModel):
    pending_id: str


class GoogleLoginRequest(BaseModel):
    credential: str


class ChangePasswordRequest(BaseModel):
    current_password: str = ""
    new_password: str


class UserCreateRequest(BaseModel):
    display_name: str
    username: str
    password: str
    role: str = "doctor"
    specialty: Optional[str] = ""
    email: Optional[str] = ""


class UserUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    username: Optional[str] = None
    specialty: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    is_disabled: Optional[bool] = None


class ResetPasswordRequest(BaseModel):
    new_password: str
    must_change: bool = True


@app.get("/api/auth/status")
def auth_status(request: Request):
    """Giao diện gọi trước khi hiện gì cả: cần thiết lập, cần đăng nhập, hay đã có phiên."""
    return {
        "needs_setup": auth_db.needs_setup(),
        "authenticated": getattr(request.state, "user", None) is not None,
        "user": getattr(request.state, "user", None),
        "roles": [{"value": k, "label": v} for k, v in auth_db.ROLES.items()],
        # Giao diện chỉ dựng nút "Đăng nhập với Google" khi máy chủ có client id;
        # thiếu cấu hình thì thư viện Google cũng không được tải về.
        "google_client_id": google_login.client_id(),
        # Chưa cấu hình Resend thì mã xác nhận in ra console máy chủ — nói thẳng
        # để người cài đặt biết chỗ lấy mã thay vì ngồi đợi thư không bao giờ tới.
        "email_delivery": mailer.is_configured(),
    }


@app.post("/api/auth/setup")
def auth_setup(payload: SetupRequest):
    if not auth_db.needs_setup():
        raise HTTPException(status_code=400, detail="Hệ thống đã được thiết lập. Vui lòng đăng nhập.")
    error = auth_db.validate_password(payload.password)
    if error:
        raise HTTPException(status_code=400, detail=error)
    user = auth_db.setup_admin(payload.password, payload.display_name, payload.username)
    if not user:
        raise HTTPException(status_code=500, detail="Không tạo được tài khoản quản trị.")
    result = auth_db.login(user["username"], payload.password)
    if not result["ok"]:
        raise HTTPException(status_code=500, detail=result["error"])
    # Hồ sơ cũ tạo từ thời chưa phân quyền chưa có bác sĩ phụ trách — giao hết cho
    # quản trị viên đầu tiên để không hồ sơ nào rơi vào trạng thái vô chủ.
    patient_db.claim_unassigned_patients(user["id"])
    return {"token": result["token"], "user": result["user"]}


@app.post("/api/auth/login")
def auth_login(payload: LoginRequest):
    result = auth_db.login(payload.username, payload.password)
    if not result["ok"]:
        raise HTTPException(status_code=401, detail=result["error"])
    return {"token": result["token"], "user": result["user"]}


@app.post("/api/auth/register")
def auth_register(payload: RegisterRequest):
    """Bước 1: cất đăng ký chờ, gửi mã xác nhận về email."""
    result = auth_db.start_registration(payload.email, payload.username, payload.password)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return {
        "pending_id": result["pending_id"],
        "email": result["email"],
        "delivered": result["delivered"],
        "expires_in": result["expires_in"],
        "resend_in": result["resend_in"],
    }


@app.post("/api/auth/register/verify")
def auth_register_verify(payload: VerifyRegistrationRequest):
    """Bước 2: đúng mã thì tài khoản ra đời và đăng nhập luôn."""
    result = auth_db.verify_registration(payload.pending_id, payload.code)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    if result.get("is_first_account"):
        # Giống luồng /api/auth/setup: người đầu tiên vào được nhận cả các hồ sơ
        # bệnh nhân tạo từ thời chưa có đăng nhập, để không hồ sơ nào vô chủ.
        patient_db.claim_unassigned_patients(result["user"]["id"])
    return {"token": result["token"], "user": result["user"]}


@app.post("/api/auth/register/resend")
def auth_register_resend(payload: ResendCodeRequest):
    result = auth_db.resend_registration_code(payload.pending_id)
    if not result["ok"]:
        raise HTTPException(status_code=429 if result.get("resend_in") else 400,
                            detail=result["error"])
    return {"delivered": result["delivered"], "expires_in": result["expires_in"],
            "resend_in": result["resend_in"]}


@app.post("/api/auth/google")
def auth_google(payload: GoogleLoginRequest):
    """Đổi ID token của Google Identity Services lấy phiên đăng nhập.

    Token bắt buộc phải kiểm ở đây; email do trình duyệt gửi lên thì ai cũng giả được.
    """
    if not google_login.is_configured():
        raise HTTPException(status_code=503,
                            detail="Máy chủ chưa bật đăng nhập bằng Google.")
    try:
        profile = google_login.verify_id_token(payload.credential)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    result = auth_db.login_with_google(profile)
    if not result["ok"]:
        raise HTTPException(status_code=403, detail=result["error"])
    if result.get("is_first_account"):
        patient_db.claim_unassigned_patients(result["user"]["id"])
    return {"token": result["token"], "user": result["user"], "created": result["created"]}


@app.post("/api/auth/logout")
def auth_logout(request: Request):
    auth_db.logout(getattr(request.state, "token", None))
    return {"ok": True}


@app.get("/api/auth/me")
def auth_me(request: Request):
    return current_user(request)


@app.post("/api/auth/change-password")
def auth_change_password(payload: ChangePasswordRequest, request: Request):
    user = current_user(request)
    error = auth_db.change_own_password(user["id"], payload.current_password, payload.new_password)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return {"ok": True}


# --- Quản lý tài khoản ---

@app.get("/api/users")
def list_users(request: Request):
    """Bác sĩ thường vẫn cần danh sách này để chọn người bàn giao bệnh nhân,
    nên trả về bản rút gọn thay vì chặn hẳn."""
    user = current_user(request)
    users = auth_db.list_users()
    if auth_db.is_admin(user):
        return users
    return [
        {k: u[k] for k in ("id", "display_name", "username", "specialty", "role",
                           "role_label", "avatar_url", "is_disabled")}
        for u in users if not u["is_disabled"]
    ]


@app.post("/api/users")
def create_user(payload: UserCreateRequest, request: Request):
    require_admin(request)
    if not payload.display_name.strip() or not payload.username.strip():
        raise HTTPException(status_code=400, detail="Tên hiển thị và tên đăng nhập không được để trống.")
    error = auth_db.validate_password(payload.password)
    if error:
        raise HTTPException(status_code=400, detail=error)
    try:
        return auth_db.create_user(
            payload.display_name, payload.username, payload.password,
            payload.role, payload.specialty or "", payload.email or "",
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Tên đăng nhập này đã được sử dụng.")


@app.put("/api/users/{user_id}")
def update_user(user_id: str, payload: UserUpdateRequest, request: Request):
    admin = require_admin(request)
    target = auth_db.get_user(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")

    # Phòng khám phải luôn còn ít nhất một quản trị viên đang hoạt động.
    losing_admin = target["role"] == "admin" and (
        (payload.role is not None and payload.role != "admin") or payload.is_disabled
    )
    if losing_admin and auth_db.count_active_admins(exclude_id=user_id) == 0:
        raise HTTPException(status_code=400, detail="Phải còn ít nhất một quản trị phòng khám đang hoạt động.")
    if payload.is_disabled and user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Không thể tự khóa tài khoản của chính mình.")

    try:
        updated = auth_db.update_user(user_id, payload.dict(exclude_unset=True))
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Tên đăng nhập này đã được sử dụng.")
    if not updated:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")
    return updated


@app.post("/api/users/{user_id}/reset-password")
def reset_user_password(user_id: str, payload: ResetPasswordRequest, request: Request):
    require_admin(request)
    error = auth_db.validate_password(payload.new_password)
    if error:
        raise HTTPException(status_code=400, detail=error)
    if not auth_db.set_password(user_id, payload.new_password, must_change=payload.must_change):
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")
    return {"ok": True}


@app.delete("/api/users/{user_id}")
def delete_user(user_id: str, request: Request):
    admin = require_admin(request)
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Không thể xóa tài khoản của chính mình.")
    target = auth_db.get_user(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")
    if target["role"] == "admin" and auth_db.count_active_admins(exclude_id=user_id) == 0:
        raise HTTPException(status_code=400, detail="Phải còn ít nhất một quản trị phòng khám đang hoạt động.")
    if not auth_db.delete_user(user_id):
        raise HTTPException(status_code=400, detail="Không thể xóa tài khoản cuối cùng trong hệ thống.")
    return {"ok": True}


# --- Thông tin cơ sở khám chữa bệnh (in trên đầu giấy tờ xuất PDF) ---

class ClinicInfoRequest(BaseModel):
    name: Optional[str] = None
    parent_org: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    department: Optional[str] = None


@app.get("/api/clinic")
def get_clinic(request: Request):
    current_user(request)
    return pdf_export.get_clinic_info()


@app.put("/api/clinic")
def update_clinic(payload: ClinicInfoRequest, request: Request):
    require_admin(request)
    return pdf_export.save_clinic_info(payload.dict(exclude_unset=True))


@app.get("/api/config")
def get_config_status():
    return {
        "has_api_key": bool(config.DEEPSEEK_API_KEY)
    }

# --- Patient records (hồ sơ bệnh nhân) — backed by SQLite (backend/data/patients.db) ---

PATIENT_ATTACHMENTS_DIR = os.path.join(config.DATA_DIR, "patient_attachments")
os.makedirs(PATIENT_ATTACHMENTS_DIR, exist_ok=True)

class PatientCreateModel(BaseModel):
    name: str
    dob: Optional[str] = None
    gender: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    occupation: Optional[str] = None
    blood_type: Optional[str] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    allergies: Optional[str] = None
    chronic_conditions: Optional[str] = None
    surgical_history: Optional[str] = None
    family_history: Optional[str] = None
    notes: Optional[str] = None
    created_by: Optional[str] = None
    owner_doctor_id: Optional[str] = None

class PatientOwnerModel(BaseModel):
    owner_doctor_id: Optional[str] = None

class QuickNoteModel(BaseModel):
    note: str
    updated_by: Optional[str] = None

class VisitCreateModel(BaseModel):
    visit_date: Optional[str] = None
    title: Optional[str] = None
    symptoms: Optional[str] = None
    diagnosis_primary: Optional[str] = None
    diagnosis_secondary: Optional[str] = None
    diagnosis_confidence: Optional[int] = None
    diagnosis_note: Optional[str] = None
    differential_diagnoses: Optional[List[Dict[str, Any]]] = None
    exam_findings: Optional[str] = None
    treatment: Optional[str] = None
    subclinical_orders: Optional[str] = None
    doctor_name: Optional[str] = None
    doctor_notes: Optional[str] = None
    medications: Optional[List[Dict[str, Any]]] = None
    goals: Optional[List[str]] = None
    protocol_duration: Optional[str] = None
    treatment_method: Optional[str] = None
    diet_regimen: Optional[str] = None
    precautions: Optional[str] = None
    no_drug_recommendations: Optional[str] = None
    care_instructions: Optional[str] = None
    followup_date: Optional[str] = None
    followup_purpose: Optional[str] = None
    status: Optional[str] = None

class VisitUpdateModel(BaseModel):
    visit_date: Optional[str] = None
    title: Optional[str] = None
    symptoms: Optional[str] = None
    diagnosis_primary: Optional[str] = None
    diagnosis_secondary: Optional[str] = None
    diagnosis_confidence: Optional[int] = None
    diagnosis_note: Optional[str] = None
    differential_diagnoses: Optional[List[Dict[str, Any]]] = None
    exam_findings: Optional[str] = None
    treatment: Optional[str] = None
    subclinical_orders: Optional[str] = None
    doctor_name: Optional[str] = None
    doctor_notes: Optional[str] = None
    medications: Optional[List[Dict[str, Any]]] = None
    goals: Optional[List[str]] = None
    protocol_duration: Optional[str] = None
    treatment_method: Optional[str] = None
    diet_regimen: Optional[str] = None
    precautions: Optional[str] = None
    no_drug_recommendations: Optional[str] = None
    care_instructions: Optional[str] = None
    followup_date: Optional[str] = None
    followup_purpose: Optional[str] = None
    status: Optional[str] = None

class NoteCreateModel(BaseModel):
    visit_date: Optional[str] = None
    doctor_name: Optional[str] = None
    title: Optional[str] = None
    reason_for_visit: Optional[str] = None
    vital_pulse: Optional[str] = None
    vital_blood_pressure: Optional[str] = None
    vital_resp_rate: Optional[str] = None
    vital_temperature: Optional[str] = None
    general_exam: Optional[str] = None
    cardio_exam: Optional[str] = None
    resp_exam: Optional[str] = None
    abdomen_exam: Optional[str] = None
    other_exam: Optional[str] = None
    ent_ear: Optional[str] = None
    ent_nose: Optional[str] = None
    ent_throat: Optional[str] = None
    ent_other: Optional[str] = None
    ent_scope_nose: Optional[str] = None
    ent_scope_ear: Optional[str] = None
    ent_scope_throat: Optional[str] = None
    status: Optional[str] = None

class NoteUpdateModel(BaseModel):
    visit_date: Optional[str] = None
    doctor_name: Optional[str] = None
    title: Optional[str] = None
    reason_for_visit: Optional[str] = None
    vital_pulse: Optional[str] = None
    vital_blood_pressure: Optional[str] = None
    vital_resp_rate: Optional[str] = None
    vital_temperature: Optional[str] = None
    general_exam: Optional[str] = None
    cardio_exam: Optional[str] = None
    resp_exam: Optional[str] = None
    abdomen_exam: Optional[str] = None
    other_exam: Optional[str] = None
    ent_ear: Optional[str] = None
    ent_nose: Optional[str] = None
    ent_throat: Optional[str] = None
    ent_other: Optional[str] = None
    ent_scope_nose: Optional[str] = None
    ent_scope_ear: Optional[str] = None
    ent_scope_throat: Optional[str] = None
    status: Optional[str] = None

class VitalCreateModel(BaseModel):
    vital_type: str
    value: str

class AiDiagnosisRequest(BaseModel):
    symptoms: str

# --- Hồ sơ bác sĩ (doctor profiles) ---

class ProfileCreateModel(BaseModel):
    display_name: str
    username: str
    specialty: Optional[str] = ""
    email: Optional[str] = ""

class ProfileUpdateModel(BaseModel):
    display_name: Optional[str] = None
    username: Optional[str] = None
    specialty: Optional[str] = None
    email: Optional[str] = None

AVATAR_EXTENSIONS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                     ".webp": "image/webp", ".gif": "image/gif"}
MAX_AVATAR_BYTES = 5 * 1024 * 1024

def ensure_own_profile(profile_id: str, request: Request) -> Dict[str, Any]:
    """Chỉ chính chủ (hoặc quản trị) mới sửa được hồ sơ bác sĩ."""
    user = current_user(request)
    if user["id"] != profile_id and not auth_db.is_admin(user):
        raise HTTPException(status_code=403, detail="Bạn chỉ chỉnh sửa được hồ sơ của chính mình.")
    return user


@app.get("/api/profiles")
def get_profiles(request: Request):
    current_user(request)
    return profile_db.list_profiles()

@app.get("/api/profiles/active")
def get_active_profile(request: Request):
    # Hồ sơ "đang hoạt động" giờ chính là tài khoản đang đăng nhập.
    user = current_user(request)
    profile = profile_db.get_profile(user["id"]) or profile_db.get_active_profile()
    if not profile:
        raise HTTPException(status_code=404, detail="Chưa có hồ sơ bác sĩ nào.")
    return profile

@app.post("/api/profiles")
def create_profile(payload: ProfileCreateModel, request: Request):
    """Giữ lại cho tương thích, nhưng chuyển thẳng sang luồng tạo tài khoản có mật khẩu:
    một hồ sơ không mật khẩu sẽ không đăng nhập được vào đâu cả."""
    require_admin(request)
    raise HTTPException(
        status_code=400,
        detail="Hãy tạo tài khoản kèm mật khẩu trong mục Quản trị phòng khám.",
    )

@app.put("/api/profiles/{profile_id}")
def update_profile(profile_id: str, payload: ProfileUpdateModel, request: Request):
    ensure_own_profile(profile_id, request)
    fields = payload.dict(exclude_none=True)
    for key in ("display_name", "username"):
        if key in fields:
            fields[key] = fields[key].strip()
            if not fields[key]:
                raise HTTPException(status_code=400, detail="Tên hiển thị và tên đăng nhập không được để trống.")
    try:
        profile = profile_db.update_profile(profile_id, fields)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Tên đăng nhập này đã được sử dụng.")
    if not profile:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ bác sĩ.")
    return profile

@app.post("/api/profiles/{profile_id}/activate")
def activate_profile(profile_id: str, request: Request):
    """Đổi người dùng giờ phải qua đăng nhập — nếu không, quy tắc "bác sĩ chỉ xem
    bệnh nhân của mình" bỏ qua được chỉ bằng một cú bấm."""
    user = current_user(request)
    if user["id"] != profile_id:
        raise HTTPException(
            status_code=403,
            detail="Hãy đăng xuất rồi đăng nhập bằng tài khoản đó để chuyển người dùng.",
        )
    profile = profile_db.set_active(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ bác sĩ.")
    return profile

@app.delete("/api/profiles/{profile_id}")
def delete_profile(profile_id: str, request: Request):
    require_admin(request)
    if not auth_db.delete_user(profile_id):
        raise HTTPException(status_code=400, detail="Không thể xóa hồ sơ bác sĩ cuối cùng.")
    return {"status": "success"}

@app.post("/api/profiles/{profile_id}/avatar")
async def upload_profile_avatar(profile_id: str, request: Request, file: UploadFile = File(...)):
    ensure_own_profile(profile_id, request)
    if not profile_db.get_profile(profile_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ bác sĩ.")

    ext = os.path.splitext(get_safe_filename(file.filename or ""))[1].lower()
    if ext not in AVATAR_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Ảnh đại diện phải là tệp PNG, JPG, WEBP hoặc GIF.",
        )

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Tệp ảnh rỗng.")
    if len(contents) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="Ảnh đại diện không được vượt quá 5 MB.")

    stored_name = f"{uuid.uuid4()}{ext}"
    try:
        with open(os.path.join(profile_db.AVATAR_DIR, stored_name), "wb") as buffer:
            buffer.write(contents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Không thể lưu ảnh: {str(e)}")

    return profile_db.set_avatar(profile_id, stored_name)

@app.get("/api/profiles/{profile_id}/avatar")
def get_profile_avatar(profile_id: str, request: Request):
    current_user(request)
    path = profile_db.avatar_path(profile_id)
    if not path:
        raise HTTPException(status_code=404, detail="Hồ sơ này chưa có ảnh đại diện.")
    media_type = AVATAR_EXTENSIONS.get(os.path.splitext(path)[1].lower(), "image/png")
    return FileResponse(path, media_type=media_type)

@app.delete("/api/profiles/{profile_id}/avatar")
def delete_profile_avatar(profile_id: str, request: Request):
    ensure_own_profile(profile_id, request)
    profile = profile_db.set_avatar(profile_id, None)
    if not profile:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ bác sĩ.")
    return profile

@app.get("/api/patients/next-code")
def get_next_patient_code(request: Request):
    current_user(request)
    return {"code": patient_db.preview_next_code()}

@app.get("/api/patients")
def get_patients(request: Request, search: Optional[str] = Query(None),
                 scope: Optional[str] = Query(None)):
    """Bác sĩ thấy bệnh nhân mình phụ trách; quản trị/điều dưỡng thấy cả phòng khám.

    Quản trị có thể truyền scope=mine để tạm thu hẹp về danh sách của riêng mình.
    """
    user = current_user(request)
    owner_id = user["id"] if scope == "mine" else scope_owner_id(user)
    return patient_db.list_patients(search, owner_id=owner_id)

@app.get("/api/notifications")
def get_notifications(request: Request, days_ahead: int = Query(7, ge=0, le=365)):
    user = current_user(request)
    return reminder_db.get_notifications(owner_id=scope_owner_id(user), days_ahead=days_ahead)

@app.post("/api/patients")
def add_patient(patient: PatientCreateModel, request: Request):
    user = require_write(request)
    if not patient.name.strip():
        raise HTTPException(status_code=400, detail="Họ và tên bệnh nhân không được để trống.")
    data = patient.dict()
    # Người tạo mặc định là bác sĩ phụ trách, trừ khi quản trị chỉ định người khác.
    if not (auth_db.is_admin(user) and data.get("owner_doctor_id")):
        data["owner_doctor_id"] = user["id"]
    return patient_db.create_patient(data)

@app.get("/api/patients/{patient_id}")
def get_patient_detail(patient_id: str, request: Request):
    user = current_user(request)
    ensure_patient_access(patient_id, user)
    patient = patient_db.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ bệnh nhân.")
    owner = patient.get("owner_doctor_id")
    owner_user = auth_db.get_user(owner) if owner else None
    patient["owner_name"] = owner_user["display_name"] if owner_user else None
    patient["can_edit"] = not auth_db.is_read_only(user)
    return patient

@app.patch("/api/patients/{patient_id}/owner")
def reassign_patient(patient_id: str, body: PatientOwnerModel, request: Request):
    """Bàn giao bệnh nhân sang bác sĩ khác. Quản trị bàn giao được mọi hồ sơ; bác
    sĩ chỉ chuyển đi hồ sơ đang do mình phụ trách."""
    user = require_write(request)
    ensure_patient_access(patient_id, user, write=True)
    if body.owner_doctor_id:
        target = auth_db.get_user(body.owner_doctor_id)
        if not target or target["is_disabled"]:
            raise HTTPException(status_code=400, detail="Không tìm thấy bác sĩ tiếp nhận.")
        if target["role"] == "assistant":
            raise HTTPException(status_code=400, detail="Không thể giao hồ sơ cho tài khoản chỉ có quyền xem.")
    elif not auth_db.is_admin(user):
        raise HTTPException(status_code=403, detail="Chỉ quản trị phòng khám mới bỏ gán bác sĩ phụ trách được.")
    updated = patient_db.set_patient_owner(patient_id, body.owner_doctor_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ bệnh nhân.")
    return updated

@app.delete("/api/patients/{patient_id}")
def delete_patient(patient_id: str, request: Request):
    user = current_user(request)
    ensure_patient_access(patient_id, user, write=True)
    if not patient_db.delete_patient(patient_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ bệnh nhân.")
    return {"status": "success"}

@app.patch("/api/patients/{patient_id}/note")
def update_patient_note(patient_id: str, body: QuickNoteModel, request: Request):
    user = current_user(request)
    ensure_patient_access(patient_id, user, write=True)
    patient = patient_db.update_quick_note(patient_id, body.note, body.updated_by or user["display_name"])
    if not patient:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ bệnh nhân.")
    return patient

@app.post("/api/patients/{patient_id}/visits")
def add_patient_visit(patient_id: str, body: VisitCreateModel, request: Request):
    user = current_user(request)
    ensure_patient_access(patient_id, user, write=True)
    return patient_db.add_visit(patient_id, body.dict())

@app.patch("/api/patients/{patient_id}/visits/{visit_id}")
def update_patient_visit(patient_id: str, visit_id: str, body: VisitUpdateModel, request: Request):
    user = current_user(request)
    ensure_patient_access(patient_id, user, write=True)
    updated = patient_db.update_visit(patient_id, visit_id, body.dict(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Không tìm thấy kế hoạch điều trị.")
    return updated

@app.delete("/api/patients/{patient_id}/visits/{visit_id}")
def delete_patient_visit(patient_id: str, visit_id: str, request: Request):
    user = current_user(request)
    ensure_patient_access(patient_id, user, write=True)
    if not patient_db.delete_visit(patient_id, visit_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy lần khám.")
    return {"success": True}

@app.post("/api/patients/{patient_id}/notes")
def add_clinical_note(patient_id: str, body: NoteCreateModel, request: Request):
    user = current_user(request)
    ensure_patient_access(patient_id, user, write=True)
    return patient_db.add_note(patient_id, body.dict(exclude_unset=True))

@app.patch("/api/patients/{patient_id}/notes/{note_id}")
def update_clinical_note(patient_id: str, note_id: str, body: NoteUpdateModel, request: Request):
    user = current_user(request)
    ensure_patient_access(patient_id, user, write=True)
    updated = patient_db.update_note(patient_id, note_id, body.dict(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Không tìm thấy ghi chú.")
    return updated

@app.delete("/api/patients/{patient_id}/notes/{note_id}")
def delete_clinical_note(patient_id: str, note_id: str, request: Request):
    user = current_user(request)
    ensure_patient_access(patient_id, user, write=True)
    if not patient_db.delete_note(patient_id, note_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy ghi chú.")
    return {"success": True}

@app.post("/api/patients/{patient_id}/visits/{visit_id}/ai-diagnosis")
def ai_suggest_diagnosis(patient_id: str, visit_id: str, body: AiDiagnosisRequest, request: Request, x_deepseek_key: Optional[str] = Header(None)):
    user = current_user(request)
    ensure_patient_access(patient_id, user, write=True)
    if not patient_db.get_visit(patient_id, visit_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy kế hoạch điều trị.")
    symptoms = body.symptoms.strip()
    if not symptoms:
        raise HTTPException(status_code=400, detail="Cần có triệu chứng để AI gợi ý chẩn đoán.")
    try:
        suggestion = agent.run_diagnostic_agent(patient_id, symptoms, search_drug_book, x_deepseek_key or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi gợi ý chẩn đoán: {str(e)}")

    updated = patient_db.update_visit(patient_id, visit_id, {
        "diagnosis_primary": suggestion["diagnosis_primary"],
        "diagnosis_secondary": "\n".join(suggestion["diagnosis_differentials"]),
    })
    updated["ai_reasoning"] = suggestion["reasoning"]
    updated["ai_agent_trace"] = suggestion.get("agent_trace", [])
    updated["ai_agent_sources"] = suggestion.get("agent_sources", [])
    return updated

@app.post("/api/patients/{patient_id}/vitals")
def add_patient_vital(patient_id: str, body: VitalCreateModel, request: Request):
    user = current_user(request)
    ensure_patient_access(patient_id, user, write=True)
    return patient_db.add_vital(patient_id, body.vital_type, body.value)

@app.post("/api/patients/{patient_id}/attachments")
async def upload_patient_attachment(patient_id: str, request: Request, file: UploadFile = File(...)):
    user = current_user(request)
    ensure_patient_access(patient_id, user, write=True)

    original_name = get_safe_filename(file.filename)
    ext = os.path.splitext(original_name)[1]
    stored_name = f"{uuid.uuid4()}{ext}"
    patient_dir = os.path.join(PATIENT_ATTACHMENTS_DIR, patient_id)
    os.makedirs(patient_dir, exist_ok=True)
    save_path = os.path.join(patient_dir, stored_name)

    try:
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Không thể lưu tệp: {str(e)}")

    size_bytes = os.path.getsize(save_path)
    file_type = (ext.lstrip(".").upper() or "FILE")
    return patient_db.add_attachment(patient_id, stored_name, original_name, file_type, size_bytes)

@app.get("/api/patients/{patient_id}/attachments/{attachment_id}/download")
def download_patient_attachment(patient_id: str, attachment_id: str, request: Request):
    user = current_user(request)
    ensure_patient_access(patient_id, user)
    attachment = patient_db.get_attachment(attachment_id)
    if not attachment or attachment["patient_id"] != patient_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp đính kèm.")
    file_path = os.path.join(PATIENT_ATTACHMENTS_DIR, patient_id, attachment["filename"])
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Tệp không tồn tại trên máy chủ.")
    return FileResponse(file_path, filename=attachment["original_name"])

@app.delete("/api/patients/{patient_id}/attachments/{attachment_id}")
def delete_patient_attachment(patient_id: str, attachment_id: str, request: Request):
    user = current_user(request)
    ensure_patient_access(patient_id, user, write=True)
    # Kiểm tra tệp thuộc đúng bệnh nhân *trước khi* xóa, nếu không một id lạ sẽ
    # xóa mất tệp của hồ sơ khác rồi mới báo 404.
    attachment = patient_db.get_attachment(attachment_id)
    if not attachment or attachment["patient_id"] != patient_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp đính kèm.")
    patient_db.delete_attachment(attachment_id)
    file_path = os.path.join(PATIENT_ATTACHMENTS_DIR, patient_id, attachment["filename"])
    if os.path.exists(file_path):
        os.remove(file_path)
    return {"status": "success"}


# =============================================================================
# NHẮC LỊCH TÁI KHÁM / THEO DÕI BỆNH NHÂN MÃN TÍNH (reminder engine)
# =============================================================================

class ReminderCreateModel(BaseModel):
    patient_id: str
    kind: str = "followup"
    title: Optional[str] = None
    note: Optional[str] = None
    due_date: Optional[str] = None
    repeat_interval_days: Optional[int] = None
    visit_id: Optional[str] = None


class ReminderUpdateModel(BaseModel):
    kind: Optional[str] = None
    title: Optional[str] = None
    note: Optional[str] = None
    due_date: Optional[str] = None
    repeat_interval_days: Optional[int] = None


class SnoozeModel(BaseModel):
    days: int = 1


def _guard_reminder(reminder_id: str, request: Request, write: bool = False):
    """Trả về (lời nhắc, tài khoản) sau khi đã kiểm tra quyền trên bệnh nhân."""
    user = current_user(request)
    reminder = reminder_db.get_reminder(reminder_id)
    if not reminder:
        raise HTTPException(status_code=404, detail="Không tìm thấy lời nhắc.")
    ensure_patient_access(reminder["patient_id"], user, write=write)
    return reminder, user


@app.get("/api/reminders")
def list_reminders(request: Request,
                   status: str = Query("pending"),
                   patient_id: Optional[str] = Query(None),
                   kind: Optional[str] = Query(None),
                   days_ahead: Optional[int] = Query(None, ge=0, le=3650),
                   scope: Optional[str] = Query(None)):
    user = current_user(request)
    if patient_id:
        ensure_patient_access(patient_id, user)
    owner_id = user["id"] if scope == "mine" else scope_owner_id(user)
    return reminder_db.list_reminders(
        owner_id=owner_id, status=status, patient_id=patient_id,
        kind=kind, days_ahead=days_ahead,
    )


@app.get("/api/reminders/summary")
def reminders_summary(request: Request, scope: Optional[str] = Query(None)):
    user = current_user(request)
    owner_id = user["id"] if scope == "mine" else scope_owner_id(user)
    summary = reminder_db.summarize(owner_id=owner_id)
    summary["kinds"] = [{"value": k, "label": v} for k, v in reminder_db.REMINDER_KINDS.items()]
    return summary


@app.post("/api/reminders")
def create_reminder(payload: ReminderCreateModel, request: Request):
    user = require_write(request)
    ensure_patient_access(payload.patient_id, user, write=True)
    data = payload.dict()
    data["created_by"] = user["display_name"]
    data["doctor_id"] = user["id"]
    return reminder_db.create_reminder(payload.patient_id, data)


@app.patch("/api/reminders/{reminder_id}")
def update_reminder(reminder_id: str, payload: ReminderUpdateModel, request: Request):
    _guard_reminder(reminder_id, request, write=True)
    updated = reminder_db.update_reminder(reminder_id, payload.dict(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Không tìm thấy lời nhắc.")
    return updated


@app.post("/api/reminders/{reminder_id}/complete")
def complete_reminder(reminder_id: str, request: Request):
    _guard_reminder(reminder_id, request, write=True)
    return reminder_db.complete_reminder(reminder_id)


@app.post("/api/reminders/{reminder_id}/snooze")
def snooze_reminder(reminder_id: str, payload: SnoozeModel, request: Request):
    _guard_reminder(reminder_id, request, write=True)
    return reminder_db.snooze_reminder(reminder_id, payload.days)


@app.post("/api/reminders/{reminder_id}/dismiss")
def dismiss_reminder(reminder_id: str, request: Request):
    _guard_reminder(reminder_id, request, write=True)
    return reminder_db.dismiss_reminder(reminder_id)


@app.post("/api/reminders/{reminder_id}/reopen")
def reopen_reminder(reminder_id: str, request: Request):
    _guard_reminder(reminder_id, request, write=True)
    return reminder_db.reopen_reminder(reminder_id)


@app.delete("/api/reminders/{reminder_id}")
def delete_reminder(reminder_id: str, request: Request):
    _guard_reminder(reminder_id, request, write=True)
    reminder_db.delete_reminder(reminder_id)
    return {"status": "success"}


# =============================================================================
# THỐNG KÊ / DASHBOARD
# =============================================================================

def _stats_scope(request: Request, scope: Optional[str]) -> Optional[str]:
    user = current_user(request)
    return user["id"] if scope == "mine" else scope_owner_id(user)


@app.get("/api/stats/overview")
def stats_overview(request: Request, date_from: Optional[str] = Query(None),
                   date_to: Optional[str] = Query(None), scope: Optional[str] = Query(None)):
    owner_id = _stats_scope(request, scope)
    data = stats_db.overview(owner_id, date_from, date_to)
    data["reminders"] = reminder_db.summarize(owner_id=owner_id)
    return data


@app.get("/api/stats/diagnoses")
def stats_diagnoses(request: Request, date_from: Optional[str] = Query(None),
                    date_to: Optional[str] = Query(None), scope: Optional[str] = Query(None),
                    limit: int = Query(12, ge=1, le=50)):
    return stats_db.top_diagnoses(_stats_scope(request, scope), date_from, date_to, limit)


@app.get("/api/stats/medications")
def stats_medications(request: Request, date_from: Optional[str] = Query(None),
                      date_to: Optional[str] = Query(None), scope: Optional[str] = Query(None),
                      limit: int = Query(15, ge=1, le=50)):
    return stats_db.top_medications(_stats_scope(request, scope), date_from, date_to, limit)


@app.get("/api/stats/trends")
def stats_trends(request: Request, date_from: Optional[str] = Query(None),
                 date_to: Optional[str] = Query(None), scope: Optional[str] = Query(None),
                 granularity: str = Query("auto")):
    return stats_db.trends(_stats_scope(request, scope), date_from, date_to, granularity)


@app.get("/api/stats/demographics")
def stats_demographics(request: Request, scope: Optional[str] = Query(None)):
    return stats_db.demographics(_stats_scope(request, scope))


@app.get("/api/stats/doctors")
def stats_by_doctor(request: Request, date_from: Optional[str] = Query(None),
                    date_to: Optional[str] = Query(None)):
    require_admin(request)
    return stats_db.by_doctor(date_from, date_to)


# =============================================================================
# XUẤT HỒ SƠ RA PDF
# =============================================================================

class ReferralModel(BaseModel):
    destination: Optional[str] = None
    destination_address: Optional[str] = None
    reason: Optional[str] = None
    condition_on_transfer: Optional[str] = None
    recommendation: Optional[str] = None
    transport: Optional[str] = None
    escort: Optional[str] = None
    insurance_number: Optional[str] = None
    doctor_name: Optional[str] = None
    diagnosis: Optional[str] = None
    clinical_signs: Optional[str] = None
    lab_results: Optional[str] = None
    treatment_given: Optional[str] = None
    visit_id: Optional[str] = None


def _pdf_response(content: bytes, filename: str) -> Response:
    """Trả PDF kèm tên tệp mã hóa RFC 5987 để dấu tiếng Việt không vỡ trên header."""
    from urllib.parse import quote
    ascii_name = filename.encode("ascii", "ignore").decode() or "ho-so.pdf"
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": disposition},
    )


def _slug(text: str) -> str:
    """Tên tệp không dấu, an toàn trên mọi hệ tệp."""
    import unicodedata
    normalized = unicodedata.normalize("NFD", str(text or ""))
    stripped = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    stripped = stripped.replace("đ", "d").replace("Đ", "D")
    return re.sub(r"[^A-Za-z0-9]+", "-", stripped).strip("-") or "ho-so"


@app.get("/api/patients/{patient_id}/export/pdf")
def export_patient_pdf(patient_id: str, request: Request,
                       doc_type: str = Query("full", pattern="^(full|visit)$"),
                       visit_id: Optional[str] = Query(None)):
    """Bệnh án tổng hợp (doc_type=full) hoặc phiếu khám một lần khám (doc_type=visit)."""
    user = current_user(request)
    ensure_patient_access(patient_id, user)
    patient = patient_db.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ bệnh nhân.")

    if doc_type == "visit":
        visit = patient_db.get_visit(patient_id, visit_id) if visit_id else None
        if not visit:
            # Không chỉ định lần khám thì in lần gần nhất — thao tác một cú bấm.
            visits = patient.get("visits") or []
            if not visits:
                raise HTTPException(status_code=400, detail="Bệnh nhân chưa có lần khám nào để xuất phiếu.")
            visit = visits[0]
        content = pdf_export.build_visit_record(patient, visit, user["display_name"])
        filename = f"phieu-kham-{_slug(patient['name'])}-{visit.get('visit_date', '')[:10]}.pdf"
    else:
        reminders = reminder_db.list_reminders(patient_id=patient_id, status="pending", sync=True)
        content = pdf_export.build_full_record(patient, reminders, user["display_name"])
        filename = f"benh-an-{patient['code']}-{_slug(patient['name'])}.pdf"

    return _pdf_response(content, filename)


@app.post("/api/patients/{patient_id}/export/referral")
def export_patient_referral(patient_id: str, payload: ReferralModel, request: Request):
    """Giấy chuyển tuyến khám bệnh, chữa bệnh."""
    user = current_user(request)
    ensure_patient_access(patient_id, user)
    patient = patient_db.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ bệnh nhân.")

    visit = None
    if payload.visit_id:
        visit = patient_db.get_visit(patient_id, payload.visit_id)
    if visit is None:
        visits = patient.get("visits") or []
        visit = visits[0] if visits else None

    referral = payload.dict()
    referral.setdefault("doctor_name", None)
    if not referral.get("doctor_name"):
        referral["doctor_name"] = user["display_name"]

    content = pdf_export.build_referral(patient, visit, referral, user["display_name"])
    return _pdf_response(content, f"giay-chuyen-tuyen-{patient['code']}-{_slug(patient['name'])}.pdf")


def get_safe_filename(filename: str) -> str:
    """Sanitizes filename to prevent directory traversal."""
    return os.path.basename(filename).replace("..", "")

@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    safe_name = get_safe_filename(file.filename)
    save_path = os.path.join(config.UPLOAD_DIR, safe_name)

    # Save PDF locally
    try:
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {str(e)}")

    try:
        # 1. Process document through Parent-Child & Summary Indexer
        processed_docs = process_pdf_parent_child_summary(save_path)
        if not processed_docs:
            if os.path.exists(save_path):
                os.remove(save_path)
            raise HTTPException(status_code=400, detail="No readable text found in the PDF.")

        # 2. Cache full page text on disk for reader lookup
        loader = SimpleLoader()
        raw_pages = loader.load_pdf(save_path)
        
        cache_file = os.path.join(PAGES_CACHE_DIR, f"{safe_name}.json")
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({str(p.metadata.get("page", 0) + 1): p.page_content for p in raw_pages}, f, ensure_ascii=False, indent=2)

        # 3. Add chunks to vector index
        db.add_chunks(processed_docs)

        return {
            "status": "success",
            "filename": safe_name,
            "pages": len(raw_pages),
            "chunks": len(processed_docs)
        }

    except Exception as e:
        # Cleanup file if indexing failed
        if os.path.exists(save_path):
            os.remove(save_path)
        raise HTTPException(status_code=500, detail=f"Error indexing document: {str(e)}")

@app.get("/api/documents")
def list_documents():
    try:
        docs = db.list_documents()
        # Enrich with the upload file's mtime (proxy for "uploaded_at") for library sorting —
        # read from disk rather than the vector store so existing indexes don't need migration.
        for doc in docs:
            path = documents.upload_path(doc["doc_name"])
            doc["uploaded_at"] = os.path.getmtime(path) if os.path.exists(path) else None
        return docs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/documents/{doc_name}/download-ticket")
def create_download_ticket(doc_name: str, request: Request):
    """Vé ngắn hạn để trình duyệt tự stream PDF xuống đĩa. Xem DOWNLOAD_TICKET_TTL_SECONDS."""
    current_user(request)
    safe_name = get_safe_filename(doc_name)
    if not os.path.exists(documents.upload_path(safe_name)):
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp tài liệu.")
    return {"ticket": _issue_download_ticket(safe_name, request.state.token),
            "expires_in": int(DOWNLOAD_TICKET_TTL_SECONDS)}


@app.get("/api/documents/{doc_name}/download")
def download_document(doc_name: str, request: Request, ticket: Optional[str] = None):
    safe_name = get_safe_filename(doc_name)
    # Đăng nhập bằng header thì không cần vé; chỉ <a download> mới phải dùng vé.
    if getattr(request.state, "user", None) is None and not _redeem_download_ticket(ticket, safe_name):
        raise HTTPException(status_code=401, detail="Vé tải tệp không hợp lệ hoặc đã hết hạn.")
    # doc_name giờ là ID ổn định ("DTQGVN-2022-Q1"), không nhất thiết trùng tên
    # file trên đĩa — manifest giữ ánh xạ qua trường source_pdf.
    pdf_path = documents.upload_path(safe_name)
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp tài liệu.")
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=os.path.basename(pdf_path),
    )

@app.delete("/api/documents/{doc_name}")
def delete_document(doc_name: str):
    safe_name = get_safe_filename(doc_name)

    # Delete from vector store
    try:
        db.delete_document(safe_name)
    except Exception as e:
        print(f"Error removing from vector index: {e}")

    # Delete local files. documents.upload_path() đọc source_pdf từ manifest nên
    # phải gọi TRƯỚC khi xoá manifest, nếu không sẽ trỏ nhầm đường dẫn.
    pdf_path = documents.upload_path(safe_name)
    for path in (
        pdf_path,
        documents.pages_cache_path(safe_name),
        documents.page_map_path(safe_name),
        documents.manifest_path(safe_name),
    ):
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                print(f"Error removing {path}: {e}")

    # Text OCR và ảnh trang đã render là thư mục — xoá đệ quy
    for folder in (documents.ocr_dir(safe_name), documents.page_images_dir(safe_name)):
        if os.path.isdir(folder):
            try:
                shutil.rmtree(folder)
            except Exception as e:
                print(f"Error removing {folder}: {e}")

    # Drop the doctor's highlights / personal notes attached to this document
    try:
        library_db.delete_highlights_for_document(safe_name)
    except Exception as e:
        print(f"Error removing highlights for document: {e}")

    return {"status": "success", "message": f"Document '{safe_name}' deleted."}

# =============================================================================
# Tra cứu y văn có trả lời của mô hình — luồng SSE, có trần thời gian, hủy được
# =============================================================================

# Các trần dưới đây đặt theo số đo thật, không phải đoán. Chạy lại bằng
# `python eval/timing_run.py --stream --repeat 2` sau mỗi lần đổi model hoặc
# đổi nhà cung cấp. Đo ngày 13/09/2026, máy còn 2,1 GB RAM trống:
#
#     tìm lần đầu (nạp model + BM25)   21,7s
#     tìm sau khi đã nạp               trung vị 65ms, chậm nhất 172ms
#     chữ đầu tiên của mô hình         trung vị 886ms, chậm nhất 1,63s
#     mô hình sinh xong                trung vị 3,06s, chậm nhất 3,68s
#
# Kế hoạch ban đầu chốt 10s cho khâu tìm. Số đo cho thấy con số đó SAI theo cả
# hai chiều: quá lỏng cho lần tìm bình thường (150 lần trung vị, nên nó chỉ nổ
# khi hệ thống đã hỏng hẳn), và quá chặt cho lần tra ĐẦU TIÊN sau khi mở app,
# vì lần đó phải nạp model mất 21,7s — một trần 10s sẽ giết đúng lần tra đầu
# ngày của bác sĩ. Nên tách làm hai trần riêng.
SEARCH_WARM_TIMEOUT_S = 5.0    # tìm khi model đã nạp: 29 lần lần chậm nhất đo được
SEARCH_COLD_TIMEOUT_S = 60.0   # tìm khi còn phải nạp model: 2,8 lần số đo được
SEARCH_TOKEN_GAP_TIMEOUT_S = 15.0  # im lặng giữa hai mẩu chữ: 9 lần chữ-đầu chậm nhất
SEARCH_TOTAL_TIMEOUT_S = 60.0  # trần cứng cả lần tra: 16 lần lần chậm nhất đo được


def _sse(event: str, payload: Any) -> str:
    """Đóng gói một sự kiện Server-Sent Events."""
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


# Chat Tab Search & Answer endpoint (uses LLM)
@app.post("/api/search")
async def search_and_answer(
    request: QueryRequest,
    x_deepseek_key: Optional[str] = Header(None),
):
    """Tra cứu y văn kèm câu trả lời của mô hình, trả về theo luồng SSE.

    Trước đây endpoint này là một hàm đồng bộ chặn từ đầu đến cuối: tìm xong
    mới gọi mô hình, mô hình sinh xong mới trả về một cục. Ba hệ quả đo được:

    1. Khâu tìm KHÔNG có trần thời gian nào. (Khâu gọi mô hình thì có —
       `llm_client.LLM_TIMEOUT` đặt read=120s — nhưng kèm `max_retries=1`, nên
       xấu nhất là ~4 phút vòng xoay, và lần thử lại thứ hai không báo cho ai.)
    2. Không hủy được. Bác sĩ gõ sai câu hỏi thì chỉ còn cách chờ hết.
    3. Không chảy dần, dù chữ đầu tiên của mô hình về sau 886ms còn cả câu mất
       hơn 3s. Tức là hơn hai giây nhìn vòng xoay trong khi chữ đã có sẵn.

    Nay: nguồn trích dẫn đẩy đi ngay khi tìm xong, chữ chảy dần về sau, mọi khâu
    có trần riêng, và bác sĩ đóng kết nối là công việc dừng thật.

    Các sự kiện của luồng:

    - ``sources``  — danh sách trích dẫn, gửi ngay khi tìm xong
    - ``delta``    — một mẩu chữ mới của câu trả lời
    - ``error``    — hỏng; ``degraded`` = true nghĩa là trích dẫn vẫn dùng được
    - ``done``     — xong, kèm số đo từng khâu
    """
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    api_key = x_deepseek_key or ""

    async def event_stream():
        timer = StageTimer("search")
        outcome = "ok"
        answer_parts: List[str] = []
        formatted_sources: List[SearchResultItem] = []
        started = time.perf_counter()

        try:
            # ---------- 1. Khâu tìm ----------
            #
            # Trần phụ thuộc việc model đã nạp chưa: lần đầu phải nạp mất 21,7s,
            # những lần sau chỉ 65ms. Dùng một trần chung thì hoặc giết lần đầu,
            # hoặc vô dụng cho các lần sau.
            warm = db.is_warm()
            budget = SEARCH_WARM_TIMEOUT_S if warm else SEARCH_COLD_TIMEOUT_S
            if not warm:
                yield _sse("status", {"phase": "loading_model",
                                      "message": "Đang nạp mô hình tra cứu y văn, lần tra đầu tiên chậm hơn…"})
            try:
                with timer.stage("retrieval"):
                    sources = await asyncio.wait_for(
                        asyncio.to_thread(lambda: enrich_sources(db.search(query, top_k=5))),
                        timeout=budget,
                    )
            except asyncio.TimeoutError:
                outcome = "retrieval_timeout"
                yield _error_event(
                    "Không tra được y văn trong giới hạn thời gian. Máy chủ tra cứu "
                    "đang quá tải hoặc chưa nạp xong. Thử lại sau một lát.",
                    degraded=False,
                    detail=f"retrieval vượt {budget:.0f}s (warm={warm})",
                )
                return

            formatted_sources = [to_search_result(s) for s in sources]
            yield _sse("sources", {"sources": [s.dict() for s in formatted_sources]})

            if not sources:
                outcome = "no_sources"
                yield _error_event(
                    "Không tìm thấy đoạn y văn nào khớp câu hỏi này. "
                    "Lưu ý Dược thư trong kho hiện chỉ có quyển 1, chữ A đến H.",
                    degraded=False,
                    detail="db.search trả về 0 kết quả",
                )
                return

            # ---------- 2. Khâu mô hình, chảy dần ----------
            #
            # Bọc generator đồng bộ của llm_client: mỗi lần lấy một mẩu chữ đều
            # là một lần chờ có trần. Trần tính theo KHOẢNG IM LẶNG giữa hai mẩu,
            # không phải tổng: mô hình đang chảy chữ đều đặn thì không có lý do
            # cắt, còn tắt tiếng giữa câu 15s thì chắc chắn là treo.
            #
            # asyncio.wait_for hủy phần chờ nhưng KHÔNG giết được thread đang
            # nằm trong socket. Thread đó tự thoát khi httpx hết read timeout,
            # nên trần ở llm_client phải cùng cỡ với trần ở đây.
            pull = _sync_iter_puller(stream_answer(query, sources, api_key))
            with timer.stage("llm"):
                while True:
                    # KHÔNG gọi http_request.is_disconnected() ở đây. Đã thử và
                    # đo: nó làm hỏng đúng cái nó định làm. StreamingResponse của
                    # Starlette tự chạy một task đọc kênh `receive` để bắt
                    # "http.disconnect" rồi hủy generator này. Gọi
                    # is_disconnected() là tranh đọc cùng kênh đó, và thông điệp
                    # disconnect bị mình lấy mất nên task kia không bao giờ thấy.
                    # Kết quả đo được: khách đóng kết nối giữa luồng mà server vẫn
                    # chạy hết, vẫn gọi mô hình tới cùng, vẫn ghi lịch sử —
                    # outcome=ok thay vì cancelled. Đường hủy đúng là
                    # CancelledError bắt ở dưới.
                    elapsed = time.perf_counter() - started
                    if elapsed > SEARCH_TOTAL_TIMEOUT_S:
                        outcome = "total_timeout"
                        yield _error_event(
                            "Câu trả lời mất quá nhiều thời gian nên đã dừng. "
                            "Các trang sách tìm được vẫn ở bên dưới.",
                            degraded=True,
                            detail=f"tổng vượt {SEARCH_TOTAL_TIMEOUT_S:.0f}s",
                        )
                        break

                    try:
                        item = await asyncio.wait_for(
                            asyncio.to_thread(pull),
                            timeout=min(SEARCH_TOKEN_GAP_TIMEOUT_S,
                                        SEARCH_TOTAL_TIMEOUT_S - elapsed),
                        )
                    except asyncio.TimeoutError:
                        outcome = "llm_stall"
                        yield _error_event(
                            "Máy chủ AI tạm thời không hoạt động. Các trang sách "
                            "tìm được vẫn ở bên dưới, dùng được ngay.",
                            degraded=True,
                            detail=f"không có mẩu chữ nào trong {SEARCH_TOKEN_GAP_TIMEOUT_S:.0f}s",
                        )
                        break

                    if item is None:
                        break

                    kind, payload = item
                    if kind == "error":
                        outcome = "llm_error"
                        yield _error_event(
                            "Máy chủ AI tạm thời không hoạt động. Các trang sách "
                            "tìm được vẫn ở bên dưới, dùng được ngay.",
                            degraded=True,
                            detail=payload,
                        )
                        break

                    answer_parts.append(payload)
                    yield _sse("delta", {"text": payload})

            # ---------- 3. Ghi lịch sử ----------
            #
            # Chỉ ghi khi có câu trả lời thật. Bản cũ ghi cả những lần hỏng, vì
            # generate_answer biến ngoại lệ thành chuỗi "Error calling DeepSeek
            # API: …" rồi trả ra như một câu trả lời — nên lịch sử tra cứu có
            # những dòng trông như câu trả lời y khoa mà thật ra là thông báo lỗi,
            # và "câu hỏi tương tự" đem chúng ra dùng lại.
            answer = "".join(answer_parts)
            if answer.strip():
                with timer.stage("history"):
                    try:
                        await asyncio.to_thread(
                            library_db.add_history,
                            query=query,
                            answer=answer,
                            sources=[s.dict() for s in formatted_sources],
                            embedding=db.embed_text(query),
                            embedding_model=db.embedding_model,
                            created_by=request.created_by,
                        )
                    except Exception as e:
                        print(f"Warning: failed to log search history: {e}")

            yield _sse("done", {"timings": timer.timings(), "outcome": outcome})

        except asyncio.CancelledError:
            # Bác sĩ bấm nút hủy hoặc đóng tab. Không phải lỗi.
            outcome = "cancelled"
            raise
        except Exception as e:
            outcome = f"crash:{type(e).__name__}"
            print(f"Lỗi khi stream tra cứu y văn: {type(e).__name__}: {e}")
            yield _error_event(
                "Tra cứu thất bại. Thử lại sau một lát.",
                degraded=bool(formatted_sources),
                detail=f"{type(e).__name__}: {e}",
            )
        finally:
            # Trong finally để lần hỏng và lần bị hủy cũng để lại số đo — đó
            # chính là những lần cần biết khâu nào đã ngốn hết thời gian.
            timer.log(f"q={len(query)}c outcome={outcome}")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Tắt buffering của proxy, nếu không toàn bộ luồng bị gom lại và
            # bác sĩ vẫn phải chờ như cũ.
            "X-Accel-Buffering": "no",
        },
    )


def _error_event(message: str, degraded: bool, detail: str) -> str:
    """Sự kiện lỗi cho giao diện.

    `detail` chỉ đi kèm khi chạy chế độ phát triển. Bác sĩ luôn nhận `message` —
    một câu tiếng Việt nói rõ chuyện gì và còn dùng được gì. `degraded` cho giao
    diện biết trích dẫn vẫn ở đó, nên đừng xoá kết quả đi khi báo lỗi.
    """
    payload = {"message": message, "degraded": degraded}
    if config.DEV_MODE:
        payload["detail"] = detail
    return _sse("error", payload)


def _sync_iter_puller(generator):
    """Biến generator đồng bộ thành một hàm lấy-một-mẩu, hết thì trả None.

    Cần vì `asyncio.to_thread` nhận một hàm để gọi, còn `next()` trên một
    generator thì ném StopIteration — mà StopIteration bay qua ranh giới
    thread/coroutine sẽ thành RuntimeError khó đọc thay vì "hết dữ liệu".
    """
    it = iter(generator)

    def pull():
        try:
            return next(it)
        except StopIteration:
            return None

    return pull

# Literature Search Tab endpoint (local retrieval only, NO LLM)
@app.post("/api/literature-search", response_model=QueryResponse)
def literature_search(request: QueryRequest):
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    timer = StageTimer("literature-search")
    try:
        # Retrieve matching document contexts using hybrid search (dense + BM25 + RRF)
        with timer.stage("retrieval"):
            sources = enrich_sources(db.search(query, top_k=10))

        # Map to Pydantic structure
        formatted_sources = [to_search_result(s) for s in sources]

        # No LLM answer returned.
        #
        # Dòng này trước đây ghi "Xếp hạng bởi RRF & Cross-Encoder Reranking".
        # Cross-Encoder reranker đã bị gỡ (xem vector_store.py), nên câu đó nói
        # sai về cách kết quả được xếp hạng — tệ hơn là không nói gì, vì bác sĩ
        # tin vào thứ tự dựa trên một khâu không còn tồn tại.
        return QueryResponse(
            answer="Kết quả tìm kiếm y văn (xếp hạng bằng hợp nhất RRF của tìm theo nghĩa và BM25):",
            sources=formatted_sources
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Literature search failed: {str(e)}")
    finally:
        timer.log(f"q={len(query)}c")

# =============================================================================
# Document research: highlights & personal notes, lookup history, source compare
# =============================================================================

class HighlightCreateRequest(BaseModel):
    page_num: int
    quote: str
    start_offset: int
    end_offset: int
    color: Optional[str] = "yellow"
    note: Optional[str] = None
    created_by: Optional[str] = None

class HighlightUpdateRequest(BaseModel):
    note: Optional[str] = None
    color: Optional[str] = None

@app.get("/api/documents/{doc_name}/highlights")
def list_document_highlights(doc_name: str, page_num: Optional[int] = Query(None)):
    return library_db.list_highlights(get_safe_filename(doc_name), page_num)

@app.post("/api/documents/{doc_name}/highlights")
def create_document_highlight(doc_name: str, payload: HighlightCreateRequest):
    quote = (payload.quote or "").strip()
    if not quote:
        raise HTTPException(status_code=400, detail="Đoạn văn bản được tô sáng không được để trống.")
    if payload.end_offset <= payload.start_offset:
        raise HTTPException(status_code=400, detail="Vị trí đoạn tô sáng không hợp lệ.")
    return library_db.create_highlight(get_safe_filename(doc_name), payload.dict())

@app.get("/api/highlights")
def list_all_highlights(q: Optional[str] = Query(None)):
    """Toàn bộ ghi chú của bác sĩ trên mọi tài liệu (dùng cho bảng 'Ghi chú của tôi')."""
    if q and q.strip():
        return library_db.search_highlights(q)
    return library_db.list_highlights()

@app.get("/api/highlights/counts")
def highlight_counts():
    return library_db.count_highlights_by_document()

@app.patch("/api/highlights/{highlight_id}")
def update_highlight(highlight_id: str, payload: HighlightUpdateRequest):
    updated = library_db.update_highlight(highlight_id, payload.dict(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Không tìm thấy ghi chú này.")
    return updated

@app.delete("/api/highlights/{highlight_id}")
def delete_highlight(highlight_id: str):
    if not library_db.delete_highlight(highlight_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy ghi chú này.")
    return {"status": "success"}

class DocNoteRequest(BaseModel):
    content: str
    updated_by: Optional[str] = None

@app.get("/api/documents/{doc_name}/note")
def get_document_note(doc_name: str):
    return library_db.get_doc_note(get_safe_filename(doc_name))

@app.put("/api/documents/{doc_name}/note")
def save_document_note(doc_name: str, payload: DocNoteRequest):
    return library_db.save_doc_note(get_safe_filename(doc_name), payload.content, payload.updated_by)

@app.get("/api/search-history")
def get_search_history(q: Optional[str] = Query(None), limit: int = Query(100, ge=1, le=500)):
    return library_db.list_history(q, limit)

@app.get("/api/search-history/{record_id}")
def get_search_history_item(record_id: str):
    record = library_db.get_history(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Không tìm thấy lượt tra cứu này.")
    return record

@app.delete("/api/search-history/{record_id}")
def delete_search_history_item(record_id: str):
    if not library_db.delete_history(record_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy lượt tra cứu này.")
    return {"status": "success"}

@app.delete("/api/search-history")
def clear_search_history():
    library_db.clear_history()
    return {"status": "success"}

class SimilarQuestionsRequest(BaseModel):
    query: str
    limit: int = 4

@app.post("/api/search-history/similar")
def find_similar_questions(request: SimilarQuestionsRequest):
    """Gợi ý câu hỏi gần nghĩa đã tra cứu trước đây, kèm câu trả lời cũ để dùng lại."""
    query = request.query.strip()
    if len(query) < 4:
        return []
    embedding = db.embed_text(query)
    return library_db.find_similar_questions(
        query,
        embedding,
        limit=max(1, min(request.limit, 10)),
        embedding_model=db.embedding_model,
    )

class CompareRequest(BaseModel):
    query: str
    doc_names: List[str]
    chunks_per_doc: int = 4

@app.post("/api/compare")
def compare_documents(request: CompareRequest, x_deepseek_key: Optional[str] = Header(None)):
    """Đối chiếu cùng một câu hỏi lâm sàng giữa nhiều tài liệu/guideline."""
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Câu hỏi đối chiếu không được để trống.")
    doc_names = [d.strip() for d in request.doc_names if d and d.strip()]
    if len(doc_names) < 2:
        raise HTTPException(status_code=400, detail="Cần chọn ít nhất 2 tài liệu để đối chiếu.")
    if len(doc_names) > 5:
        raise HTTPException(status_code=400, detail="Chỉ đối chiếu tối đa 5 tài liệu cùng lúc.")

    per_doc = []
    top_k = max(2, min(request.chunks_per_doc, 8))
    for name in doc_names:
        try:
            chunks = db.search(query, top_k=top_k, doc_names=[name])
        except Exception as e:
            print(f"Compare search failed for '{name}': {e}")
            chunks = []
        per_doc.append({
            "doc_name": name,
            "chunks": [
                {"page_num": c.get("page_num"), "text": c.get("text", ""), "score": c.get("score")}
                for c in chunks
            ],
        })

    if not any(d["chunks"] for d in per_doc):
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy nội dung liên quan tới câu hỏi trong các tài liệu đã chọn."
        )

    try:
        result = generate_document_comparison(query, per_doc, x_deepseek_key or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi đối chiếu tài liệu: {str(e)}")

    result["question"] = query
    result["retrieved"] = per_doc
    result["created_at"] = time.strftime("%d/%m/%Y %H:%M")
    return result

# Drug / Medicine Lookup AI Report Endpoint
# Cache for drug textbook metadata
_book_metadata_cache = None

def get_book_metadata():
    """Chunk của mọi sách đã lập chỉ mục, dùng cho tra cứu thuốc theo tên.

    Đọc thẳng từ data/chunks/<doc_name>.json — chính tệp mà ingest_book.py nạp
    vào ChromaDB — thay cho bản sao metadata.json trước đây. Giữ hai bản đồng
    nghĩa mỗi lần bóc tách lại phải nhớ cập nhật cả hai; đã một lần lệch nhau:
    metadata.json còn 3 341 chunk mang tên UNKNOWN_DRUG sau khi drug_parser được
    sửa. Đọc chung một nguồn thì không lệch được nữa.

    Tiện thể tra cứu thấy được cả Dược thư Quốc gia, trước đây chỉ thấy cuốn
    Thuốc Biệt Dược vì metadata.json chỉ chứa sách đó.
    """
    global _book_metadata_cache
    if _book_metadata_cache is None:
        entries: List[Dict[str, Any]] = []
        for manifest in documents.list_manifests():
            path = documents.chunks_path(manifest["doc_name"])
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                entries.extend(loaded)
                print(f"Loaded {len(loaded)} chunks for {manifest['doc_name']}")
            except Exception as e:
                print(f"Warning: Failed to read {path}: {e}")
        _book_metadata_cache = entries
    return _book_metadata_cache

def search_drug_book(query: str, top_k: int = 6) -> List[Dict[str, Any]]:
    meta_entries = get_book_metadata()
    q_lower = query.lower().strip()
    q_words = [w for w in re.findall(r'\w+', q_lower) if len(w) > 1]
    
    exact_matches = []
    content_matches = []
    
    if meta_entries:
        for entry in meta_entries:
            generic = (entry.get("generic_name") or "").lower()
            brands = [b.lower() for b in entry.get("brand_names", []) if b]
            content = (entry.get("content") or "").lower()
            
            score = 0.0
            if q_lower == generic or any(q_lower == b for b in brands):
                score = 1.0
            elif generic and (generic in q_lower or q_lower in generic):
                score = 0.95
            elif any(b in q_lower or q_lower in b for b in brands):
                score = 0.92
            elif any(w in generic for w in q_words) or any(any(w in b for b in brands) for w in q_words):
                score = 0.85
            elif all(w in content for w in q_words):
                score = 0.75
            elif any(w in content for w in q_words):
                score = 0.5
                
            if score >= 0.8:
                exact_matches.append((score, entry))
            elif score >= 0.5:
                content_matches.append((score, entry))
                
    exact_matches.sort(key=lambda x: x[0], reverse=True)
    content_matches.sort(key=lambda x: x[0], reverse=True)
    
    # 2. Vector DB search as fallback / supplemental
    vec_results = []
    if db:
        try:
            vec_results = db.search(query, top_k=top_k)
        except Exception as e:
            print(f"Vector search warning: {e}")
            vec_results = []
            
    combined = []
    seen_pages = set()
    
    # Format exact and high-confidence matches from metadata.json
    for score, item in (exact_matches + content_matches)[:top_k]:
        page = item.get("page_in_file") or item.get("book_page_display", 1)
        doc_name = item.get("source_file") or "THUOC-BIET-DUOC-VA-CACH-SU-DUNG.pdf"
        field_name = item.get("field_name", "Chuyên luận Dược học")
        content = item.get("content", "")
        gen_title = item.get("generic_name", "")
        
        manifest = documents.load_manifest(doc_name) or {}
        combined.append({
            "id": str(len(combined) + 1),
            "doc_name": doc_name,
            "doc_title": manifest.get("doc_title") or doc_name,
            "citation": documents.display_citation(doc_name, page),
            "page_num": f"Trang {page}",
            "file_size": "PDF",
            "field_name": field_name,
            "generic_name": gen_title,
            "brand_names": item.get("brand_names", []),
            "snippet": f"[{field_name}]: {content}"[:320].strip() + "...",
            "text": f"### {gen_title} - {field_name} (Trang {page})\n\n{content}",
            "score": score
        })
        seen_pages.add((doc_name, page))
        
    # Supplement with any unique pages from vector DB if slots remain
    for v in vec_results:
        if len(combined) >= top_k:
            break
        p_num = v.get("page_num", 1)
        # doc_name lấy từ chính kết quả tìm kiếm. Trước đây khối này gán cứng tên
        # cuốn Thuốc Biệt Dược cho MỌI kết quả vector, nên từ khi index thêm sách
        # thứ hai, một đoạn của Dược thư vẫn hiện là trích từ Thuốc Biệt Dược —
        # bác sĩ bấm kiểm chứng sẽ mở nhầm sách.
        v_doc = v.get("doc_name") or "THUOC-BIET-DUOC-VA-CACH-SU-DUNG.pdf"
        # Khoá trùng phải gồm cả tên sách: hai cuốn đều có trang 300.
        key = (v_doc, p_num)
        if key not in seen_pages:
            manifest = documents.load_manifest(v_doc) or {}
            combined.append({
                "id": str(len(combined) + 1),
                "doc_name": v_doc,
                "doc_title": manifest.get("doc_title") or v_doc,
                "citation": documents.display_citation(v_doc, p_num),
                "page_num": f"Trang {p_num}",
                "file_size": "PDF",
                "field_name": "Trích dẫn Dược thư",
                "snippet": v.get("text", "")[:320].strip() + "...",
                "text": v.get("text", ""),
                "score": v.get("score", 0.7)
            })
            seen_pages.add(key)
            
    return combined[:top_k]

class DrugReportRequest(BaseModel):
    query: str

# _sse dùng chung với đường tra cứu y văn, định nghĩa ở trên.

@app.post("/api/drugs/report")
def api_generate_drug_report(request: DrugReportRequest, x_deepseek_key: Optional[str] = Header(None)):
    """Trả báo cáo tra cứu thuốc theo luồng SSE.

    Trước đây endpoint này chặn ~18,7s: chờ DeepSeek sinh xong toàn bộ JSON
    3.500 token rồi mới trả về một cục, nên bác sĩ nhìn màn hình trắng suốt
    thời gian đó. Nay nguồn trích dẫn được đẩy đi ngay khi tìm xong, còn nội
    dung báo cáo chảy dần về theo từng đoạn — chữ đầu tiên xuất hiện sau
    khoảng nửa giây.
    """
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Tên thuốc hoặc triệu chứng không được để trống.")

    def event_stream():
        try:
            # 1. Tìm ngữ cảnh từ sách. Gửi nguồn đi trước để giao diện dựng
            #    được khối trích dẫn trong lúc LLM còn đang sinh chữ.
            sources = search_drug_book(query, top_k=6)
            yield _sse("meta", {
                "sources": sources,
                "created_at": time.strftime("%d/%m/%Y %H:%M"),
                "model_used": "Deepseek",
            })

            # 2. Nội dung báo cáo, phát dần theo luồng.
            for kind, payload in stream_drug_report(query, sources, x_deepseek_key or ""):
                if kind == "error":
                    yield _sse("error", {"detail": payload})
                    return
                yield _sse("update", payload)

            yield _sse("done", {})
        except Exception as e:
            print(f"Lỗi khi stream báo cáo thuốc: {e}")
            yield _sse("error", {"detail": f"Lỗi khi tạo báo cáo tra cứu thuốc: {str(e)}"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Tắt buffering của proxy, nếu không toàn bộ luồng bị gom lại và
            # người dùng vẫn phải chờ như cũ.
            "X-Accel-Buffering": "no",
        },
    )


# Diagnosis Tree Pipeline (3-step agent pipeline)
#
# Cả bốn bước đều nhận `patient_id` KHÔNG bắt buộc. Có id thì backend tự đọc hồ
# sơ và tự dựng khối tiền sử đã khử danh; không có thì prompt y hệt như trước,
# nên đường tra tự do (gõ mô tả, không chọn bệnh nhân) không hề đổi.
#
# Khử danh làm ở BACKEND chứ không ở frontend, dù frontend đã có sẵn tên trong
# tay: để tên bệnh nhân chỉ có đúng MỘT chỗ có thể lọt ra, thay vì bốn chỗ gọi
# API đều phải nhớ tự cắt tên, mãi mãi.
#
# Mỗi endpoint trả lại `patient_context` — đúng chuỗi đã gửi đi — để giao diện
# hiện nguyên văn cho bác sĩ. Đó cũng là cách tự kiểm: tên bệnh nhân mà lọt vào
# thì nó hiện ngay trên màn hình, không phải đào nhật ký agent mới thấy.

def _doi_chieu_di_ung(patient_id: Optional[str],
                      medications: Optional[List[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    """Đối chiếu ô dị ứng của bệnh nhân với danh sách thuốc vừa gợi ý.

    Trả None khi bác sĩ không chọn hồ sơ nào — không có bệnh án thì không có gì
    để đối chiếu, và một khối "chưa kiểm" ở đường tra tự do chỉ là tiếng ồn.
    Có hồ sơ mà ô dị ứng bỏ trống thì KHÔNG trả None: đó chính là trạng thái
    "chưa kiểm" cần phải hiện ra.
    """
    if not patient_id:
        return None
    patient = patient_db.get_patient(patient_id)
    if not patient:
        return None
    return drug_allergy.kiem_tra(patient.get("allergies"), medications)


class GenerateTreeRequest(BaseModel):
    description: str
    patient_id: Optional[str] = None

@app.post("/api/diagnosis-tree/generate")
def api_generate_diagnosis_tree(request: GenerateTreeRequest, x_deepseek_key: Optional[str] = Header(None)):
    description = request.description.strip()
    if not description:
        raise HTTPException(status_code=400, detail="Mô tả bệnh nhân không được để trống.")
    patient_ctx, patient_block = patient_context.build_prompt_block(request.patient_id)
    try:
        tree = generate_diagnosis_tree(description, x_deepseek_key or "", patient_block=patient_block)
        tree["patient_context"] = patient_ctx
        return tree
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi sinh cây chẩn đoán: {str(e)}")

class EndoscopyRequest(BaseModel):
    confirmed_symptoms: List[str]
    excluded_symptoms: List[str] = []
    patient_id: Optional[str] = None

@app.post("/api/diagnosis-tree/endoscopy")
def api_suggest_endoscopy(request: EndoscopyRequest, x_deepseek_key: Optional[str] = Header(None)):
    confirmed = [s.strip() for s in request.confirmed_symptoms if s.strip()]
    if not confirmed:
        raise HTTPException(status_code=400, detail="Cần ít nhất một triệu chứng đã xác nhận 'Có'.")
    excluded = [s.strip() for s in request.excluded_symptoms if s.strip()]
    patient_ctx, patient_block = patient_context.build_prompt_block(request.patient_id)
    try:
        result = suggest_endoscopy_exam(confirmed, excluded, x_deepseek_key or "", patient_block=patient_block)
        result["patient_context"] = patient_ctx
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi gợi ý khám & nội soi: {str(e)}")

class FinalDiagnosisRequest(BaseModel):
    confirmed_symptoms: List[str]
    excluded_symptoms: List[str] = []
    exam_notes: str
    patient_id: Optional[str] = None

@app.post("/api/diagnosis-tree/final")
def api_final_diagnosis(request: FinalDiagnosisRequest, x_deepseek_key: Optional[str] = Header(None)):
    exam_notes = request.exam_notes.strip()
    if not exam_notes:
        raise HTTPException(status_code=400, detail="Cần nhập kết quả khám lâm sàng & nội soi.")
    confirmed = [s.strip() for s in request.confirmed_symptoms if s.strip()]
    excluded = [s.strip() for s in request.excluded_symptoms if s.strip()]
    patient_ctx, patient_block = patient_context.build_prompt_block(request.patient_id)
    try:
        diagnoses = generate_final_diagnosis(confirmed, excluded, exam_notes, x_deepseek_key or "",
                                             patient_block=patient_block)
        return {"diagnoses": diagnoses, "patient_context": patient_ctx}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi chẩn đoán cuối cùng: {str(e)}")

class TreatmentSuggestionRequest(BaseModel):
    diagnoses: List[Dict[str, Any]]
    exam_notes: Optional[str] = None
    patient_id: Optional[str] = None

@app.post("/api/diagnosis-tree/treatment")
def api_treatment_suggestion(request: TreatmentSuggestionRequest, x_deepseek_key: Optional[str] = Header(None)):
    if not request.diagnoses:
        raise HTTPException(status_code=400, detail="Cần ít nhất một chẩn đoán đã chọn.")
    # Bước này là bước trả về medications[] rồi chảy thẳng vào bệnh án, nên đây
    # đúng là chỗ dị ứng thuốc bị bỏ sót gây hại nhất. Trước đợt này nó nhận
    # đúng hai thứ — chẩn đoán và ghi chú khám — và không có đường nào để biết
    # bệnh nhân dị ứng penicillin.
    patient_ctx, patient_block = patient_context.build_prompt_block(request.patient_id)
    try:
        result = generate_treatment_suggestion(request.diagnoses, request.exam_notes or "",
                                               x_deepseek_key or "", patient_block=patient_block)
        result["patient_context"] = patient_ctx
        # Đối chiếu dị ứng chạy SAU mô hình và ĐỘC LẬP với nó: mô hình đã được
        # nhắc tránh thuốc chống chỉ định, nhưng lời nhắc là lời khuyên chứ
        # không phải ràng buộc — đo được là mô hình bỏ qua tool 11,8-20,6% số
        # lần ngay cả khi tác vụ bắt buộc phải gọi. Lớp này là mã tất định nên
        # nó không phụ thuộc vào việc mô hình có chịu nghe hay không.
        #
        # Chạy ở backend vì ô dị ứng nằm trong bệnh án, và bệnh án không rời
        # khỏi máy. Kết quả trả ra chỉ chứa chữ trong ô dị ứng và tên thuốc —
        # không có tên người bệnh, không có mã hồ sơ.
        result["allergy_check"] = _doi_chieu_di_ung(request.patient_id,
                                                    result.get("medications"))
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi gợi ý phác đồ điều trị: {str(e)}")

# Shared conversation snapshots (read-only links, like ChatGPT's "Share" feature)
SHARES_FILE = os.path.join(config.DATA_DIR, "shares.json")

class ShareMessage(BaseModel):
    role: str
    text: str
    time: Optional[str] = None
    sources: Optional[List[Dict[str, Any]]] = None

class ShareCreateRequest(BaseModel):
    title: str
    messages: List[ShareMessage]

@app.post("/api/share")
def create_share(request: ShareCreateRequest):
    if not request.messages:
        raise HTTPException(status_code=400, detail="Cuộc trò chuyện trống, không thể chia sẻ.")
    shares = read_json_data(SHARES_FILE)
    share_id = str(uuid.uuid4())
    record = {
        "id": share_id,
        "title": request.title or "Cuộc trò chuyện chưa đặt tên",
        "messages": [m.dict() for m in request.messages],
        "created_at": time.time()
    }
    shares.append(record)
    write_json_data(SHARES_FILE, shares)
    return {"id": share_id}

@app.get("/api/share/{share_id}")
def get_share(share_id: str):
    shares = read_json_data(SHARES_FILE)
    record = next((s for s in shares if s.get("id") == share_id), None)
    if not record:
        raise HTTPException(status_code=404, detail="Không tìm thấy cuộc trò chuyện được chia sẻ này.")
    return record

@app.get("/api/documents/{doc_name}/pages/{page_num}/image")
def get_page_image(doc_name: str, page_num: int, dpi: int = 150):
    """
    Ảnh scan gốc của một trang, để bác sĩ tự kiểm chứng trích dẫn.

    Với sách scan, text OCR luôn có sạn — chính bản OCR có thể là chỗ sai. Bác sĩ
    cần nhìn được trang thật thì việc fact-check mới có nghĩa. page_num là số
    trang IN; bản đồ trang lo việc quy về đúng trang PDF.
    """
    safe_name = get_safe_filename(doc_name)
    pdf_path = documents.upload_path(safe_name)
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp tài liệu.")

    pdf_page = documents.printed_to_pdf_page(safe_name, page_num)
    dpi = max(72, min(dpi, 300))

    cache_dir = documents.page_images_dir(safe_name)
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"{pdf_page:04d}_{dpi}.jpg")

    if not os.path.exists(cache_file):
        try:
            try:
                import pymupdf as fitz
            except ImportError:
                import fitz
            with fitz.open(pdf_path) as doc:
                if not (1 <= pdf_page <= len(doc)):
                    raise HTTPException(status_code=404, detail="Trang không tồn tại.")
                pix = doc[pdf_page - 1].get_pixmap(dpi=dpi)
                pix.pil_save(cache_file, format="JPEG", quality=80, optimize=True)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Không render được trang: {e}")

    # Phía trình duyệt phải tự fetch ảnh này rồi dụng blob URL (thẻ <img> trần không
    # mang được header Authorization), nên mỗi lần lật qua lật lại là một lượt tải mới
    # nếu không cho phép cache. Nội dung là sách tham khảo đã xuất bản, không phải dữ
    # liệu bệnh nhân; "private" vẫn chặn proxy dùng chung giữ bản sao.
    return FileResponse(
        cache_file,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


SEARCH_IN_DOC_MAX_PAGES = 200
SEARCH_IN_DOC_SNIPPET_PAD = 70


@app.get("/api/documents/{doc_name}/search")
def search_in_document(doc_name: str, q: str = Query(..., min_length=2)):
    """
    Tìm một cụm chữ TRONG một tài liệu, trả về các trang IN có chứa nó.

    Việc này thuộc về backend chứ không phải frontend: tìm ở phía trình duyệt
    thì chỉ tìm được những trang bác sĩ đã mở, tức là tìm được càng ít khi càng
    cần tìm.

    So khớp sau khi GẤP DẤU (xem text_fold): gõ không dấu vẫn ra, và quan trọng
    hơn, những chỗ OCR làm rụng nét ngang của đ — kho này có thật, ví dụ "Giảm
    dau" — vẫn khớp khi bác sĩ gõ "giảm đau".

    Lượt tìm đầu tiên của mỗi tài liệu phải dựng chỉ mục (Dược thư Quyển 1 mất
    khoảng 10 giây cho 913 trang); các lượt sau khoảng 4ms. Trả kèm `was_cold`
    để giao diện nói được vì sao lần đầu lâu, thay vì để bác sĩ nhìn vòng xoay
    và đoán là hỏng.
    """
    safe_name = get_safe_filename(doc_name)
    was_cold = not doc_index.is_warm(safe_name)
    texts, folded = doc_index.get_index(safe_name)
    if not folded:
        raise HTTPException(status_code=404, detail="Tài liệu này chưa có bản văn bản để tìm.")

    needle = text_fold.fold(q.strip())
    if not needle:
        return {"query": q, "total_pages": 0, "truncated": False, "was_cold": was_cold, "matches": []}

    matches = []
    truncated = False
    for printed_page in sorted(folded.keys()):
        hay = folded[printed_page]
        hit = hay.find(needle)
        if hit == -1:
            continue
        if len(matches) >= SEARCH_IN_DOC_MAX_PAGES:
            truncated = True
            break

        text = texts.get(printed_page, "")
        # Bảng chỉ số chỉ dựng cho trang thật sự khớp — dựng cho cả 913 trang là
        # hàng chục MB trên một máy chỉ còn khoảng 1 GB trống.
        _, index_map = text_fold.fold_with_map(text)
        if hit < len(index_map):
            orig_start = index_map[hit]
            end_idx = min(hit + len(needle), len(index_map)) - 1
            orig_end = index_map[end_idx] + 1
        else:
            orig_start, orig_end = 0, 0

        left = max(0, orig_start - SEARCH_IN_DOC_SNIPPET_PAD)
        right = min(len(text), orig_end + SEARCH_IN_DOC_SNIPPET_PAD)
        snippet = text[left:right].strip().replace("\n", " ")
        matches.append({
            "page_num": printed_page,
            "citation": documents.display_citation(safe_name, printed_page),
            "snippet": ("…" if left > 0 else "") + snippet + ("…" if right < len(text) else ""),
            # Vị trí trong chữ GỐC, để reader cuộn tới đúng chỗ và tô sáng.
            "match_start": orig_start,
            "match_end": orig_end,
            "count": hay.count(needle),
        })

    return {
        "query": q,
        "total_pages": len(matches),
        "truncated": truncated,
        "was_cold": was_cold,
        "matches": matches,
    }


@app.get("/api/documents/{doc_name}/pages/{page_num}")
def get_page_content(doc_name: str, page_num: int):
    """
    Text OCR của một trang. page_num là số trang IN — cùng đơn vị với trích dẫn
    trong kết quả tìm kiếm và với endpoint ảnh scan ở trên.

    File OCR lại đánh tên theo CHỈ SỐ PDF, và với sách scan hai số này lệch nhau
    (Dược thư Quyển 1: lệch từ +1 tới −10 tùy chỗ). Nên phải quy đổi qua bản đồ
    trang, nếu không bác sĩ bấm vào trích dẫn trang 297 sẽ đọc phải trang 301.
    Tài liệu không có bản đồ trang thì printed_to_pdf_page trả về chính nó.
    """
    safe_name = get_safe_filename(doc_name)
    cache_path = documents.pages_cache_path(safe_name)
    pdf_page = documents.printed_to_pdf_page(safe_name, page_num)
    citation = documents.display_citation(safe_name, page_num)

    # 1. Kiểm tra cache tổng hợp JSON trước
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                pages = json.load(f)
            page_str = str(page_num)
            if page_str in pages and pages[page_str].strip():
                return {
                    "doc_name": safe_name,
                    "page_num": page_num,
                    "pdf_page": pdf_page,
                    "citation": citation,
                    "text": pages[page_str]
                }
        except Exception as e:
            print(f"Error reading pages_cache: {e}")

    # 2. Kiểm tra file text OCR trang đơn — trong thư mục RIÊNG của tài liệu.
    # Trước đây bước này đọc từ pdf_text/ dùng chung cho mọi doc_name, nên khi có
    # từ hai tài liệu trở lên, mở một trang sẽ trả về nội dung của tài liệu khác.
    txt_file = documents.ocr_page_path(safe_name, pdf_page)
    if os.path.exists(txt_file):
        try:
            with open(txt_file, "r", encoding="utf-8") as f:
                return {
                    "doc_name": safe_name,
                    "page_num": page_num,
                    "pdf_page": pdf_page,
                    "citation": citation,
                    "text": f.read()
                }
        except Exception as e:
            print(f"Error reading page txt: {e}")

    # 3. Trả về thông báo trang
    return {
        "doc_name": safe_name,
        "page_num": page_num,
        "pdf_page": pdf_page,
        "citation": citation,
        "text": f"[Trang {page_num}]\nĐang nạp và hiển thị tài liệu {safe_name}..."
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT)
