# -*- coding: utf-8 -*-
r"""Đối chiếu tương tác thuốc–thuốc trong một đơn — BẰNG MÃ TẤT ĐỊNH, đọc từ Dược thư.

Cùng triết lý với drug_allergy.py: không có mô hình ngôn ngữ nào ở đây, cùng một
đơn thuốc luôn cho cùng một kết quả, và mỗi cảnh báo kèm NGUYÊN CÂU trong sách
cùng số trang để bác sĩ tự kiểm.


VÌ SAO ĐỌC TỪ DƯỢC THƯ CHỨ KHÔNG DÙNG CƠ SỞ DỮ LIỆU TƯƠNG TÁC

API tương tác của NLM (RxNav) đã ngừng từ 01/2024; các bộ dữ liệu còn lại
(DrugBank, Lexicomp, Medscape) đều trả phí và viết theo thuốc lưu hành ở Mỹ. Dược
thư Quốc gia 2022 thì đã nằm trong kho: 1.257 đoạn thuộc mục "Tương tác thuốc"
của 728 chuyên luận, đúng nguồn mà bác sĩ Việt Nam vẫn tra bằng tay.

Cái giá: mục đó là VĂN XUÔI đã OCR, không phải bảng cặp thuốc. Nên tệp này
không "biết" tương tác — nó chỉ tìm câu mà chuyên luận của thuốc A nhắc tới
thuốc B (hoặc nhóm của B), và đọc mức độ từ chính câu đó.


HAI KIỂU KHỚP

    TEN  — câu nhắc ĐÍCH DANH thuốc kia (tên gốc, tên đồng nghĩa, tên quốc tế).
    NHOM — câu nhắc NHÓM chứa thuốc kia ("NSAID", "statin", "macrolid"...).
           Nhóm xác định bằng mã ATC có sẵn trong chuyên luận. Khác hẳn dị ứng
           (đi theo cấu trúc hoá học, xem drug_allergy.py): tương tác phần lớn đi
           theo cơ chế dược lý, và đó chính là thứ ATC phân loại.

So khớp theo TOKEN NGUYÊN VẸN như drug_allergy.py, vì cùng một lý do: so chuỗi
con thì 'amoxi' khớp cả TAMOXIFEN.


MỨC ĐỘ — ĐỌC TỪ CHỮ TRONG CÂU, KHÔNG TỰ GÁN

    CHONG_CHI_DINH — câu có "chống chỉ định"
    TRANH          — "tránh dùng", "không nên dùng/phối hợp"...
    THAN_TRONG     — "tăng nguy cơ", "theo dõi", "điều chỉnh liều", "tăng/giảm
                     nồng độ/tác dụng"...
    CO_NHAC        — có nhắc tên nhưng câu không có từ chỉ mức độ nào
    KHONG_TUONG_TAC— câu nói rõ "không có tương tác" / "không ảnh hưởng"

Câu có nhiều từ khoá thì lấy mức nặng nhất. Mức của một cặp là mức nặng nhất
trong các câu bằng chứng.


NHỮNG GÌ TỆP NÀY KHÔNG BAO GIỜ KHẲNG ĐỊNH

1. KHÔNG nói "đơn an toàn". Chỉ nói "không thấy câu nào nhắc tới cặp này trong
   mục Tương tác thuốc của Dược thư". Sách không liệt kê hết, OCR có thể làm
   hỏng đúng tên thuốc cần tìm.
2. Thuốc không nhận ra trong Dược thư (tên biệt dược, gõ sai) được liệt kê riêng
   là CHƯA KIỂM, không im lặng bỏ qua.
3. Không kiểm liều, không kiểm theo bệnh nền, không kiểm tương tác với thức ăn.
"""

import json
import os
import re
import threading
from typing import Any, Dict, List, Optional, Tuple

import documents
import drug_alias
from drug_allergy import _chua_day, _tokens

# --------------------------------------------------------------------------
# Mức độ, theo thứ tự nặng giảm dần — giao diện xếp theo thứ tự này.
# --------------------------------------------------------------------------
CHONG_CHI_DINH = "chong_chi_dinh"
TRANH = "tranh"
THAN_TRONG = "than_trong"
CO_NHAC = "co_nhac"
KHONG_TUONG_TAC = "khong_tuong_tac"

_MUC_ORDER = {CHONG_CHI_DINH: 0, TRANH: 1, THAN_TRONG: 2, CO_NHAC: 3, KHONG_TUONG_TAC: 4}

MUC_LABEL = {
    CHONG_CHI_DINH: "Chống chỉ định phối hợp",
    TRANH: "Tránh phối hợp",
    THAN_TRONG: "Thận trọng / theo dõi",
    CO_NHAC: "Có nhắc tới",
    KHONG_TUONG_TAC: "Sách ghi không tương tác",
}

TEN = "ten"
NHOM = "nhom"

# Cụm từ (đã gấp dấu) chỉ mức độ. Viết dạng token để dùng _chua_day.
_KHOA: List[Tuple[str, List[str]]] = [
    (CHONG_CHI_DINH, ["chong chi dinh"]),
    (TRANH, ["tranh dung", "tranh phoi hop", "tranh ket hop", "nen tranh", "tranh cac",
             "tranh su ket hop", "khong khuyen cao",
             "khong nen dung", "khong nen phoi hop", "khong nen ket hop",
             "khong duoc dung", "khong dung dong thoi", "khong dung chung",
             "khong phoi hop", "khong ket hop"]),
    (THAN_TRONG, ["tang nguy co", "lam tang nguy co", "nguy co", "theo doi",
                  "dieu chinh lieu", "giam lieu", "than trong", "tang nong do",
                  "giam nong do", "tang tac dung", "giam tac dung", "tang doc tinh",
                  "doc tinh", "keo dai khoang qt", "xuat huyet", "ha kali", "tang kali",
                  "ha duong huyet", "ha huyet ap", "ton thuong than", "suy than",
                  "tieu co van", "hoi chung serotonin", "lam giam hap thu",
                  "giam hap thu", "tang hap thu", "uc che chuyen hoa", "cam ung",
                  "chay mau", "hiep dong", "suy tuy", "doc voi than", "doc voi tai",
                  "tang thoi gian prothrombin", "tang inr"]),
]
_KHONG_TUONG_TAC_CUM = ["khong co tuong tac", "khong tuong tac", "khong anh huong",
                        "khong thay tuong tac", "khong lam thay doi"]
_KHOA_TOK = [(muc, [tuple(_tokens(c)) for c in cums]) for muc, cums in _KHOA]
_KHONG_TT_TOK = [tuple(_tokens(c)) for c in _KHONG_TUONG_TAC_CUM]


def muc_cua_cau(cau_tokens: List[str]) -> str:
    for muc, cums in _KHOA_TOK:
        if any(_chua_day(cau_tokens, c) for c in cums):
            # "không có tương tác ... không cần điều chỉnh liều" vẫn là câu phủ định
            if muc != CHONG_CHI_DINH and any(_chua_day(cau_tokens, c) for c in _KHONG_TT_TOK):
                return KHONG_TUONG_TAC
            return muc
    if any(_chua_day(cau_tokens, c) for c in _KHONG_TT_TOK):
        return KHONG_TUONG_TAC
    return CO_NHAC


# --------------------------------------------------------------------------
# NHÓM DƯỢC LÝ — tên nhóm như sách viết, tiền tố ATC, và thành viên liệt kê tay.
#
# Chỉ những nhóm hay xuất hiện trong mục Tương tác thuốc. Tên nhóm viết đủ các
# lối mà Dược thư dùng (có dấu hay không đều được, vì so sau khi gấp dấu).
#
# Vì sao cần cả `members` lẫn `atc`: mã ATC trong kho đi qua OCR và không tin
# được một mình. Đo trên kho: IBUPROFEN mang C01EB16 (mã dùng để đóng ống động
# mạch, không phải M01 của NSAID), SIMVASTATIN không có mã nào. Chỉ dùng ATC thì
# chuyên luận warfarin nói "NSAID" mà không nối được tới ibuprofen.
# --------------------------------------------------------------------------
_NHOM: List[Dict[str, Any]] = [
    {"id": "nsaid", "label": "NSAID",
     "forms": ["nsaid", "thuoc chong viem khong steroid", "chong viem khong steroid",
               "khang viem khong steroid", "thuoc giam dau chong viem khong steroid", "ains"],
     "members": ["ibuprofen", "diclofenac", "naproxen", "meloxicam", "piroxicam", "celecoxib", "etoricoxib", "ketoprofen", "indometacin", "ketorolac", "aceclofenac", "nabumeton", "acid mefenamic"],
     "atc": ["M01A", "N02BA"]},
    {"id": "khang_vitamin_k", "label": "thuốc kháng vitamin K",
     "forms": ["khang vitamin k", "thuoc chong dong khang vitamin k", "coumarin", "dan chat coumarin"],
     "members": ["warfarin", "acenocoumarol"],
     "atc": ["B01AA"]},
    {"id": "chong_dong", "label": "thuốc chống đông",
     "forms": ["thuoc chong dong", "thuoc chong dong mau", "chong dong mau"],
     "atc": ["B01AA", "B01AB", "B01AE", "B01AF", "B01AX"]},
    {"id": "chong_ket_tap", "label": "thuốc chống kết tập tiểu cầu",
     "forms": ["chong ket tap tieu cau", "uc che ket tap tieu cau"],
     "members": ["clopidogrel", "ticagrelor", "prasugrel", "aspirin", "acid acetylsalicylic", "dipyridamol"],
     "atc": ["B01AC"]},
    {"id": "heparin", "label": "heparin", "forms": ["heparin"], "atc": ["B01AB"]},
    {"id": "statin", "label": "statin",
     "forms": ["statin", "chat uc che hmg coa reductase", "uc che hmg coa reductase"],
     "members": ["simvastatin", "atorvastatin", "rosuvastatin", "pravastatin", "lovastatin", "fluvastatin", "pitavastatin"],
     "atc": ["C10AA"]},
    {"id": "macrolid", "label": "macrolid", "forms": ["macrolid", "khang sinh macrolid"], "members": ["erythromycin", "clarithromycin", "azithromycin", "roxithromycin", "spiramycin"],
     "atc": ["J01FA"]},
    {"id": "quinolon", "label": "quinolon/fluoroquinolon",
     "forms": ["quinolon", "fluoroquinolon", "khang sinh quinolon"], "members": ["ciprofloxacin", "levofloxacin", "ofloxacin", "moxifloxacin", "norfloxacin", "acid nalidixic"],
     "atc": ["J01MA", "J01MB"]},
    {"id": "aminoglycosid", "label": "aminoglycosid",
     "forms": ["aminoglycosid", "khang sinh aminoglycosid"], "atc": ["J01GB"]},
    {"id": "azol", "label": "thuốc chống nấm nhóm azol",
     "forms": ["thuoc chong nam azol", "chong nam nhom azol", "dan chat azol", "nhom azol"],
     "members": ["fluconazol", "itraconazol", "ketoconazol", "voriconazol", "posaconazol", "miconazol"],
     "atc": ["J02AC", "J02AB"]},
    {"id": "ppi", "label": "thuốc ức chế bơm proton",
     "forms": ["uc che bom proton", "thuoc uc che bom proton"], "members": ["omeprazol", "esomeprazol", "lansoprazol", "pantoprazol", "rabeprazol"],
     "atc": ["A02BC"]},
    {"id": "khang_h2", "label": "thuốc kháng H2",
     "forms": ["khang thu the h2", "thuoc khang h2", "khang histamin h2"], "atc": ["A02BA"]},
    {"id": "antacid", "label": "thuốc kháng acid",
     "forms": ["thuoc khang acid", "antacid", "thuoc chong acid"], "atc": ["A02A"]},
    {"id": "ssri", "label": "SSRI",
     "forms": ["ssri", "uc che tai thu hoi chon loc serotonin", "uc che tai hap thu chon loc serotonin",
               "uc che chon loc tai hap thu serotonin", "uc che chon loc tai thu hoi serotonin"],
     "members": ["fluoxetin", "sertralin", "paroxetin", "citalopram", "escitalopram", "fluvoxamin"],
     "atc": ["N06AB"]},
    {"id": "ba_vong", "label": "thuốc chống trầm cảm ba vòng",
     "forms": ["chong tram cam ba vong", "thuoc chong tram cam 3 vong"], "atc": ["N06AA"]},
    {"id": "maoi", "label": "thuốc ức chế MAO",
     "forms": ["maoi", "uc che mao", "uc che monoamin oxidase"], "atc": ["N06AF", "N06AG"]},
    {"id": "benzodiazepin", "label": "benzodiazepin", "forms": ["benzodiazepin"], "atc": ["N05BA", "N05CD"]},
    {"id": "opioid", "label": "opioid",
     "forms": ["opioid", "thuoc giam dau opioid", "dan chat opioid", "thuoc giam dau gay ngu"],
     "members": ["morphin", "codein", "tramadol", "fentanyl", "pethidin", "oxycodon", "methadon"],
     "atc": ["N02A"]},
    {"id": "chen_beta", "label": "thuốc chẹn beta",
     "forms": ["chen beta", "thuoc chen beta", "chen thu the beta"], "atc": ["C07"]},
    {"id": "chen_calci", "label": "thuốc chẹn kênh calci",
     "forms": ["chen kenh calci", "thuoc chen kenh calci", "doi khang calci"], "atc": ["C08"]},
    {"id": "ace", "label": "thuốc ức chế men chuyển",
     "forms": ["uc che men chuyen", "uc che enzym chuyen", "uc che ace", "thuoc uc che enzym chuyen angiotensin"],
     "members": ["enalapril", "captopril", "lisinopril", "perindopril", "ramipril", "imidapril"],
     "atc": ["C09A", "C09B"]},
    {"id": "arb", "label": "thuốc chẹn thụ thể angiotensin II",
     "forms": ["chen thu the angiotensin", "doi khang thu the angiotensin"], "members": ["losartan", "valsartan", "irbesartan", "telmisartan", "candesartan"],
     "atc": ["C09C", "C09D"]},
    {"id": "loi_tieu", "label": "thuốc lợi tiểu",
     "forms": ["thuoc loi tieu", "loi tieu"], "atc": ["C03"]},
    {"id": "loi_tieu_thiazid", "label": "lợi tiểu thiazid",
     "forms": ["thiazid", "loi tieu thiazid"], "members": ["hydroclorothiazid", "indapamid", "clorthalidon"],
     "atc": ["C03A"]},
    {"id": "loi_tieu_quai", "label": "lợi tiểu quai",
     "forms": ["loi tieu quai"], "members": ["furosemid", "torasemid", "bumetanid"],
     "atc": ["C03C"]},
    {"id": "loi_tieu_giu_kali", "label": "lợi tiểu giữ kali",
     "forms": ["loi tieu giu kali"], "members": ["spironolacton", "amilorid", "triamteren", "eplerenon"],
     "atc": ["C03D"]},
    {"id": "corticosteroid", "label": "corticosteroid",
     "forms": ["corticosteroid", "corticoid", "glucocorticoid"], "atc": ["H02AB"]},
    {"id": "glycosid_tim", "label": "glycosid tim",
     "forms": ["glycosid tim", "digitalis"], "atc": ["C01AA"]},
    {"id": "sulfonylure", "label": "sulfonylure",
     "forms": ["sulfonylure", "sulfonylurea"], "atc": ["A10BB"]},
    {"id": "ha_duong_huyet", "label": "thuốc hạ đường huyết",
     "forms": ["thuoc ha duong huyet", "thuoc chong dai thao duong", "thuoc dieu tri dai thao duong"],
     "atc": ["A10"]},
    {"id": "khang_histamin_h1", "label": "thuốc kháng histamin H1",
     "forms": ["khang histamin h1", "thuoc khang histamin"], "atc": ["R06A"]},
    {"id": "tetracyclin", "label": "tetracyclin", "forms": ["tetracyclin", "nhom tetracyclin"], "atc": ["J01AA"]},
    {"id": "nitrat", "label": "nitrat",
     # Không có "nitrat" trơn: đó cũng là gốc muối (miconazol nitrat...).
     "forms": ["nitrat huu co", "cac nitrat", "thuoc nitrat", "dan chat nitrat", "cho nitric oxid",
               "cho no", "nitrovasodilator"],
     "members": ["glyceryl trinitrat", "nitroglycerin", "isosorbid dinitrat", "isosorbid mononitrat"],
     "atc": ["C01DA"]},
    {"id": "pde5", "label": "thuốc ức chế phosphodiesterase typ 5",
     "forms": ["uc che phosphodiesterase typ 5", "uc che phosphodiesterase 5", "uc che pde5", "uc che pde 5"],
     "members": ["sildenafil", "tadalafil", "vardenafil"],
     "atc": ["G04BE"]},
]
_NHOM_MEMBERS_TOK = {g["id"]: [tuple(_tokens(m)) for m in g.get("members", [])] for g in _NHOM}
_NHOM_FORMS_TOK = {g["id"]: [tuple(_tokens(f)) for f in g["forms"]] for g in _NHOM}
_NHOM_BY_ID = {g["id"]: g for g in _NHOM}

# Hậu tố muối/gốc: bác sĩ thường kê "Warfarin 5 mg" chứ không viết "warfarin natri".
_MUOI = set(_tokens(
    "natri kali calci magnesi hydroclorid clorid hydrobromid bromid sulfat maleat "
    "besilat mesylat mesilat tartrat citrat acetat phosphat succinat fumarat "
    "lactat gluconat nitrat dihydrat monohydrat trihydrat hyclat sodium potassium "
    "calcium hydrochloride sulfate dipropionat propionat valerat"
))


# --------------------------------------------------------------------------
# Chỉ mục: dựng một lần từ các tệp chunk của Dược thư.
# --------------------------------------------------------------------------

def _bien_the_ten(ten: str) -> List[Tuple[str, ...]]:
    """Các dãy token dùng để nhận ra một hoạt chất: tên đủ và tên bỏ hậu tố muối."""
    tok = tuple(_tokens(ten))
    if not tok:
        return []
    out = {tok}
    goc = tuple(t for t in tok if t not in _MUOI)
    # Bỏ muối mà chỉ còn một token ngắn (vd. "kali clorid" -> không còn gì) thì giữ tên đủ.
    if goc and goc != tok and (len(goc) > 1 or len(goc[0]) >= 5):
        out.add(goc)
    return list(out)


class _Index:
    def __init__(self, chuyen_luan: List[Dict[str, Any]]):
        self.chuyen_luan = chuyen_luan
        # Danh sách (dãy token, chỉ số chuyên luận), dài trước: "acid acetylsalicylic"
        # phải thắng "acid" khi nhận diện tên kê đơn.
        self.ten: List[Tuple[Tuple[str, ...], int]] = sorted(
            ((v, i) for i, c in enumerate(chuyen_luan) for v in c["bien_the"]),
            key=lambda x: -len(x[0]),
        )


def _cat_cau(text: str) -> List[str]:
    text = re.sub(r"-\n(?=\w)", "", text or "")       # nối chữ bị ngắt dòng
    text = re.sub(r"\s+", " ", text).strip()
    return [c.strip() for c in re.split(r"(?<=[.;!?])\s+(?=[A-ZÀ-Ỹ0-9(\-•])", text) if len(c.strip()) > 15]


def _dung_chi_muc(doc_names: List[str]) -> _Index:
    by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for doc in doc_names:
        path = documents.chunks_path(doc)
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            chunks = json.load(f)
        for ch in chunks:
            ten = (ch.get("generic_name") or "").strip()
            if not ten or ten == "UNKNOWN_DRUG":
                continue
            c = by_key.setdefault((doc, ten), {
                "ten": ten, "doc_name": doc, "atc": ch.get("atc_code") or "",
                "names": {ten, *(ch.get("synonyms") or []), *( [ch["intl_name"]] if ch.get("intl_name") else [])},
                "cau": [], "_seen": set(),
            })
            if ch.get("field_name") != "Tương tác thuốc":
                continue
            page = ch.get("page_in_file") or ch.get("pdf_page") or 1
            for cau in _cat_cau(ch.get("content", "")):
                key = tuple(_tokens(cau))
                # Chunk gối đầu nhau nên một câu có thể lặp lại; câu bị cắt dở ở
                # mép chunk là tiền tố của câu đủ — vẫn giữ, vô hại.
                if key in c["_seen"]:
                    continue
                c["_seen"].add(key)
                c["cau"].append({"text": cau, "tokens": list(key), "page": page})
    out = []
    for c in by_key.values():
        c.pop("_seen")
        c["bien_the"] = [v for n in c["names"] for v in _bien_the_ten(n)]
        c["nhom"] = sorted(
            g["id"] for g in _NHOM
            if (c["atc"] and any(c["atc"].startswith(p) for p in g["atc"]))
            or any(m in c["bien_the"] for m in _NHOM_MEMBERS_TOK[g["id"]])
        )
        c["names"] = sorted(c["names"])
        out.append(c)
    return _Index(out)


_index: Optional[_Index] = None
_index_lock = threading.Lock()


def _nguon_duoc_thu() -> List[str]:
    """Các quyển Dược thư (tài liệu chung, parser dtqg) đang có trong kho."""
    return [m["doc_name"] for m in documents.list_manifests()
            if (m.get("parser") or "").startswith("dtqg") and documents.visibility_of(m) == "shared"]


def chi_muc() -> _Index:
    global _index
    if _index is None:
        with _index_lock:
            if _index is None:
                _index = _dung_chi_muc(_nguon_duoc_thu())
    return _index


def lam_moi() -> None:
    """Gọi sau khi nạp lại Dược thư."""
    global _index
    _index = None


# --------------------------------------------------------------------------
# Đối chiếu
# --------------------------------------------------------------------------

def nhan_dien(ten_ke: str, idx: Optional[_Index] = None) -> Optional[Dict[str, Any]]:
    """Tên trên đơn ("Warfarin 5mg", "Amoxicillin 500 mg") -> chuyên luận Dược thư."""
    idx = idx or chi_muc()
    tok = _tokens(ten_ke)
    for bien_the, i in idx.ten:
        if _chua_day(tok, bien_the):
            return idx.chuyen_luan[i]
    # Biệt dược / tên Mỹ ("Mucodyne", "albuterol"): hỏi kho bí danh thuốc rồi
    # thử lại với tên hoạt chất. Trước đây những tên này rơi vào "chưa kiểm".
    resolved = drug_alias.with_resolved_name(ten_ke)
    if resolved != ten_ke:
        tok = _tokens(resolved)
        for bien_the, i in idx.ten:
            if _chua_day(tok, bien_the):
                return idx.chuyen_luan[i]
    return None


def _bang_chung(a: Dict[str, Any], b: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Câu trong mục Tương tác thuốc của A nhắc tới B (đích danh hoặc theo nhóm)."""
    ket = []
    for cau in a["cau"]:
        kieu, khop = None, None
        for v in b["bien_the"]:
            if _chua_day(cau["tokens"], v):
                kieu, khop = TEN, " ".join(v)
                break
        if kieu is None:
            for gid in b["nhom"]:
                if any(_chua_day(cau["tokens"], f) for f in _NHOM_FORMS_TOK[gid]):
                    kieu, khop = NHOM, _NHOM_BY_ID[gid]["label"]
                    break
        if kieu is None:
            continue
        ket.append({
            "muc": muc_cua_cau(cau["tokens"]),
            "kieu": kieu,
            "khop": khop,
            "trong_chuyen_luan": a["ten"],
            "cau": cau["text"][:600],
            "doc_name": a["doc_name"],
            "page_num": cau["page"],
            "citation": documents.display_citation(a["doc_name"], cau["page"]),
        })
    # Đích danh trước nhóm, nặng trước nhẹ; mỗi chiều tối đa 3 câu.
    ket.sort(key=lambda k: (k["kieu"] != TEN, _MUC_ORDER[k["muc"]]))
    return ket[:3]


PHAM_VI = {
    "nguon": "Mục \"Tương tác thuốc\" của Dược thư Quốc gia Việt Nam 2022 (bản OCR trong kho).",
    "gioi_han": [
        "Chỉ tìm câu mà sách nhắc tới cặp thuốc; sách không liệt kê mọi tương tác, "
        "và lỗi OCR có thể làm hỏng đúng tên cần tìm. Không thấy cảnh báo KHÔNG có "
        "nghĩa là phối hợp an toàn.",
        "Chỉ nhận ra thuốc kê theo tên hoạt chất có chuyên luận trong Dược thư. "
        "Tên biệt dược và thuốc phối hợp nhiều hoạt chất có thể không nhận ra.",
        "Mức độ đọc từ chữ trong câu (\"chống chỉ định\", \"tránh\", \"theo dõi\"...), "
        "không phải phân hạng của một cơ sở dữ liệu tương tác chuẩn.",
        "Không kiểm liều, không kiểm theo bệnh nền, không kiểm tương tác với thức ăn, rượu.",
    ],
}


def kiem_tra(medications: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Toàn bộ API công khai. Như drug_allergy.kiem_tra, KHÔNG BAO GIỜ nói "an toàn".

    ket_luan:
        "co_tuong_tac"  — có ít nhất một cặp được sách nhắc tới (trừ câu "không tương tác")
        "khong_thay"    — đã nhận ra ≥2 hoạt chất nhưng sách không nhắc cặp nào
        "chua_kiem"     — nhận ra dưới 2 hoạt chất, không có gì để đối chiếu
    """
    meds = [m for m in (medications or []) if isinstance(m, dict) and (m.get("name") or "").strip()]
    idx = chi_muc()

    nhan_ra: List[Tuple[int, Dict[str, Any], Dict[str, Any]]] = []
    khong_nhan_ra = []
    for i, m in enumerate(meds):
        c = nhan_dien(m["name"], idx)
        if c is None:
            khong_nhan_ra.append({"index": i, "ten": m["name"]})
        else:
            nhan_ra.append((i, m, c))

    cap = []
    for x in range(len(nhan_ra)):
        for y in range(x + 1, len(nhan_ra)):
            (ia, ma, ca), (ib, mb, cb) = nhan_ra[x], nhan_ra[y]
            if ca is cb:
                continue
            bang_chung = _bang_chung(ca, cb) + _bang_chung(cb, ca)
            if not bang_chung:
                continue
            muc = min((b["muc"] for b in bang_chung), key=_MUC_ORDER.get)
            cap.append({
                "a": {"index": ia, "ten": ma["name"], "hoat_chat": ca["ten"]},
                "b": {"index": ib, "ten": mb["name"], "hoat_chat": cb["ten"]},
                "muc": muc,
                "muc_label": MUC_LABEL[muc],
                "bang_chung": bang_chung,
            })
    cap.sort(key=lambda c: _MUC_ORDER[c["muc"]])

    co_canh_bao = any(c["muc"] != KHONG_TUONG_TAC for c in cap)
    if len(nhan_ra) < 2:
        ket_luan = "chua_kiem"
    elif co_canh_bao:
        ket_luan = "co_tuong_tac"
    else:
        ket_luan = "khong_thay"

    return {
        "ket_luan": ket_luan,
        "so_thuoc": len(meds),
        "nhan_ra": [{"index": i, "ten": m["name"], "hoat_chat": c["ten"]} for i, m, c in nhan_ra],
        "khong_nhan_ra": khong_nhan_ra,
        "cap": cap,
        "pham_vi": PHAM_VI,
    }
