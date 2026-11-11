# Kế hoạch đưa Trợ lý Fil lên Internet — frontend trên Vercel

Soạn ngày 2026-10-07. Frontend đã chạy trên Vercel. Các bước dành cho máy chủ
backend bên dưới là kế hoạch. Số liệu Vercel và giá máy chủ cần đối chiếu trước
khi chọn gói.

---

## 0. Kết luận trước

Frontend chạy trên Vercel. Backend Fil cần ổ đĩa bền để giữ tài khoản, chỉ
mục và tài liệu:

| Backend cần | Vercel Functions có |
|---|---|
| Ghi `backend/data/` (Chroma 434 MB, SQLite, PDF 1,8 GB, OCR, cache model 471 MB) | Ổ đĩa tạm, mất sau mỗi lần gọi |
| Một tiến trình sống liên tục: luồng nạp sẵn, `writer_lock` suốt vòng đời, job nạp PDF giữ trong RAM | Hàm khởi động–tắt theo request |
| Model `multilingual-e5-small` + BM25 33k chunk nằm sẵn trong RAM, PyMuPDF, Tesseract | Giới hạn kích thước gói và bộ nhớ hàm |

Kiến trúc chọn:

```
Trình duyệt bác sĩ
      │  https://fil.<ten-mien>        (một origin duy nhất)
      ▼
┌──────────────────────────┐
│ Vercel                   │  /            → dist/ của Vite (tĩnh)
│  vercel.ts               │  /api/*       → proxy sang backend
└──────────┬───────────────┘
           │  https://api.fil.<ten-mien>/api/*
           ▼
┌──────────────────────────┐
│ Máy chủ (VPS 8 GB RAM)   │  Caddy (TLS, chặn request thiếu secret)
│  Docker: uvicorn 1 worker│  ──► FastAPI main.py
│  Volume: /app/backend/data│  Chroma, SQLite, PDF, OCR, hf_cache
└──────────────────────────┘
           │
           ▼  DeepSeek / Resend / PubMed / Tavily (như hiện nay)
```

**Vì sao proxy qua Vercel thay vì cho trình duyệt gọi thẳng `api.…`:**
`frontend/src/lib/apiClient.js` chỉ gắn header `Authorization` cho request
**cùng origin** bắt đầu bằng `/api/` (hàm `apiPathOf`). Giữ cùng origin thì
**không phải sửa dòng frontend nào**, không cần CORS, và 111 lời gọi
`fetch('/api/...')` trong mã vẫn đúng.

---

## 1. Những điều cần chốt trước khi bắt tay

1. **Tên miền.** Cần một tên miền (ví dụ `fil-clinic.vn`) với hai bản ghi:
   `fil.` trỏ Vercel, `api.` trỏ IP máy chủ.
2. **Nơi đặt backend.** Đề xuất: **VPS 4 vCPU / 8 GB RAM / 80 GB SSD tại Việt
   Nam hoặc Singapore**.
   - Nhà cung cấp trong nước (Viettel IDC, FPT Cloud, VNPT, BizFly…): dữ liệu
     sức khoẻ ở lại Việt Nam — dễ trả lời hơn khi bị hỏi theo Nghị định
     13/2023/NĐ-CP. Đây là lựa chọn nên ưu tiên.
   - Hoặc DigitalOcean / Vultr / Linode vùng Singapore: rẻ, nhiều tài liệu.
   - 8 GB vì máy hiện tại 7,3 GB đã chạy sát (RUNBOOK); OCR khi nạp PDF ăn
     thêm RAM.
3. **Gói Vercel.** Gói Hobby chỉ cho dùng cá nhân, phi thương mại; phòng khám
   là dùng thương mại → **Vercel Pro**. Kiểm lại điều khoản lúc đăng ký.
4. **Ai được vào.** Hiện `/api/auth/register` cho **bất kỳ ai có email** tự tạo
   tài khoản. Chạy nội bộ thì vô hại; lên Internet thì người lạ tạo được tài
   khoản, đọc tài liệu chung và tiêu tiền khoá DeepSeek. Phải chọn một:
   tắt tự đăng ký (quản trị tạo tài khoản ở Quản trị phòng khám — đề xuất),
   hoặc bắt quản trị duyệt.
5. **Đồng ý của phòng khám** về việc hồ sơ bệnh nhân rời máy phòng khám. Thiết
   kế hiện nay hứa “dữ liệu nằm trên máy của phòng khám” (RUNBOOK). Đổi lời hứa
   đó là quyết định của bác sĩ, không phải của kỹ thuật.

> Phương án thay thế nếu bác sĩ không muốn dữ liệu rời phòng khám: xem mục 9.

---

## 2. Giai đoạn A — Sửa mã cho môi trường Internet

Thứ tự trong giai đoạn này là thứ tự nên làm. Mỗi mục là một commit riêng.

### A1. Cấu hình theo biến môi trường (backend/config.py, main.py)

| Biến mới | Mặc định (giữ hành vi cũ) | Trên máy chủ |
|---|---|---|
| `ALLOWED_ORIGINS` | `*` | `https://fil.<ten-mien>` |
| `ORIGIN_SECRET` | rỗng = tắt kiểm | chuỗi 64 hex ngẫu nhiên |
| `REGISTRATION_ENABLED` | `1` | `0` |
| `EXPOSE_API_DOCS` | `1` | `0` (tắt `/docs`, `/openapi.json`) |
| `HOST` | `127.0.0.1` | `0.0.0.0` (trong container) |

- `main.py:104` đang `allow_origins=["*"]` **cùng** `allow_credentials=True` —
  đổi sang đọc `ALLOWED_ORIGINS`.
- Thêm middleware: nếu `ORIGIN_SECRET` có giá trị thì request thiếu hoặc sai
  header `x-origin-secret` → 403 (so sánh bằng `hmac.compare_digest`). Mục đích:
  không ai gọi thẳng `api.…` bỏ qua Vercel.
- Thêm middleware gắn `Cache-Control: no-store` cho **mọi** phản hồi `/api/*`.
  Từ 06/04/2026 Vercel mặc định **cache phản hồi proxy theo header của
  backend**; hồ sơ bệnh nhân tuyệt đối không được nằm trong CDN.
- `REGISTRATION_ENABLED=0` → ba endpoint `/api/auth/register*` trả 403, và
  `/api/auth/status` báo thêm cờ để `LoginScreen.jsx` ẩn nút đăng ký.

### A2. Giới hạn đăng nhập sai

`/api/auth/login` hiện không có giới hạn số lần thử. Thêm khoá tạm theo
tên đăng nhập + IP (lấy từ `x-real-ip` do Vercel gửi kèm, chỉ tin khi
`x-origin-secret` đúng), ví dụ 5 lần sai / 15 phút.

### A3. Các request có thể vượt 120 giây — **rủi ro chính**

Vercel đợi backend **tối đa 120 giây cho byte đầu tiên**; sau đó luồng được
giữ nếu cứ dưới 120 giây lại có dữ liệu. Quá hạn → 504.

| Đường | Tình trạng |
|---|---|
| `/api/search` (chat chảy dần) | An toàn: trần cứng 60 s, chữ chảy liên tục. |
| `/api/documents/ingest/{id}/events` (SSE nạp PDF) | An toàn nếu heartbeat < 120 s — đã có heartbeat (WP3), kiểm chu kỳ. |
| `/api/drugs/report` (chảy dần) | Kiểm byte đầu < 120 s. |
| `/api/diagnosis-tree/*`, `/api/compare`, `ai-diagnosis` | **Không chảy dần.** `LLM_TIMEOUT` read=120 s và `max_retries=1` → một lần gọi có thể tới ~240 s. Agent ReAct (`agent.py`) gọi DeepSeek tới **4 vòng**. |

Việc cần làm: đo thời gian thật của các endpoint nhóm cuối trên dữ liệu thật.
Nếu có ca > 90 s thì chọn một trong hai:
- gửi khoảng trắng/heartbeat sớm rồi trả JSON ở cuối (đổi sang
  `StreamingResponse`, frontend đọc hết rồi `JSON.parse`), hoặc
- tạo job + hỏi trạng thái (giống mẫu `ingest_jobs.py`).
Ít nhất phải hạ tổng thời gian chờ của agent về dưới 110 s.

### A4. Tải PDF 64 MiB qua proxy

Tài liệu Vercel **không ghi giới hạn dung lượng body** cho rewrite ra ngoài.
Phải thử thật ở giai đoạn E (mục E4). Nếu bị chặn: thêm một đường tải lên trực
tiếp `https://api.…/api/documents/ingest` có CORS chỉ cho origin của Vercel,
và cho `apiClient.js` gắn token cho đúng origin đó (biến `VITE_API_ORIGIN`).

### A5. Đóng gói Docker

`backend/Dockerfile` (phác thảo):

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-vie tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
ENV HOST=0.0.0.0 PORT=8000 PYTHONUNBUFFERED=1
EXPOSE 8000
# MỘT worker, KHÔNG reload: job nạp PDF ở RAM, writer_lock và luồng nạp sẵn
# đều giả định đúng một tiến trình.
CMD ["python", "start_server.py"]
```

- `start_server.py` đã chạy `reload=False`, một worker — dùng lại được.
- Không `COPY` thư mục `data/` vào image: nó là volume (mục B).
- Kiểm `backend/tessdata` (bảng chữ đang dùng) có cần thay gói apt không.
- `docker-compose.yml` ở gốc: service `backend` + `caddy`, volume
  `./data:/app/backend/data`, `restart: unless-stopped`, `env_file: .env.production`.

### A6. Frontend

Khi FastAPI đã chạy trên HTTPS, đặt biến môi trường `FIL_BACKEND_ORIGIN`
trong project Vercel thành origin của máy chủ, ví dụ `https://api.example.com`,
rồi triển khai lại frontend. `frontend/vercel.ts` chuyển tiếp `/api/*` sang
FastAPI và tắt cache cho các phản hồi API. Kiểm tra `GET /api/auth/status`
qua tên miền Fil sau khi triển khai.

Proxy trong `vite.config.js` phục vụ môi trường local. Biến
`FIL_BACKEND_ORIGIN` chỉ dùng khi tạo cấu hình triển khai Vercel.

### A6b. SQLite cho nhiều người dùng cùng lúc

Sáu module `*_db.py` mở SQLite bằng `sqlite3.connect(DB_PATH)` mặc định:
chế độ journal `DELETE` (đang ghi thì người khác không đọc được) và chờ khoá
tối đa 5 s rồi báo `database is locked`. Chạy một máy thì không lộ; nhiều bác
sĩ dùng qua link cùng lúc thì có thể gặp. Sửa ở hàm `_connect()` của từng
module (hoặc gom về một hàm chung):

```python
conn = sqlite3.connect(DB_PATH, timeout=15)
conn.execute("PRAGMA journal_mode=WAL")    # đọc không bị chặn khi có người ghi
conn.execute("PRAGMA busy_timeout=15000")
```

WAL sinh thêm tệp `-wal`/`-shm` cạnh mỗi `.db`: sao lưu vẫn phải dừng
container rồi chép **cả thư mục** như mục 7.

### A7. Kiểm lại trên máy trước khi đẩy

```powershell
python -m unittest discover -s tests -q
cd frontend; npm test; npm run build; cd ..
docker compose up --build        # chạy thử với một BẢN SAO data
```

---

## 3. Giai đoạn B — Dựng máy chủ

1. Tạo VPS Ubuntu 24.04 LTS, đăng nhập bằng SSH key, **tắt đăng nhập mật khẩu**.
2. Tường lửa (`ufw`): chỉ mở 22 (SSH), 80, 443. **Không mở 8000.**
3. Cài Docker + Docker Compose plugin.
4. `Caddyfile`:
   ```
   api.fil.<ten-mien> {
       @nosecret not header x-origin-secret {env.ORIGIN_SECRET}
       respond @nosecret 403
       reverse_proxy backend:8000 {
           flush_interval -1        # không đệm SSE / chữ chảy dần
       }
       request_body { max_size 70MB }
   }
   ```
   Caddy tự lấy chứng chỉ TLS. Chặn ở đây và cả ở middleware A1 — hai lớp.
5. `.env.production` trên máy chủ (quyền `600`, không commit): `DEEPSEEK_*`,
   `RESEND_*`, `GOOGLE_CLIENT_ID`, `TAVILY_API_KEY`…, cộng các biến ở A1.
   **Dùng khoá DeepSeek mới**, không dùng lại khoá đang nằm trong `.env` máy bác sĩ
   (config.py ghi khoá cũ từng lộ trong lịch sử git).

---

## 4. Giai đoạn C — Chuyển dữ liệu

1. Trên máy bác sĩ: tắt `run.py`, sao lưu `backend/data/` theo RUNBOOK.
2. Chép sang máy chủ **trừ** hai bản sao lưu cũ (~540 MB):
   `vector_db_backup_before_fts_repair_*`, `vector_db_minilm_backup_*`.
   Còn lại khoảng **2,5 GB**. Ví dụ:
   ```bash
   rsync -avz --progress \
     --exclude 'vector_db_*backup*' \
     backend/data/ user@may-chu:/srv/fil/data/
   ```
   (Trên Windows dùng WSL hoặc nén thành `.zip` rồi `scp`.)
3. `hf_cache` đi kèm → máy chủ chạy offline với model, không phải tải lại.
4. Từ thời điểm này **máy chủ là bản chính**. Không mở `run.py` trên máy bác sĩ
   để ghi bệnh án nữa, nếu không hai bản sẽ lệch nhau.

---

## 5. Giai đoạn D — Dựng project Vercel

1. Import repo GitHub vào Vercel.
2. **Root Directory:** `frontend`. Framework preset: **Vite**.
   Build: `npm run build`. Output: `dist`. Node 20.
3. Biến môi trường (Production + Preview): `ORIGIN_SECRET` (cùng giá trị máy chủ).
4. Thêm domain `fil.<ten-mien>`, trỏ DNS theo hướng dẫn của Vercel.
5. **Bản Preview (mỗi nhánh/PR) cũng proxy tới backend thật** với cùng secret.
   Bật **Deployment Protection** (Vercel Authentication) cho Preview để người
   ngoài không mở được.
6. Google Login (nếu dùng): thêm `https://fil.<ten-mien>` vào *Authorized
   JavaScript origins* trong Google Cloud Console.
7. Resend: xác minh domain riêng để gửi thư từ `no-reply@<ten-mien>` thay vì
   `onboarding@resend.dev`.

---

## 6. Giai đoạn E — Nghiệm thu (làm đủ mới báo bác sĩ dùng)

| # | Kiểm | Đạt khi |
|---|---|---|
| E1 | `curl https://api.fil.<ten-mien>/api/auth/status` không kèm secret | 403 |
| E2 | Mở `https://fil.<ten-mien>`, đăng nhập | Vào được; `/api/index/health`: `bm25_ready=true`, `embedding_loaded=true`, `degraded=false`, `corpus_chunks` ≈ trên máy cũ |
| E3 | Tra y văn một câu | Chữ chảy dần, có `[n]`, mở đúng trang trích dẫn (ảnh trang hiện) |
| E4 | Tải lên PDF **~60 MiB** ở Thư viện | Upload qua; tiến độ SSE chạy tới cuối, không 504 |
| E5 | Cây chẩn đoán 4 bước + gợi ý chẩn đoán AI cho lần khám | Không bước nào 504; ghi thời gian từng bước |
| E6 | Đối chiếu 5 tài liệu, báo cáo thuốc | Như E5 |
| E7 | Xuất PDF bệnh án, giấy chuyển tuyến; tải tệp đính kèm | Tải được, đúng nội dung |
| E8 | Header phản hồi `/api/patients` | Có `cache-control: no-store`; `x-vercel-cache` không phải `HIT` |
| E9 | Tạo tài khoản mới từ màn hình đăng nhập | Không còn đường tự đăng ký (nếu đã chốt tắt) |
| E10 | Link chia sẻ `/?share=…` ở cửa sổ ẩn danh | Mở được bản chỉ đọc |
| E11 | Tài khoản `doctor` A mở bệnh nhân của B | Bị từ chối |
| E11b | 3–5 người cùng lưu lần khám / ghi chú trong một phút | Không ai gặp lỗi `database is locked` |
| E12 | Khởi động lại container giữa lúc nạp PDF | App lên lại; job dở được dọn (WP3), không hỏng Chroma |

---

## 7. Vận hành sau khi chạy

- **Sao lưu hằng đêm:** dừng container vài phút (Chroma/SQLite không chép
  nóng an toàn — RUNBOOK), nén `/srv/fil/data`, đẩy sang nơi lưu khác (bucket
  của nhà cung cấp, mã hoá). Giữ 14 bản. Thử khôi phục mỗi tháng một lần.
  Thêm snapshot ổ đĩa của VPS nếu nhà cung cấp có.
- **Cập nhật mã:** frontend tự deploy khi merge `main`. Backend:
  `git pull && docker compose up -d --build` — app tắt vài chục giây và nạp
  lại model (~20–35 s); làm ngoài giờ khám.
- **Nạp sách Dược thư mới bằng CLI** (RUNBOOK): chạy trong container với
  backend đã dừng: `docker compose stop backend` →
  `docker compose run --rm backend python ocr_book.py …` → … → `start`.
- **Theo dõi:** UptimeRobot (hoặc tương tự) gọi `/api/auth/status` qua Vercel
  mỗi 5 phút; cảnh báo ổ đĩa > 80 %; xem log `docker compose logs -f backend`.
- **Rollback frontend:** Vercel → Deployments → Promote bản cũ.
  **Rollback backend:** giữ tag image cũ; dữ liệu khôi phục từ bản sao đêm trước.

---

## 8. Chi phí ước tính (kiểm lại lúc mua)

| Hạng mục | Khoảng |
|---|---|
| Vercel Pro | 20 USD/tháng/thành viên |
| VPS 4 vCPU / 8 GB | 10–50 USD/tháng tuỳ nhà cung cấp và vùng |
| Lưu trữ sao lưu ~50 GB | 1–3 USD/tháng |
| Tên miền `.vn` | vài trăm nghìn đồng/năm |
| DeepSeek, Resend, Tavily | Như hiện nay, theo lượng dùng |

---

## 9. Phương án thay thế: dữ liệu ở lại phòng khám

Nếu bác sĩ không muốn hồ sơ rời máy phòng khám: **giữ backend trên máy hiện
tại**, mở đường ra Internet bằng **Cloudflare Tunnel** (không phải mở cổng
router), frontend vẫn trên Vercel với `FIL_BACKEND_ORIGIN` trỏ tới tên miền của
tunnel.

- Được: dữ liệu không rời phòng khám, không tốn tiền VPS, bỏ qua giai đoạn C.
- Mất: máy phải bật 24/7; RAM 7,3 GB vốn đã sát; điện/mạng phòng khám rớt là
  app rớt; sao lưu vẫn phải tự làm.
- Các mục A1–A4, A6, D, E vẫn phải làm y nguyên.

---

## 10. Những việc kế hoạch này KHÔNG giải quyết

- Khử danh dữ liệu gửi DeepSeek vẫn còn lỗ (WP6: ô gõ tự do chưa khử danh).
  Lên Internet không làm việc này tốt hơn hay tệ hơn, nhưng nên làm trước.
- Job nạp PDF vẫn nằm trong RAM; khởi động lại là mất job đang chạy.
- Chỉ chạy được **một** tiến trình backend; không mở rộng ngang được nếu không
  thay Chroma/SQLite bằng dịch vụ có máy chủ riêng.
- Đánh giá pháp lý đầy đủ theo Nghị định 13/2023 về dữ liệu sức khoẻ.
