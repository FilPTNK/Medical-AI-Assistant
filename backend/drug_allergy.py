# -*- coding: utf-8 -*-
r"""Đối chiếu dị ứng đã ghi trong bệnh án với thuốc được gợi ý — BẰNG MÃ TẤT ĐỊNH.

Không có mô hình ngôn ngữ nào trong tệp này. Y văn CDS coi kiểm tra dị ứng thuốc
là việc của luật tất định: cùng một bệnh án phải cho cùng một kết quả, mọi lần,
và phải giải thích được vì sao nó báo.


VÌ SAO KHÔNG DÙNG MÃ ATC — DÙ KHO NÀY CÓ SẴN 329 MÃ

Ý đầu tiên là gom nhóm theo `atc_code` đã có trong chunk của Dược thư. Sai.
First Databank — bộ dữ liệu dị ứng thương mại lớn nhất — nói thẳng rằng họ
"định nghĩa nhóm dị ứng THẬT và KHÔNG dùng lại nhóm điều trị hay các phân loại
có sẵn khác". Lý do: ATC xếp thuốc theo *cơ quan đích và mục đích điều trị*,
còn dị ứng đi theo *cấu trúc hoá học*. Hai chuyện đó không trùng nhau:

  - ASPIRIN mang mã A01AD05 (nhóm A = đường tiêu hoá) còn DICLOFENAC mang
    M01AB05 (nhóm M = cơ xương khớp). Cùng một cơ chế dị ứng chéo (ức chế
    COX-1), hai nhánh ATC khác hẳn nhau ngay từ chữ cái đầu.
  - Ngược lại J01 gom mọi kháng sinh toàn thân, trong đó penicilin và
    macrolid không hề dị ứng chéo với nhau.

Đo thêm (Goss và cộng sự, MedInfo 2015) trên NDF-RT: nhánh "cơ chế tác dụng"
cho NPV chỉ 56,8% — tức BỎ SÓT khoảng một nửa số thuốc thật sự dị ứng chéo.
Nên nhóm dị ứng ở đây là BẢNG TỰ SOẠN, từng liên kết ghi rõ nguồn và mức chắc
chắn, chứ không suy ra từ một cây phân loại có sẵn.


BA MỨC KHỚP — VÀ VÌ SAO PHẢI TÁCH RA

Theo mô hình của Oracle Cerner và thuật toán phân tầng của Wasserman
(Int J Med Inform, 01/2025), mức khớp là MỘT TRỤC, mức nặng của phản ứng đã ghi
là TRỤC KIA. Tệp này chỉ tính trục thứ nhất và đọc trục thứ hai ra khỏi bệnh án;
việc quyết định hiện thế nào là của giao diện.

    EXACT  — trùng đúng hoạt chất đã ghi dị ứng.
    GROUP  — cùng nhóm dị ứng (ghi "penicilin", thuốc là amoxicilin).
    CROSS  — dị ứng chéo giữa hai nhóm (penicilin -> cephalosporin).
    UNREAD — có chữ trong ô dị ứng mà tệp này KHÔNG đọc ra.

Tách ra vì đo được là chúng đáng tin khác hẳn nhau. Trên 101.492 cảnh báo
(JAMIA Open 2026) chỉ 9,7% là khớp đúng hoạt chất; 90,3% còn lại là khớp nhóm
hoặc khớp chéo, và 98,9% tổng số bị bác sĩ bỏ qua. Quan trọng hơn: soi lại bệnh
án cho thấy 94–96,5% lần bỏ qua đó là ĐÚNG VỀ LÂM SÀNG (BMJ Qual Saf 2016).
Nghĩa là lỗi nằm ở chỗ cảnh báo nổ, không nằm ở chỗ bác sĩ lười đọc. Gộp bốn
mức này thành một chữ "cảnh báo" đỏ là cách chắc chắn nhất để biến lưới an toàn
thành tiếng ồn.


NHỮNG GÌ TỆP NÀY KHÔNG BAO GIỜ KHẲNG ĐỊNH

1. KHÔNG nói "không có xung đột". Chỉ nói "không khớp gì trong phần chữ đọc
   được". Bộ phân tích dị ứng chữ tự do tốt nhất đã công bố đạt độ nhạy 75,73%
   (PMC12695520, 06/2025) — và đó là tiếng Anh, chưa ai đo cho tiếng Việt.
2. KHÔNG coi ô không đọc được là ô đã kiểm. UNREAD phải hiện ra, khác hẳn với
   "đã kiểm và sạch".
3. KHÔNG khẳng định nhãn dị ứng là dị ứng thật. Hơn 90% người mang nhãn "dị ứng
   penicilin" dung nạp được penicilin khi làm test (PMC6954877).
4. KHÔNG coi khớp chéo là chống chỉ định. Dán nhãn dị ứng quá tay gây hại đo
   được: HR 1,69 với MRSA và 1,26 với C. difficile trên 301.399 người
   (BMJ 2018) — vì bác sĩ bị đẩy sang kháng sinh phổ rộng hơn.

Điểm 4 là lý do bảng dưới đây CỐ Ý NGHÈO. Mọi liên kết chéo không có số đo thì
không được vào bảng; xem `_KHONG_CO_SO_LIEU`.


SO KHỚP THEO TOKEN NGUYÊN VẸN, KHÔNG PHẢI SO KHỚP CHUỖI CON

Đo trên đúng 3.816 tên thuốc của kho này — so khớp chuỗi con sinh ra:

    'amoxi'  -> AMOXICILIN nhưng cũng TAMOXIFEN     (thuốc ung thư vú)
    'sulfa'  -> 27 tên, trong đó BUSULFAN, ITROSULFAN, ATROPIN SULFAT,
                MAGNESI SULFAT — muối sulfat KHÔNG dị ứng chéo với sulfonamid
    'cef'    -> 38 tên, gồm cả 'CEF-3' (tên biệt dược, không phải hoạt chất)

Nên mọi so khớp ở đây là TOKEN NGUYÊN VẸN hoặc CỤM TOKEN LIỀN NHAU.
'busulfan' không bao giờ khớp 'sulfa' vì đó là hai token khác nhau.


CHÍNH TẢ MỘT L HAY HAI L — GỘP BẰNG PHÉP BIẾN ĐỔI, KHÔNG BẰNG LIỆT KÊ

Kho này có CẢ HAI lối viết, vì hai cuốn sách dịch khác nhau:
Dược thư viết AMOXICILIN, AMPICILIN, BENZYLPENICILIN (một chữ l);
cuốn Biệt dược viết AMPICILLIN, ASPOXICILLIN, HETACILLIN (hai chữ l).
Liệt kê tay cả hai lối cho từng tên là thứ chắc chắn sẽ sót.

Nên `_squeeze()` bóp mọi ký tự lặp liền nhau về một: 'ampicillin' và
'ampicilin' cùng về 'ampicilin'. Đo trên 3.816 tên: phép bóp này gây đúng 6 va
chạm, và CẢ SÁU đều là hai lối viết của CÙNG MỘT THUỐC
(allopurinol/alopurinol, attapulgit/atapulgit, cinnarizin/cinarizin,
ampicilin/ampicillin). Không có cặp nào là hai thuốc khác nhau bị trộn lẫn.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

import drug_alias
from text_fold import fold

# --------------------------------------------------------------------------
# Mức khớp. Thứ tự này là thứ tự nghiêm trọng giảm dần, giao diện xếp theo nó.
# --------------------------------------------------------------------------
EXACT = "exact"    # trùng đúng hoạt chất
GROUP = "group"    # cùng nhóm dị ứng
CROSS = "cross"    # dị ứng chéo giữa hai nhóm
UNREAD = "unread"  # có chữ trong ô dị ứng mà không đọc ra

_TIER_ORDER = {EXACT: 0, GROUP: 1, CROSS: 2, UNREAD: 3}


# --------------------------------------------------------------------------
# NHÓM DỊ ỨNG
#
# `forms`   = cách bác sĩ gõ TÊN NHÓM vào ô dị ứng của bệnh án.
# `members` = hoạt chất thuộc nhóm; đây cũng là thứ đem so với tên thuốc kê.
#
# Danh sách hoạt chất lấy từ chính 3.816 tên trong kho, không chép từ trí nhớ.
# Chỉ giữ tên gốc (INN); tên biệt dược thì bỏ — xem `_THIEU_BIET_DUOC`.
# --------------------------------------------------------------------------

_GROUPS: List[Dict[str, Any]] = [
    {
        "id": "penicilin",
        "label": "Penicilin",
        "forms": ["penicilin", "penicillin", "pencilin", "pnc", "peni"],
        "members": [
            "amoxicilin", "ampicilin", "benzylpenicilin", "benzathin penicilin",
            "benzathin penicilin g", "penicilin g", "penicilin v",
            "phenoxymethylpenicilin", "procain penicilin", "clemizol penicilin",
            "oxacilin", "cloxacilin", "dicloxacilin", "flucloxacilin",
            "meticilin", "nafcilin", "piperacilin", "azlocilin", "mezlocilin",
            "ticarcilin", "carbenicilin", "sulbenicilin", "apalcilin",
            "azidocilin", "propicilin", "talampicilin", "etampicilin",
            "hetacilin", "aspoxicilin", "carindacilin", "penamecilin",
            "clometocilin", "amoxicilin va acid clavulanic",
            "ampicilin va sulbactam",
        ],
    },
    {
        # Tách riêng vì đây là nhóm DUY NHẤT có số đo dị ứng chéo cao với
        # penicilin. Bốn thuốc này dùng chung chuỗi bên R1 với aminopenicilin.
        "id": "cephalosporin_r1",
        "label": "Cephalosporin dùng chung chuỗi R1",
        "forms": [],  # không ai gõ tên nhóm này; chỉ tới đây qua tên hoạt chất
        "members": ["cefalexin", "cephalexin", "cefadroxil", "cefaclor", "cefprozil"],
    },
    {
        "id": "cephalosporin",
        "label": "Cephalosporin",
        "forms": ["cephalosporin", "cefalosporin", "cepha"],
        "members": [
            "cefacetril", "cefalotin", "cefamandol", "cefapirin", "cefatrizin",
            "cefazedon", "cefazolin", "cefdinir", "cefditoren", "cefepim",
            "cefetamet", "cefixim", "cefmenoxim", "cefonicid", "cefoperazon",
            "cefoselis", "cefotaxim", "cefotetan", "cefotiam", "cefoxitin",
            "cefozopran", "cefpiramid", "cefpirom", "cefpodoxim", "cefradin",
            "cefsulodin", "ceftazidim", "ceftezol", "ceftibuten", "ceftriaxon",
            "cefuroxim",
        ],
    },
    {
        "id": "carbapenem",
        "label": "Carbapenem",
        "forms": ["carbapenem"],
        "members": ["imipenem", "meropenem", "ertapenem", "doripenem"],
    },
    {
        "id": "monobactam",
        "label": "Monobactam",
        "forms": ["monobactam"],
        "members": ["aztreonam"],
    },
    {
        # Chỉ SULFONAMID KHÁNG SINH. Nhóm amin thơm ở vị trí N4 mới là thứ gây
        # dị ứng; muối sulfat, sulfit và lưu huỳnh KHÔNG liên quan gì.
        "id": "sulfonamid",
        "label": "Sulfonamid kháng khuẩn",
        "forms": ["sulfamid", "sulfonamid", "sulfa", "bactrim", "biseptol"],
        "members": [
            "co-trimoxazol", "cotrimoxazol", "trimoxazol", "sulfamethoxazol",
            "sulfadiazin", "sulfadimidin", "sulfadimethoxin", "sulfadoxin",
            "sulfaguanidin", "sulfamerazin", "sulfamethizol",
            "sulfamethoxypyridazin", "sulfamethylthiazol", "sulfamoxol",
            "sulfanilamid", "sulfaphenazol", "sulfaproxylin", "sulfapyridin",
            "sulfasalazin", "sulfacetamid", "sulfabenzamid", "sulfacarbamid",
            "sulfathiourea",
        ],
    },
    {
        # Dị ứng chéo ở đây là do ỨC CHẾ COX-1, không phải do IgE và không theo
        # từng thuốc. Nên nhóm này cố ý gom rộng.
        "id": "nsaid",
        "label": "Kháng viêm không steroid (ức chế COX-1)",
        "luu_y_trong_nhom": (
            "Không dung nạp NSAID có HAI kiểu và bệnh án thường không ghi đủ để "
            "phân biệt: kiểu do ức chế COX-1 thì chéo với gần như mọi NSAID khác; "
            "kiểu phản ứng với một thuốc đơn lẻ thì đặc hiệu và KHÔNG chéo. "
            "(Khan và cs., JACI 12/2022 — đồng thuận số 22)"
        ),
        "forms": [
            "nsaid", "khang viem khong steroid", "chong viem khong steroid",
            "giam dau khang viem",
        ],
        "members": [
            "aspirin", "acid acetylsalicylic", "acetylsalicylic",
            "ibuprofen", "dexibuprofen", "diclofenac", "naproxen", "ketoprofen",
            "dexketoprofen", "ketorolac", "piroxicam", "tenoxicam", "meloxicam",
            "indomethacin", "indometacin", "sulindac", "mefenamic",
            "acid mefenamic", "flurbiprofen", "tiaprofenic", "nabumeton",
            "nimesulid", "aceclofenac", "etodolac", "alminoprofen",
            "fenoprofen", "oxaprozin", "phenylbutazon",
        ],
    },
    {
        # Ức chế COX-2 chọn lọc — nhóm RIÊNG, vì đa số người không dung nạp
        # NSAID vẫn dùng được. Gom chung vào nhóm trên là đẩy bác sĩ bỏ mất
        # lựa chọn còn an toàn.
        "id": "coxib",
        "label": "Ức chế COX-2 chọn lọc",
        "forms": ["coxib"],
        "members": ["celecoxib", "etoricoxib", "parecoxib", "rofecoxib", "valdecoxib"],
    },
    {
        "id": "opioid_phenanthren",
        "label": "Opioid nhân phenanthren",
        "luu_y_trong_nhom": (
            "Morphin và codein gây mất hạt dưỡng bào qua MRGPRX2 chứ không qua "
            "IgE — giống dị ứng trên lâm sàng nhưng khác cơ chế. Mức chéo trong "
            "nhóm CHƯA có số đo; đây chỉ là thứ tự ưu tiên. "
            "(Baldo, Br J Clin Pharmacol 2023 — tổng quan)"
        ),
        "forms": ["opioid", "opiat"],
        "members": [
            "morphin", "codein", "ethylmorphin", "dihydrocodein", "hydrocodon",
            "oxycodon", "hydromorphon", "oxymorphon", "buprenorphin",
            "nalbuphin", "butorphanol", "dextromethorphan",
        ],
    },
    {
        "id": "opioid_khac",
        "label": "Opioid nhân khác",
        "forms": [],
        "members": ["fentanyl", "pethidin", "meperidin", "methadon", "tramadol",
                    "sufentanil", "alfentanil", "remifentanil", "loperamid"],
    },
]

# Nhóm nhận diện được TÊN nhưng KHÔNG có số đo dị ứng chéo nào đáng tin. Vẫn
# khớp đúng hoạt chất (EXACT/GROUP) nhưng không bao giờ sinh khớp chéo (CROSS).
# Ghi ra đây để lần sau khỏi phải đi tìm lại và tưởng là đã bỏ quên.
_KHONG_CO_SO_LIEU: List[Dict[str, Any]] = [
    {
        "id": "macrolid",
        "label": "Macrolid",
        "forms": ["macrolid"],
        "members": ["erythromycin", "clarithromycin", "azithromycin",
                    "spiramycin", "roxithromycin", "josamycin", "midecamycin"],
        "note": "Mức dị ứng chéo trong nhóm macrolid chưa được đo — "
                "tài liệu tham số 2022 ghi rõ là chưa biết.",
    },
    {
        "id": "quinolon",
        "label": "Quinolon",
        "forms": ["quinolon", "fluoroquinolon"],
        "members": ["ciprofloxacin", "levofloxacin", "ofloxacin", "norfloxacin",
                    "moxifloxacin", "pefloxacin", "lomefloxacin", "acid nalidixic"],
        "note": "Dị ứng chéo trong nhóm ước chừng ~50% nhưng chỉ từ vài loạt "
                "ca lẻ, không đủ để đưa thành con số.",
    },
    {
        "id": "thuoc_te",
        "label": "Thuốc tê",
        "forms": ["thuoc te", "gay te"],
        "members": ["lidocain", "lignocain", "bupivacain", "ropivacain",
                    "mepivacain", "prilocain", "procain", "tetracain",
                    "benzocain", "cloroprocain", "articain"],
        "note": "Cách chia ester/amid là bài giảng kinh điển, KHÔNG có trong "
                "tài liệu tham số 2022. Không đủ căn cứ để báo chéo.",
    },
]


# --------------------------------------------------------------------------
# LIÊN KẾT DỊ ỨNG CHÉO
#
# Mỗi liên kết phải có MỘT SỐ ĐO và MỘT NGUỒN. Không có số thì không vào bảng.
# `rate` là chữ để hiện thẳng cho bác sĩ, không phải số để tính toán.
#
# Liên kết có chiều: ghi dị ứng A, kê thuốc thuộc B. Chiều ngược lại phải khai
# riêng — dị ứng cephalosporin rồi kê penicilin KHÔNG có cùng số đo, vì các
# nghiên cứu đều làm trên người dị ứng penicilin.
# --------------------------------------------------------------------------

# Bảng này CỐ Ý không có liên kết tự trỏ (nhóm X -> chính nhóm X). Hai thuốc
# cùng một nhóm dị ứng đã là mức GROUP rồi; thêm một liên kết chéo cho cùng
# cặp đó chỉ làm một lần khớp đếm thành hai. Lời cảnh báo về chéo TRONG nhóm
# — NSAID có hai kiểu, opioid chưa có số đo — nằm ở `luu_y_trong_nhom` của
# chính nhóm đó và đi kèm mức GROUP.
_CROSS_LINKS: List[Dict[str, str]] = [
    {
        "from": "penicilin", "to": "cephalosporin_r1",
        "rate": "khoảng 16,5% (KTC 95%: 11,1–23,8)",
        "why": "dùng chung chuỗi bên R1 với aminopenicilin",
        "src": "Khan và cs., JACI 150(6):1333, 12/2022 — gộp 21 nghiên cứu",
    },
    {
        "from": "penicilin", "to": "cephalosporin",
        "rate": "khoảng 2,1% (KTC 95%: 1,0–4,5)",
        "why": "chuỗi bên R1 khác hẳn; gần bằng nền chung của người đa dị ứng",
        "src": "Khan và cs., JACI 150(6):1333, 12/2022",
    },
    {
        "from": "penicilin", "to": "carbapenem",
        "rate": "dưới 1% (0,87%; KTC 95%: 0,32–2,32)",
        "why": "gộp 11 nghiên cứu, 1.127 người",
        "src": "Khan và cs., JACI 150(6):1333, 12/2022",
    },
    {
        "from": "cephalosporin_r1", "to": "penicilin",
        "rate": "có, nhưng chưa có số đo riêng cho chiều này",
        "why": "các nghiên cứu đều làm trên người dị ứng penicilin, không phải chiều ngược",
        "src": "suy từ cùng một cơ chế chuỗi R1 — KHÔNG phải số đo",
    },
    {
        # Chiều này CÓ số vì aztreonam và ceftazidim dùng chung đúng một chuỗi.
        "from": "monobactam", "to": "cephalosporin",
        "rate": "chỉ với ceftazidim (chung chuỗi R1); với cephalosporin khác: không",
        "why": "aztreonam không dị ứng chéo với penicilin",
        "src": "Khan và cs., JACI 150(6):1333, 12/2022",
    },
]

# Những liên kết mà người ta HAY TƯỞNG là có, và đo ra là KHÔNG.
# Nằm đây để giao diện nói được câu "đã xét và không phải" — im lặng thì bác sĩ
# tưởng máy bỏ sót.
_KHONG_CHEO: List[Dict[str, str]] = [
    {
        "allergen": "sulfonamid",
        "nhung_khong_voi": "furosemid, hydroclorothiazid, indapamid, celecoxib, "
                           "acetazolamid, sulfonylurea (gliclazid, glyburid), "
                           "sumatriptan, dapson",
        "why": "sulfonamid kháng khuẩn mang nhóm amin thơm ở vị trí N4; các "
               "thuốc trên không có. Nguy cơ cao hơn ở người dị ứng sulfa là do "
               "cơ địa đa dị ứng, không phải do chéo",
        "src": "Strom và cs., NEJM 2003 — 19.257 người",
    },
    {
        "allergen": "sulfonamid",
        "nhung_khong_voi": "muối sulfat (magnesi sulfat, atropin sulfat…), "
                           "sulfit, lưu huỳnh",
        "why": "khác hẳn nhau về hoá học; chỉ trùng vần",
        "src": "Khan và cs., JACI 150(6):1333, 12/2022 — bảng XIV",
    },
    {
        "allergen": "nsaid",
        "nhung_khong_voi": "celecoxib, etoricoxib (ức chế COX-2 chọn lọc)",
        "why": "đa số người không dung nạp NSAID vẫn dùng được",
        "src": "Khan và cs., JACI 150(6):1333, 12/2022 — đồng thuận số 22",
    },
    {
        "allergen": "penicilin",
        "nhung_khong_voi": "aztreonam",
        "why": "không dị ứng chéo với penicilin",
        "src": "Khan và cs., JACI 150(6):1333, 12/2022",
    },
]


# --------------------------------------------------------------------------
# Ô DỊ ỨNG RỖNG, VÀ Ô DỊ ỨNG NÓI "KHÔNG RÕ" — HAI CHUYỆN KHÁC NHAU
#
# App.jsx có NO_DATA_PHRASES gộp cả hai làm một, và với việc TÔ MÀU thẻ thì gộp
# như vậy là đúng: cả hai đều không phải thông tin lâm sàng nên không tô đỏ.
#
# Với việc ĐỐI CHIẾU thì gộp là sai và sai nguy hiểm. "Không có" nghĩa là đã
# hỏi và bệnh nhân không dị ứng gì. "Không rõ" nghĩa là CHƯA AI HỎI. Coi cái
# thứ hai là đã kiểm và sạch đúng là lớp hỏng mà y văn cảnh báo: bác sĩ thấy
# máy im lặng thì tưởng đã có lưới, trong khi chưa có gì được kiểm cả.
# --------------------------------------------------------------------------

_PHU_DINH = {
    "khong", "khong co", "khong bi", "khong di ung", "khong co di ung",
    "chua co", "chua ghi nhan", "khong ghi nhan", "khong co tien su di ung",
    "kcg", "0",
}

_KHONG_BIET = {
    "", "-", "--", "?", "n/a", "na", "khong ro", "chua ro", "chua ghi",
    "chua hoi", "khong nho", "chua khai thac", "unknown",
}

# Mức nặng của phản ứng ĐÃ GHI — trục thứ hai của thuật toán phân tầng.
# Chỉ đọc ra, không suy diễn: không thấy chữ nào thì trả về None, chứ không
# mặc định là nhẹ. 36,2% mục dị ứng beta-lactam trong y văn bỏ trống phần phản
# ứng, nên "không ghi" là trạng thái thường gặp chứ không phải ngoại lệ.
_NANG = [
    ("soc phan ve", "sốc phản vệ"), ("phan ve", "phản vệ"),
    ("phu mach", "phù mạch"), ("phu quincke", "phù Quincke"),
    ("stevens", "hội chứng Stevens-Johnson"), ("lyell", "hội chứng Lyell"),
    ("hoai tu thuong bi", "hoại tử thượng bì"),
    ("kho tho", "khó thở"), ("co that phe quan", "co thắt phế quản"),
    ("tut huyet ap", "tụt huyết áp"), ("ngung tim", "ngừng tim"),
]
_VUA = [
    ("me day", "mề đay"), ("may day", "mày đay"), ("noi ban", "nổi ban"),
    ("phat ban", "phát ban"), ("ngua", "ngứa"), ("man do", "mẩn đỏ"),
]
_NHE = [
    ("buon non", "buồn nôn"), ("non", "nôn"), ("tieu chay", "tiêu chảy"),
    ("day bung", "đầy bụng"), ("dau dau", "đau đầu"), ("chong mat", "chóng mặt"),
]

NANG = "nang"
VUA = "vua"
NHE = "nhe"
KHONG_GHI = None


def _squeeze(s: str) -> str:
    """Bỏ dấu, hạ chữ thường, rồi bóp mọi ký tự lặp liền nhau về một.

    Bước bóp là thứ gộp 'ampicillin' với 'ampicilin' mà không phải liệt kê tay
    cả hai lối viết ở mọi chỗ. Đo trên 3.816 tên trong kho: đúng 6 va chạm, cả
    sáu đều là hai lối viết của cùng một thuốc.
    """
    return re.sub(r"(.)\1+", r"\1", fold(s))


def _tokens(s: str) -> List[str]:
    """Cắt thành token chữ-số, đã bóp. Dấu câu và ký tự lạ đều là ranh giới."""
    return [t for t in re.split(r"[^0-9a-z]+", _squeeze(s)) if t]


def _chua_day(tokens: List[str], can: Tuple[str, ...]) -> bool:
    """Dãy token có chứa dãy con này ở dạng NGUYÊN VẸN không.

    So theo token chứ không theo chuỗi con. Đây đúng là chỗ 'busulfan' không
    được phép khớp 'sulfa', và 'tamoxifen' không được phép khớp 'amoxicilin'.
    """
    n = len(can)
    if not n or n > len(tokens):
        return False
    return any(tuple(tokens[i:i + n]) == can for i in range(len(tokens) - n + 1))


def _chua_cum(tokens: List[str], cum: str) -> bool:
    """Như trên, nhưng nhận chuỗi thô. Chỉ dùng ở chỗ cụm không dựng sẵn được."""
    return _chua_day(tokens, tuple(_tokens(cum)))


# Chỉ mục dựng một lần khi nạp module. Bảng nhỏ (vài trăm mục) nên dựng thẳng.
_ALL_GROUPS = _GROUPS + _KHONG_CO_SO_LIEU
_BY_ID = {g["id"]: g for g in _ALL_GROUPS}

# Mọi cụm trong bảng được tách token MỘT LẦN khi nạp module, không phải tách
# lại ở mỗi lần so. Bảng có khoảng 250 cụm; tách lại mỗi lần nghĩa là mỗi tên
# thuốc phải chạy 250 lượt chuẩn hoá Unicode chỉ để so vài token. Đo khi quét
# thử cả 3.816 tên trong kho thì cách cũ chạy quá hai phút; cách này còn vài
# giây. Bảng là hằng số nên dựng sẵn không mất gì.
_INDEX: List[Tuple[str, str, str, Tuple[str, ...]]] = []
for _g in _ALL_GROUPS:
    for _m in _g["members"]:
        _INDEX.append((_g["id"], "member", _m, tuple(_tokens(_m))))
    for _f in _g.get("forms", []):
        _INDEX.append((_g["id"], "group", _f, tuple(_tokens(_f))))


def _tim_nhom(tokens: List[str]) -> List[Tuple[str, str, str]]:
    """Dãy token này chạm tới nhóm dị ứng nào.

    Trả về danh sách (group_id, kieu, chuoi_khop) với kieu là "member" (khớp
    tên hoạt chất) hoặc "group" (khớp tên nhóm).
    """
    return [(gid, kieu, chuoi) for gid, kieu, chuoi, can in _INDEX
            if _chua_day(tokens, can)]


def doc_muc_di_ung(allergies: Optional[str]) -> Dict[str, Any]:
    """Đọc ô dị ứng chữ tự do thành thứ đối chiếu được.

    `trang_thai` là một trong:
      "trong"       — ô rỗng hoặc ghi rõ là không có dị ứng
      "khong_biet"  — ô nói không rõ / chưa hỏi. KHÁC với "trong".
      "doc_duoc"    — nhận ra ít nhất một nhóm dị ứng
      "khong_doc_duoc" — có chữ thật mà không nhận ra nhóm nào
    """
    raw = (allergies or "").strip()
    norm = re.sub(r"[.,;:!]+$", "", raw.lower()).strip()
    folded = _squeeze(norm)

    if folded in _KHONG_BIET:
        return {"trang_thai": "khong_biet", "raw": raw, "nhom": [], "muc_nang": KHONG_GHI}
    if folded in _PHU_DINH:
        return {"trang_thai": "trong", "raw": raw, "nhom": [], "muc_nang": KHONG_GHI}

    tokens = _tokens(raw)
    if not tokens:
        return {"trang_thai": "trong", "raw": raw, "nhom": [], "muc_nang": KHONG_GHI}

    # Mức nặng đọc từ chính câu chữ bác sĩ đã ghi.
    muc_nang, nhan_nang = KHONG_GHI, None
    for bang, muc in ((_NANG, NANG), (_VUA, VUA), (_NHE, NHE)):
        for cum, nhan in bang:
            if _chua_cum(tokens, cum):
                muc_nang, nhan_nang = muc, nhan
                break
        if muc_nang:
            break

    hits = _tim_nhom(tokens)
    if not hits:
        # CÓ chữ mà không đọc ra. Đây là trạng thái phải hiện, không được nuốt.
        return {"trang_thai": "khong_doc_duoc", "raw": raw, "nhom": [],
                "muc_nang": muc_nang, "nhan_nang": nhan_nang}

    nhom = []
    for gid, kieu, chuoi in hits:
        nhom.append({"id": gid, "label": _BY_ID[gid]["label"], "kieu": kieu, "khop": chuoi})
    return {"trang_thai": "doc_duoc", "raw": raw, "nhom": nhom,
            "muc_nang": muc_nang, "nhan_nang": nhan_nang}


def _doi_chieu_mot_thuoc(ten_thuoc: str, muc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Một tên thuốc so với một ô dị ứng đã đọc. Trả về các lần khớp."""
    tokens = _tokens(ten_thuoc)
    if not tokens:
        return []
    thuoc_nhom = _tim_nhom(tokens)
    if not thuoc_nhom:
        return []

    di_ung_ids = {n["id"] for n in muc["nhom"]}
    ket: List[Dict[str, Any]] = []
    da_co = set()

    for gid, kieu, chuoi in thuoc_nhom:
        # --- EXACT: chính hoạt chất đó nằm trong ô dị ứng
        for n in muc["nhom"]:
            if n["kieu"] == "member" and n["khop"] == chuoi and kieu == "member":
                key = (EXACT, chuoi)
                if key not in da_co:
                    da_co.add(key)
                    ket.append({
                        "tier": EXACT, "thuoc_khop": chuoi, "nhom": gid,
                        "nhom_label": _BY_ID[gid]["label"],
                        "di_ung_khop": n["khop"],
                        "vi_sao": "trùng đúng hoạt chất đã ghi dị ứng",
                        "ty_le": None, "nguon": None,
                    })

        # --- GROUP: cùng nhóm dị ứng
        if gid in di_ung_ids:
            nguon_khop = next(n for n in muc["nhom"] if n["id"] == gid)
            if not any(k["tier"] == EXACT and k["thuoc_khop"] == chuoi for k in ket):
                key = (GROUP, gid, chuoi)
                if key not in da_co:
                    da_co.add(key)
                    ket.append({
                        "tier": GROUP, "thuoc_khop": chuoi, "nhom": gid,
                        "nhom_label": _BY_ID[gid]["label"],
                        "di_ung_khop": nguon_khop["khop"],
                        "vi_sao": f"cùng nhóm {_BY_ID[gid]['label']}",
                        "ty_le": None, "nguon": None,
                        "luu_y": _BY_ID[gid].get("luu_y_trong_nhom"),
                    })

        # --- CROSS: dị ứng chéo giữa hai nhóm, CHỈ khi bảng có số đo
        for link in _CROSS_LINKS:
            if link["to"] != gid or link["from"] not in di_ung_ids:
                continue
            nguon_khop = next(n for n in muc["nhom"] if n["id"] == link["from"])
            key = (CROSS, link["from"], gid, chuoi)
            if key in da_co:
                continue
            da_co.add(key)
            ket.append({
                "tier": CROSS, "thuoc_khop": chuoi, "nhom": gid,
                "nhom_label": _BY_ID[gid]["label"],
                "di_ung_khop": nguon_khop["khop"],
                "vi_sao": link["why"], "ty_le": link["rate"], "nguon": link["src"],
            })

    ket.sort(key=lambda k: _TIER_ORDER[k["tier"]])
    return ket


# Phạm vi tự khai. Không phải phép lịch sự: ONC HTI-1 bắt buộc công cụ hỗ trợ
# quyết định lâm sàng phải công bố thuộc tính "cautioned out-of-scope use" bằng
# lời thường, và đây là chỗ nó sống.
PHAM_VI = {
    "nhom_co_so_lieu": [g["label"] for g in _GROUPS],
    "nhom_chi_khop_ten": [g["label"] for g in _KHONG_CO_SO_LIEU],
    "gioi_han": [
        "Chỉ đọc được phần chữ trong ô dị ứng. Bộ phân tích chữ tự do tốt nhất "
        "đã công bố đạt độ nhạy 75,73% và đó là trên tiếng Anh — chưa ai đo cho "
        "tiếng Việt.",
        "Chỉ so theo tên hoạt chất. Đơn kê bằng tên biệt dược mà không kèm hoạt "
        "chất thì không đối chiếu được.",
        "Không kiểm tương tác thuốc–thuốc, không kiểm liều, không kiểm chống "
        "chỉ định theo bệnh nền.",
        "Nhãn dị ứng trong bệnh án phần lớn không phải dị ứng thật: hơn 90% "
        "người mang nhãn dị ứng penicilin dung nạp được khi làm test.",
    ],
}


def kiem_tra(allergies: Optional[str],
             medications: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Đối chiếu ô dị ứng với danh sách thuốc. Đây là toàn bộ API công khai.

    KHÔNG BAO GIỜ trả về "không có xung đột". Trường `ket_luan` chỉ nhận một
    trong ba giá trị, và cả ba đều nói về PHÉP ĐO chứ không nói về bệnh nhân:

        "co_khop"        — tìm thấy ít nhất một lần khớp
        "khong_thay_khop"— không khớp gì TRONG PHẦN CHỮ ĐỌC ĐƯỢC
        "chua_kiem"      — không đủ dữ kiện để kiểm (ô trống, không rõ, hoặc
                           không đọc ra chữ nào)

    "chua_kiem" tồn tại riêng vì đó là điều kiện mà im lặng gây hiểu lầm nặng
    nhất: bác sĩ thấy không có cảnh báo thì tưởng đã kiểm và sạch.
    """
    muc = doc_muc_di_ung(allergies)
    meds = [m for m in (medications or []) if isinstance(m, dict) and (m.get("name") or "").strip()]

    ket_qua: List[Dict[str, Any]] = []
    tong_khop = 0
    if muc["trang_thai"] == "doc_duoc":
        for i, m in enumerate(meds):
            # Biệt dược được viết kèm tên hoạt chất ("Zinnat (Cefuroxim)") để
            # nhận ra nhóm dị ứng — chỉ THÊM khả năng cảnh báo, không bớt.
            khop = _doi_chieu_mot_thuoc(drug_alias.with_resolved_name(m["name"]), muc)
            tong_khop += len(khop)
            if khop:
                ket_qua.append({"index": i, "ten": m["name"], "khop": khop})

    if muc["trang_thai"] in ("khong_biet", "khong_doc_duoc"):
        ket_luan = "chua_kiem"
    elif muc["trang_thai"] == "trong":
        # Ô ghi rõ "không có". Vẫn KHÔNG gọi là đã kiểm sạch — chỉ là không có
        # gì để đối chiếu.
        ket_luan = "khong_thay_khop"
    elif tong_khop:
        ket_luan = "co_khop"
    else:
        ket_luan = "khong_thay_khop"

    # Những chuyện "hay tưởng là chéo mà đo ra là không", lọc theo đúng nhóm dị
    # ứng của bệnh nhân này. Nói ra được thì bác sĩ biết máy đã xét chứ không bỏ sót.
    ids = {n["id"] for n in muc["nhom"]}
    da_xet = [k for k in _KHONG_CHEO if k["allergen"] in ids]

    return {
        "ket_luan": ket_luan,
        "muc_di_ung": muc,
        "so_thuoc": len(meds),
        "so_thuoc_co_khop": len(ket_qua),
        "ket_qua": ket_qua,
        "da_xet_khong_cheo": da_xet,
        "pham_vi": PHAM_VI,
    }
