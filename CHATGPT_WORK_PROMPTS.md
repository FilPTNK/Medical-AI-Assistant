# Bộ prompt giao việc cho ChatGPT Work — Trợ lý Fil (Antigravity Medical Assistant)

Ngày lập: 2026-09-24. Nhánh: `fix/retrieval-and-stability`.

ChatGPT **chỉ làm trong môi trường của nó**: không chạy được app, không có dữ liệu
sách, không có mô hình embedding, không có khoá DeepSeek. Vì vậy mọi gói việc dưới
đây được thiết kế để **làm và kiểm được bằng đọc mã, mock, và lý lẽ có dẫn chứng**;
phần nào chỉ chạy được trên máy của bạn thì ChatGPT phải ghi rõ "chưa kiểm chứng".

## Cách dùng

1. Tải `medical-assistant-source.zip` (chỉ mã nguồn, ~6 MB, **không có `.env`**, không có `backend/data/`) lên ChatGPT.
2. Mở một cuộc trò chuyện mới, dán **PROMPT NỀN** (mục A). Chờ nó xác nhận đã đọc xong.
3. Mỗi gói việc (mục B) dán vào **một lượt riêng** trong cùng cuộc trò chuyện, hoặc cuộc mới kèm lại prompt nền. Không dán gộp nhiều gói một lượt: chất lượng tụt rõ.
4. Nhận về patch + ghi chú, áp trên máy bạn (mục C), chạy lệnh kiểm chứng, rồi báo lại Claude Code nếu cần sửa.

Thứ tự khuyến nghị: **WP1 → WP3 → WP2 → WP6 → WP4 → WP5 → WP7.** WP1 và WP3 chạm phần lõi nên làm trước; WP5 sửa `App.jsx` nên làm sau WP4 để khỏi xung đột.

---

## A. PROMPT NỀN (dán đầu tiên)

~~~
Bạn là kỹ sư phần mềm cao cấp kiêm chuyên gia RAG tiếng Việt, đang nhận bàn giao dự án
"Trợ lý Fil" — trợ lý tra cứu y văn cho bác sĩ phòng khám ở Việt Nam. Tệp đính kèm
medical-assistant-source.zip là TOÀN BỘ mã nguồn (không có dữ liệu sách, không có mô hình,
không có khoá API). Hãy giải nén và đọc trước khi trả lời. Trả lời bằng tiếng Việt; tên
kỹ thuật, tên hàm, lệnh để nguyên tiếng Anh.

## Môi trường THẬT của người dùng (để bạn không đề xuất thứ chạy không nổi)
- Windows 11, Python 3.14, Node + Vite 5, React 18. MỘT ổ SSD 238 GB, còn ~24 GB trống.
- RAM tổng 7,3 GB và thường chỉ còn 0,3–1 GB trống (trình duyệt của bác sĩ ăn nhiều).
  Hệ điều hành đã nhiều lần tự giết tiến trình nền vì thiếu RAM. => mọi đề xuất phải
  tiết kiệm RAM; không đề xuất nạp thêm mô hình lớn, không đề xuất chạy nhiều tiến trình.
- Không có GPU. Không có Docker. Không có mạng ổn định để tải mô hình lớn.
- Bạn KHÔNG chạy được app. Bạn KHÔNG có dữ liệu. Nếu một kết luận cần chạy thật mới biết,
  hãy nói "chưa kiểm chứng, cần chạy: <lệnh>" thay vì khẳng định.

## Kiến trúc
- Backend: FastAPI (backend/main.py, ~2500 dòng), ChromaDB (SQLite) + LangChain, BM25
  (rank_bm25) + dense (intfloat/multilingual-e5-small, 384 chiều, cosine, tiền tố query:/passage:),
  hợp nhất RRF (k=60). LLM ngoài: DeepSeek qua HTTP (backend/llm_client.py).
- Frontend: React/Vite, MỘT file khổng lồ frontend/src/App.jsx (~6.600 dòng) + vài component.
  Xác thực Bearer token, window.fetch bị vá trong frontend/src/lib/apiClient.js.
- Kho tài liệu (3 cuốn, 33.490 child chunk): DTQGVN-2022-Q1 (7.144 chunk, thuốc A–Hydroxyzin),
  DTQGVN-2022-Q2 (7.638 chunk, Ibuprofen–Zolpidem; trang in đánh số LIÊN TỤC từ Q1, thân sách
  trang in 885–1778), THUOC-BIET-DUOC-VA-CACH-SU-DUNG.pdf (18.708 chunk, tra theo tên biệt dược).
- Mỗi tài liệu có manifest JSON (backend/documents.py) là nguồn sự thật duy nhất cho số trang,
  tên, tập, phạm vi. Chunk nạp qua backend/ingest_book.py (id tất định theo nội dung, upsert).
- Tài liệu bác sĩ tự tải lên đi qua backend/generic_ingest.py (mới): đọc lớp chữ từng trang,
  trang nào < 40 ký tự thì OCR bằng Tesseract (vie+eng), cắt theo trang, nạp qua ingest_book.
  Chạy nền trong thread, tiến độ qua SSE (backend/ingest_jobs.py, job lưu trong RAM).

## Quy ước dự án (bắt buộc theo)
- Chú thích trong mã bằng TIẾNG VIỆT và chỉ để giải thích VÌ SAO (ràng buộc ẩn, lỗi đã đo được),
  không giải thích cái mã đang làm. Không viết chú thích nhiều đoạn dài cho việc hiển nhiên.
- Không thêm thư viện mới trừ khi có lý do đo được; nếu thêm, nêu tên, kích thước, và cách
  chạy mà không cần thêm RAM đáng kể.
- Không thêm tương thích ngược thừa, không thêm cờ tính năng, không thêm tầng trừu tượng
  "phòng xa". Sửa đúng chỗ, giữ diff nhỏ.
- Nguyên tắc chứng cứ của dự án (xem HANDOFF.md và cách viết của nó): phân biệt rõ
  "ĐO ĐƯỢC" / "SUY RA" / "CHƯA AI ĐO". Không bịa số liệu, không bịa nguồn, không bịa tên nghiên cứu.
- An toàn lâm sàng: KHÔNG tự viết kiến thức y khoa (liều, chỉ định, tương tác) như sự thật.
  Mọi nội dung y khoa bạn tạo (vd. bộ câu hỏi đánh giá) phải gắn nhãn "CẦN DƯỢC SĨ DUYỆT".
- Không đụng vào backend/data/, .env, khoá API, hay thứ gì liên quan dữ liệu bệnh nhân.

## Trạng thái hiện tại (ghi đè HANDOFF.md nếu mâu thuẫn — HANDOFF.md cũ hơn, còn ghi 25.852 chunk và chỉ Q1)
ĐÃ XONG trong phiên gần nhất, ĐỪNG báo lại như lỗi:
- Nạp Q2; gộp tab "Thư viện" + "Đối chiếu" (chọn nhiều + thanh hành động nổi);
  hệ tự nạp PDF (generic_ingest + SSE); bỏ tab Giới thiệu, bỏ báo cáo Paracetamol mẫu, bỏ tin chào mẫu.
- page_map.py: cận offset trang in theo pdf_pages (quyển 2 đánh số liên tục).
- VectorStore.db có khoá (trước đây hai request đồng thời dựng Chroma chồng nhau làm hỏng client).
- VectorStore lấy dữ liệu theo lô 500 (get() một lượt cho 33k chunk vượt trần 32.766 biến SQLite
  => "too many SQL variables" làm hỏng cả Thư viện lẫn tra cứu).
- HF_HOME ép về backend/data/hf_cache trong config.py (biến môi trường máy trỏ ổ D: rời; khi ổ
  vắng, mô hình không nạp được => corpus rỗng => search() trả [] => giao diện báo
  "Không tìm thấy đoạn y văn nào khớp" cho MỌI câu hỏi). Chạy offline khi đã có model.
- Chat: nếu search() rỗng mà db.is_warm() là False thì báo "chỉ mục chưa sẵn sàng", không nói "không khớp".

CÒN MỞ (cơ sở của các gói việc bên dưới):
- search() vẫn trả [] khi hạ tầng hỏng; chỉ đường chat được vá. Các đường khác (search_drug_book,
  /api/compare, tra cứu thuốc) vẫn không phân biệt "hỏng" với "không khớp".
- Truy vấn theo TRIỆU CHỨNG cho kết quả trung bình: "thuốc giảm đau bụng" ra ALKA-SELTZER, DIMETICON,
  ROFECOXIB, KAOLOGEAIS, MEBEVERIN (hạng 3 là rofecoxib đáng ngờ). Truy vấn theo TÊN thuốc thì tốt
  ("Ibuprofen" => 5/5 đúng Q2 tr.885). Chunk theo mục (INDICATIONS, DOSAGE…) chưa được dùng để tăng điểm.
- Khởi động nguội mất 60–155 s (dựng BM25 33k chunk ~76 s). Có bm25_tokens.pkl nhưng chưa rõ mức tận dụng.
- Chạy script CLI ghi Chroma (ingest_book.py) trong lúc server đang chạy đã từng làm hỏng chỉ mục FTS5
  của chroma.sqlite3 (đã sửa bằng rebuild). Chưa có rào chắn nào chống lặp lại.
- Pipeline tự nạp PDF chưa được gia cố: không giới hạn kích thước/số lượng, job chỉ ở RAM (mất khi
  restart), xoá tài liệu đang nạp chưa xử lý, OCR 4 luồng có thể vượt RAM, chưa có test nào.
- Kiểm tra giao diện: không có test React nào; chỉ có node frontend/contrast_check.mjs và npm run build.
- Chưa làm: rà soát UX toàn app có dẫn chứng (mới làm phần gộp thư viện).

## Định dạng sản phẩm bàn giao (áp cho MỌI gói việc)
1. Mỗi gói: một tệp patch unified diff áp được bằng `git apply` từ gốc repo (đường dẫn a/… b/…).
   Tệp mới thì đưa nguyên nội dung. Sửa quá ~60% một tệp thì đưa nguyên tệp mới thay vì diff.
2. Kèm NOTES.md ngắn cho gói đó: (a) đã đổi gì và VÌ SAO, (b) rủi ro/đánh đổi, (c) lệnh để tôi
   tự kiểm chứng trên máy, (d) danh sách những thứ bạn KHÔNG kiểm chứng được.
3. Test viết bằng pytest, chỉ dùng mock/fake cho chromadb, torch, sentence_transformers,
   pytesseract, DeepSeek. Test phải chạy được trong môi trường không có các thư viện nặng đó.
   Nếu môi trường của bạn chạy được test, hãy chạy và dán kết quả thật; nếu không, nói rõ.
4. Trước khi trả patch, tự đọc lại: tên hàm có tồn tại trong zip không, import có vòng lặp không,
   chữ ký hàm có khớp nơi gọi không. Liệt kê những gì đã tự đối chiếu.
5. Không làm việc của gói khác. Gặp lỗi ngoài phạm vi thì ghi vào mục "Phát hiện ngoài phạm vi"
   trong NOTES.md, không tự sửa.

Xác nhận bằng đúng một câu: đã đọc xong zip, nêu 5 tệp bạn thấy quan trọng nhất và một điều
bạn thấy rủi ro nhất. Chưa làm gì thêm cho đến khi tôi giao gói việc.
~~~

---

## B. CÁC GÓI VIỆC

### WP1 — Độ bền của truy xuất và chỉ mục  (ưu tiên cao nhất)

~~~
GÓI WP1 — Độ bền của truy xuất và chỉ mục.

Vấn đề gốc: khi mô hình embedding hoặc Chroma không nạp được, VectorStore.search() trả []
âm thầm, và bác sĩ đọc thành "không có y văn nào khớp" — một lỗi hạ tầng bị hiểu thành câu
trả lời sai. Đã vá riêng đường chat trong backend/main.py (nhánh `not sources and not db.is_warm()`).
Cần làm cho ĐÚNG và ĐỦ.

Đọc: backend/vector_store.py, backend/main.py (search_and_answer, search_drug_book,
compare_documents, list_documents, lifespan/_warm), backend/config.py.

Việc:
1. Đề xuất và viết chế độ suy giảm có kiểm soát: nếu embedding không nạp được, search() phải
   chạy BM25-only (corpus vẫn dựng được từ Chroma.get, không cần embedding) và trả kèm cờ
   "degraded": true + lý do, thay vì []. Chỉ trả [] khi thật sự không có corpus.
   Chú ý: VectorStore.db hiện yêu cầu self.embedding truthy mới dựng Chroma — nên tách đường đọc
   metadata/documents khỏi embedding nếu chromadb cho phép (đọc mã langchain_chroma để xác nhận,
   ghi rõ nếu không chắc).
2. Thống nhất một hợp đồng lỗi: hàm/exception phân biệt EMPTY_INDEX, EMBEDDING_UNAVAILABLE,
   NO_MATCH. Cập nhật MỌI nơi gọi search() (chat, drug report, compare, tìm trong tài liệu)
   để hiển thị đúng thông điệp tiếng Việt cho từng trường hợp.
3. Thêm GET /api/index/health (cần đăng nhập như các API khác): trả embedding_loaded,
   corpus_chunks, bm25_ready, docs [{doc_name, chunks}], degraded, lần dựng gần nhất và thời gian.
4. Rào chắn "một người ghi": ghi chunk vào Chroma (ingest_book.ingest, generic_ingest) khi server
   đang chạy ở tiến trình khác đã làm hỏng FTS5 một lần. Đề xuất cơ chế khoá tệp
   (backend/data/vector_db/.writer.lock, dùng msvcrt/portalocker-free stdlib) mà cả server lẫn
   CLI đều lấy khi ghi; CLI thấy khoá thì thoát với thông báo tiếng Việt rõ ràng.
5. Khởi động nguội: đọc cách bm25_tokens.pkl đang được dùng. Đề xuất (và viết) cách lưu/đọc
   corpus + BM25 để khởi động nguội < 30 s trên máy 7 GB, có kiểm tra "corpus đổi chưa" bằng
   dấu vân tay rẻ (số chunk + mtime chroma.sqlite3 + hash danh sách id), không bằng đọc lại toàn bộ.
   Ước lượng RAM đỉnh trước/sau bằng lập luận có số (vd. 33.490 chuỗi × độ dài trung bình).

Tiêu chí đạt: test pytest bằng FakeChroma/FakeEmbedding chứng minh: (i) embedding lỗi => search
trả kết quả BM25 + degraded=true; (ii) corpus rỗng => EMPTY_INDEX; (iii) không khớp => NO_MATCH
khác hẳn hai cái trên; (iv) hai thread gọi .db cùng lúc chỉ dựng Chroma một lần; (v) get theo lô
đúng số lô và không mất/nhân đôi phần tử ở biên (0, 499, 500, 501, 1000 phần tử).
Không được: đổi mô hình embedding, đổi tham số RRF, đổi schema metadata trong Chroma (đổi là phải
nạp lại 33k chunk).
~~~

### WP2 — Chất lượng truy vấn theo triệu chứng + bộ đánh giá

~~~
GÓI WP2 — Truy vấn theo triệu chứng ("thuốc giảm đau bụng") và bộ đánh giá.

Dữ kiện đo được: truy vấn theo tên thuốc tốt, truy vấn theo triệu chứng/chỉ định trung bình.
"thuốc giảm đau bụng" => ALKA-SELTZER, DIMETICON, ROFECOXIB, KAOLOGEAIS, MEBEVERIN.
Dược thư có chunk theo mục (field_type: INDICATIONS, DOSAGE, CONTRAINDICATION, ADR, PREGNANCY,
INTERACTION, PHARMACODYNAMICS…) và metadata drug_class, atc_code, generic_name.

Đọc: backend/vector_store.py (search, tokenize_text, expand_rare_compounds, RRF),
backend/dtqg_parser.py (BLOCK_SECTIONS, field_type), backend/text_fold.py,
eval/eval_set.py, eval/eval_set_holdout.py, eval/eval_run.py, HANDOFF.md mục 2.

Việc:
1. Chẩn đoán bằng đọc mã: vì sao truy vấn triệu chứng kém? Nêu tối đa 4 giả thuyết, xếp theo khả
   năng, mỗi giả thuyết kèm thí nghiệm rẻ nhất để kiểm (chạy được bằng eval/eval_run.py).
2. Thiết kế "hiểu ý truy vấn" nhẹ, KHÔNG dùng LLM ở khâu tìm (độ trễ + RAM + chi phí):
   phát hiện truy vấn dạng triệu chứng/chỉ định (từ khoá "thuốc … cho/điều trị/giảm/chữa …"),
   rồi (a) tăng trọng số chunk field_type INDICATIONS, (b) mở rộng đồng nghĩa có kiểm soát từ
   một bảng tay nhỏ, có cờ CẦN DƯỢC SĨ DUYỆT (vd. "đau bụng" ~ "co thắt", "đau quặn", "đau dạ dày",
   "chuột rút ruột"), (c) lọc/hạ hạng chunk có tên thuốc thuộc nhóm không liên quan khi
   drug_class cho biết. Viết bằng mã tất định, có đơn vị test.
3. Mở rộng bộ đánh giá: ~80 truy vấn tiếng Việt theo 4 nhóm (tên hoạt chất, tên biệt dược,
   triệu chứng/chỉ định, tình huống thận trọng: thai kỳ/suy gan/suy thận). Mỗi truy vấn ghi thuốc
   kỳ vọng nằm trong top-5 và thuốc "bẫy" không được nằm trong top-5. TOÀN BỘ nhãn kỳ vọng phải gắn
   "CẦN DƯỢC SĨ DUYỆT" — bạn không phải dược sĩ. Đặt theo đúng định dạng eval/eval_set.py.
4. Cách đo trước/sau: mở rộng eval/eval_run.py để in P@5 theo nhóm truy vấn, và in các truy vấn
   xấu đi so với bản trước (regression) — thay vì chỉ trung bình.

Tiêu chí đạt: tôi chạy `python eval/eval_run.py` trên máy và thấy số theo nhóm; thay đổi bật/tắt
được bằng một hằng số để so sánh. Cam kết bằng văn bản KHÔNG hứa mức cải thiện cụ thể nào trước khi đo.
Không được: sửa đè các nhãn trong eval_set.py hiện có; đổi RRF_K / trọng số cho vừa với vài truy vấn.
~~~

### WP3 — Gia cố pipeline tự nạp PDF của bác sĩ

~~~
GÓI WP3 — Rà soát và gia cố hệ thống tự nạp PDF.

Đọc: backend/generic_ingest.py, backend/ingest_jobs.py, backend/ocr_book.py (ocr_page),
backend/ingest_book.py, đoạn POST /api/documents/ingest và GET /api/documents/ingest/{job_id}/events
trong backend/main.py, DELETE /api/documents/{doc_name}, và handleFileUpload + uploadJobs trong
frontend/src/App.jsx.

Tìm và sửa (mỗi mục: mô tả lỗi cụ thể + kịch bản tái hiện bằng lời + cách sửa):
1. Giới hạn: kích thước tệp, số trang, số job chạy đồng thời (đề xuất 1 job OCR tại một thời điểm,
   hàng đợi cho phần còn lại), loại MIME thật (không chỉ đuôi .pdf), PDF mã hoá/hỏng.
2. Job chỉ ở RAM: server restart giữa lúc nạp => tệp PDF + manifest dở còn lại, giao diện mất
   tiến độ. Đề xuất cách dọn "tài liệu mồ côi" lúc khởi động (manifest có ingested_at = null và
   không có job sống) mà KHÔNG xoá nhầm tài liệu hợp lệ; và cách cho phép nạp lại.
3. Xoá tài liệu đang nạp; hai lần tải cùng tên (slugify_doc_name có race không?); tên tệp có ký tự
   lạ / quá dài / trùng phân biệt hoa-thường trên Windows.
4. Bộ nhớ: OCR_WORKERS=4 luồng Tesseract 300 DPI trên máy 7 GB. Ước lượng RAM đỉnh mỗi luồng
   (ảnh trang 300 DPI khổ A4) và đề xuất số luồng an toàn + cách hạ DPI theo cỡ trang.
5. Trang scan bị OCR ra rác: có thước đo chất lượng rẻ nào (tỉ lệ ký tự tiếng Việt hợp lệ, tỉ lệ
   từ có trong từ điển tối thiểu) để cảnh báo bác sĩ "trang X đọc kém" ngay trong thẻ tiến độ?
6. SSE qua proxy dev của Vite có thể gom đệm sự kiện. Đề xuất cách kiểm và cách khắc phục (heartbeat
   comment ":\n\n", tiêu đề) — ghi rõ phần nào chưa kiểm chứng.
7. Phân biệt tài liệu tự nạp với sách tham khảo trong giao diện Thư viện (huy hiệu, ai nạp, ngày).

Sản phẩm: patch + test pytest (mock pymupdf/pytesseract/ingest_book) cho: chọn OCR theo trang,
chia đoạn, dọn khi lỗi, tên tệp, hàng đợi. Không viết lại kiến trúc; sửa tại chỗ.
Không được: đổi định dạng chunk mà ingest_book.build_documents đã đọc (chunk_id, field_name, content,
page_in_file, pdf_page); thêm generic_name (sẽ làm chèn nhãn "THUỐC:" sai vào tài liệu không phải thuốc).
~~~

### WP4 — Rà soát UX có dẫn chứng (deep research)

~~~
GÓI WP4 — Rà soát UX toàn app, viết theo thang chứng cứ của dự án.

Đối tượng dùng: bác sĩ phòng khám nhỏ ở Việt Nam, dùng giữa giờ khám, thường trên laptop cỡ trung,
tập trung cao, ít kiên nhẫn với lỗi. Các tab hiện có: Thuốc, Thư viện (đã gộp Đối chiếu), Bệnh nhân,
Nhắc lịch, Thống kê, Chẩn đoán, và luồng Trò chuyện.

Đọc: frontend/src/App.jsx (theo từng tab), các component trong frontend/src/components/,
frontend/src/index.css (token màu, WCAG đã đo bằng frontend/contrast_check.mjs).

Việc:
1. Nghiên cứu (nếu môi trường của bạn duyệt được web thì dùng và TRÍCH NGUỒN có đường dẫn; nếu
   không duyệt được thì nói thẳng "không tra cứu được" và chỉ dùng kiến thức có thể kiểm chứng,
   tuyệt đối không bịa tên nghiên cứu/con số): UX phần mềm hỗ trợ quyết định lâm sàng, mệt mỏi vì cảnh
   báo, tải nhận thức, thiết kế màn hình cho người dùng bận, giao diện tìm kiếm tài liệu y khoa,
   độ tin cậy của trích dẫn trong RAG.
2. Khảo sát TỪNG tab theo đọc mã (nhãn, trạng thái rỗng, trạng thái lỗi, trạng thái đang tải, thứ tự
   thao tác, số lần bấm cho việc thường gặp, phím tắt, bàn phím/đọc màn hình, kích thước chạm).
3. Viết báo cáo theo đúng khung: mỗi phát hiện gắn nhãn ĐO ĐƯỢC / SUY RA / CHƯA CÓ, kèm nguồn hoặc
   kèm "đọc từ dòng X của tệp Y". Xếp ưu tiên theo (tần suất gặp × hậu quả) chứ không theo sở thích.
4. Với các việc rủi ro thấp + giá trị cao (nhãn, trạng thái rỗng/lỗi, a11y, thứ tự tab, thông điệp lỗi
   tiếng Việt): kèm patch cho frontend/src. Việc lớn hơn (đổi kiến trúc thông tin, thêm tab): chỉ đề
   xuất kèm phương án và đánh đổi, KHÔNG viết patch.

Sản phẩm: báo cáo Markdown ~1.500–2.500 từ + patch nhỏ + NOTES.md. Không dùng emoji.
Không được: đề xuất thư viện UI mới; đổi bảng màu (đã đo WCAG AA 66/66 cặp — nếu đổi phải nêu cách
chạy lại contrast_check.mjs); đổi hành vi nghiệp vụ.
~~~

### WP5 — Tách LibraryView khỏi App.jsx và thêm kiểm thử giao diện

~~~
GÓI WP5 — Tách phần Thư viện + Đối chiếu ra thành component và có kiểm thử.

Bối cảnh: frontend/src/App.jsx dài ~6.600 dòng; phần Thư viện (lưới/danh sách, chọn nhiều, thanh
"Đối chiếu N tài liệu", thẻ tiến độ nạp SSE) nằm lẫn trong đó, kèm CompareView.jsx.

Việc:
1. Tách một component frontend/src/components/LibraryView.jsx nhận props tường minh (documents,
   uploadJobs, highlightCounts, các handler…). CHỈ DI CHUYỂN mã, không đổi hành vi, không đổi tên class CSS.
2. Rút phần logic thuần (lọc/sắp xếp tài liệu, giới hạn 5 tài liệu khi chọn, tính phần trăm tiến độ,
   ghép câu mô tả kho) ra frontend/src/lib/library.js để test không cần DOM.
3. Đề xuất bộ test: Vitest cho lib/library.js (thêm devDependencies tối thiểu: vitest) và, nếu bạn
   cho rằng đáng, React Testing Library cho LibraryView. Nêu rõ thêm những gói nào và dung lượng.
4. Kiểm tra bằng đọc: mọi biến App.jsx còn dùng sau khi tách có bị thiếu prop không.

Tiêu chí đạt: nếu môi trường của bạn chạy được `npm install && npm run build`, dán kết quả thật; nếu
không, ghi "CHƯA BUILD" ở đầu NOTES.md và liệt kê từng biến/prop bạn đã tự đối chiếu.
Không được: đụng các tab khác; định dạng lại cả tệp (diff phải nhỏ và đọc được).
~~~

### WP6 — Rà soát prompt LLM và an toàn lâm sàng

~~~
GÓI WP6 — Prompt hệ thống, bám nguồn, và ranh giới an toàn.

Đọc: backend/llm_client.py (mọi prompt: trả lời y văn, báo cáo thuốc stream_drug_report, đối chiếu
generate_document_comparison, chẩn đoán/điều trị), backend/patient_context.py (khử danh trước khi gửi
ra ngoài), backend/drug_allergy.py (đối chiếu tất định), phần trích dẫn trong frontend/src/App.jsx
(renderMessageText, sourceCitation).

Việc:
1. Với từng prompt: liệt kê (a) yêu cầu bám nguồn có đủ chặt không, (b) chuyện gì xảy ra khi
   đoạn nguồn không trả lời được câu hỏi (mô hình có được phép nói "nguồn không đề cập"?), (c) định
   dạng trích dẫn [n] có ổn định không, (d) có chỗ nào khuyến khích mô hình thêm kiến thức ngoài nguồn.
2. Viết lại các prompt cần sửa. Giữ nguyên tên biến/đầu ra JSON mà mã hiện đọc (đọc kỹ nơi parse).
   Đưa bản trước/sau cạnh nhau kèm lý do từng thay đổi.
3. Bộ kiểm thử hồi quy KHÔNG cần gọi LLM: tệp JSON các ca (ngữ cảnh giả + câu hỏi) kèm tiêu chí chấm
   bằng quy tắc (có [n] hợp lệ; không có số liều xuất hiện mà không có trong ngữ cảnh; có câu "nguồn
   không đề cập" khi ngữ cảnh không liên quan) + hàm chấm bằng regex viết bằng Python để tôi chạy trên
   đầu ra thật của DeepSeek ở máy mình.
4. Rà chỗ khử danh: liệt kê mọi đường mà văn bản bệnh nhân có thể rời máy tới DeepSeek; nêu những chỗ
   khử danh còn hở (tên người trong ghi chú tự do, số điện thoại, địa chỉ). Chỉ đề xuất và viết test,
   không kết luận pháp lý.

Không được: viết kiến thức y khoa vào prompt như dữ kiện; đổi mô hình; thêm few-shot chứa thông tin
y khoa do bạn tự nghĩ ra.
~~~

### WP7 — Cập nhật tài liệu vận hành

~~~
GÓI WP7 — Cập nhật HANDOFF.md và viết RUNBOOK.md.

Việc:
1. Cập nhật HANDOFF.md cho khớp thực tế (kho 3 cuốn / 33.490 chunk; Q1 A–Hydroxyzin, Q2 Ibuprofen–
   Zolpidem; tab Thư viện đã gộp Đối chiếu; tự nạp PDF; cache HF trong dự án; các lỗi đã sửa ở phần
   "ĐÃ XONG" của prompt nền). Giữ giọng văn và cấu trúc cũ; số nào không có trong tài liệu hoặc mã thì
   ghi "chưa đo lại", không suy diễn.
2. Viết RUNBOOK.md ngắn cho người vận hành không chuyên: cách chạy trên máy 7 GB (thứ tự bật, dấu hiệu
   thiếu RAM, cách biết server "sẵn sàng"), cách nạp một cuốn sách mới (từng bước, lệnh thật trong repo),
   cách sao lưu/khôi phục backend/data/vector_db (kể cả sự cố FTS5 "malformed inverted index" và cách
   rebuild), quy tắc "không chạy CLI ghi Chroma khi server đang chạy", cách kiểm model đã có offline
   (backend/data/hf_cache/hub/models--intfloat--multilingual-e5-small/snapshots/…).
3. Liệt kê MỌI lệnh trong tài liệu mà bạn đã đối chiếu với tệp thật trong zip (tên script, tham số).
Không được: bịa tham số dòng lệnh không có trong argparse của script.
~~~

---

## C. Nhận kết quả về máy

```powershell
cd "C:\Users\HP\Desktop\Project\Antigravity - Medical Assistant"
git status                      # phải sạch phần ngoài các tệp bạn định sửa
git apply --check wp1.patch     # thử trước, không đổi gì
git apply wp1.patch
python -m py_compile backend\main.py backend\vector_store.py
cd frontend; npm run build; cd ..
node frontend\contrast_check.mjs
python eval\eval_run.py         # chỉ khi gói đó chạm truy xuất
```

Quy tắc khi nhận:
- Áp từng gói một và chạy kiểm chứng giữa các gói; đừng áp cả bảy rồi mới chạy.
- **Đừng chạy `ingest_book.py` trong lúc server đang chạy.** Đã từng làm hỏng chỉ mục FTS5.
- Thứ ChatGPT ghi "chưa kiểm chứng" thì coi là chưa kiểm chứng, cho tới khi bạn hoặc Claude Code chạy thật.
- Cần Claude Code xem lại patch nào khó áp: đưa nguyên patch + NOTES.md của gói đó.
