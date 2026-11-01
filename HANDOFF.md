# Bàn giao — Antigravity Medical Assistant

Cập nhật: 2026-09-24 (WP7 — khớp mã WP1–WP6 và trạng thái kho được bàn giao).
Nhánh được ghi trong bản bàn giao gốc: `fix/retrieval-and-stability`;
trạng thái nhánh trên máy bác sĩ **chưa kiểm chứng**.
Các số đo trước đây được giữ theo **mốc đo cũ**. Kho 3 cuốn / 33.490 child
chunk là số trong `CHATGPT_WORK_PROMPTS.md` do người dùng bàn giao, không có
dữ liệu sách trong ZIP để đo lại. Số nào không có trong mã hoặc tài liệu gốc
được ghi **chưa đo lại**.

Đợt 2026-09-12 làm **giao diện** (mục 2b). Đợt 2026-09-05 làm **#4, #5, #2**
và ý tưởng "cân RRF" của bàn giao trước.

Kế hoạch bốn đợt đã chốt với bác sĩ sau năm vòng phỏng vấn — **đã xong cả bốn**:
1 giao diện → 2 không bao giờ treo → 3 tiền sử vào chẩn đoán → 4 trình xem tài liệu.
Đợt 5 (đối chiếu dị ứng ↔ thuốc) trước ghi là "hoãn có chủ đích", nay đã làm.

---

## 1. Hệ thống

FastAPI + React/Vite + Chroma + DeepSeek. RAG tiếng Việt cho phòng khám.

- Kho được bàn giao: **33.490 child chunk / 3 cuốn** (số theo prompt nền,
  **chưa đo lại** từ Chroma của máy bác sĩ):
  - `THUOC-BIET-DUOC-VA-CACH-SU-DUNG.pdf`: **18.708 chunk**, tra tên biệt dược.
  - `DTQGVN-2022-Q1`: **7.144 chunk**, Dược thư Quốc gia quyển 1,
    **A–Hydroxyzin**.
  - `DTQGVN-2022-Q2`: **7.638 chunk**, quyển 2,
    **Ibuprofen–Zolpidem**, trang in thân sách **885–1778**; số trang PDF
    và dải trang thực của từng cuốn phải lấy từ manifest trên máy.
  Số **3.816 thuốc** trong các phép quét cũ là số đo trên kho cũ,
  **chưa đo lại** trên cả ba cuốn.
- Truy xuất lai: dense (Chroma HNSW, **cosine**) + BM25 + hợp nhất RRF (k=60, 1:1)
- Embedding: **`intfloat/multilingual-e5-small`**, 384 chiều, `max_seq_length=512`,
  vector chuẩn hoá, tiền tố `query:` / `passage:`
- Chạy: `python run.py` (backend 8000, Vite 3000). Backend riêng:
  `python backend/dev_server.py`; không mở cả hai cùng lúc.
- Tab **Thư viện đã gộp Đối chiếu**: chọn nhiều tài liệu và thao tác nổi;
  tài liệu PDF tự tải lên dùng `generic_ingest.py` + SSE qua `ingest_jobs.py`,
  chia trang, OCR trang cần thiết rồi dùng lại `ingest_book.py`. Pipeline
  giới hạn 64 MiB / 300 trang, một worker OCR, job giữ trong RAM;
  cần đối chiếu trang gốc sau khi nạp.
- `config.py` ép `HF_HOME` vào `backend/data/hf_cache`, tránh cache trên ổ
  D: rời; khi cache đã có snapshot, đặt offline. Chỉ mục/model **chưa có**
  trong ZIP, kiểm trên máy theo `RUNBOOK.md`.

---

## 2. Chất lượng truy xuất — lần đo cũ, chưa đo lại kho ba cuốn

P@5 trên hai bộ truy vấn trong `eval/`, đo khi kho **hai cuốn / 25.852
chunk**. "Trước" và "sau" dưới đây chỉ là hai mốc của đợt 2026-09-05;
**không đại diện P@5 hiện tại** với Q2 và mã WP1–WP6. Chạy lại theo mục 5.

| | bộ chính: trước | bộ chính: sau | bộ giữ riêng: trước | bộ giữ riêng: sau |
|---|---|---|---|---|
| BM25 | 92,0% | **100,0%** | 88,0% | 88,0% |
| DENSE | 78,0% | **90,0%** | 72,0% | **94,0%** |
| **RRF (kết quả thật)** | **90,0%** | **100,0%** | **80,0%** | **98,0%** |
| bẫy-nhầm (RRF) | 4,0% | **0,0%** | 0,0% | 0,0% |

Trong lần đo cũ, truy vấn "thuốc hạ sốt" đạt **100%**, không còn
thuốc sốt rét nào trong top-5.

**Điểm liên quan** (`similarity_search_with_relevance_scores`):
`-1,897 … -2,211` kèm cảnh báo *"must be between 0 and 1"* → **`0,913 … 0,896`**,
hết cảnh báo.

Bản bàn giao cũ ghi **17,2s** để backend sẵn sàng (đợt trước 27,1s);
trên kho ba cuốn và bản WP1–WP6 **chưa đo lại**. `/api/auth/status`
trả HTTP chỉ báo máy chủ nhận request; cần xem `/api/index/health` sau
đăng nhập để biết BM25/model đã nạp xong (xem `RUNBOOK.md`).

---

## 2b. Giao diện — đợt 2026-09-12

### Cách kiểm chứng

```
node frontend/contrast_check.mjs      # 33 cặp màu x 2 chế độ, thoát 1 nếu hỏng
cd frontend
npm run build                          # dựng thật, bắt lỗi cú pháp JSX/CSS
cd ..
```

Ở đợt 2026-09-12, **66/66 cặp đạt WCAG AA**; đợt 5 đã mở rộng thành
85 cặp × 2 chế độ. Chạy lại `node frontend/contrast_check.mjs` trên bản
WP1–WP6 ngày 2026-09-24: **Hỏng: 0; Bỏ qua: 0**; số cặp hiện tại
**chưa đếm lại**. WP5 đã thêm test React/Vitest và tách component nên câu
"không có test React" trong bàn giao cũ không còn đúng. Script màu chỉ kiểm
cặp token định nghĩa trong tệp, không chứng nhận toàn giao diện.

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

### Chưa làm trong đợt 2026-09-12 (ghi nhận lịch sử)

- **Chưa tách file vào thời điểm đó.** `App.jsx` vẫn 6.7k dòng. Thay đổi đợt này gần như toàn bộ
  nằm ở CSS cộng vài chỗ JSX nhỏ, nên tách file sẽ là tách thứ mình không sửa —
  đúng cái bác sĩ đã bảo đừng làm. **WP5 về sau đã tách các view**; xem mục 2d.
- **`DashboardView.css` giữ nguyên bảng màu biểu đồ** (10 mã màu). Tab Thống kê
  không nằm trong ba tab của đợt này, và màu chuỗi biểu đồ là một hệ riêng cần
  đo lại theo nền mới.
- **`IntroExperience.css`** cố ý giữ thế giới tối riêng; chỉ đổi màu nhấn cho
  cùng họ.
- **Bộ ảnh chụp "sau" chưa đủ.** Chrome treo vì máy hết RAM (xem mục 6b) nên
  chỉ chụp được tab Bệnh nhân chế độ sáng. Ảnh "trước" thì đủ cả 6.

---

## 2c. Đối chiếu dị ứng ↔ thuốc — đợt 2026-09-23

Đây là mục "Đợt 5" mà bàn giao trước ghi là hoãn có chủ đích. Lý do hoãn vẫn
đúng — *"làm nửa vời mà sót chéo nhóm thì nguy hơn không làm, vì trông như đã
có lưới"* — nên đợt này bắt đầu bằng việc đọc y văn để biết cái lưới đó phải
có hình gì.

### Cách kiểm chứng

```
python eval/allergy_run.py           # 46 phép kiểm, thoát 1 nếu hỏng
python eval/allergy_run.py --sweep   # thêm 9 phép quét cả 3.816 tên
node frontend/contrast_check.mjs     # nay 85 cặp x 2 chế độ
cd frontend
npm run build
cd ..
```

**55/55 đạt ở lần đo 2026-09-23 (kho cũ). Chưa đo lại sau Q2.** `backend/drug_allergy.py` không import gì ngoài `text_fold`, nên
bộ kiểm chạy được cả khi máy chưa cài thư viện backend.

### Không dùng ATC, dù kho có sẵn 329 mã

Ý đầu tiên là gom nhóm dị ứng theo `atc_code`. **Sai.** First Databank nói
thẳng rằng họ "định nghĩa nhóm dị ứng THẬT và KHÔNG dùng lại nhóm điều trị":
ATC xếp theo cơ quan đích, dị ứng đi theo cấu trúc hoá học. Trong chính kho
này, ASPIRIN mang `A01AD05` còn DICLOFENAC mang `M01AB05` — cùng một cơ chế dị
ứng chéo, hai nhánh ATC khác nhau từ chữ cái đầu. Đo thêm (Goss, MedInfo 2015):
nhánh "cơ chế tác dụng" của NDF-RT cho NPV 56,8%, tức bỏ sót một nửa.

Nên bảng nhóm là **tự soạn**: 10 nhóm có số đo + 3 nhóm chỉ khớp theo tên,
205 cụm, 5 liên kết chéo — mỗi liên kết kèm tỉ lệ và nguồn.

### Bốn mức, và vì sao không được gộp

| mức | nghĩa | ví dụ |
|---|---|---|
| `exact` | trùng đúng hoạt chất | ghi "amoxicilin", kê Amoxicillin |
| `group` | cùng nhóm dị ứng | ghi "penicilin", kê Amoxicillin |
| `cross` | chéo giữa hai nhóm, **kèm tỉ lệ** | ghi "penicilin", kê Cefalexin |
| `chua_kiem` | ô trống / "không rõ" / không đọc ra | — |

Đo được (JAMIA Open 2026, 101.492 cảnh báo): chỉ **9,7%** là khớp đúng hoạt
chất, **90,3%** là khớp nhóm hoặc chéo, và **98,9%** bị bỏ qua. Nhưng soi lại
bệnh án thì **94–96,5%** lần bỏ qua đó **đúng về lâm sàng** (BMJ Qual Saf 2016)
— lỗi nằm ở chỗ cảnh báo nổ, không nằm ở bác sĩ. Gộp bốn mức thành một chữ
"cảnh báo" đỏ là cách chắc chắn nhất để biến lưới an toàn thành tiếng ồn.

Cụ thể, hai dòng sau **không được** trông giống nhau:

- penicilin → Cefalexin: **16,5%** (KTC 11,1–23,8) — chung chuỗi bên R1
- penicilin → Ceftriaxon: **2,1%** (KTC 1,0–4,5) — chuỗi R1 khác hẳn

Con số "10% dị ứng chéo penicilin–cephalosporin" là **sai và đã bị thay**: nó
vốn là 8% trên tờ hướng dẫn của FDA, cao giả vì cephalosporin trước 1980 bị
lẫn penicilin.

### Những liên kết CỐ Ý không có trong bảng

- **sulfonamid kháng khuẩn ↔ furosemid / thiazid / celecoxib / sulfonylurea /
  acetazolamid**: Strom, NEJM 2003, 19.257 người — **không** chéo.
- **sulfonamid ↔ muối sulfat, sulfit, lưu huỳnh**: chỉ trùng vần.
- **aspirin ↔ celecoxib**: ức chế COX-2 chọn lọc, đa số vẫn dùng được.
- **penicilin ↔ aztreonam**: không chéo (trừ ceftazidim, chung chuỗi R1).
- **macrolid, quinolon, thuốc tê**: khớp đúng tên thì báo, nhưng **không**
  dựng khớp chéo — y văn 2022 ghi rõ là chưa đo được. Cách chia thuốc tê
  ester/amid là bài giảng kinh điển, không có trong tài liệu tham số.

Bốn nhóm đầu hiện trên giao diện ở mục gập **"Đã xét và KHÔNG báo"** — im lặng
thì bác sĩ tưởng máy bỏ sót.

### So khớp theo token, không theo chuỗi con — đo trên chính kho này

Chuỗi con sinh ra dương tính giả thật, không phải giả định:

| dò chuỗi con | trúng nhầm |
|---|---|
| `amoxi` | AMOXICILIN **và TAMOXIFEN** |
| `sulfa` | 27 tên, gồm **BUSULFAN, ITROSULFAN, ATROPIN SULFAT** |
| `cef` | 38 tên, gồm cả `CEF-3` (tên biệt dược) |

Nên mọi so khớp là **token nguyên vẹn**. Quét cả kho sau khi sửa:

| ô dị ứng | khớp / 3.816 |
|---|---|
| "Dị ứng penicillin" | 67 (1,8%) |
| "Dị ứng cephalosporin" | 32 (0,8%) |
| "Dị ứng sulfamid" | 22 (0,6%) |
| "Dị ứng aspirin" | 21 (0,6%) |
| "Dị ứng morphin" | 7 (0,2%) |

> Phép thử `--sweep` bản đầu tự mắc đúng cái lỗi nó đi bắt: nó dò chuỗi con
> `"SULFAT" in name` nên chấm **SULFATHIOUREA** là dương tính giả, trong khi
> đó là một sulfonamid kháng khuẩn thật và phải khớp. Nay nó xét `sulfat` có
> đứng riêng thành một từ hay không.

### Chính tả một `l` hay hai `l` — gộp bằng phép biến đổi

Dược thư viết `AMOXICILIN`, cuốn Biệt dược viết `AMPICILLIN`. Liệt kê tay cả
hai lối cho từng tên là thứ chắc chắn sẽ sót. Nên `_squeeze()` bóp mọi ký tự
lặp liền nhau về một. Đo trên 3.816 tên: **đúng 6 va chạm, cả sáu đều là hai
lối viết của CÙNG một thuốc** (allopurinol/alopurinol, attapulgit/atapulgit,
cinnarizin/cinarizin, ampicilin/ampicillin). Không cặp nào trộn hai thuốc khác
nhau.

### Ô trống KHÁC ô ghi "không có"

`App.jsx` có `NO_DATA_PHRASES` gộp cả hai, và với việc **tô màu thẻ** thì gộp
như vậy đúng. Với việc **đối chiếu** thì sai, và sai nguy hiểm: "Không có"
nghĩa là đã hỏi và không dị ứng; ô trống và "không rõ" nghĩa là **chưa ai hỏi**.
Coi cái sau là đã kiểm sạch đúng là lớp hỏng y văn cảnh báo — bác sĩ thấy máy
im thì tưởng đã có lưới. Nên ô trống → `chua_kiem`, hiện thành khối riêng,
trông khác hẳn "đã đối chiếu và không thấy gì".

Trong `patients.db` hiện có 3 bệnh nhân: một ghi `"Không có"`, hai bỏ trống —
tức **hai trong ba** sẽ hiện khối "chưa đối chiếu được".

### Công cụ không được nhận nhiều hơn nó làm được

`ket_luan` chỉ nhận ba giá trị, và cả ba nói về **phép đo** chứ không nói về
bệnh nhân: `co_khop`, `khong_thay_khop`, `chua_kiem`. **Không bao giờ có
"không có xung đột"** — bộ phân tích dị ứng chữ tự do tốt nhất đã công bố đạt
độ nhạy 75,73%, và đó là tiếng Anh; chưa ai đo cho tiếng Việt. Có phép thử
riêng chặn các chữ "an toàn", "không có xung đột", "đã kiểm hết".

`PHAM_VI` công bố thẳng chỗ công cụ không với tới — ONC HTI-1 bắt buộc thuộc
tính *"cautioned out-of-scope use"* bằng lời thường.

Khối cảnh báo còn nói rõ đây là **gợi ý xem lại, không phải chống chỉ định**:
hơn 90% người mang nhãn dị ứng penicilin dung nạp được khi test, và tránh
kháng sinh quá tay có hại đo được (HR 1,69 với MRSA, 1,26 với C. difficile
trên 301.399 người).

### Giao diện: không có hộp thoại chặn

Rào chặn cứng trong y văn chỉ đặt cho khớp **đúng hoạt chất kèm phản ứng nặng
đã ghi**, và kết quả của nó **vẫn đang chờ đo**. Thêm nữa, thí nghiệm 2025
(n=281 và n=373) **không lặp lại được** kết quả Buçinca 2021 về "cognitive
forcing function": cả ba kiểu ma sát chủ ý đều không giảm được thiên lệch. Nên
khối chỉ **chắn tầm mắt**, đặt TRÊN danh sách thuốc — trên đường mắt đi từ
tiêu đề xuống đơn thuốc rồi tới nút Lưu — chứ không chặn tay.

Mỗi mức mang **bốn kênh**: biểu tượng, chữ nhãn viết hoa, vạch dày bên trái,
và màu. Bỏ màu đi vẫn đọc ra thứ bậc (WCAG 1.4.1).

> Khối "không khớp gì" **cố ý trung tính chứ không xanh lá**. Xanh lá đọc ra là
> "đã kiểm, an toàn" — đúng thứ khối này không được phép nói.

`contrast_check.mjs` bắt được một lỗi thật trong đợt này: `--text-muted` trên
nền tinh chỉ đạt **4,14:1** (đỏ nhạt) và **4,10:1** (cam nhạt), đều dưới 4,5.
Nền tinh sáng hơn nền thẻ nên chữ nhạt tụt qua ngưỡng ở đúng chỗ đó. Khối dùng
`--text-secondary` (6,7:1).

### Chưa làm trong đợt 2026-09-23; cần kiểm lại trên máy thật

- **Chỉ gắn vào `/api/diagnosis-tree/treatment`.** Đường `ai-diagnosis` và
  agent ReAct chưa có đối chiếu. Cùng hàm `_doi_chieu_di_ung()` dùng lại được.
- **Chưa đối chiếu khi bác sĩ tự gõ thêm thuốc** trong phiếu khám — hiện chỉ
  đối chiếu danh sách do mô hình gợi ý.
- **Tên biệt dược không đối chiếu được.** Bảng chỉ chứa tên gốc. Trong 38 tên
  bắt đầu bằng `cef` của kho, 3 là tên biệt dược (`CEF-3`, `CEFACET`,
  `CEFOBAC`) nên không nằm trong bảng.
- **Chưa ghi lại lý do bác sĩ bỏ qua cảnh báo.** Y văn khuyến nghị thu lý do
  có mã và chuyển tiếp cho dược sĩ.
- **Backend không chạy được trên máy này lúc viết mã**: `python` hệ thống chưa
  cài `dotenv`/`fastapi`/`chromadb`, nên `eval/deid_run.py` và endpoint thật
  chưa chạy lại được sau thay đổi. `python run.py --reinstall` là cách cài
  ở thời điểm đó; đây không phải kết quả thử backend WP1–WP6.
  Phần đối chiếu đã kiểm đầy đủ vì nó không phụ thuộc thư viện nào.

---

## 2d. Cập nhật từ mã WP1–WP6 (2026-09-24)

### Truy xuất và giới hạn máy 7 GB

- Khi Chroma không đọc được chỉ mục, trả lỗi chỉ mục; khi corpus thực sự rỗng,
  trả lỗi kho rỗng; khi có corpus nhưng truy vấn không khớp, báo không khớp.
  Nếu embedding lỗi nhưng BM25 có corpus, `search()` trả kết quả BM25 với
  `degraded=true` và lý do. Các đường tra cứu, báo cáo, đối chiếu không còn
  tự biến lỗi hạ tầng thành câu trả lời "không có tài liệu".
- `VectorStore.db` có khóa trong tiến trình; dữ liệu Chroma được lấy theo lô
  **500** để tránh lỗi `too many SQL variables` trên kho ~33k; cache BM25
  lưu corpus/token và kiểm vân tay trước khi đọc. Mục tiêu khởi động <30s
  **chưa đo lại** trên máy thật.
- Server giữ `backend/data/vector_db/.writer.lock` trong vòng đời;
  `ingest_book.py` phải lấy khóa đó trước khi ghi từ CLI. **Không chạy CLI ghi
  Chroma khi server đang chạy**. Sự cố FTS5 `malformed inverted index` đã
  từng xảy ra khi chạy đồng thời; cách sao lưu/dựng lại ở `RUNBOOK.md`.
- `page_map.py` kẹp offset trang in theo `pdf_pages`, tránh tính sai
  quyển đánh số liên tục. Cache HF đã đưa vào `backend/data/hf_cache`; khi
  chỉ mục chưa warm, chat không được gọi đó là không khớp y văn.

### Tài liệu và giao diện

- Tab Thư viện kiêm Đối chiếu; PDF tự tải lên qua `generic_ingest.py`, theo
  dõi SSE. WP3 giới hạn **64 MiB / 300 trang**, xác nhận PDF thật,
  tuần tự OCR một worker, kiểm trang OCR đọc kém và dọn manifest dở;
  job vẫn lưu trong RAM và không tự tiếp tục sau khi khởi động lại.
- WP4 đã rà soát UX trong báo cáo riêng; WP5 đã tách `App.jsx` thành các
  view/component và thêm phép thử React/Vitest. Mốc dòng 6.7k ở mục 2b
  là ảnh chụp lịch sử, không phải tình trạng file hiện tại.
- WP6 đã chỉnh prompt y khoa bám nguồn và giữ lối báo thiếu nguồn. Quy tắc
  prompt không phải phép kiểm đầu ra LLM; xem mục 6 về nguồn chẩn đoán và
  dữ liệu bệnh án tự do. Chưa thử với mô hình/API và bệnh án thật.

---

## 3. Đã làm đợt này (2026-09-05)

### Đính chính một con số của bàn giao trước

Bàn giao trước ghi BM25 = 96,0%. **Sai, số thật là 92,0%.** Bộ đo cũ chia điểm
cho *số kết quả trả về* thay vì cho 5. BM25 chỉ trả nổi 1 chunk cho "thuốc ho"
nên được chấm 1/1 = 100% — tức là **thưởng cho việc không tìm ra gì**. Bộ đo mới
luôn chia cho 5.

### Cân RRF + mở rộng từ ghép hiếm (đo trên kho cũ, không cần index lại)

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
> `SearchResultItem` theo từng trường nên cờ chưa lọt ra API ở đợt cũ.
> WP1–WP6 hiện cần kiểm lại luồng API/giao diện bằng dữ liệu thật.

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
Khi đổi kho và logic truy vấn (WP2), số cũ **chưa đo lại**.

---

## 5. Cách đo

Bộ đo nay **nằm trong kho** (`eval/`), không còn ở scratchpad của phiên.
`eval/eval_run.py` hiện mặc định `--set all` (có cả bộ WP2); muốn chỉ
so hai bộ cũ dùng `--set both`. Chạy đánh giá là tải chỉ mục/model;
trên máy bác sĩ **chưa đo lại**.

```
python eval/eval_run.py --set both                 # hai bộ cũ, chỉ mục đang chạy
python eval/eval_run.py --set both --sweep         # quét trọng số RRF
python eval/eval_run.py --persist-dir <thư mục>    # mọi bộ, chấm chỉ mục dựng thử
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

**Trong lần đo cũ, backend bị hệ điều hành giết hai lần trong một phiên làm việc**, mã thoát
`4294967295` (tức là bị kết liễu từ ngoài, không phải tự thoát). Đo được:

| | |
|---|---|
| RAM tổng | 7,3 GB |
| RAM trống khi app chạy (lần đo cũ) | **1,01 GB** |

Backend phải nạp torch + `multilingual-e5-small` + Chroma, nhiều hơn 1 GB. Cuối
phiên Chrome cũng treo, không chụp nổi màn hình nữa.

Đây **không phải** vấn đề của mã nguồn và không sửa được bằng mã. Nhưng nếu nó
xảy ra giữa lúc đang khám thì nặng hơn mọi thứ trong kế hoạch bốn đợt. Cần đóng
bớt chương trình trước khi mở app, hoặc thêm RAM.

---

## 6. Còn phải làm

### Đã giải quyết từ sau bàn giao cũ

Quyển 2 đã nạp theo trạng thái người dùng bàn giao: không còn ghi
"thiếu Paracetamol/Ibuprofen" như một kết luận hiện tại. Mã mới còn có
chế độ BM25 khi embedding lỗi, trạng thái lỗi chỉ mục và health (WP1),
điều chỉnh truy vấn theo triệu chứng cùng bộ đánh giá mở rộng **gắn nhãn cần
dược sĩ duyệt** (WP2), giới hạn/tuần tự hoá nạp PDF (WP3), rà soát UX có
dẫn chứng (WP4), tách view và test giao diện (WP5), chỉnh prompt bám nguồn
và ghi nhận đường dữ liệu bệnh nhân (WP6). Đây là **đọc mã và patch**, hiệu quả
trên dữ liệu thật và thời gian khởi động máy 7 GB **chưa đo lại**.

### Cần đo hoặc sửa tiếp

- Đo lại P@5 theo nhóm trên **ba cuốn**, đo cold start/RAM trên máy thật;
  truy vấn triệu chứng và các nhãn kỳ vọng trong WP2 **cần dược sĩ duyệt**.
  Số P@5 cũ, 17,2s và 55/55 không phải số đo mới.
- `GET /api/index/health` có đăng nhập, báo corpus/BM25/model/suy giảm;
  xác nhận trực tiếp sau khi nhận patch. `run.py` chỉ chờ HTTP của endpoint
  xác thực, không chờ warmup tìm kiếm.
- Kiểm trích dẫn, OCR, bản đồ trang in ↔ trang PDF của từng quyển; đặc biệt
  Q2 đánh số tiếp 885–1778. Số trang PDF/dải thân sách của quyển mới lấy từ
  manifest thực, không suy từ số trang in.
- WP6 phát hiện: trường tự do bệnh án và truy vấn tự gõ có thể chứa tên,
  số điện thoại, địa chỉ; phần bỏ tên/id trong dữ liệu có cấu trúc **chưa**
  khử danh các đoạn tự do trước khi gửi DeepSeek. Cần khắc phục và thử với
  dữ liệu giả trước khi dựa vào cam kết bảo mật.
- Prompt y khoa mới yêu cầu bám nguồn nhưng các endpoint cây chẩn đoán hiện
  gọi `context_chunks=None` và có thể trả danh sách trống; cần nối nguồn,
  kiểm chứng trích dẫn và đánh giá bởi bác sĩ trước khi dùng cho quyết định.
- Đối chiếu dị ứng trong phiếu bác sĩ tự gõ và các đường ngoài
  `/api/diagnosis-tree/treatment` vẫn cần đối chiếu; tên biệt dược chưa được
  phân nhóm bằng bảng tên hoạt chất. Các phép quét cũ là lịch sử.
- Chất lượng OCR nội dung, hai truy vấn giữ riêng và cờ tên nghi ngờ cần
  đo lại theo kho mới. Nếu cảnh báo đã hiện trong nguồn, kiểm UX thực tế
  trước khi coi vấn đề là giải quyết hoàn toàn.

---

## 7. Trạng thái git & dữ liệu

Các hash dưới đây thuộc lần bàn giao cũ. Bản ZIP chỉ gồm mã nguồn;
nhánh/commit/dữ liệu thực trên máy bác sĩ **chưa kiểm chứng**. WP1–WP6 và WP7
được bàn giao bằng patch; trạng thái áp dụng trên máy bác sĩ **chưa đo lại**.

```
f0cc98c  Đo sau khi index lại: gỡ trọng số RRF, chốt ngưỡng tương tự 0,92
a48afe9  Đưa cờ name_suspect ra tới kết quả tìm kiếm và ngữ cảnh LLM
f519615  #4+#2 Chuyển sang multilingual-e5-small, cosine và vector chuẩn hoá
cf7c6d0  #5 Chuẩn hoá tên thuốc và gắn cờ tên hỏng OCR — không xoá, không đoán
3c15c82  Nghiêng RRF về BM25 và mở rộng từ ghép hiếm; đưa bộ đo vào kho
2780ef4  Thêm HANDOFF.md — báo cáo bàn giao        <- đầu đợt này
```

Ở thời điểm ghi bản cũ: nhánh `fix/retrieval-and-stability`, chưa merge vào `master`; **chưa kiểm tra lại trên máy bác sĩ**.

**Bản bàn giao cũ ghi có chỉ mục để lùi; ZIP không chứa thư mục đó, chưa kiểm tra lại:**
`backend/data/vector_db_minilm_backup_20260905_154559/` (304 MB). Xoá được khi
đã yên tâm — nhưng muốn lùi thì phải đổi **cả** `config.EMBEDDING_MODEL` về
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, vì chỉ mục đó
sinh bằng model cũ.

---

## 8. Việc còn treo từ đợt trước

**Bản bàn giao cũ ghi có khoá API bị lộ; trạng thái thu hồi hiện nay chưa xác minh trên dashboard.** Khoá đã
không còn trong mã nguồn hiện tại; xoá lịch sử git **không thu hồi được khoá** nếu nó từng lọt ra ngoài. Cần người quản lý xác minh đã thu hồi và đổi khoá.

Bản sao lưu sự cố mất mã nguồn:
`C:\Users\HP\Desktop\Project\_RECOVERY_Antigravity_20260905_122647\` (135 MB theo bản cũ) —
**chưa xác minh còn tồn tại**, không xoá nếu chưa kiểm tra bản sao hiện hành.

Quy tắc git giữ nguyên:

- Commit trước khi chạy bất kỳ lệnh nào viết lại lịch sử git
- Không chạy hai phiên Claude Code cùng lúc trên cùng thư mục

---

## 9. Cạm bẫy đã gặp trên máy này (ghi nhận từ bàn giao cũ)

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
