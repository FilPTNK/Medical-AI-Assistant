# Bàn giao — Antigravity Medical Assistant

Cập nhật: 2026-09-12 (đợt giao diện). Nhánh: `fix/retrieval-and-stability`.
Toàn bộ số liệu dưới đây là **đo được**, không phải ước lượng, trừ chỗ ghi rõ.

Đợt 2026-09-12 làm **giao diện** (mục 2b). Đợt 2026-09-05 làm **#4, #5, #2**
và ý tưởng "cân RRF" của bàn giao trước.

Kế hoạch bốn đợt đã chốt với bác sĩ sau năm vòng phỏng vấn:
**1 giao diện (xong) → 2 không bao giờ treo → 3 tiền sử vào chẩn đoán →
4 trình xem tài liệu.**

---

## 1. Hệ thống

FastAPI + React/Vite + Chroma + DeepSeek. RAG tiếng Việt cho phòng khám.

- Kho: **25.852 child chunk**, **3.816 thuốc**, 2 nguồn:
  - `THUOC-BIET-DUOC-VA-CACH-SU-DUNG.pdf` — tra theo *tên biệt dược*
  - `DTQGVN-2022-Q1` — Dược thư Quốc gia, **chỉ quyển 1, chữ A–H** (352 thuốc)
- Truy xuất lai: dense (Chroma HNSW, **cosine**) + BM25 + hợp nhất RRF (k=60, 1:1)
- Embedding: **`intfloat/multilingual-e5-small`**, 384 chiều, `max_seq_length=512`,
  vector chuẩn hoá, tiền tố `query:` / `passage:`
- Chạy: `python run.py` (backend 8000, Vite 3000). Backend riêng: `python backend/dev_server.py`

---

## 2. Chất lượng truy xuất — trạng thái hiện tại

P@5 trên hai bộ truy vấn trong `eval/`. "Trước" = đầu đợt này, "sau" = hiện tại.

| | bộ chính: trước | bộ chính: sau | bộ giữ riêng: trước | bộ giữ riêng: sau |
|---|---|---|---|---|
| BM25 | 92,0% | **100,0%** | 88,0% | 88,0% |
| DENSE | 78,0% | **90,0%** | 72,0% | **94,0%** |
| **RRF (kết quả thật)** | **90,0%** | **100,0%** | **80,0%** | **98,0%** |
| bẫy-nhầm (RRF) | 4,0% | **0,0%** | 0,0% | 0,0% |

Truy vấn "thuốc hạ sốt" — bài toán gốc của cả hai đợt — nay **100%**, không còn
thuốc sốt rét nào trong top-5.

**Điểm liên quan** (`similarity_search_with_relevance_scores`):
`-1,897 … -2,211` kèm cảnh báo *"must be between 0 and 1"* → **`0,913 … 0,896`**,
hết cảnh báo.

Backend sẵn sàng phục vụ sau **17,2s** (đợt trước 27,1s).

---

## 2b. Giao diện — đợt 2026-09-12

### Cách kiểm chứng

```
node frontend/contrast_check.mjs      # 33 cặp màu x 2 chế độ, thoát 1 nếu hỏng
cd frontend && npm run build          # dựng thật, bắt lỗi cú pháp JSX/CSS
```

Hiện **66/66 cặp đạt WCAG AA**, không bỏ sót cặp nào. Script đọc thẳng token
trong `index.css` nên đổi màu là chạy lại có số ngay. Đây là phép kiểm **duy
nhất** cho giao diện — không có test React nào.

### Bảng màu

Xanh dương `#2563eb` → xanh mòng két `#0b7a94` (sáng) / `#4cbbd4` (tối).

> Xanh `#0891B2` mà ui-ux-pro-max đề xuất **chỉ đạt 3,68:1 trên nền trắng**,
> không dùng được cho chữ. Bản đang dùng tối hơn, đạt 5,03:1.

**Chế độ tối được làm ngang chế độ sáng.** Ban đầu tưởng nó là mã chết và định
bỏ qua; đăng nhập vào mới thấy app mở ra ở chế độ tối — đó là thiết lập đang
lưu của tài khoản bác sĩ.

### Ba nguyên nhân của cảm giác "đơn điệu"

1. `--bg-app` và `--bg-card` **đều là `#ffffff`**, phân tách bằng đúng một viền
   1px. Nay nền vùng làm việc khác sắc độ với nền thẻ. Cộng lớp nền không phẳng
   đặt ở `.main-workspace::before`: chuyển sắc nhẹ (sáng) / hoa văn chấm nối
   **tĩnh** (tối). Dùng lớp giả chứ không phải nền nhiều lớp vì các panel con
   tự tô nền của mình, nên hoa văn không bao giờ lọt xuống dưới bảng số liệu.
2. Mọi tiêu đề trong tab Bệnh nhân đều **15px/700**. Nay ba bậc:
   `--title-page` 28px, `--title-section` 17px, `--title-rail` 12,5px in hoa.
3. Màu chỉ để trang trí: **ô Dị ứng luôn đỏ kể cả khi trống.** Xem dưới.

### Màu phải mang nghĩa — và cái bẫy trong đó

Ô trống nay về trung tính, chỉ ô có dữ liệu thật mới mang màu, kèm **vạch dày
bên trái** để người mù màu cũng phân biệt được. Thẻ "Cảnh báo y tế" tự thăng
lên cỡ chữ cột chính khi thật sự có cảnh báo.

**Phép thử không thể chỉ là truthy.** Trong `patients.db` có bệnh nhân với
`allergies` bằng đúng chuỗi `"Không có"` — một chuỗi truthy. Nếu chỉ xét truthy
thì bệnh nhân KHÔNG dị ứng vẫn hiện ô đỏ, và lỗi cũ quay lại nguyên vẹn.
`hasClinicalValue()` trong `App.jsx` nhận diện các câu phủ định **nguyên vẹn,
viết trọn**, và cố ý không đoán xa hơn: *"không dị ứng penicillin đã biết"* vẫn
là thông tin lâm sàng thật và phải giữ màu cảnh báo.

### Token và mã màu viết cứng

`index.css`: **131 mã màu viết cứng → 6**, cả 6 đều cố ý và đã ghi chú tại chỗ
(nền khối mã luôn tối vì highlight.js chỉ có bảng màu cho nền tối; nền giấy
trắng sau ảnh scan; vài sắc độ dẫn xuất).

Token mới đáng chú ý: **`--text-on-fill`**. Chữ trắng trên nút ở chế độ tối chỉ
đạt **2,26:1**, vì mọi mảng màu đặc ở chế độ đó đều *sáng*. Một giá trị tối
dùng chung cho cả bốn màu ngữ nghĩa, thấp nhất 7,97:1.

`LoginScreen.css` và `SettingsDialog.css` trước đây có bảng màu **riêng** (vàng
hổ phách; xanh ChatGPT), nay dẫn xuất từ token chung. `LoginScreen.css` còn
**0** mã màu viết cứng.

### Phông

**Be Vietnam Pro**, nhúng vào bản dựng qua `@fontsource` (`main.jsx`), không
gọi Google Fonts — phòng khám có thể mất mạng và chữ sẽ nhảy phông giữa lúc
đang khám. Bản dựng có đủ 4 trọng lượng × bộ ký tự **vietnamese**.

> **Figtree mà ui-ux-pro-max đề xuất KHÔNG có dấu tiếng Việt.** Dùng nó là mọi
> chữ có dấu rơi sang phông dự phòng và màn hình lẫn lộn hai phông.

### Màn hình khởi động

Trước: `#root` rỗng, **không một dòng CSS** cho tới khi gói JS tải xong →
khoảng **11 giây màn hình trắng trơn**. Nay màn khởi động nằm thẳng trong
`index.html`, hiện từ byte đầu, có tên app, thanh tiến trình và **nói thật đang
chờ gì** ("Đang nạp mô hình tra cứu y văn…", sau 75s thì gợi ý chạy lại).
Lớp `dark` đặt trước khi vẽ để không loé trắng một nhịp.

Thanh tiến trình **cố ý không có phần trăm**: một thanh phần trăm bịa ra sẽ
đứng ở 90% rồi treo, tệ hơn là không có gì.

### `run.py` không còn nói dối về "sẵn sàng"

Trước: chỉ mở socket tới cổng 8000. Hai cách nó nói dối, **cả hai đã gặp thật**:
một tiến trình backend **cũ** còn sống vẫn giữ cổng đó (runner in "sẵn sàng sau
0s" trong khi backend mới chưa nạp xong); hoặc cổng mở nhưng uvicorn còn đang
nạp mô hình nên mọi request đều treo. Nay đợi một **phản hồi HTTP thật** từ
`/api/auth/status`.

### Chưa làm trong đợt này

- **Chưa tách file.** `App.jsx` vẫn 6.7k dòng. Thay đổi đợt này gần như toàn bộ
  nằm ở CSS cộng vài chỗ JSX nhỏ, nên tách file sẽ là tách thứ mình không sửa —
  đúng cái bác sĩ đã bảo đừng làm.
- **`DashboardView.css` giữ nguyên bảng màu biểu đồ** (10 mã màu). Tab Thống kê
  không nằm trong ba tab của đợt này, và màu chuỗi biểu đồ là một hệ riêng cần
  đo lại theo nền mới.
- **`IntroExperience.css`** cố ý giữ thế giới tối riêng; chỉ đổi màu nhấn cho
  cùng họ.
- **Bộ ảnh chụp "sau" chưa đủ.** Chrome treo vì máy hết RAM (xem mục 6b) nên
  chỉ chụp được tab Bệnh nhân chế độ sáng. Ảnh "trước" thì đủ cả 6.

---

## 3. Đã làm đợt này (2026-09-05)

### Đính chính một con số của bàn giao trước

Bàn giao trước ghi BM25 = 96,0%. **Sai, số thật là 92,0%.** Bộ đo cũ chia điểm
cho *số kết quả trả về* thay vì cho 5. BM25 chỉ trả nổi 1 chunk cho "thuốc ho"
nên được chấm 1/1 = 100% — tức là **thưởng cho việc không tìm ra gì**. Bộ đo mới
luôn chia cho 5.

### Cân RRF + mở rộng từ ghép hiếm (không cần index lại)

- pyvi gộp "thuốc ho" thành một token `thuốc_ho` có **df = 1** trên 25.852
  chunk, nên cả truy vấn còn đúng một token hiếm và BM25 chỉ trả nổi 1 chunk.
  Token ghép có `df < 10` nay được bổ sung thêm âm tiết, **chỉ ở phía truy vấn**
  — corpus vẫn giữ token ghép nên không làm sống lại va chạm "sốt" mà #3 đã sửa.
  Ngưỡng phải thấp hơn df của `hạ_sốt` (22): đo được ngưỡng ≥50 làm tụt về 96%.
- Trọng số RRF: có đặt 1,5 nghiêng về BM25, **rồi gỡ ra**. Xem mục 4.

### #5 — tên thuốc: chuẩn hoá và gắn cờ, KHÔNG xoá, KHÔNG đoán

Bàn giao trước gọi việc này là "lọc rác parser". **Tiền đề đó sai** — đọc thẳng
nội dung thì thấy:

- Chunk mang tên rác vẫn chứa **dữ liệu thuốc thật**: `- ALIMEMAZIN` đúng là
  chuyên luận alimemazin, `AL 400` là albendazol 400mg, `566 C80` là atovaquon
  (mã nghiên cứu của chính thuốc đó). **Xoá là mất thuốc thật khỏi kho.**
- Ký tự đầu bị OCR thay (`3AMBUTEROL` = BAMBUTEROL) **không tự sửa được**. Đã
  thử và đo hai cách:
  - suy từ vần (sách xếp theo bảng chữ cái): đúng **91,5%** trên 3.522 tên lành
  - đối chiếu từ điển tên thuốc: đo lần đầu ra 100%, nhưng phép đo đó **rò rỉ**
    vì từ điển dựng từ chính tên đang thử. Loại tên đó ra rồi đo lại — đúng tình
    huống thật, vì tên hỏng chỉ xuất hiện một lần ở dạng đã hỏng:
    **đúng 0 · SAI 7 · không quyết 493** (mẫu 500). Bảy lần nó quyết thì sai cả
    bảy: COCAIN→ROCAIN, CHIAMIN→THIAMIN, PHYTIN→THYTIN.

Một trợ lý y khoa đổi tên COCAIN thành ROCAIN nguy hiểm hơn hẳn việc để nguyên
một cái tên đọc không ra. Nên việc thật sự làm:

- `backend/drug_name.py` — cắt rác dấu câu ở rìa (giữ ngoặc đơn, vì
  `ATROPIN (dùng toàn thân)` là tên thật) và `is_suspect_name()` gắn cờ.
- Cắt rác ở **đầu** thì luôn gắn cờ: không phân biệt được `.AMEFLU` (tên nguyên)
  với `-EFAZOLIN` (mất chữ C). Cắt cả hai thì cái sau thành `EFAZOLIN` — một cái
  tên trông rất chỉnh mà lại sai, **tệ hơn** `-EFAZOLIN` vì nhìn không ra là hỏng.
- Đo trên 25.852 chunk: chuẩn hoá **485 (1,9%)**, gắn cờ **1.152 (4,5%)**.
- Cờ đi tới nơi dùng được: `search()` trả kèm `name_suspect`, và `llm_client`
  chèn cảnh báo vào đúng đoạn ngữ cảnh đó — nếu không, model sẽ trích dẫn chuỗi
  rác như `3AMBUTEROL` y hệt một tên thuốc có thật.

> Chưa làm: hiện cảnh báo trên giao diện. `to_search_result()` dựng
> `SearchResultItem` theo từng trường nên cờ chưa lọt ra API — thêm vào model đó
> là xong.

### #4 + #2 — cosine, vector chuẩn hoá, đổi embedding (một lần index lại)

- `hnsw:space="cosine"` + `normalize_embeddings=True`. Chỉ mục cũ **không đặt
  space** nên Chroma dùng L2 mặc định.
- `paraphrase-multilingual-MiniLM-L12-v2` → `intfloat/multilingual-e5-small`.
  Vẫn 384 chiều nên schema không đổi; `max_seq_length` 512 thay vì 128, xoá hẳn
  chuyện 35,9% chunk bị cắt cụt.
- Họ e5 **bắt buộc** tiền tố `query:` / `passage:`; `HuggingFaceEmbeddings` không
  tự thêm nên có lớp bọc `PrefixedEmbeddings` (chỉ thêm khi tên model chứa "e5",
  để đổi ngược về model cũ vẫn chạy được).
- Index lại 25.852 chunk mất **25,6 phút**, dựng ở thư mục riêng rồi chấm điểm
  xong mới thay chỉ mục đang chạy.

**Ba việc kéo theo — không có thì đổi model xong là hỏng lặng lẽ:**

1. Vector câu hỏi cũ (sinh bởi model cũ) vẫn bị đem tính cosine với vector mới →
   ra một số vô nghĩa. Thêm cột `embedding_model`, chỉ so khi trùng model.
2. **Ngưỡng** "câu hỏi tương tự": e5 nén điểm lên cao — hai câu *khác chủ đề* vẫn
   ở 0,84–0,92 — nên ngưỡng 0,55 cũ sẽ coi mọi câu hỏi là gần nghĩa. Nay 0,92,
   đo bằng `eval/calibrate_similarity.py`.
3. Cache token BM25 khoá theo **id** chunk, mà id dẫn xuất từ content chứ không
   từ tên thuốc. Chuẩn hoá tên (#5) làm text đổi trong khi id giữ nguyên ⇒ cache
   báo "còn khớp" và trả token của corpus cũ. Khoá nay phủ cả nội dung.

Ngoài ra `config.EMBEDDING_MODEL` trước mặc định `all-MiniLM-L6-v2` — model
**thuần tiếng Anh** mà không chỗ nào đọc tới, vì `vector_store` tự hard-code model
riêng; đặt `EMBEDDING_MODEL` trong `.env` vì thế không có tác dụng gì. Nay là
nguồn duy nhất.

---

## 4. Bài học đáng giữ: miếng vá và cái gốc

Giữa đợt có đặt `RRF_W_SPARSE = 1,5` để nghiêng về BM25. Lúc đó dense mới đạt
78% so với 92% của BM25 nên trộn 1:1 kéo kết quả xuống dưới cả BM25 đứng một
mình; nghiêng về BM25 nâng bộ giữ riêng từ 80% lên 92%. **Số liệu ủng hộ.**

Đổi sang e5 xong thì dense lên 94% và **vượt** BM25 trên bộ câu hỏi tự nhiên.
Đo lại: `w=1,0` cho **98%**, còn `w≥1,2` chỉ còn 94%. Tức là trọng số kia là
**miếng vá cho một nhánh dense yếu, không phải tính chất của bài toán** — sửa
đúng gốc rồi thì phải gỡ vá ra, nếu không nó quay lại làm hỏng.

Đổi model lần nữa thì quét lại: `python eval/eval_run.py --sweep`.

---

## 5. Cách đo

Bộ đo nay **nằm trong kho** (`eval/`), không còn ở scratchpad của phiên.

```
python eval/eval_run.py                            # cả hai bộ, chỉ mục đang chạy
python eval/eval_run.py --sweep                    # quét trọng số RRF
python eval/eval_run.py --persist-dir <thư mục>    # chấm một chỉ mục dựng thử
python eval/calibrate_similarity.py                # chọn ngưỡng "câu hỏi tương tự"
```

- `eval/eval_set.py` — 10 truy vấn từ khoá, giữ nguyên từ đợt trước để số liệu
  còn so sánh được.
- `eval/eval_set_holdout.py` — 10 câu hỏi đặt theo **lời người bệnh**, viết
  *trước* khi chọn tham số. Đây là chỗ dense lẽ ra phải giỏi hơn BM25, nên nó là
  phép thử thật cho mọi thay đổi nghiêng về một nhánh.
- Luôn đọc cả **ba** nhánh: một thay đổi có thể nâng nhánh này mà hạ nhánh kia.
- **P@5 chia cho 5**, không chia cho số kết quả trả về (xem mục 3).
- Kết quả `db.search()` dùng khoá **`child_text`** (chunk khớp), không phải
  `content` (không tồn tại) hay `text` (là parent text).

---

## 6b. Máy này sắp không chạy nổi app

**Backend bị hệ điều hành giết hai lần trong một phiên làm việc**, mã thoát
`4294967295` (tức là bị kết liễu từ ngoài, không phải tự thoát). Đo được:

| | |
|---|---|
| RAM tổng | 7,3 GB |
| RAM trống khi app chạy | **1,01 GB** |

Backend phải nạp torch + `multilingual-e5-small` + Chroma, nhiều hơn 1 GB. Cuối
phiên Chrome cũng treo, không chụp nổi màn hình nữa.

Đây **không phải** vấn đề của mã nguồn và không sửa được bằng mã. Nhưng nếu nó
xảy ra giữa lúc đang khám thì nặng hơn mọi thứ trong kế hoạch bốn đợt. Cần đóng
bớt chương trình trước khi mở app, hoặc thêm RAM.

---

## 6. Còn phải làm

### Quan trọng nhất: nạp nốt Dược thư quyển 2 trở đi

Đang thiếu monograph của **Paracetamol, Ibuprofen, Omeprazol…** — Dược thư mới
có chữ A–H. `generic_name` chứa "PARACETAMOL": **0 / 3.816 thuốc**. Không thuật
toán nào tìm được tài liệu không tồn tại; đây giờ là trần chất lượng thật sự,
không còn nằm ở khâu truy xuất.

### Ba đợt còn lại đã chốt với bác sĩ

**Đợt 2 — không bao giờ treo.** `/api/search` hiện **không timeout, không hủy
được, không stream**: DeepSeek treo là vòng xoay quay vĩnh viễn. Đã chốt: timeout
10s cho khâu tìm và 60s cho LLM; đo thời gian từng khâu; chuyển sang SSE như
`/api/drugs/report` đã làm; nút hủy, không tự thử lại. Hỏng thì **vẫn trả nguồn
trích dẫn** kèm câu báo máy chủ tạm thời không hoạt động — bác sĩ không bao giờ
ra về tay trắng; chi tiết kỹ thuật chỉ hiện ở chế độ phát triển.
Xoá luôn dòng chữ nói dối ở `main.py:1512`: kết quả tra y văn vẫn tự xưng được
xếp hạng bởi Cross-Encoder, mà reranker đã gỡ từ lâu (`vector_store.py:139`).

**Đợt 3 — tiền sử vào chẩn đoán.** `App.jsx:6139` có ô chọn bệnh nhân và tooltip
ghi "kết hợp tiền sử bệnh", nhưng `handleGenerateTree` (`App.jsx:2411`) **chỉ
gửi đúng `description`**. Tooltip đang nói sai sự thật. Ngược lại
`agent.run_diagnostic_agent` thì đã đọc tiền sử rồi — hai đường không nối nhau.
Đã chốt: tiền sử **nạp sẵn**, không để agent tự quyết có gọi tool hay không
(câu lệnh hệ thống chỉ *dặn* "luôn gọi", đó là lời khuyên chứ không phải ràng
buộc; quên đọc dị ứng penicillin là một dạng hỏng im lặng). Đi vào **cả bốn
bước**. **Bỏ tên và mã hồ sơ trước khi gửi ra DeepSeek** — áp dụng cho cả đường
`ai-diagnosis` đang có. Hiện rõ AI đã đọc gì. Bác sĩ bấm nút mới ghi vào bệnh án.

**Đợt 4 — trình xem tài liệu.** Hộp thoại hiện có đúng sáu nút: tải xuống, đóng,
đánh dấu, ghi chú, hai mũi tên. **Trên quyển 913 trang.** Thứ tự đã chốt:
nhảy tới trang và tìm chữ trong tài liệu **trước** (không tới được trang thì
không có gì để kiểm chứng), rồi hai cột ảnh scan + text OCR, rồi trích dẫn mở
thẳng đúng trang. Endpoint ảnh scan đã có sẵn (`main.py:1967`) nhưng giao diện
chưa dùng tới.

### Nhỏ hơn

- Hiện cờ `name_suspect` trên giao diện (thêm trường vào `SearchResultItem`).
- Chất lượng OCR trong **nội dung** (không phải tên): "Giảm dau", "Ha nhiệt",
  "Thdn trong". Một mẫu dò thận trọng bắt được 3,9% chunk, **soi tay cho thấy tỉ
  lệ thật cao hơn, chưa đo chính xác.** Chưa đụng tới đợt này.
- Hai truy vấn còn dưới 100% ở bộ giữ riêng: "bị đau đầu thì uống thuốc gì"
  (60%) và "trẻ em bị tiêu chảy dùng thuốc nào" (80%).
- Bộ đo mới có 20 truy vấn — đủ để bắt hồi quy, **quá nhỏ để tin vào chênh lệch
  1–2 điểm**. Muốn tinh chỉnh tiếp thì phải mở rộng bộ đo trước.

---

## 7. Trạng thái git & dữ liệu

```
f0cc98c  Đo sau khi index lại: gỡ trọng số RRF, chốt ngưỡng tương tự 0,92
a48afe9  Đưa cờ name_suspect ra tới kết quả tìm kiếm và ngữ cảnh LLM
f519615  #4+#2 Chuyển sang multilingual-e5-small, cosine và vector chuẩn hoá
cf7c6d0  #5 Chuẩn hoá tên thuốc và gắn cờ tên hỏng OCR — không xoá, không đoán
3c15c82  Nghiêng RRF về BM25 và mở rộng từ ghép hiếm; đưa bộ đo vào kho
2780ef4  Thêm HANDOFF.md — báo cáo bàn giao        <- đầu đợt này
```

Nhánh `fix/retrieval-and-stability`, **chưa merge vào `master`**.

**Chỉ mục cũ giữ lại để lùi được:**
`backend/data/vector_db_minilm_backup_20260905_154559/` (304 MB). Xoá được khi
đã yên tâm — nhưng muốn lùi thì phải đổi **cả** `config.EMBEDDING_MODEL` về
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, vì chỉ mục đó
sinh bằng model cũ.

---

## 8. Việc còn treo từ đợt trước

**Khoá API `sk-b877...` vẫn chưa thu hồi trên dashboard DeepSeek.** Khoá đã
không còn trong mã nguồn lẫn lịch sử git, nhưng xoá lịch sử trên máy này **không
thu hồi được khoá** nếu nó từng lọt ra ngoài. *(Vẫn chưa làm.)*

Bản sao lưu sự cố mất mã nguồn:
`C:\Users\HP\Desktop\Project\_RECOVERY_Antigravity_20260905_122647\` (135 MB) —
xoá được khi đã yên tâm.

Quy tắc git giữ nguyên:

- Commit trước khi chạy bất kỳ lệnh nào viết lại lịch sử git
- Không chạy hai phiên Claude Code cùng lúc trên cùng thư mục

---

## 9. Cạm bẫy đã gặp trên máy này

| Bẫy | Cách tránh |
|---|---|
| stdout tiến trình con là **cp1252** khi bị pipe | luôn đặt `PYTHONIOENCODING=utf-8` |
| Git Bash đổi `/api/x` thành đường dẫn Windows | `export MSYS_NO_PATHCONV=1` trước khi `curl` |
| Python đọc heredoc bash theo cp1252 | ghi script ra file UTF-8 rồi chạy |
| `\w`, `\d` trong docstring gây `SyntaxWarning` | dùng `r"""..."""` |
| Ký tự thoát qua nhiều lớp heredoc bị diễn giải sớm, hỏng chuỗi | ghi đoạn chèn ra file rồi mới ghép |
| RAM chỉ còn ~0,8 GB khi app chạy | đóng bớt IDE trước khi index lại |
| `git rm -r --cached a b c` huỷ toàn bộ nếu một path sai | chạy tách riêng từng path |
| tqdm ghi bằng ký tự về đầu dòng, `tail -c` đọc ra tiến độ cũ | đổi CR thành LF rồi mới `tail` |
| `/api/*` cần đăng nhập, curl trần trả 401 | kiểm tra thẳng bằng Python trong tiến trình |
