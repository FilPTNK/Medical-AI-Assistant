# Sổ tay vận hành — Trợ lý Fil

Tất cả lệnh bên dưới chạy trong **PowerShell tại thư mục gốc dự án** (nơi có
`run.py`). Đường dẫn là tương đối với thư mục đó. Chỉ mục, sách, mô hình và hồ
sơ bệnh nhân nằm trên máy của phòng khám; bản ZIP mã nguồn không chứa các dữ liệu
này. Số 33.490 là trạng thái được bàn giao, **chưa đo lại trên máy này**.

## Mở ứng dụng trên máy RAM 7,3 GB

1. Đóng bớt tab trình duyệt và chương trình nặng, bảo đảm còn chỗ trống trên ổ
   chứa dự án. Không mở hai bản ứng dụng cùng lúc.
2. Chạy `python run.py`. Lần đầu có thể cài Python/Node và tải model, cần
   mạng; lần sau chỉ cài lại Python nếu `requirements.txt` đổi. Runner mở
   backend trước, đợi HTTP từ `/api/auth/status`, rồi mở Vite. Đừng chạy thêm
   `python backend/dev_server.py` hoặc `npm run dev` khi runner còn mở.
3. Chờ thông báo `Backend đã sẵn sàng` và `App is launching`, mở
   `http://127.0.0.1:3000`. **HTTP sẵn sàng chưa có nghĩa chỉ mục đã nạp xong**:
   backend nạp corpus/BM25 và embedding trong luồng nền. Sau khi đăng nhập,
   nhấn F12 → Console trong tab ứng dụng, chạy
   `fetch('/api/index/health').then(r => r.json()).then(console.log)`:
   `bm25_ready=true`, `corpus_chunks` khác 0; `embedding_loaded=true`
   nếu muốn tìm dense đầy đủ. Nếu `degraded=true`, đọc `reason` và dùng
   thông báo BM25 suy giảm như tín hiệu kiểm tra lại, không coi là tra cứu đầy đủ.
   Endpoint này cần đăng nhập; mở URL trực tiếp không kèm token có thể trả 401.
4. Nếu backend tự thoát, máy ì, trình duyệt treo hoặc hệ điều hành đóng tiến
   trình, kiểm RAM trong Task Manager, đóng ứng dụng khác rồi khởi động lại.
   Nếu đã quá 180 giây, runner vẫn có thể mở giao diện dù backend chưa đáp ứng;
   lúc đó xem log backend và đừng suy diễn “không có tài liệu”.
5. Khi xong, nhấn **Ctrl+C trong cửa sổ chạy `run.py`**, đợi hai server tắt
   hẳn trước khi sao lưu, khôi phục hoặc chạy CLI ghi chỉ mục.

### Model khi không có mạng

Trong File Explorer, kiểm tra
`backend/data/hf_cache/hub/models--intfloat--multilingual-e5-small/snapshots/`
có thư mục snapshot và các tệp model thực sự đọc được. `config.py` ép
`HF_HOME` vào `backend/data/hf_cache`, không dùng cache ở ổ D: của máy.
Có thư mục snapshot **chỉ là dấu hiệu**, chưa bảo đảm tải đủ tệp; sau khi mở
app cần xem `embedding_loaded=true` và `degraded=false` ở health.
Nếu thiếu model, cần mạng hoặc bản cache hợp lệ cùng phiên bản model; đừng
đổi `EMBEDDING_MODEL` để chữa tạm vì vector cũ không tương thích model mới.

## Nạp sách

**Tài liệu thường, tối đa 64 MiB / 300 trang:** đăng nhập, vào **Thư viện** →
tải PDF lên; theo dõi tiến độ OCR/nạp tại đó, kiểm thẻ tài liệu và mở một trang
để so với PDF gốc. Job chạy trong chính server và cập nhật qua SSE; không mở
CLI Chroma. PDF vượt giới hạn, bị mã hoá hoặc hỏng sẽ bị từ chối. Tài liệu
upload được cắt theo trang, không bóc thành chuyên luận thuốc; kiểm lại độ
chính xác OCR và trích dẫn trước khi dùng.

**Sách chuyên luận Dược thư scan cần cấu trúc mục thuốc** (ví dụ quyển mới):

1. Tắt `run.py`; sao lưu theo mục dưới. Đặt PDF vào
   `backend/data/uploads/DTQGVN-2022-Q3.pdf`. ID chỉ là ví dụ; chọn ID ổn
   định, chưa tồn tại. Không dùng `migrate_phase0.py` để thêm quyển này:
   script ấy chỉ khai báo Q1 và sách Biệt dược.
2. Tạo `backend/data/documents/DTQGVN-2022-Q3.json` theo schema
   `documents.new_manifest` trong `backend/documents.py`: điền
   `doc_name`, `doc_title`, `short_title`, `source_pdf`,
   **số trang PDF kiểm từ tệp thật** vào `pdf_pages`, `doc_series`,
   `volume`, `coverage`, `parser: "dtqg_parser"`,
   `ocr: {"dpi": 300, "columns": 1, "lang": "vie+eng"}`,
   `body_page_range: null`, `chunk_count: 0`, `ingested_at: null`.
   Sao mẫu trường từ `documents.new_manifest`, không sao chép số trang/dải
   chuyên luận của Q1/Q2.
3. Chạy tuần tự, đóng các ứng dụng nặng trong lúc OCR/index:

   ```powershell
   python backend/ocr_book.py --doc-name DTQGVN-2022-Q3 --workers 1
   python backend/page_map.py --doc-name DTQGVN-2022-Q3
   python backend/dtqg_parser.py --doc-name DTQGVN-2022-Q3
   python backend/ingest_book.py --doc-name DTQGVN-2022-Q3
   ```

   OCR ghi `backend/data/ocr_text/<ID>/`; page map ghi
   `backend/data/page_map/<ID>.json` và cập nhật dải thân sách; parser ghi
   `backend/data/chunks/<ID>.json`; CLI cuối
   ghi Chroma và cập nhật manifest. Rà soát trang OCR, `body_page_range` và
   chunk JSON **trước** bước cuối, đặc biệt khi trang in đánh số liên tục
   qua các quyển. Số chunk mới, thời gian và độ chính xác: **chưa đo lại**.
4. Chạy `python run.py`, đăng nhập, kiểm `/api/index/health` và mở vài
   trích dẫn đúng quyển/trang gốc. Nếu tài liệu cũ cùng ID cần thay hẳn,
   `ingest_book.py` có `--replace`; chỉ dùng sau khi sao lưu và server
   đã tắt. Mặc định CLI upsert theo ID tất định, không tự xóa chunk cũ đã
   thay nội dung.

**Quy tắc tuyệt đối:** không chạy `backend/ingest_book.py` hay một CLI khác
ghi Chroma khi server đang chạy. Server giữ `.writer.lock` suốt vòng đời;
khóa CLI sẽ từ chối ghi đồng thời, nhưng vẫn phải tắt server trước. Việc tải
PDF qua Thư viện dùng chính tiến trình server nên là luồng hợp lệ.

## Sao lưu, khôi phục và lỗi FTS5

- **Sao lưu:** đóng runner, kiểm không còn server nền, rồi sao chép **cả thư
  mục** `backend/data/` sang ổ sao lưu (trong đó có `vector_db`,
  `documents`, `chunks`, `uploads`, OCR/page map, `hf_cache` và các
  `.db` của ứng dụng). Ví dụ từ gốc dự án, tạo sẵn `E:\SaoLuu` và chọn
  tên bản sao **chưa tồn tại** trên ổ còn đủ chỗ:

  ```powershell
  Copy-Item -LiteralPath "backend/data" -Destination "E:\SaoLuu\data-20260924" -Recurse
  ```

  Kiểm bản sao có `vector_db/chroma.sqlite3` và các thư mục segment; đừng chỉ
  sao chép một tệp SQLite khi server còn chạy. Với máy chỉ còn ít dung lượng
  ổ C:, dùng ổ sao lưu khác. `backend/data/` còn chứa hồ sơ bệnh nhân, giữ
  bản sao trong nơi được phòng khám quản lý.
- **Khôi phục:** tắt server, giữ nguyên thư mục hiện tại dưới tên khác để còn
  đường quay lại, rồi chép lại **toàn bộ** `data` từ bản sao cùng thời điểm.
  Ví dụ khi đã xác nhận bản sao tồn tại, và tên `data-truoc-khoi-phuc`
  **chưa tồn tại**:

  ```powershell
  Rename-Item -LiteralPath "backend/data" -NewName "data-truoc-khoi-phuc"
  Copy-Item -LiteralPath "E:\SaoLuu\data-20260924" -Destination "backend/data" -Recurse
  ```

  Mở lại app và kiểm sức khỏe chỉ mục, hồ sơ và trang trích dẫn. Tránh ghép
  `vector_db` đời này với manifests/chunks đời khác.
- **`malformed inverted index` (FTS5):** dừng app và **sao lưu nguyên hiện
  trạng bị lỗi** trước. Ưu tiên khôi phục toàn bộ `data` từ bản sao lành cùng
  thời điểm. Nếu không có, dựng lại **toàn bộ Chroma** từ các tệp
  `backend/data/chunks/<doc_name>.json` và manifest tương ứng; không sửa
  `chroma.sqlite3` trực tiếp và không chạy `REINDEX` mò bảng:

  ```powershell
  python backend/ingest_book.py --doc-name DTQGVN-2022-Q1 --persist-dir backend/data/vector_db_rebuild
  python backend/ingest_book.py --doc-name DTQGVN-2022-Q2 --persist-dir backend/data/vector_db_rebuild
  python backend/ingest_book.py --doc-name THUOC-BIET-DUOC-VA-CACH-SU-DUNG.pdf --persist-dir backend/data/vector_db_rebuild
  ```

  Nạp tiếp **mọi** ID khác có manifest `ingested_at` và tệp chunks (bao gồm
  sách/tài liệu tự upload) bằng cùng cú pháp `--doc-name ID --persist-dir
  backend/data/vector_db_rebuild`; đừng bỏ sót. Trong lúc dựng staging, CLI
  cập nhật `chunk_count` và `ingested_at` ở manifest gốc; giữ bản sao
  `data` để đối chiếu nếu có lỗi. Khi cả ba lệnh và mọi tài liệu bổ sung
  hoàn thành, **vẫn để server tắt**, kiểm tên `vector_db-loi` chưa tồn tại,
  chuyển nguyên thư mục bị lỗi đi và đặt staging vào chỗ cũ:

  ```powershell
  Rename-Item -LiteralPath "backend/data/vector_db" -NewName "vector_db-loi"
  Rename-Item -LiteralPath "backend/data/vector_db_rebuild" -NewName "vector_db"
  ```

  Mở lại `python run.py`, kiểm health và tra thử trích dẫn mỗi cuốn. Dựng
  index cần model embedding trong cache hoặc mạng, thời gian/dung lượng **chưa
  đo lại** trên máy 7 GB; nếu thiếu một tệp chunk hoặc model thì dừng, khôi
  phục bản sao, không dùng index thiếu sách.

## Tài liệu riêng và tài liệu chung

- Bác sĩ tải PDF lên ở Thư viện thì tài liệu nằm trong **kho riêng của tài
  khoản đó**. Chỉ người tải thấy, tìm, đối chiếu và xoá được; quản trị cũng
  không thấy.
- Quản trị phòng khám tải lên thì tài liệu là **tài liệu chung**. Ai cũng thấy,
  chỉ quản trị xoá được. Sách nạp bằng script (Dược thư, Thuốc Biệt Dược) cũng
  là tài liệu chung.
- Phạm vi ghi trong manifest `backend/data/documents/<doc_name>.json`, ở hai
  trường `visibility` (`private`/`shared`) và `owner_id`. Manifest không có
  `visibility` được coi là tài liệu chung. Muốn chuyển một tài liệu riêng thành
  tài liệu chung thì sửa `visibility` thành `shared` rồi khởi động lại.

Lịch sử tra cứu, đoạn tô sáng và ghi chú tài liệu cũng là của riêng từng
tài khoản (`owner_id` trong `library.db`, do máy chủ gắn theo phiên đăng nhập).
Lần khởi động đầu tiên sau khi cập nhật, máy chủ gắn chủ cho dữ liệu cũ theo tên
người tạo đã lưu, chỉ khi tên đó khớp đúng một tài khoản. Dòng không khớp (tên
trống, tài khoản thử "smoke") vẫn nằm trong tệp nhưng không ai thấy nữa. Việc
gắn này chỉ chạy một lần, đánh dấu trong bảng `migrations`.

## Tìm thêm trên web

Nút **Web** cạnh ô hỏi ở tab Tra y văn. Mặc định nút tắt, bác sĩ bật khi cần.
Mã nằm ở `backend/web_tools.py`. Biến trong `.env`, tất cả đều tuỳ chọn:

```
TAVILY_API_KEY=      # tìm web trong trang y khoa tin cậy; miễn phí 1.000 lượt/tháng ở tavily.com
NCBI_API_KEY=        # PubMed: 3 -> 10 lượt/giây
OPENFDA_API_KEY=     # nhãn thuốc FDA: 1.000 -> 120.000 lượt/ngày
WEB_SEARCH_ENABLED=1 # đặt 0 để tắt hẳn và ẩn nút
WEB_SEARCH_DOMAINS=  # danh sách tên miền cho Tavily, cách nhau bằng dấu phẩy
```

Không đặt khoá nào thì PubMed, nhãn FDA và ClinicalTrials.gov vẫn chạy, chỉ
thiếu ô tìm web chung. Câu hỏi được gửi tới DeepSeek để chọn công cụ và dịch
sang tiếng Anh, rồi tới các dịch vụ trên. Không có dữ liệu hồ sơ bệnh nhân nào
đi kèm, nhưng nếu bác sĩ gõ tên người bệnh vào câu hỏi thì chữ đó vẫn đi ra
ngoài. Giao diện có nhắc điều này khi nút đang bật.

## Đối chiếu lệnh với mã

| Lệnh trong tài liệu | Tệp và tham số đã kiểm |
|---|---|
| `python run.py` | `run.py:main`; có nhận diện `--reinstall` khi cài lại dependency (không cần dùng ở đây). |
| `python backend/dev_server.py` | `backend/dev_server.py` có entry point không có argparse; nêu để tránh mở hai server. |
| `npm run dev` | `frontend/package.json` có script `dev`; `run.py:run_frontend` cũng gọi nó. |
| `python backend/ocr_book.py --doc-name ID --workers 1` | `backend/ocr_book.py:main` khai báo `--doc-name`, `--workers`; mặc định PDF từ manifest. |
| `python backend/page_map.py --doc-name ID` | `backend/page_map.py:main` khai báo `--doc-name`. |
| `python backend/dtqg_parser.py --doc-name ID` | `backend/dtqg_parser.py:main` khai báo `--doc-name`. |
| `python backend/ingest_book.py --doc-name ID [--persist-dir DIR] [--replace]` | `backend/ingest_book.py:main` khai báo `--doc-name`, `--chunks`, `--replace`, `--batch-size`, `--persist-dir`; trong ví dụ chỉ dùng những cờ có thật. |
| `python backend/migrate_phase0.py` (không dùng để thêm Q3) | `backend/migrate_phase0.py:main` chỉ tạo Q1/sách Biệt dược; tùy chọn duy nhất `--dry-run`. |
| `python backend/parse_biet_duoc.py --doc-name ID` | `backend/parse_biet_duoc.py:main` có `--doc-name`, `--out`, `--monograph-pages`. |
| `node frontend/contrast_check.mjs` | `frontend/contrast_check.mjs` chạy trực tiếp, không khai báo cờ; đọc token CSS. |
| `cd frontend`, `npm run build`, `cd ..` | `frontend/package.json` có script `build`; `cd` là lệnh PowerShell. |
| `python eval/allergy_run.py [--sweep]` | `eval/allergy_run.py` kiểm `--sweep` trong `sys.argv`; các số 3.816/55 là lần đo cũ. |
| `python eval/eval_run.py [--set both] [--sweep] [--persist-dir DIR]` | `eval/eval_run.py:main` khai báo đủ ba cờ (`--set` có các lựa chọn `main/holdout/both/wp2/all`); chạy không cờ mặc định `all`. |
| `python eval/calibrate_similarity.py` | `eval/calibrate_similarity.py:main` không có argparse; chạy trực tiếp khi model/index sẵn. |
| `python run.py --reinstall` | `run.py:setup_dependencies` kiểm `--reinstall` trong `sys.argv`; không phải cờ argparse. |
| `eval/deid_run.py` | Tệp có trong `eval/`, chỉ được nhắc như một phép thử lịch sử trong HANDOFF; không có lệnh chạy/flag trong hướng dẫn mới. |
| `Copy-Item`, `Rename-Item` | Lệnh có sẵn của PowerShell, **không phải** CLI của repo; kiểm tên thư mục đích trên máy trước khi chạy. |
| `export MSYS_NO_PATHCONV=1`, `curl`, `git rm -r --cached` | Mục 9 HANDOFF là các ví dụ **lịch sử** của Git Bash/git, không phải script/flag của repo và không nằm trong quy trình RUNBOOK. |
| `GET /api/auth/status`, `GET /api/index/health` | `run.py:wait_for_backend`, `backend/main.py`; endpoint thứ hai cần đăng nhập. |
| `fetch('/api/index/health').then(r => r.json()).then(console.log)` | JavaScript trình duyệt; `frontend/src/lib/apiClient.js:installAuthFetch` tự gắn Bearer token sau đăng nhập, endpoint ở `backend/main.py`. |

Với sách Biệt dược cần parser riêng, repo có
`backend/parse_biet_duoc.py --doc-name ID` (tùy chọn `--out`,
`--monograph-pages`); **không** chạy `batch_process_book.py` hay
`ingest_metadata_to_vectordb.py` đã được ghi là thay thế.

## Đợt thiết kế lại 2026-10-28 — ba chức năng

- App chỉ còn **Hỏi đáp y khoa · Chẩn đoán · Tra cứu thuốc**. Đã gỡ Bệnh nhân, Nhắc lịch,
  Thống kê (frontend + route backend). Tệp dữ liệu cũ `backend/data/patients.db`,
  `patients.json`, `patient_attachments/` **không bị xoá** — chỉ không còn được đọc.
- **Tô sáng trích dẫn trên trang gốc**: `POST /api/documents/{doc}/pages/{trang_in}/locate`
  (`backend/page_locate.py`). Sách scan: lần đầu mở một trang phải OCR lại trang đó
  (~5–8 s), kết quả cache ở `backend/data/page_words/`.
- **Hỏi về tài liệu này**: `/api/search` nhận thêm `doc_name`, `near_page`.
- **Chẩn đoán**: ô "Tình trạng bệnh nhân trước đó (không bắt buộc)" thay cho chọn hồ sơ;
  bốn endpoint `/api/diagnosis-tree/*` nhận `patient_history` thay cho `patient_id`.
- **Reranker (tắt mặc định)**: đặt `RERANKER_MODEL=BAAI/bge-reranker-v2-m3` (hoặc
  `AITeamVN/Vietnamese_Reranker`) và tải model trước khi bật; đo độ trễ trên máy phòng khám.
- **Tài liệu bổ sung**: `python backend/library_sources.py` (liệt kê, kèm giấy phép),
  `--download` để tải về `backend/data/incoming/`, rồi nạp qua "Sách & tài liệu gốc" → Tải lên.
