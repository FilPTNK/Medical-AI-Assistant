# -*- coding: utf-8 -*-
"""
Bất biến của đợt 5: đối chiếu dị ứng phải TẤT ĐỊNH, PHÂN HẠNG, và KHÔNG BAO
GIỜ tự nhận là đã kiểm hết.

Chạy:  python eval/allergy_run.py            (thoát 1 nếu hỏng)
       python eval/allergy_run.py --sweep    (quét cả 3.816 tên trong kho)

Ba lớp kiểm, theo đúng thứ tự nguy hiểm giảm dần:

  [1] DƯƠNG TÍNH GIẢ — thứ phá hoại nhiều nhất. Đo được trên y văn: 98,9%
      cảnh báo dị ứng bị bỏ qua, và soi lại bệnh án thì 94–96,5% lần bỏ qua đó
      là ĐÚNG VỀ LÂM SÀNG. Cảnh báo sai không chỉ vô ích, nó dạy bác sĩ bỏ qua
      cả cảnh báo thật. Dán nhãn dị ứng quá tay còn gây hại đo được: HR 1,69
      với MRSA, 1,26 với C. difficile trên 301.399 người.

  [2] ÂM TÍNH GIẢ — thứ giết người. Dị ứng có ghi rành rành mà không báo.

  [3] LỜI TỰ NHẬN — công cụ không được nói "không có xung đột" bao giờ.

Phép thử KHÔNG chạm cơ sở dữ liệu thật và KHÔNG gọi ra mạng.
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

import drug_allergy as da  # noqa: E402

failures = []
checks = 0


def check(ok, label):
    global checks
    checks += 1
    if not ok:
        failures.append(label)
    print(("  ok    " if ok else "  HỎNG  ") + label)


def tiers(allergies, ten_thuoc):
    """Các mức khớp sinh ra cho đúng một thuốc."""
    r = da.kiem_tra(allergies, [{"name": ten_thuoc}])
    return [m["tier"] for k in r["ket_qua"] for m in k["khop"]]


# =========================================================== 1. DƯƠNG TÍNH GIẢ
print("\n[1] Dương tính giả — tên chỉ TRÙNG VẦN, không dị ứng chéo")

# Đo trên chính 3.816 tên của kho: so khớp chuỗi con sinh ra đúng những cặp này.
BAY = [
    ("Dị ứng amoxicillin", "Tamoxifen 20mg", "amoxi nằm trong TAMOXIFEN"),
    ("Dị ứng sulfamid", "Busulfan 2mg", "sulfa nằm trong BUSULFAN"),
    ("Dị ứng sulfamid", "Atropin sulfat 0,25mg", "muối sulfat không phải sulfonamid"),
    ("Dị ứng sulfamid", "Magnesi sulfat", "muối sulfat không phải sulfonamid"),
    ("Dị ứng sulfamid", "Itrosulfan", "sulfa nằm giữa tên"),
]
for allergies, thuoc, vi_sao in BAY:
    check(tiers(allergies, thuoc) == [], thuoc + " KHÔNG báo (" + vi_sao + ")")

print("\n  Liên kết y văn đã bác bỏ — phải im lặng")
# Strom và cs., NEJM 2003, 19.257 người: sulfonamid kháng khuẩn KHÔNG dị ứng
# chéo với sulfonamid không kháng khuẩn.
for thuoc in ["Furosemid 40mg", "Hydroclorothiazid 25mg", "Celecoxib 200mg",
              "Acetazolamid 250mg", "Gliclazid 80mg"]:
    check(tiers("Dị ứng sulfamid", thuoc) == [], "dị ứng sulfamid -> " + thuoc + ": không báo")

# Ức chế COX-2 chọn lọc: đa số người không dung nạp NSAID vẫn dùng được.
check(tiers("Dị ứng aspirin", "Celecoxib 200mg") == [],
      "dị ứng aspirin -> Celecoxib: không báo (COX-2 chọn lọc)")
# Aztreonam không dị ứng chéo với penicilin.
check(tiers("Dị ứng penicillin", "Aztreonam 1g") == [],
      "dị ứng penicilin -> Aztreonam: không báo")
# Nhóm không có số đo thì không được bịa ra khớp chéo.
check(tiers("Dị ứng erythromycin", "Azithromycin 500mg") == [da.GROUP],
      "macrolid: chỉ khớp NHÓM, không dựng khớp chéo")
check(tiers("Dị ứng lidocain", "Procain") == [da.GROUP],
      "thuốc tê: chỉ khớp NHÓM, không chia ester/amid")

# Không có dị ứng thì không có gì để báo.
for thuoc in ["Amoxicillin 500mg", "Cefalexin 500mg"]:
    check(tiers("Không có", thuoc) == [], "ô ghi 'Không có' -> " + thuoc + ": không báo")


# ============================================================ 2. ÂM TÍNH GIẢ
print("\n[2] Âm tính giả — dị ứng có ghi mà không báo")

check(tiers("Dị ứng penicillin", "Amoxicillin 500mg") == [da.GROUP],
      "dị ứng penicilin -> Amoxicillin: báo mức NHÓM")
check(tiers("Dị ứng amoxicilin", "Amoxicillin 500mg") == [da.EXACT],
      "một l / hai l vẫn khớp ĐÚNG hoạt chất")
check(tiers("Dị ứng ampicillin", "Ampicilin 500mg") == [da.EXACT],
      "hai l / một l, chiều ngược lại, vẫn EXACT")
check(da.CROSS in tiers("Dị ứng penicillin", "Cefalexin 500mg"),
      "dị ứng penicilin -> Cefalexin: báo khớp CHÉO (chung chuỗi R1)")
check(da.CROSS in tiers("Dị ứng penicillin", "Ceftriaxon 1g"),
      "dị ứng penicilin -> Ceftriaxon: báo khớp CHÉO (R1 khác)")
check(da.CROSS in tiers("Dị ứng penicillin", "Meropenem 1g"),
      "dị ứng penicilin -> Meropenem: báo khớp CHÉO")
check(tiers("Dị ứng Bactrim", "Sulfamethoxazol + Trimethoprim") == [da.GROUP],
      "tên thông dụng 'Bactrim' -> sulfamethoxazol: báo mức NHÓM")
check(da.GROUP in tiers("Dị ứng NSAID", "Ibuprofen 400mg"),
      "dị ứng 'NSAID' -> Ibuprofen: báo mức NHÓM")
# Aspirin và diclofenac CÙNG một nhóm dị ứng, nên đây là mức NHÓM chứ không
# phải khớp chéo giữa hai nhóm. Mức nhóm ở đây phải mang theo lời cảnh báo
# rằng không dung nạp NSAID có hai kiểu, vì bệnh án hầu như không ghi đủ để
# biết là kiểu nào.
aspi = da.kiem_tra("Dị ứng aspirin", [{"name": "Diclofenac 50mg"}])["ket_qua"][0]["khop"][0]
check(aspi["tier"] == da.GROUP, "dị ứng aspirin -> Diclofenac: mức NHÓM")
check("KHÔNG chéo" in (aspi.get("luu_y") or ""),
      "và kèm cảnh báo rằng kiểu đơn lẻ thì không chéo")
opi = da.kiem_tra("Dị ứng morphin", [{"name": "Codein 30mg"}])["ket_qua"][0]["khop"][0]
check(opi["tier"] == da.GROUP, "dị ứng morphin -> Codein: mức NHÓM")
check("CHƯA có số đo" in (opi.get("luu_y") or ""),
      "và nói thẳng là chưa có số đo, chỉ là thứ tự ưu tiên")

print("\n  Phân hạng phải KHÁC NHAU, không gộp thành một chữ 'cảnh báo'")
r1 = tiers("Dị ứng penicillin", "Cefalexin 500mg")   # chung chuỗi R1: ~16,5%
r2 = tiers("Dị ứng penicillin", "Ceftriaxon 1g")     # R1 khác: ~2,1%
check(r1 == r2 == [da.CROSS], "cả hai đều là CROSS")
one = da.kiem_tra("Dị ứng penicillin", [{"name": "Cefalexin"}])["ket_qua"][0]["khop"][0]
two = da.kiem_tra("Dị ứng penicillin", [{"name": "Ceftriaxon"}])["ket_qua"][0]["khop"][0]
check(one["ty_le"] != two["ty_le"], "nhưng mang HAI tỉ lệ khác nhau, không gộp")
check("16,5" in one["ty_le"] and "2,1" in two["ty_le"], "đúng số của y văn 2022")
check(all(m["nguon"] for m in (one, two)), "mỗi khớp chéo đều kèm nguồn")


# ============================================================ 3. LỜI TỰ NHẬN
print("\n[3] Công cụ không được nhận nhiều hơn nó làm được")

r = da.kiem_tra("Không rõ", [{"name": "Amoxicillin 500mg"}])
check(r["ket_luan"] == "chua_kiem", "'Không rõ' -> chua_kiem, KHÔNG phải đã kiểm sạch")
# Ô RỖNG KHÔNG PHẢI LÀ "KHÔNG DỊ ỨNG". Rỗng nghĩa là chưa ai ghi gì, tức là
# chưa ai hỏi — khác hẳn với ô ghi rõ "Không có". Đây là chỗ dễ nhầm nhất và
# là chỗ y văn cảnh báo thẳng: đừng coi mục chưa điền là mục đã kiểm và sạch.
r = da.kiem_tra("", [{"name": "Amoxicillin 500mg"}])
check(r["ket_luan"] == "chua_kiem", "ô RỖNG -> chua_kiem, KHÔNG phải đã kiểm sạch")
check(r["muc_di_ung"]["trang_thai"] == "khong_biet", "và trạng thái là khong_biet")
r = da.kiem_tra("Không có", [{"name": "Amoxicillin 500mg"}])
check(r["ket_luan"] == "khong_thay_khop", "'Không có' -> khong_thay_khop")
r = da.kiem_tra("Dị ứng hải sản và phấn hoa", [{"name": "Amoxicillin 500mg"}])
check(r["ket_luan"] == "chua_kiem", "dị ứng KHÔNG phải thuốc -> chua_kiem, không nuốt")
check(r["muc_di_ung"]["trang_thai"] == "khong_doc_duoc", "và nói rõ là không đọc ra")

# Câu phủ định KHÔNG được nuốt cả câu có thông tin thật.
r = da.kiem_tra("Không dị ứng penicillin đã biết", [{"name": "Amoxicillin 500mg"}])
check(r["ket_luan"] == "co_khop",
      "'không dị ứng penicillin ĐÃ BIẾT' vẫn là thông tin lâm sàng -> vẫn báo")

print("\n  Không có chữ nào hứa hẹn quá tay trong kết quả trả ra")
blob = json.dumps(da.kiem_tra("Dị ứng penicillin", [{"name": "Paracetamol"}]),
                  ensure_ascii=False).lower()
for cam in ["an toàn", "không có xung đột", "đã kiểm hết"]:
    check(cam not in blob, "không xuất hiện chữ '" + cam + "'")
check(len(da.PHAM_VI["gioi_han"]) >= 4, "có công bố giới hạn phạm vi")

# Mức nặng đọc ra được, và không ghi thì KHÔNG đoán là nhẹ.
check(da.doc_muc_di_ung("Dị ứng penicillin, sốc phản vệ")["muc_nang"] == da.NANG,
      "đọc ra 'sốc phản vệ' -> mức NẶNG")
check(da.doc_muc_di_ung("Dị ứng penicillin")["muc_nang"] is None,
      "không ghi phản ứng -> None, KHÔNG mặc định là nhẹ")

print("\n  Tất định: chạy lại cho kết quả y hệt")
a = da.kiem_tra("Dị ứng penicillin, mề đay", [{"name": "Cefalexin"}, {"name": "Aspirin"}])
b = da.kiem_tra("Dị ứng penicillin, mề đay", [{"name": "Cefalexin"}, {"name": "Aspirin"}])
check(json.dumps(a, ensure_ascii=False) == json.dumps(b, ensure_ascii=False),
      "hai lần gọi cho kết quả trùng khít")


# ------------------------------------------------------------------ QUÉT KHO
# Ba lớp trên kiểm bằng ví dụ tay. Lớp này kiểm bằng CẢ KHO: đem từng tên trong
# 3.816 tên thật ra đối chiếu rồi nhìn tỉ lệ khớp. Tỉ lệ phình lên là dấu hiệu
# bảng đang gom quá rộng — thứ mà ví dụ tay không bao giờ bắt được, vì mình chỉ
# viết ví dụ cho những trường hợp mình đã nghĩ ra.
def sweep():
    chunks = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "backend", "data", "chunks")
    names = set()
    for f in ("DTQGVN-2022-Q1.json", "THUOC-BIET-DUOC-VA-CACH-SU-DUNG.pdf.json"):
        for c in json.load(open(os.path.join(chunks, f), encoding="utf-8")):
            if c.get("generic_name"):
                names.add(c["generic_name"])
    meds = [{"name": n} for n in sorted(names)]
    print("\n[4] Quét cả kho — " + str(len(meds)) + " tên thuốc")
    # Trần đặt rộng hơn số đo hiện tại khá nhiều: đây là lưới bắt việc bảng
    # phình ra, không phải chốt giữ đúng con số của hôm nay.
    TRAN = [("Dị ứng penicillin", 4.0), ("Dị ứng sulfamid", 2.0),
            ("Dị ứng aspirin", 2.0), ("Dị ứng morphin", 1.0),
            ("Dị ứng cephalosporin", 2.0)]
    for allergies, tran in TRAN:
        r = da.kiem_tra(allergies, meds)
        n = len(r["ket_qua"])
        pct = 100.0 * n / len(meds)
        check(pct <= tran, "%-24s khớp %3d/%d = %.1f%% (trần %.1f%%)"
              % (allergies, n, len(meds), pct, tran))
    # Hai cái bẫy chuỗi con, kiểm lại trên chính kho chứ không phải trên ví dụ.
    pen = {k["ten"] for k in da.kiem_tra("Dị ứng amoxicillin", meds)["ket_qua"]}
    check("TAMOXIFEN" not in pen, "TAMOXIFEN không lọt vào nhóm penicilin")
    sul = {k["ten"] for k in da.kiem_tra("Dị ứng sulfamid", meds)["ket_qua"]}
    check("BUSULFAN" not in sul, "BUSULFAN không lọt vào nhóm sulfonamid")
    # MUỐI sulfat là tên có "sulfat" đứng RIÊNG thành một từ — "Atropin sulfat",
    # "Magnesi sulfat". Không phải tên có chuỗi "sulfat" nằm bên trong:
    # SULFATHIOUREA đúng là một sulfonamid kháng khuẩn thật và PHẢI khớp.
    # Bản đầu của phép thử này dò chuỗi con nên chấm SULFATHIOUREA là hỏng —
    # tức là chính phép thử mắc đúng cái lỗi mà nó được viết ra để bắt.
    muoi = {n for n in sul if "sulfat" in n.lower().split()}
    check(not muoi, "không muối sulfat nào lọt vào (thấy: " + (", ".join(sorted(muoi)) or "không") + ")")
    check("SULFATHIOUREA" in sul, "nhưng SULFATHIOUREA thì CÓ, vì đó là sulfonamid thật")


if "--sweep" in sys.argv:
    sweep()


print("\n" + str(checks - len(failures)) + "/" + str(checks) + " đạt")
if failures:
    print("\nHỎNG:")
    for f in failures:
        print("  - " + f)
    sys.exit(1)
print("Đối chiếu dị ứng: tất định, phân hạng, và không nhận quá phần nó làm được.")
