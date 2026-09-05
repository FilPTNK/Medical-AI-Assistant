# Bàn giao — Antigravity Medical Assistant

Cập nhật: 2026-09-05. Nhánh: `fix/retrieval-and-stability`.
Toàn bộ số liệu dưới đây là **đo được**, không phải ước lượng, trừ chỗ ghi rõ.

---

## 1. Hệ thống

FastAPI + React/Vite + Chroma + DeepSeek. RAG tiếng Việt cho phòng khám.

- Kho: **25.852 child chunk**, **3.816 thuốc**, 2 nguồn:
  - `THUOC-BIET-DUOC-VA-CACH-SU-DUNG.pdf` — tra theo *tên biệt dược*
  - `DTQGVN-2022-Q1` — Dược thư Quốc gia, **chỉ quyển 1, chữ A–H** (352 thuốc)
- Truy xuất lai: dense (Chroma HNSW) + BM25 + hợp nhất RRF (k=60)
- Embedding: `paraphrase-multilingual-MiniLM-L12-v2`, 384 chiều, `max_seq_length=128`
- Chạy: `python run.py` (backend 8000, Vite 3000). Backend riêng: `python backend/dev_server.py`

---

## 2. Sự cố mất mã nguồn — ĐỌC TRƯỚC KHI ĐỘNG VÀO GIT

Ngày 2026-09-05 lúc 12:18:47, một phiên Claude Code khác chạy `git filter-repo`
để xoá khoá API khỏi lịch sử. Lệnh đó viết lại lịch sử, đưa cây làm việc về HEAD
và **xoá sạch mọi thay đổi chưa commit**, đồng thời xoá reflog nên không lùi được.

Lúc đó 23/28 module backend và 27/27 component frontend **chưa từng được commit**.
Khôi phục được nhờ `~/.claude/file-history/` và bản ghi hội thoại.

**Quy tắc từ nay:**

- Commit trước khi chạy bất kỳ lệnh nào viết lại lịch sử git
- Không chạy hai phiên Claude Code cùng lúc trên cùng thư mục
- Bản sao lưu sự cố: `C:\Users\HP\Desktop\Project\_RECOVERY_Antigravity_20260905_122647\`
  (23 file `.pyc` + 44 bản ghi hội thoại + ảnh chụp mã nguồn, 135 MB) — xoá được
  khi đã yên tâm

Khoá API `sk-b877...` đã **không còn trong file nguồn lẫn lịch sử git**.
Vẫn cần **thu hồi trên dashboard DeepSeek** — xoá lịch sử máy này không thu hồi
được khoá nếu nó từng lọt ra ngoài. *(Việc này chưa làm.)*

---

## 3. Đã sửa: backend treo vô hạn

Triệu chứng: hỏi trong chat, spinner quay 10–15 phút. Cổng 8000 vẫn LISTENING,
**CPU 0%**, `/docs` (trang tĩnh) cũng không trả lời.

Chẩn đoán bằng `py-spy dump` — luồng chính kẹt trong `logging.emit`, luồng xử lý
request kẹt trong `_showwarnmsg_impl`. Cả hai đều kẹt khi **ghi ra stdout**.

Chuỗi nhân quả:

1. `run.py` pipe stdout của backend. Khi bị pipe, Python con dùng **cp1252**,
   không phải UTF-8 → mọi dòng log tiếng Việt ném `UnicodeEncodeError`
2. Phía cha đọc bằng `encoding="utf-8"` → gặp byte cp1252 → lỗi giải mã
3. `log_output` bọc `try/except: pass` quanh **cả vòng lặp** → luồng đọc chết im lặng
4. Không ai rút pipe → pipe đầy (~64KB) → backend đứng hình giữa request

Đã sửa: ép UTF-8 cả hai đầu (`PYTHONIOENCODING` + `reconfigure`), `errors="replace"`,
bọc lỗi **từng dòng**, và nếu vẫn hỏng thì vẫn tiếp tục rút pipe.

Các lỗi treo khác đã xử lý trong cùng đợt:

- `llm_client.py`: 7 client OpenAI không đặt timeout (mặc định 600s × 2 lần thử
  = treo tới 30 phút) → thêm `_llm_client()` có timeout + giới hạn retry
- `main.py`: nạp model chặn lifespan 35s khiến Vite proxy trả ECONNREFUSED
  → chuyển sang thread nền, uvicorn bind cổng ngay
- `vector_store.py`: bỏ quét tuyến tính O(k×N) trong `search()`; thêm khoá dùng chung
- `dev_server.py`: chạy uvicorn qua API Python vì Windows nở glob `--reload-exclude`

**Kết quả đo trên ứng dụng thật (2026-09-05):**

| | Trước | Sau |
|---|---|---|
| `/api/search` "thuốc hạ sốt" | treo 10–15 phút | **3,99 s** |
| `/api/search` "thuốc giảm đau bụng" | treo | **3,31 s** |
| Backend sẵn sàng phục vụ | — | 27,1 s |
| Treo tệ nhất có thể | ~30 phút | ~4 phút |

**Lưu ý về RAM:** backend chiếm ~1,3 GB trên máy 7,3 GB. Có lúc chẩn đoán nhầm
là thiếu RAM — **sai**, nguyên nhân thật là pipe ở trên. RAM chật nhưng đủ.

---

## 4. Chất lượng truy xuất — chẩn đoán có bằng chứng

Truy vấn "thuốc hạ sốt" trả về **thuốc sốt rét**. Ba nguyên nhân riêng biệt:

**a) Tách từ tiếng Việt** — ĐÃ SỬA (mục 5)

**b) Nhánh dense yếu.** Top-10 dense: 7/10 là thuốc sốt rét, 0 thuốc hạ sốt.
Model nhầm "hạ sốt" với "sốt rét". Kho càng đẩy theo hướng đó:
`"sốt rét"` 107 chunk vs `"hạ sốt"` 31 chunk.

**c) Thiếu dữ liệu.** `generic_name` chứa "PARACETAMOL": **0 / 3.816 thuốc**.
Sách biệt dược tra theo tên thương mại (paracetamol chỉ là thành phần của
ACORALEN, ALAXAN…), còn Dược thư mới nạp tới chữ H.

### Đã kiểm tra và LOẠI TRỪ

`hnsw:space` không được đặt → Chroma dùng **L2** trên vector **không chuẩn hoá**
(độ dài 1,77–4,14) trong khi model huấn luyện cho cosine. Là lỗi thật, nhưng
đã tính lại toàn bộ xếp hạng bằng cosine: **gần như không đổi**, vẫn nguyên nhóm
sốt rét. Nên sửa cho đúng chuẩn, **đừng kỳ vọng nó cứu chất lượng**.

### Đính chính số liệu cũ

Một phiên trước từng nói 77,9% chunk bị cắt / 50,7% token bị bỏ. **Sai.**
Đo lại bằng chính tokenizer của model:

```
trung vị 89 token, p90 = 328, max = 1158
chunk bị cắt (>128): 35,9%
token bị bỏ qua:     35,1%
```

---

## 5. Đã làm: #3 — tách từ tiếng Việt cho BM25

`re.findall(r'\w+')` xé từ ghép: `"hạ sốt"` thành `["hạ","sốt"]`, `"sốt rét"`
thành `["sốt","rét"]`. Hai khái niệm khác hẳn nhau dùng chung token `"sốt"`.

Dùng **pyvi** (`ViTokenizer`): nối từ ghép bằng dấu gạch dưới, cho `"hạ_sốt"` và
`"sốt_rét"` thành hai token riêng. `\w+` coi `_` là ký tự chữ nên không cần đổi regex.

> Đã thử **underthesea** và loại: nó vẫn tách `"hạ sốt"` thành hai âm tiết —
> tức không sửa được đúng lỗi này — và chậm hơn 2,7 lần (11,4 vs 4,2 ms/chunk).

Tách từ tốn ~51s cho 25.852 chunk nên cache ra
`backend/data/vector_db/bm25_tokens.pkl`, khoá theo phiên bản bộ tách từ +
danh sách id. Đổi `SEGMENTER_VERSION` trong `vector_store.py` để buộc dựng lại.

**Kết quả (10 truy vấn y khoa, P@5):**

| | Trước | Sau |
|---|---|---|
| BM25 | 94,0% | **96,0%** |
| DENSE | 76,0% | 76,0% (không đổi — đúng như thiết kế) |
| RRF | 88,0% | **90,0%** |
| RRF bẫy-nhầm | 6,0% | **4,0%** |
| "thuốc kháng sinh" | 80% | **100%** |
| Nạp corpus | 24,6 s | **19,3 s** (có cache) |

**Vấn đề còn lại — quan trọng cho bước sau.** Riêng "thuốc hạ sốt" vẫn 40%:

```
BM25  top-5:  PARASORB, DEXIBUPROFEN, AMSACRIN, ALKA-SELTZER, KETOPROFEN  <- đúng cả 5
DENSE top-5:  ARTEFLEN, SALGYDAL, MALAREX, MALARIA, CLORHEXIDIN           <- 4/5 sốt rét
RRF   top-5:  ARTEFLEN, PARASORB, SALGYDAL, DEXIBUPROFEN, MALAREX         <- trộn 1:1
```

BM25 đã hoàn hảo cho truy vấn này. **RRF trộn 1:1 nên mỗi kết quả đúng lại kèm
một thuốc sốt rét từ nhánh dense.** Nút thắt giờ nằm ở dense.

---

## 6. Còn phải làm

Thứ tự người dùng đã chốt: **#4 → #5 → #2**. (#1 hoãn: chưa có Dược thư quyển 2.)

### #4 — cosine + chuẩn hoá vector

Đặt `hnsw:space="cosine"` khi tạo collection và
`encode_kwargs={'normalize_embeddings': True}`. **Phải index lại toàn bộ.**
Đã đo: lợi ích chất lượng khoảng 0. Làm vì đúng chuẩn và vì
`similarity_search_with_relevance_scores` đang trả điểm âm (−3,9 … −6,3) kèm cảnh báo.

### #5 — lọc rác parser

Có "thuốc" mang tên là chuỗi ký tự vô nghĩa (`LEP i NIAAUN`, `Ỉ`, và cả câu văn
bị coi là tên thuốc). Sửa ở `drug_parser.py` / `dtqg_parser.py`.
Cũng có lỗi OCR: "Giảm dau", "Ha nhiệt", "Thdn trong" — một mẫu dò thận trọng
bắt được 3,9% chunk, **soi tay cho thấy tỉ lệ thật cao hơn, chưa đo chính xác**.

### #2 — đổi embedding sang `multilingual-e5-small`

384 chiều (giữ nguyên schema), `max_seq_length=512` (hết 35,9% bị cắt).
Đây là việc **quan trọng nhất còn lại** — dense đang là nhánh yếu kéo tụt RRF.
Nhớ tiền tố `query:` / `passage:` mà họ e5 yêu cầu. **Phải index lại.**

> Gộp #4 và #2 vào **một lần index lại** để khỏi chạy hai lượt.

### Ý tưởng rẻ, chưa làm

BM25 đang 96% còn dense 76%. **Cân RRF lệch về BM25** (hoặc giảm số ứng viên dense)
có thể cải thiện ngay mà không cần index lại. Nên đo thử trước khi làm #2.

### Khi có Dược thư quyển 2 trở đi

Nạp nốt I–Z. Đang thiếu monograph của Paracetamol, Ibuprofen, Omeprazol…
Không thuật toán nào tìm được tài liệu không tồn tại.

---

## 7. Cách đo (bắt buộc dùng trước/sau mỗi thay đổi)

Bộ đo nằm ở scratchpad của phiên cũ; nếu mất thì dựng lại theo mô tả này:

- `eval_set.py` — 10 truy vấn, mỗi truy vấn có `expect` (dấu hiệu chunk đúng chủ đề)
  và `trap` (chủ đề bị nhầm sang). Ví dụ: `"thuốc hạ sốt"` có expect
  `["hạ sốt","hạ nhiệt","giảm sốt","cảm sốt","paracetamol","ibuprofen","aspirin"]`,
  trap `["sốt rét","sốt xuất huyết"]`
- `eval_run.py` — chấm P@5 riêng cho **BM25**, **DENSE**, **RRF**. Đo cả ba, vì
  một thay đổi có thể cải thiện nhánh này mà làm hỏng nhánh kia
- Kết quả `db.search()` dùng khoá **`child_text`** (chunk khớp), không phải
  `content` (không tồn tại) hay `text` (là parent text)

---

## 8. Cạm bẫy đã gặp trên máy này

| Bẫy | Cách tránh |
|---|---|
| stdout tiến trình con là **cp1252** khi bị pipe | luôn đặt `PYTHONIOENCODING=utf-8` |
| Git Bash đổi `/api/x` thành đường dẫn Windows | `export MSYS_NO_PATHCONV=1` trước khi `curl` |
| Python đọc heredoc bash theo cp1252 | ghi script ra file UTF-8 rồi chạy |
| `\w`, `\d` trong docstring gây `SyntaxWarning` | dùng `r"""..."""` |
| Import module backend ghi đè `.pyc` | đừng chạy app khi đang cần `.pyc` để cứu dữ liệu |
| RAM chỉ còn ~0,5 GB khi app chạy | đóng bớt IDE trước khi index lại |
| `git rm -r --cached a b c` huỷ toàn bộ nếu một path sai | chạy tách riêng từng path |

---

## 9. Trạng thái git

```
3615561  #3 Tách từ tiếng Việt cho BM25 bằng pyvi
2590015  Đưa toàn bộ mã nguồn vào kho và sửa các lỗi treo backend
449b823  2                          (sau khi filter-repo viết lại)
```

Nhánh `fix/retrieval-and-stability`, **chưa merge vào `master`**.
Đã gỡ `frontend/node_modules` và `frontend/dist` khỏi theo dõi (5.358 file).
Dữ liệu (`backend/data/`, 1,2 GB) không nằm trong kho và **không bị ảnh hưởng**
bởi bất kỳ việc nào ở trên.
