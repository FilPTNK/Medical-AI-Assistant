# Bàn giao — Antigravity Medical Assistant

Cập nhật: 2026-09-05 (đợt 2). Nhánh: `fix/retrieval-and-stability`.
Toàn bộ số liệu dưới đây là **đo được**, không phải ước lượng, trừ chỗ ghi rõ.

Đợt này làm xong **#4, #5, #2** và ý tưởng "cân RRF" của bàn giao trước.

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

## 3. Đã làm đợt này

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

## 6. Còn phải làm

### Quan trọng nhất: nạp nốt Dược thư quyển 2 trở đi

Đang thiếu monograph của **Paracetamol, Ibuprofen, Omeprazol…** — Dược thư mới
có chữ A–H. `generic_name` chứa "PARACETAMOL": **0 / 3.816 thuốc**. Không thuật
toán nào tìm được tài liệu không tồn tại; đây giờ là trần chất lượng thật sự,
không còn nằm ở khâu truy xuất.

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
