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
from starlette.concurrency import run_in_threadpool
from typing import Annotated, List, Optional, Any, Dict

import config
import documents
import google_login
import mailer
import patient_context
import drug_allergy
import drug_catalog
import drug_interaction
import pediatric_dose
import text_fold
import doc_index
import page_locate
import profile_db
import auth_db
import pdf_export
import library_db
import generic_ingest
import ingest_jobs
import web_tools
import answer_verify
import feedback_db
from vector_store import VectorStore, IndexUnavailable, SearchHits
from writer_lock import writer_lock
from llm_client import coverage_notes, generate_answer, stream_answer, generate_diagnosis_tree, suggest_endoscopy_exam, generate_final_diagnosis, generate_treatment_suggestion, generate_drug_report, stream_drug_report, generate_document_comparison

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
    # Ở lifespan chứ không ở cấp module: import main trong test không được
    # chạm vào dữ liệu thật. Chỉ chạy một lần trong đời của library.db.
    legacy = library_db.assign_legacy_owners(_unique_user_names())
    if legacy:
        print(f"[library_db] Gắn chủ cho lịch sử/ghi chú cũ: {legacy}")

    def _warm():
        t0 = time.perf_counter()
        print("[STARTUP] Đang nạp model embedding và chỉ mục BM25 ở nền...")
        try:
            generic_ingest.cleanup_orphans(db)
            drug_interaction.chi_muc()
            for doc in drug_interaction._nguon_duoc_thu():
                pediatric_dose._cau_lieu_cua_tai_lieu(doc)
            db._get_corpus_and_bm25()
            db.embedding
            print(f"[STARTUP] Sẵn sàng phục vụ tìm kiếm sau {time.perf_counter() - t0:.1f}s.")
        except Exception as e:
            print(f"[STARTUP] Cảnh báo: nạp trước thất bại ({e}). Sẽ nạp lười khi có truy vấn.")

    # Máy chủ giữ quyền ghi trong suốt vòng đời; CLI không được mở Chroma để ghi song song.
    with writer_lock(config.VECTOR_DB_DIR):
        threading.Thread(target=_warm, name="warmup", daemon=True).start()
        yield

app = FastAPI(title="Medical RAG Assistant API", lifespan=lifespan)

# Initialize doctor profile database (SQLite) + xác thực/phân quyền trên cùng bảng
profile_db.init_db()
auth_db.init_db()

# Initialize document research database: highlights, notes, search history (SQLite)
library_db.init_db()

# Nhật ký tra cứu + phản hồi của bác sĩ (feedback_db.py) — tách khỏi library.db.
feedback_db.init_db()


def _unique_user_names() -> Dict[str, str]:
    """Tên hiển thị / tên đăng nhập -> id, chỉ với tên thuộc đúng một tài khoản."""
    seen: Dict[str, set] = {}
    for u in auth_db.list_users():
        for name in {u.get("display_name"), u.get("username")}:
            if name:
                seen.setdefault(name, set()).add(u["id"])
    return {name: next(iter(ids)) for name, ids in seen.items() if len(ids) == 1}


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

class QueryRequest(BaseModel):
    query: str
    created_by: Optional[str] = None
    # Giao diện tự bật khi máy chủ cấu hình công cụ web. Giữ mặc định False
    # cho các client cũ không truyền lựa chọn này.
    web: bool = False
    # "Hỏi về tài liệu này": giới hạn tra cứu trong đúng một cuốn sách, ưu tiên
    # các đoạn gần trang bác sĩ đang đọc.
    doc_name: Optional[str] = None
    near_page: Optional[int] = None
    # None: toàn kho; []: không dùng sách; danh sách: chỉ các nguồn đã chọn.
    doc_names: Optional[List[str]] = None

class SearchResultItem(BaseModel):
    id: Optional[str] = None
    text: str
    doc_name: str = ""
    # Nguồn web không có số trang.
    page_num: Optional[int] = None
    score: float = 0.0
    # "book" = trang sách trong kho; "web" = kết quả từ web_tools (có url).
    kind: str = "book"
    url: Optional[str] = None
    provider: Optional[str] = None
    published: Optional[str] = None
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
    # Đoạn con (child chunk) đã khớp — ngắn và đúng chỗ hơn `text` (đoạn cha),
    # dùng để tô sáng vị trí trích dẫn trên ảnh trang.
    quote: Optional[str] = None

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
        quote=s.get("child_text") or None,
    )

def web_hit_to_source(hit: dict) -> dict:
    """Kết quả web_tools -> nguồn cùng dạng với trang sách, để chung dãy số [n].

    Nhãn bắt đầu bằng "Nguồn web" để chính mô hình cũng phân biệt được, xem
    quy tắc 6 trong llm_client._build_answer_messages.
    """
    when = f", {hit['published']}" if hit.get("published") else ""
    return {
        **hit,
        "id": hit["url"],
        "doc_name": "",
        "doc_title": hit["title"],
        "citation": f"Nguồn web — {hit['provider']}: {hit['title']} ({hit['domain']}{when})",
        "score": 0.0,
    }


def to_web_result(s: dict) -> SearchResultItem:
    return SearchResultItem(
        id=s.get("id"), text=s["text"], kind="web", url=s["url"],
        provider=s.get("provider"), published=s.get("published") or None,
        doc_title=s.get("doc_title"), citation=s.get("citation"),
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
# Mọi endpoint theo từng tài liệu (trang, ảnh scan, tìm trong sách, tô sáng, ghi
# chú, tải xuống, xoá...) đều nằm dưới tiền tố này. Kiểm quyền xem MỘT chỗ ở
# middleware thay vì rải vào từng route: thêm endpoint mới dưới tiền tố này là
# tự được che, không có đường nào quên kiểm.
DOC_SCOPED_PATH_RE = re.compile(r"^/api/documents/([^/]+)(?:/|$)")
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

    doc_match = DOC_SCOPED_PATH_RE.match(request.scope.get("path") or path)
    if doc_match and request.state.user is not None and doc_match.group(1) != "ingest":
        # 404 chứ không 403: không xác nhận cho người ngoài là tài liệu đó tồn tại.
        if not documents.can_view(request.state.user, get_safe_filename(doc_match.group(1))):
            return JSONResponse(status_code=404, content={"detail": "Không tìm thấy tài liệu."})

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
        "has_api_key": bool(config.DEEPSEEK_API_KEY),
        # Rỗng = máy chủ không bật tìm web; giao diện ẩn nút đi.
        "web_search_tools": web_tools.available_tools(),
    }

# --- Patient records (hồ sơ bệnh nhân) — backed by SQLite (backend/data/patients.db) ---

PATIENT_ATTACHMENTS_DIR = os.path.join(config.DATA_DIR, "patient_attachments")
os.makedirs(PATIENT_ATTACHMENTS_DIR, exist_ok=True)

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

def get_safe_filename(filename: str) -> str:
    """Sanitizes filename to prevent directory traversal."""
    return os.path.basename(filename).replace("..", "")

@app.post("/api/documents/ingest")
async def ingest_document(request: Request, file: UploadFile = File(...)):
    """
    Bác sĩ tự tải PDF lên — không cần ai viết parser riêng cho tài liệu này.

    Trả về ngay {job_id, doc_name}; việc đọc/OCR/cắt đoạn/nạp chỉ mục chạy ở
    một luồng nền (có thể mất vài phút với PDF scan dày), tiến độ theo dõi
    qua GET /api/documents/ingest/{job_id}/events (SSE). Xem
    backend/generic_ingest.py để biết luồng nạp — dùng lại đúng
    ingest_book.ingest() nên tài liệu ra đời có đủ mọi tính năng của Thư viện
    (tải xuống, xoá, tô sáng, Đối chiếu, trình đọc trang) mà không cần đụng gì
    tới các endpoint đó.
    """
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ tệp PDF.")
    try:
        job = ingest_jobs.reserve(file.filename, lambda active:
            generic_ingest.slugify_doc_name(file.filename, active))
    except ValueError as e:
        raise HTTPException(status_code=429, detail=str(e))
    job_id, doc_name = job["job_id"], job["doc_name"]
    user = current_user(request)
    # Quản trị tải lên = tài liệu chung cho cả phòng khám; bác sĩ tải lên = kho
    # riêng của chính tài khoản đó.
    visibility = (documents.VISIBILITY_SHARED if auth_db.is_admin(user)
                  else documents.VISIBILITY_PRIVATE)
    # Manifest tạm ghi TRƯỚC khi tệp chạm đĩa: tên tài liệu lấy từ tên tệp nên
    # đoán được, và không có manifest thì middleware coi là tài liệu chung —
    # người khác tải được PDF riêng trong lúc nó còn xếp hàng chờ nạp.
    stub = documents.new_manifest(doc_name=doc_name, doc_title=os.path.splitext(file.filename)[0],
                                  source_pdf=doc_name, pdf_pages=0, parser="generic")
    stub.update(owner_id=user["id"], visibility=visibility, uploaded_by=user.get("display_name"))
    documents.save_manifest(stub)
    save_path = os.path.join(config.UPLOAD_DIR, doc_name)
    try:
        size = 0
        with open(save_path, "xb") as buffer:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > generic_ingest.MAX_PDF_BYTES:
                    raise ValueError("PDF vượt giới hạn 64 MiB.")
                buffer.write(chunk)
        if size == 0:
            raise ValueError("Tệp PDF rỗng.")
        generic_ingest.validate_pdf(save_path)
    except (ValueError, FileExistsError) as e:
        ingest_jobs.discard(job_id)
        _remove_if_exists(documents.manifest_path(doc_name))
        if not isinstance(e, FileExistsError) and os.path.exists(save_path):
            os.remove(save_path)
        raise HTTPException(status_code=400 if not isinstance(e, FileExistsError) else 409, detail=str(e))
    except Exception as e:
        ingest_jobs.discard(job_id)
        _remove_if_exists(documents.manifest_path(doc_name))
        if os.path.exists(save_path):
            os.remove(save_path)
        raise HTTPException(status_code=500, detail=f"Không lưu được tệp đã tải lên: {e}")

    doc_title = os.path.splitext(file.filename)[0]
    uploader = user.get("display_name")

    def _run():
        try:
            def warn(page_num):
                current = ingest_jobs.get(job_id)
                warnings = current["warnings"] if current else []
                ingest_jobs.update(job_id, warnings=warnings + [page_num])
            generic_ingest.ingest_generic_pdf(
                doc_name, save_path, doc_title,
                progress_cb=ingest_jobs.make_progress_cb(job_id),
                vector_store=db,
                uploaded_by=uploader,
                warning_cb=warn,
                owner_id=user["id"],
                visibility=visibility,
            )
            _invalidate_book_metadata()
            ingest_jobs.update(job_id, status="done", stage="Hoàn tất")
        except Exception as e:
            print(f"[ingest] Lỗi nạp '{doc_name}': {type(e).__name__}: {e}")
            ingest_jobs.update(job_id, status="error", error=str(e))
            try:
                generic_ingest.cleanup_orphans(db)
            except Exception as cleanup_error:
                print(f"[ingest] Chưa dọn được chỉ mục dở: {cleanup_error}")
            if not documents.load_manifest(doc_name) and os.path.exists(save_path):
                os.remove(save_path)

    ingest_jobs.submit(job_id, _run)
    return {"job_id": job_id, "doc_name": doc_name, "visibility": visibility}


def _remove_if_exists(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


@app.get("/api/documents/ingest/{job_id}/events")
async def ingest_progress_events(job_id: str):
    async def event_stream():
        last_snapshot = None
        ticks = 0
        while True:
            job = ingest_jobs.get(job_id)
            if job is None:
                yield _sse("error", {"message": "Tiến trình nạp đã mất (máy chủ có thể đã khởi động lại). Hãy tải lại PDF."})
                return
            snapshot = (job["status"], job["stage"], job["current"], job["total"], tuple(job["warnings"]))
            if snapshot != last_snapshot:
                yield _sse("progress", job)
                last_snapshot = snapshot
            if job["status"] in ("done", "error"):
                return
            ticks += 1
            if ticks % 37 == 0:
                yield ":\n\n"
            await asyncio.sleep(0.4)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@app.get("/api/index/health")
def index_health(request: Request):
    health = db.health()
    hidden = documents.hidden_doc_names(current_user(request))
    health["docs"] = [d for d in health["docs"] if d["doc_name"] not in hidden]
    return health


@app.get("/api/documents")
def list_documents(request: Request):
    user = current_user(request)
    try:
        hidden = documents.hidden_doc_names(user)
        docs = [d for d in db.list_documents() if d["doc_name"] not in hidden]
        # Enrich with the upload file's mtime (proxy for "uploaded_at") for library sorting —
        # read from disk rather than the vector store so existing indexes don't need migration.
        for doc in docs:
            path = documents.upload_path(doc["doc_name"])
            doc["uploaded_at"] = os.path.getmtime(path) if os.path.exists(path) else None
            manifest = documents.load_manifest(doc["doc_name"]) or {}
            doc["source_type"] = "self_uploaded" if manifest.get("parser") == "generic" else "reference"
            doc["uploaded_by"] = manifest.get("uploaded_by") if doc["source_type"] == "self_uploaded" else None
            doc["visibility"] = documents.visibility_of(manifest)
            doc["can_delete"] = documents.can_delete(user, doc["doc_name"])
        return docs
    except IndexUnavailable as e:
        raise _index_http_error(e)
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
def delete_document(doc_name: str, request: Request):
    safe_name = get_safe_filename(doc_name)
    # Middleware đã chặn tài liệu riêng của người khác (404). Ở đây chỉ còn một
    # trường hợp: tài liệu chung, chỉ quản trị phòng khám được xoá.
    if not documents.can_delete(current_user(request), safe_name):
        raise HTTPException(status_code=403, detail="Chỉ quản trị phòng khám mới xoá được tài liệu dùng chung.")
    if ingest_jobs.is_active(safe_name):
        raise HTTPException(status_code=409, detail="Tài liệu đang nạp; hãy đợi hoàn tất rồi xoá.")

    # Delete from vector store
    try:
        db.delete_document(safe_name)
    except Exception as e:
        raise HTTPException(status_code=503, detail="Không xóa được chỉ mục; tài liệu vẫn được giữ để thử lại.") from e

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
    _invalidate_book_metadata()

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
SCOPED_SEARCH_TIMEOUT_S = 15.0
SEARCH_COLD_TIMEOUT_S = 60.0   # tìm khi còn phải nạp model: 2,8 lần số đo được
SEARCH_TOKEN_GAP_TIMEOUT_S = 15.0  # im lặng giữa hai mẩu chữ: 9 lần chữ-đầu chậm nhất
SEARCH_TOTAL_TIMEOUT_S = 60.0  # trần cứng cả lần tra: 16 lần lần chậm nhất đo được
# Phần "Tìm thêm trên web": lập kế hoạch 12s + gọi dịch vụ ngoài 10s (song
# song), cộng dư. Hết trần thì trả lời bằng sách như khi không bật web.
WEB_PHASE_TIMEOUT_S = 25.0


def _sse(event: str, payload: Any) -> str:
    """Đóng gói một sự kiện Server-Sent Events."""
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _library_coverage_note(hidden: Optional[set] = None) -> str:
    """Liệt kê ngắn gọn các tài liệu đang có trong kho, đọc động từ manifest.

    Trước đây thông báo "0 kết quả" hard-code "Dược thư hiện chỉ có quyển 1,
    chữ A đến H" — đúng lúc viết, nhưng sai ngay khi nạp thêm Quyển 2 vì không
    ai nhớ sửa câu này. Đọc động từ documents.list_manifests() thì không thể
    lạc hậu theo kiểu đó nữa: nạp thêm sách nào, câu này tự nhắc đúng sách đó.
    """
    parts: List[str] = []
    for m in documents.list_manifests():
        if hidden and m.get("doc_name") in hidden:
            continue
        title = m.get("short_title") or m.get("doc_title") or m.get("doc_name")
        vol = m.get("volume")
        label = f"{title} Q.{vol}" if vol else str(title)
        coverage = m.get("coverage")
        if coverage:
            label += f" ({coverage})"
        parts.append(label)
    return "; ".join(parts)


# Chat Tab Search & Answer endpoint (uses LLM)
# Cửa sổ trang coi là "gần trang đang đọc" khi hỏi về một tài liệu.
NEAR_PAGE_WINDOW = 15


def _retrieve(query: str, request: "QueryRequest", hidden: set):
    """Tra các nguồn đã chọn, toàn kho cho client cũ, hoặc một tài liệu cụ thể.

    Khi hỏi về một tài liệu: lấy rộng hơn rồi đẩy các đoạn nằm gần trang đang
    đọc lên trước — bác sĩ hỏi ngay cạnh trang đang mở thì thường hỏi về chính
    chuyên luận đó. Thứ tự trong từng nhóm giữ nguyên theo điểm hợp nhất.
    """
    doc = (request.doc_name or "").strip()
    selected = [get_safe_filename(doc)] if doc else (
        list(dict.fromkeys(get_safe_filename(name.strip()) for name in request.doc_names if name.strip()))
        if request.doc_names is not None else None
    )
    if selected is None:
        return db.search(query, top_k=5, exclude_doc_names=hidden)
    if not selected:
        return SearchHits(status="NO_MATCH")
    hits = db.search(query, top_k=8, doc_names=selected, exclude_doc_names=hidden)
    if doc and request.near_page:
        near = [h for h in hits if abs((h.get("page_num") or 0) - request.near_page) <= NEAR_PAGE_WINDOW]
        far = [h for h in hits if h not in near]
        hits[:] = near + far
    del hits[5:]
    return hits


@app.post("/api/search")
async def search_and_answer(
    request: QueryRequest,
    http_request: Request,
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
    user = current_user(http_request)
    hidden = documents.hidden_doc_names(user)

    async def event_stream():
        timer = StageTimer("search")
        outcome = "ok"
        answer_parts: List[str] = []
        formatted_sources: List[SearchResultItem] = []
        started = time.perf_counter()
        log_id: Optional[str] = None
        verify: Optional[dict] = None

        try:
            # ---------- 1. Khâu tìm ----------
            #
            # Trần phụ thuộc việc model đã nạp chưa: lần đầu phải nạp mất 21,7s,
            # những lần sau chỉ 65ms. Dùng một trần chung thì hoặc giết lần đầu,
            # hoặc vô dụng cho các lần sau.
            warm = db.is_warm()
            budget = SEARCH_WARM_TIMEOUT_S if warm else SEARCH_COLD_TIMEOUT_S
            if request.doc_name or request.doc_names:
                # Lọc theo một tài liệu: lượt đầu phải dựng tập id được phép trên
                # toàn kho (đo ~2,8s trên máy không tải), các lượt sau ~0,2s.
                budget = max(budget, SCOPED_SEARCH_TIMEOUT_S)
            if not warm:
                yield _sse("status", {"phase": "loading_model",
                                      "message": "Đang nạp mô hình tra cứu y văn, lần tra đầu tiên chậm hơn…"})
            try:
                with timer.stage("retrieval"):
                    sources = await asyncio.wait_for(
                        asyncio.to_thread(lambda: enrich_sources(_retrieve(query, request, hidden))),
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

            if sources.degraded:
                yield _sse("status", {"phase": "bm25_only", "degraded": True,
                                      "code": "EMBEDDING_UNAVAILABLE",
                                      "message": "Mô hình tìm theo nghĩa chưa sẵn sàng; đang tra bằng từ khóa BM25."})
            formatted_sources = [to_search_result(s) for s in sources]
            yield _sse("sources", {"sources": [s.dict() for s in formatted_sources],
                                   "degraded": sources.degraded, "reason": sources.reason})
            if sources.normalized is not None:
                # Bác sĩ gõ không dấu / quên bật bộ gõ: nói rõ đã tra theo câu nào,
                # để một lần khôi phục sai ("trị nam" thay vì "trị nấm") không bị giấu.
                yield _sse("query_normalized", sources.normalized.as_dict())
            if sources.understood:
                # Thuốc nào, mục nào, điều kiện nào, viết tắt nào — hiện cho bác
                # sĩ để một lần hiểu sai ("THA" thành gì khác) không bị giấu.
                yield _sse("query_understood", sources.understood)
            if sources.coverage:
                # Bảng kiểm từng cặp (thuốc, điều kiện) + câu nguyên văn trong
                # sách — giao diện vẽ khối liều thẳng từ đây, không qua mô hình.
                yield _sse("coverage", {"items": sources.coverage})
            try:
                log_id = await asyncio.to_thread(
                    feedback_db.log_query, user["id"], query,
                    sources.normalized.text if sources.normalized is not None else None,
                    request.doc_name, list(sources),
                )
            except Exception as e:
                print(f"Warning: không ghi được nhật ký tra cứu: {e}")

            # ---------- 1b. Tìm thêm trên web khi client yêu cầu ----------
            #
            # Trang sách đã gửi đi ở trên nên bác sĩ đọc được ngay trong lúc chờ
            # web. Xong thì gửi lại danh sách gộp: sách trước, web sau, chung
            # một dãy số [n] với câu trả lời.
            web_context: List[dict] = []
            if request.web:
                if not web_tools.available_tools():
                    yield _sse("status", {"phase": "web_disabled",
                                          "message": "Máy chủ chưa bật tìm kiếm web; chỉ trả lời theo sách."})
                else:
                    yield _sse("status", {"phase": "web_search",
                                          "message": "Đang tìm thêm trên web (PubMed, nhãn thuốc FDA, trang y khoa)…"})
                    with timer.stage("web"):
                        try:
                            web = await asyncio.wait_for(
                                asyncio.to_thread(web_tools.gather, query, api_key or config.DEEPSEEK_API_KEY),
                                timeout=WEB_PHASE_TIMEOUT_S,
                            )
                        except asyncio.TimeoutError:
                            web = {"sources": [], "calls": [], "errors": ["hết thời gian"]}
                    web_context = [web_hit_to_source(h) for h in web["sources"]]
                    formatted_sources += [to_web_result(s) for s in web_context]
                    yield _sse("sources", {"sources": [s.dict() for s in formatted_sources],
                                           "degraded": sources.degraded, "reason": sources.reason,
                                           "web_calls": web["calls"]})
                    if not web_context:
                        yield _sse("status", {"phase": "web_empty",
                                              "message": "Không lấy được kết quả web; câu trả lời chỉ dựa trên sách."})

            if not sources and not web_context:
                outcome = "no_sources"
                coverage_note = _library_coverage_note(hidden)
                yield _error_event(
                    ("BM25 đang chạy do mô hình embedding chưa sẵn sàng; chưa tìm thấy "
                     "đoạn khớp từ khóa" if sources.degraded else
                     "Không tìm thấy đoạn y văn nào khớp câu hỏi này trong các tài liệu đã nạp") + (f" ({coverage_note})" if coverage_note else "") + ".",
                    degraded=False,
                    detail="NO_MATCH: chỉ mục có dữ liệu nhưng truy vấn không khớp",
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
            pull = _sync_iter_puller(stream_answer(query, list(sources) + web_context, api_key,
                                                   coverage_notes(sources.coverage)))
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

            # ---------- 2b. Cổng số liệu ----------
            #
            # Mọi cặp (số, đơn vị) trong câu trả lời phải có trong đúng đoạn [n]
            # mà câu đó trích, hoặc ít nhất trên cùng trang sách. Không có thì
            # báo cho bác sĩ, không lặng lẽ sửa chữ nào. Xem answer_verify.py.
            if answer.strip():
                with timer.stage("verify"):
                    try:
                        verify = await asyncio.to_thread(
                            answer_verify.verify_answer, answer,
                            [s.dict() for s in formatted_sources], _book_page_text,
                        )
                        yield _sse("verify", verify)
                    except Exception as e:
                        print(f"Warning: cổng số liệu lỗi: {type(e).__name__}: {e}")

            if answer.strip():
                with timer.stage("history"):
                    try:
                        await asyncio.to_thread(
                            library_db.add_history,
                            owner_id=user["id"],
                            query=query,
                            answer=answer,
                            sources=[s.dict() for s in formatted_sources],
                            embedding=db.embed_text(query),
                            embedding_model=db.embedding_model,
                            created_by=user.get("display_name"),
                        )
                    except Exception as e:
                        print(f"Warning: failed to log search history: {e}")

            yield _sse("done", {"timings": timer.timings(), "outcome": outcome, "log_id": log_id})

        except IndexUnavailable as e:
            outcome = e.code
            yield _error_event(str(e), degraded=False, detail=e.code)
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
            if log_id:
                try:
                    feedback_db.finish_query(log_id, outcome, verify)
                except Exception as e:
                    print(f"Warning: không cập nhật được nhật ký tra cứu: {e}")

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


def _book_page_text(source: dict) -> str:
    """Văn bản OCR của cả trang sách chứa nguồn — cho cổng số liệu tìm con số
    nằm ngoài đoạn đã cắt làm ngữ cảnh. Nguồn web thì không có trang."""
    if source.get("kind") == "web" or not source.get("doc_name") or not source.get("page_num"):
        return ""
    return get_page_content(source["doc_name"], int(source["page_num"])).get("text", "")


class FeedbackRequest(BaseModel):
    log_id: str
    kind: str
    source_index: Optional[int] = None
    note: Optional[str] = None


@app.post("/api/feedback")
def post_feedback(body: FeedbackRequest, http_request: Request):
    """Bác sĩ đánh giá câu trả lời, mở một trang trích dẫn, hoặc báo trang đó sai."""
    user = current_user(http_request)
    try:
        ok = feedback_db.add_feedback(body.log_id, user["id"], body.kind,
                                      body.source_index, (body.note or "")[:500] or None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="Không tìm thấy lượt tra cứu này.")
    return {"ok": True}


@app.get("/api/feedback/summary")
def get_feedback_summary(http_request: Request):
    return feedback_db.summary(current_user(http_request)["id"])


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
def _index_http_error(exc):
    return HTTPException(status_code=503, detail={"code": exc.code, "message": str(exc)})


@app.post("/api/literature-search", response_model=QueryResponse)
def literature_search(request: QueryRequest, http_request: Request):
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    timer = StageTimer("literature-search")
    try:
        # Retrieve matching document contexts using hybrid search (dense + BM25 + RRF)
        with timer.stage("retrieval"):
            hidden = documents.hidden_doc_names(current_user(http_request))
            sources = enrich_sources(db.search(query, top_k=10, exclude_doc_names=hidden))

        # Map to Pydantic structure
        formatted_sources = [to_search_result(s) for s in sources]

        # No LLM answer returned.
        #
        # Dòng này trước đây ghi "Xếp hạng bởi RRF & Cross-Encoder Reranking".
        # Cross-Encoder reranker đã bị gỡ (xem vector_store.py), nên câu đó nói
        # sai về cách kết quả được xếp hạng — tệ hơn là không nói gì, vì bác sĩ
        # tin vào thứ tự dựa trên một khâu không còn tồn tại.
        return QueryResponse(
            answer=("Đang tra bằng BM25 vì mô hình embedding chưa sẵn sàng. " if sources.degraded else "")
                   + "Kết quả tìm kiếm y văn:",
            sources=formatted_sources
        )
    except IndexUnavailable as e:
        raise _index_http_error(e)
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
def list_document_highlights(doc_name: str, request: Request, page_num: Optional[int] = Query(None)):
    return library_db.list_highlights(current_user(request)["id"], get_safe_filename(doc_name), page_num)

@app.post("/api/documents/{doc_name}/highlights")
def create_document_highlight(doc_name: str, payload: HighlightCreateRequest, request: Request):
    quote = (payload.quote or "").strip()
    if not quote:
        raise HTTPException(status_code=400, detail="Đoạn văn bản được tô sáng không được để trống.")
    if payload.end_offset <= payload.start_offset:
        raise HTTPException(status_code=400, detail="Vị trí đoạn tô sáng không hợp lệ.")
    user = current_user(request)
    data = dict(payload.dict(), created_by=user.get("display_name"))
    return library_db.create_highlight(user["id"], get_safe_filename(doc_name), data)

@app.get("/api/highlights")
def list_all_highlights(request: Request, q: Optional[str] = Query(None)):
    """Toàn bộ ghi chú của bác sĩ trên mọi tài liệu (dùng cho bảng 'Ghi chú của tôi')."""
    owner = current_user(request)["id"]
    if q and q.strip():
        return library_db.search_highlights(owner, q)
    return library_db.list_highlights(owner)

@app.get("/api/highlights/counts")
def highlight_counts(request: Request):
    return library_db.count_highlights_by_document(current_user(request)["id"])

@app.patch("/api/highlights/{highlight_id}")
def update_highlight(highlight_id: str, payload: HighlightUpdateRequest, request: Request):
    updated = library_db.update_highlight(current_user(request)["id"], highlight_id,
                                          payload.dict(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Không tìm thấy ghi chú này.")
    return updated

@app.delete("/api/highlights/{highlight_id}")
def delete_highlight(highlight_id: str, request: Request):
    if not library_db.delete_highlight(current_user(request)["id"], highlight_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy ghi chú này.")
    return {"status": "success"}

class DocNoteRequest(BaseModel):
    content: str
    updated_by: Optional[str] = None

@app.get("/api/documents/{doc_name}/note")
def get_document_note(doc_name: str, request: Request):
    return library_db.get_doc_note(current_user(request)["id"], get_safe_filename(doc_name))

@app.put("/api/documents/{doc_name}/note")
def save_document_note(doc_name: str, payload: DocNoteRequest, request: Request):
    user = current_user(request)
    return library_db.save_doc_note(user["id"], get_safe_filename(doc_name), payload.content,
                                    user.get("display_name"))

# Lịch sử tra cứu là của từng tài khoản: mọi truy vấn lọc theo id do máy chủ
# lấy từ phiên đăng nhập. Trường created_by trong body chỉ còn để tương thích
# với giao diện cũ và không được dùng để phân quyền.

@app.get("/api/search-history")
def get_search_history(request: Request, q: Optional[str] = Query(None), limit: int = Query(100, ge=1, le=500)):
    return library_db.list_history(current_user(request)["id"], q, limit)

@app.get("/api/search-history/{record_id}")
def get_search_history_item(record_id: str, request: Request):
    record = library_db.get_history(current_user(request)["id"], record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Không tìm thấy lượt tra cứu này.")
    return record

@app.delete("/api/search-history/{record_id}")
def delete_search_history_item(record_id: str, request: Request):
    if not library_db.delete_history(current_user(request)["id"], record_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy lượt tra cứu này.")
    return {"status": "success"}

@app.delete("/api/search-history")
def clear_search_history(request: Request):
    library_db.clear_history(current_user(request)["id"])
    return {"status": "success"}

class SimilarQuestionsRequest(BaseModel):
    query: str
    limit: int = 4

@app.post("/api/search-history/similar")
def find_similar_questions(request: SimilarQuestionsRequest, http_request: Request):
    """Gợi ý câu hỏi gần nghĩa đã tra cứu trước đây, kèm câu trả lời cũ để dùng lại."""
    query = request.query.strip()
    if len(query) < 4:
        return []
    embedding = db.embed_text(query)
    return library_db.find_similar_questions(
        current_user(http_request)["id"],
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
def compare_documents(request: CompareRequest, http_request: Request, x_deepseek_key: Optional[str] = Header(None)):
    """Đối chiếu cùng một câu hỏi lâm sàng giữa nhiều tài liệu/guideline."""
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Câu hỏi đối chiếu không được để trống.")
    doc_names = [d.strip() for d in request.doc_names if d and d.strip()]
    if len(doc_names) < 2:
        raise HTTPException(status_code=400, detail="Cần chọn ít nhất 2 tài liệu để đối chiếu.")
    if len(doc_names) > 5:
        raise HTTPException(status_code=400, detail="Chỉ đối chiếu tối đa 5 tài liệu cùng lúc.")

    user = current_user(http_request)
    for name in doc_names:
        if not documents.can_view(user, get_safe_filename(name)):
            raise HTTPException(status_code=404, detail=f"Không tìm thấy tài liệu: {name}")

    per_doc = []
    top_k = max(2, min(request.chunks_per_doc, 8))
    for name in doc_names:
        try:
            chunks = db.search(query, top_k=top_k, doc_names=[name])
        except IndexUnavailable as e:
            raise _index_http_error(e)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Không tra được chỉ mục của {name}: {e}")
        per_doc.append({
            "doc_name": name,
            "degraded": chunks.degraded,
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
    result["degraded"] = any(d.get("degraded") for d in per_doc)
    result["created_at"] = time.strftime("%d/%m/%Y %H:%M")
    return result

# Structured drug reference catalog
@app.get("/api/drug-catalog")
def list_drug_catalog(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return drug_catalog.list_drugs()


@app.get("/api/drug-catalog/{drug_id}")
def get_catalog_drug(drug_id: str, response: Response):
    record = drug_catalog.get_drug(drug_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi thuốc.")
    response.headers["Cache-Control"] = "no-store"
    return record


@app.post("/api/admin/drug-import")
async def import_drug_catalog(
    request: Request,
    file_format: str,
    publish: bool = False,
    admin: Dict[str, Any] = Depends(require_admin),
):
    content = bytearray()
    async for block in request.stream():
        if len(content) + len(block) > drug_catalog.MAX_BYTES:
            raise HTTPException(status_code=413, detail="Tệp vượt quá giới hạn 8 MB.")
        content.extend(block)
    try:
        records = await run_in_threadpool(drug_catalog.parse_upload, content, file_format)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if publish:
        await run_in_threadpool(drug_catalog.publish, records)
    return {
        "count": len(records),
        "sample": [{key: row[key] for key in ("name", "source_title")} for row in records[:5]],
    }


# Drug report support and textbook metadata
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
                # Gắn tên tài liệu để lọc theo quyền xem: chunk của tài liệu tự
                # tải không mang source_file nên không suy ngược được.
                for entry in loaded:
                    entry["_doc_name"] = manifest["doc_name"]
                entries.extend(loaded)
                print(f"Loaded {len(loaded)} chunks for {manifest['doc_name']}")
            except Exception as e:
                print(f"Warning: Failed to read {path}: {e}")
        _book_metadata_cache = entries
    return _book_metadata_cache

def _invalidate_book_metadata() -> None:
    """Gọi sau khi nạp/xoá tài liệu — nếu không, tra thuốc vẫn đọc bản cũ tới lúc khởi động lại."""
    global _book_metadata_cache
    _book_metadata_cache = None


# Thứ tự mục khi bác sĩ gõ đúng tên một thuốc: cái cần đọc trước đứng trước.
_SECTION_ORDER = ["INDICATIONS", "DOSAGE", "CONTRAINDICATION", "WARNINGS", "ADR",
                  "INTERACTION", "PREGNANCY", "LACTATION", "OVERDOSE", "DOSAGE_FORM"]
# Nối mảnh tới khoảng chừng này ký tự mỗi mục: đủ một mục liều điển hình, mà
# sáu mục cộng lại không phình prompt báo cáo thuốc quá vài nghìn token.
_SECTION_MAX_CHARS = 3000


def _group_sections(matches: List[tuple]) -> List[tuple]:
    """Một nguồn cho mỗi mục của mỗi chuyên luận khớp tên.

    Chunk trong tệp nằm theo thứ tự trang, nên lấy N chunk đầu của một chuyên
    luận là lấy "Dạng thuốc" cùng bốn mảnh liền nhau của "Dược lực học" — năm
    thẻ cùng một trang, và báo cáo không có phần liều hay chống chỉ định nào.
    Các mảnh liền nhau của cùng mục được nối lại thành một nguồn (giữ trang của
    mảnh đầu), rồi xếp mục theo _SECTION_ORDER.
    """
    groups: Dict[tuple, Dict[str, Any]] = {}
    for pos, (score, entry) in enumerate(matches):
        key = (entry.get("_doc_name"), (entry.get("generic_name") or "").lower(),
               entry.get("field_type") or entry.get("field_name"))
        g = groups.get(key)
        if g is None:
            groups[key] = {"score": score, "pos": pos, "entry": dict(entry)}
        elif len(g["entry"].get("content") or "") < _SECTION_MAX_CHARS:
            g["entry"]["content"] = (g["entry"].get("content") or "") + "\n" + (entry.get("content") or "")
    rank = {s: i for i, s in enumerate(_SECTION_ORDER)}
    ordered = sorted(groups.values(), key=lambda g: (
        -g["score"], rank.get(g["entry"].get("field_type"), len(rank)), g["pos"]))
    return [(g["score"], g["entry"]) for g in ordered]


def search_drug_book(query: str, top_k: int = 6, exclude_doc_names: Optional[set] = None) -> List[Dict[str, Any]]:
    excluded = set(exclude_doc_names or ())
    meta_entries = [e for e in get_book_metadata() if e.get("_doc_name") not in excluded]
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
                
    exact_matches = _group_sections(exact_matches)
    content_matches.sort(key=lambda x: x[0], reverse=True)
    
    # 2. Vector DB search as fallback / supplemental
    #
    # Nhánh exact/content_matches phía trên đọc thẳng file chunk JSON, không
    # qua Chroma — vẫn tra được thuốc theo tên dù chỉ mục vector hỏng. Trước
    # đây db.search() ném lỗi (IndexUnavailable/EmptyIndex) sẽ làm chết cả
    # search_drug_book, mất luôn phần exact match KHÔNG phụ thuộc Chroma.
    vec_results = SearchHits([], degraded=False, reason=None, status="OK")
    if db:
        try:
            vec_results = db.search(query, top_k=top_k, exclude_doc_names=excluded)
        except IndexUnavailable as e:
            vec_results = SearchHits([], degraded=True, reason=str(e), status=e.code)

    combined = []
    seen_pages = set()
    
    # Format exact and high-confidence matches from metadata.json
    for score, item in (exact_matches + content_matches)[:top_k]:
        page = item.get("page_in_file") or item.get("book_page_display", 1)
        # Mặc định trung lập khi thiếu source_file — KHÔNG gán cứng tên một
        # cuốn cụ thể, nếu không trích dẫn sẽ trỏ sai sách khi rơi vào nhánh
        # này (xem chú thích ở nhánh vector_results bên dưới, cùng lớp lỗi).
        doc_name = item.get("source_file") or "(không rõ tài liệu)"
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
        v_doc = v.get("doc_name") or "(không rõ tài liệu)"
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
            
    return SearchHits(combined[:top_k], degraded=vec_results.degraded,
                      reason=vec_results.reason, status=vec_results.status)

class DrugReportRequest(BaseModel):
    query: str

# _sse dùng chung với đường tra cứu y văn, định nghĩa ở trên.

@app.post("/api/drugs/report")
def api_generate_drug_report(request: DrugReportRequest, http_request: Request, x_deepseek_key: Optional[str] = Header(None)):
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
    hidden = documents.hidden_doc_names(current_user(http_request))

    def event_stream():
        try:
            # 1. Tìm ngữ cảnh từ sách. Gửi nguồn đi trước để giao diện dựng
            #    được khối trích dẫn trong lúc LLM còn đang sinh chữ.
            sources = search_drug_book(query, top_k=6, exclude_doc_names=hidden)
            yield _sse("meta", {
                "sources": sources,
                "degraded": sources.degraded,
                "reason": sources.reason,
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
        except IndexUnavailable as e:
            yield _sse("error", {"detail": str(e), "code": e.code})
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
# Cả bốn bước nhận `patient_history` KHÔNG bắt buộc: chữ bác sĩ gõ vào ô
# "Tình trạng bệnh nhân trước đó". Để trống thì prompt y hệt đường tra tự do.
# Mỗi endpoint trả lại `patient_context` — đúng chuỗi đã gửi đi — để giao diện
# hiện nguyên văn cho bác sĩ.

def _doi_chieu_di_ung(patient_history: Optional[str],
                      medications: Optional[List[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    """Đối chiếu phần nói về dị ứng trong ô tiền sử với danh sách thuốc vừa gợi ý.

    Trả None khi bác sĩ để trống ô tiền sử — không có gì để đối chiếu, và một
    khối "chưa kiểm" ở đường tra tự do chỉ là tiếng ồn. Có tiền sử nhưng không
    nhắc tới dị ứng thì vẫn trả kết quả "chưa kiểm" để bác sĩ thấy rõ.
    """
    if not patient_context.clean_history(patient_history):
        return None
    return drug_allergy.kiem_tra(patient_context.allergy_text(patient_history), medications)


class InteractionCheckRequest(BaseModel):
    medications: List[Dict[str, Any]]


@app.get("/api/drugs/pediatric-dosing")
def api_pediatric_dosing(name: str = Query(..., min_length=2, max_length=200)):
    """Câu liều mg/kg của một hoạt chất trong Dược thư, kèm con số máy đọc ra.

    Chỉ trả câu trong sách — KHÔNG chọn liều. Phép nhân với cân nặng nằm ở
    frontend/src/lib/doseCalc.js. Xem pediatric_dose.py vì sao máy không tự chọn.
    """
    return pediatric_dose.tra_cuu(name)


@app.post("/api/drugs/interactions")
def api_check_interactions(payload: InteractionCheckRequest):
    """Đối chiếu tương tác thuốc–thuốc của một đơn, đọc từ Dược thư.

    Giao diện gọi mỗi khi đơn thay đổi (thêm/bớt thuốc), nên phải rẻ: không
    gọi mô hình, không chạm chỉ mục vector — chỉ so token trên bảng dựng sẵn.
    Chỉ cần tên thuốc; không có dữ liệu bệnh nhân nào đi qua đây.
    """
    meds = [{"name": str(m.get("name") or "")[:200]} for m in payload.medications[:30]]
    return drug_interaction.kiem_tra(meds)


class GenerateTreeRequest(BaseModel):
    description: str
    # Ô "Tình trạng bệnh nhân trước đó" (không bắt buộc) — xem patient_context.
    patient_history: Optional[str] = None

@app.post("/api/diagnosis-tree/generate")
def api_generate_diagnosis_tree(request: GenerateTreeRequest, x_deepseek_key: Optional[str] = Header(None)):
    description = request.description.strip()
    if not description:
        raise HTTPException(status_code=400, detail="Mô tả bệnh nhân không được để trống.")
    patient_ctx, patient_block = patient_context.build_prompt_block(request.patient_history)
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
    # Ô "Tình trạng bệnh nhân trước đó" (không bắt buộc) — xem patient_context.
    patient_history: Optional[str] = None

@app.post("/api/diagnosis-tree/endoscopy")
def api_suggest_endoscopy(request: EndoscopyRequest, x_deepseek_key: Optional[str] = Header(None)):
    confirmed = [s.strip() for s in request.confirmed_symptoms if s.strip()]
    if not confirmed:
        raise HTTPException(status_code=400, detail="Cần ít nhất một triệu chứng đã xác nhận 'Có'.")
    excluded = [s.strip() for s in request.excluded_symptoms if s.strip()]
    patient_ctx, patient_block = patient_context.build_prompt_block(request.patient_history)
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
    # Ô "Tình trạng bệnh nhân trước đó" (không bắt buộc) — xem patient_context.
    patient_history: Optional[str] = None

@app.post("/api/diagnosis-tree/final")
def api_final_diagnosis(request: FinalDiagnosisRequest, x_deepseek_key: Optional[str] = Header(None)):
    exam_notes = request.exam_notes.strip()
    if not exam_notes:
        raise HTTPException(status_code=400, detail="Cần nhập kết quả khám lâm sàng & nội soi.")
    confirmed = [s.strip() for s in request.confirmed_symptoms if s.strip()]
    excluded = [s.strip() for s in request.excluded_symptoms if s.strip()]
    patient_ctx, patient_block = patient_context.build_prompt_block(request.patient_history)
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
    # Ô "Tình trạng bệnh nhân trước đó" (không bắt buộc) — xem patient_context.
    patient_history: Optional[str] = None

@app.post("/api/diagnosis-tree/treatment")
def api_treatment_suggestion(request: TreatmentSuggestionRequest, x_deepseek_key: Optional[str] = Header(None)):
    if not request.diagnoses:
        raise HTTPException(status_code=400, detail="Cần ít nhất một chẩn đoán đã chọn.")
    # Bước này là bước trả về medications[] rồi chảy thẳng vào bệnh án, nên đây
    # đúng là chỗ dị ứng thuốc bị bỏ sót gây hại nhất. Trước đợt này nó nhận
    # đúng hai thứ — chẩn đoán và ghi chú khám — và không có đường nào để biết
    # bệnh nhân dị ứng penicillin.
    patient_ctx, patient_block = patient_context.build_prompt_block(request.patient_history)
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
        result["allergy_check"] = _doi_chieu_di_ung(request.patient_history,
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
def get_page_image(
    doc_name: str, page_num: int, dpi: int = 150,
    source_pdf_page: Annotated[Optional[int], Query(ge=1)] = None,
):
    """
    Ảnh scan gốc của một trang, để bác sĩ tự kiểm chứng trích dẫn.

    Với sách scan, text OCR luôn có sạn — chính bản OCR có thể là chỗ sai. Bác sĩ
    cần nhìn được trang thật thì việc fact-check mới có nghĩa. page_num là số
    trang IN; bản đồ trang lo việc quy về đúng trang PDF. Danh mục thuốc có
    sẵn số trang PDF để đối chiếu cả khi số trang in bị lặp trong bản quét.
    """
    safe_name = get_safe_filename(doc_name)
    pdf_path = documents.upload_path(safe_name)
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp tài liệu.")

    pdf_page = source_pdf_page or documents.printed_to_pdf_page(safe_name, page_num)
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


class LocateRequest(BaseModel):
    quote: str


@app.post("/api/documents/{doc_name}/pages/{page_num}/locate")
async def locate_quote_on_page(doc_name: str, page_num: int, payload: LocateRequest, request: Request):
    """
    Hộp tô sáng (toạ độ 0–1) của đoạn trích dẫn trên ảnh trang — xem page_locate.

    page_num là số trang IN, cùng đơn vị với trích dẫn và endpoint ảnh. Lần đầu
    mở một trang scan phải OCR lại trang đó (vài giây), nên chạy ở thread riêng.
    """
    user = current_user(request)
    safe_name = get_safe_filename(doc_name)
    if not documents.can_view(user, safe_name):
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")
    quote = (payload.quote or "").strip()
    if not quote:
        return {"rects": [], "confidence": 0.0, "matched": 0, "method": None}
    pdf_page = documents.printed_to_pdf_page(safe_name, page_num)
    try:
        result = await asyncio.to_thread(page_locate.locate_on_page, safe_name, pdf_page, quote[:4000])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp tài liệu.")
    except IndexError:
        raise HTTPException(status_code=404, detail="Trang không tồn tại.")
    except Exception as e:
        # Không tô được thì giao diện vẫn mở đúng trang và nói rõ; không phải lỗi chặn.
        return {"rects": [], "confidence": 0.0, "matched": 0, "method": None, "error": str(e)}
    result["pdf_page"] = pdf_page
    return result


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
