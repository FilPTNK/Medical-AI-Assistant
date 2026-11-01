# -*- coding: utf-8 -*-
r"""Câu liều theo cân nặng (mg/kg) trong Dược thư, kèm các con số máy đọc ra được.

Tệp này KHÔNG chọn liều. Mục "Liều lượng và cách dùng" của một chuyên luận
thường có hàng chục liều khác nhau theo chỉ định, nhóm tuổi và đường dùng — đo
trên paracetamol: 19 câu có "mg/kg", từ sơ sinh thiếu tháng 7,5 mg/kg tới đau
sau phẫu thuật 30 mg/kg liều đầu. Máy tự chọn một liều trong đó là đoán thay
bác sĩ đúng ở chỗ nguy hiểm nhất.

Nên đầu ra là: NGUYÊN CÂU trong sách (bác sĩ đọc nhóm tuổi, chỉ định, đường
dùng), cộng các con số máy hiểu được từ câu đó (mg/kg, theo liều hay theo ngày,
số lần/ngày, mức tối đa) để bác sĩ bấm "dùng liều này" thay vì gõ lại. Phép
nhân với cân nặng nằm ở frontend (frontend/src/lib/doseCalc.js), tất định và có
test riêng.

Đọc số từ chữ OCR: "me/kg", "my/kg", "mg kg", "mg/ kg" đều là mg/kg; "ngay" và
"24 giờ" đều là ngày. Câu nào đọc không ra con số liều thì vẫn trả về (chữ là
nguồn, số chỉ là tiện ích) nhưng không có nút điền.
"""

import json
import os
import re
import threading
from typing import Any, Dict, List, Optional

import documents
import drug_interaction
from text_fold import fold

_NUM = r"(\d+(?:[.,]\d+)?)"
_RANGE = _NUM + r"(?:\s*(?:-|–|den)\s*" + _NUM + r")?"


def _so(s: Optional[str]) -> Optional[float]:
    return float(s.replace(",", ".")) if s else None


def _chuan_hoa(text: str) -> str:
    """Gấp dấu + sửa các lối OCR hay gặp của đơn vị, để regex chỉ cần một dạng."""
    t = fold(text)
    t = re.sub(r"\bm[gey]\s*/?\s*k[ge]\b", "mg/kg", t)          # me/kg, my/kg, mg kg, me kẹ
    t = re.sub(r"\bgid\b", "gio", t)                              # "giờ" OCR thành "gid"
    t = re.sub(r"mg/kg\s*/\s*(ngay|24\s*gio)", "mg/kg/ngay", t)
    t = re.sub(r"\s*/\s*24\s*gio", "/ngay", t)
    t = re.sub(r"\btoi\s*da\b", "toi da", t)
    t = re.sub(r"(\d)\s*,\s*(\d)", r"\1,\2", t)
    return re.sub(r"\s+", " ", t)


_LIEU_RE = re.compile(_RANGE + r"\s*mg/kg(/ngay)?")
_MAX_KG_NGAY_RE = re.compile(r"(?:toi da|khong qua|khong vuot qua|den)[^0-9]{0,15}" + _NUM + r"\s*mg/kg/ngay")
_MAX_MG_RE = re.compile(r"(?:toi da|khong qua|khong vuot qua)[^0-9]{0,15}" + _NUM + r"\s*(mg|g)\b(?!/kg)(\s*(?:/ngay|moi ngay|mot ngay))?")
_LAN_NGAY_RE = re.compile(r"(?:x|chia(?: lam| thanh)?)\s*" + _RANGE + r"\s*lan")
_LAN_NGAY2_RE = re.compile(_RANGE + r"\s*lan\s*/?\s*ngay")
_CACH_GIO_RE = re.compile(r"(?:cach(?: nhau)?|moi|cu)\s*" + _RANGE + r"\s*gio")


# Mệnh đề trong một câu liều: "20 mg/kg một liều duy nhất; sau đó 10 - 15 mg/kg
# cách 8 - 12 giờ; tối đa 60 mg/kg/ngày". Đọc cả câu như một khối thì liều 20
# mg/kg nhận nhầm tần suất của liều 10 - 15 mg/kg — nên tách mệnh đề trước.
_TACH_MENH_DE_GIU = re.compile(r"(;|\bsau do\b|\bhoac\b|\bthem\b)")
_TRAN_TRUOC = re.compile(r"toi da|khong qua|vuot qua|khong duoc qua")


def _doc_menh_de(t: str) -> Dict[str, Any]:
    """Một mệnh đề: liều mg/kg (nếu có) cùng tần suất và mức trần NẰM TRONG mệnh đề đó."""
    out: Dict[str, Any] = {"lieu": None}
    for m in _LIEU_RE.finditer(t):
        if _TRAN_TRUOC.search(t[:m.start()]):
            continue                 # "không được vượt quá ... 60 mg/kg": trần, không phải liều
        out["lieu"] = m
        break
    lieu = out["lieu"]
    sau = t[lieu.end():] if lieu else t

    m = _LAN_NGAY_RE.search(sau) or _LAN_NGAY2_RE.search(sau)
    out["so_lan_ngay"] = [_so(m.group(1)), _so(m.group(2)) or _so(m.group(1))] if m else None
    m = _CACH_GIO_RE.search(sau)
    out["cach_gio"] = None
    if m:
        lo, hi = _so(m.group(1)), _so(m.group(2)) or _so(m.group(1))
        if lo and hi and hi <= 24:
            out["cach_gio"] = [lo, hi]
            if out["so_lan_ngay"] is None:
                out["so_lan_ngay"] = [round(24 / hi), round(24 / lo)]

    m = _MAX_KG_NGAY_RE.search(t)
    out["toi_da_mg_kg_ngay"] = _so(m.group(1)) if m else None
    out["toi_da_mg_lieu"] = out["toi_da_mg_ngay"] = None
    for m in _MAX_MG_RE.finditer(t):
        mg = _so(m.group(1)) * (1000 if m.group(2) == "g" else 1)
        if mg <= 0:
            continue
        key = "toi_da_mg_ngay" if m.group(3) else "toi_da_mg_lieu"
        out[key] = out[key] or mg
    return out


def doc_cau(text: str) -> List[Dict[str, Any]]:
    """Các liều mg/kg trong một câu, mỗi liều kèm tần suất và mức trần của chính nó.

    Mệnh đề chỉ có mức trần (vd. "; tối đa 60 mg/kg/ngày" ở cuối câu) áp cho các
    liều đứng TRƯỚC nó trong cùng câu mà chưa có trần riêng.
    """
    t = _chuan_hoa(text)
    # "không được vượt quá 1 g ở người lớn HOẶC 60 mg/kg ở trẻ em": vế sau "hoặc"
    # vẫn thuộc mức trần. Tách ra thì 60 mg/kg mất chữ "vượt quá" đứng trước và
    # bị đọc thành liều — nên mệnh đề trần nuốt luôn vế "hoặc" theo sau nó.
    menh_de: List[str] = []
    phan = _TACH_MENH_DE_GIU.split(t)
    menh_de.append(phan[0])
    for i in range(1, len(phan), 2):
        noi, ve = phan[i], phan[i + 1]
        if noi == "hoac" and _TRAN_TRUOC.search(menh_de[-1]):
            menh_de[-1] += f" {noi} {ve}"
        else:
            menh_de.append(ve)

    ket: List[Dict[str, Any]] = []
    for md_text in menh_de:
        md = _doc_menh_de(md_text)
        tran = {k: md[k] for k in ("toi_da_mg_kg_ngay", "toi_da_mg_lieu", "toi_da_mg_ngay")}
        if md["lieu"] is None:
            for k, v in tran.items():
                if v is None:
                    continue
                for prev in ket:
                    if prev[k] is None:
                        prev[k] = v
            continue
        lieu = md["lieu"]
        lo, hi = _so(lieu.group(1)), _so(lieu.group(2)) or _so(lieu.group(1))
        if not lo or hi < lo:
            continue                     # khoảng ngược = đọc sai chữ OCR; bỏ, không đoán
        ket.append({
            "mg_kg_min": lo,
            "mg_kg_max": hi,
            "theo": "ngay" if lieu.group(3) else "lieu",
            "so_lan_ngay": md["so_lan_ngay"],
            "cach_gio": md["cach_gio"],
            "mot_lieu": "lieu duy nhat" in md_text or "lieu don" in md_text,
            **tran,
        })
    return ket


def _rac(text: str) -> bool:
    """Mảnh bảng OCR ("| 10 - 30 sử |\" mg/kg mỗi 12 .") — không đáng đưa cho bác sĩ đọc."""
    chu = sum(ch.isalpha() for ch in text)
    return len(text) < 25 or chu / max(len(text), 1) < 0.4 or text.count("|") >= 2


_cache: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
_lock = threading.Lock()


def _cau_lieu_cua_tai_lieu(doc_name: str) -> Dict[str, List[Dict[str, Any]]]:
    with _lock:
        if doc_name in _cache:
            return _cache[doc_name]
    by_drug: Dict[str, List[Dict[str, Any]]] = {}
    seen: Dict[str, set] = {}
    path = documents.chunks_path(doc_name)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for ch in json.load(f):
                if ch.get("field_name") != "Liều lượng và cách dùng":
                    continue
                ten = ch.get("generic_name") or ""
                page = ch.get("page_in_file") or ch.get("pdf_page") or 1
                for cau in drug_interaction._cat_cau(ch.get("content", "")):
                    if "kg" not in cau or _rac(cau):
                        continue
                    key = _chuan_hoa(cau)
                    if key in seen.setdefault(ten, set()):
                        continue
                    seen[ten].add(key)
                    by_drug.setdefault(ten, []).append({"cau": cau[:500], "page": page})
    with _lock:
        _cache[doc_name] = by_drug
    return by_drug


def tra_cuu(ten_ke: str) -> Dict[str, Any]:
    """Câu liều mg/kg của hoạt chất trong tên kê đơn. Chỉ đọc sách, không tính gì."""
    c = drug_interaction.nhan_dien(ten_ke)
    if c is None:
        return {"nhan_ra": False, "ten": ten_ke, "cau": []}
    out = []
    for item in _cau_lieu_cua_tai_lieu(c["doc_name"]).get(c["ten"], []):
        lieu = doc_cau(item["cau"])
        if not lieu:
            continue
        out.append({
            "cau": item["cau"],
            "page_num": item["page"],
            "citation": documents.display_citation(c["doc_name"], item["page"]),
            "doc_name": c["doc_name"],
            # Câu nói về trẻ em/sơ sinh lên trước: đây là máy tính liều cho trẻ.
            "tre_em": bool(re.search(r"\btre\b|so sinh|tuoi|thang", _chuan_hoa(item["cau"]))),
            "lieu": lieu,
        })
    out.sort(key=lambda x: not x["tre_em"])
    return {"nhan_ra": True, "ten": ten_ke, "hoat_chat": c["ten"], "cau": out}
