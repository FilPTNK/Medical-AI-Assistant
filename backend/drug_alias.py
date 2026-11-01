# -*- coding: utf-8 -*-
r"""Kho bí danh thuốc: mọi cách gọi một hoạt chất -> đúng các chuyên luận của nó.

Bác sĩ gọi cùng một thuốc theo bốn kiểu, và sách thì chỉ in một kiểu:

    INN Việt (Dược thư)   amoxicilin, clorpheniramin, cefalexin
    INN Anh / Pháp        amoxicillin, chlorpheniramine, cephalexin
    tên khác              acid acetylsalicylic = aspirin, vitamin C = acid ascorbic
    biệt dược             Mucodyne, Rhinathiol -> carbocistein

Kho này dựng lại TỪ CHÍNH KHO SÁCH mỗi lần chỉ mục dựng lại (không có bảng
nào phải nhập tay), từ bốn trường metadata mà parser đã bóc sẵn:
`generic_name`, `intl_name`, `synonyms` (Dược thư) và `brand_names` (sách
Thuốc Biệt Dược, dạng "Tên (Hãng, Nước), Tên khác, …").


BỘ GẤP CHÍNH TẢ INN (`inn_key`)

Phần đặc thù tiếng Việt: Dược thư Việt hoá tên quốc tế theo vài quy tắc đều
đặn, nên hai lối viết gặp nhau ở một khoá tất định — không cần khớp mờ:

    gộp phụ âm đôi     amoxicillin  -> amoxicilin
    ph -> f            cephalexin   -> cefalexin
    th -> t, chl -> cl methyl / chlorpheniramine -> metyl / clorpheniramin
    y -> i             cyclosporin  -> ciclosporin
    bỏ đuôi -e         morphine, prednisolone, hydrochloride, sulfate
    tên muối           sodium -> natri, potassium -> kali, calcium -> calci
    trật tự từ         "acetylsalicylic acid" = "acid acetylsalicylic"

Đo trên chính kho (eval/eval_phase2.py --collisions): 0 cặp chuyên luận Dược
thư khác nhau bị gộp chung một khoá. Các quy tắc suy từ thói quen Dược thư,
chưa đối chiếu với văn bản quy định chính thức nào.


VÌ SAO KHÔNG KHỚP MỜ

Một trợ lý y khoa nhận "tramadol" thành "trandolapril" là hỏng nặng. Khớp mờ
(nếu có sau này) chỉ được GỢI Ý "Có phải: …?" để bác sĩ bấm chọn. Ở đây chỉ
nhận khớp nguyên vẹn trên khoá đã gấp, theo token (giống drug_allergy._chua_day:
"busulfan" không khớp "sulfa").


LỌC BÍ DANH RÁC

Danh sách biệt dược in kèm hãng và nước trong ngoặc, OCR lại hay làm mất dấu
đóng ngoặc, nên "Carrier (Chiesi, Parma, Sigmatau, Disocor" để lọt "Parma",
"Sigmatau" thành biệt dược. Ba bộ lọc, đều tất định:

  - bí danh trỏ tới hơn MAX_ENTITIES_PER_ALIAS hoạt chất là tên hãng/nơi chốn;
  - bí danh mà mọi token đều là âm tiết tiếng Việt có trong kho ("Nhat Bản",
    "XNDP Hà Nội" thì vẫn còn token "xndp" nên giữ, nhưng chỉ khớp khi gõ đủ cả
    cụm) — tên thuốc gần như không bao giờ là âm tiết tiếng Việt;
  - bí danh một token ngắn hơn 4 chữ cái ("TM", "EF", "My").
"""

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

from text_fold import fold

ALIAS_VERSION = "alias-1"

MAX_ENTITIES_PER_ALIAS = 3
MIN_SINGLE_TOKEN_LEN = 4
MAX_ALIAS_TOKENS = 5

# Cặp đồng nghĩa KHÔNG suy ra được bằng quy tắc chính tả (USAN Mỹ ↔ INN). Tệp
# này do người soạn tay; mỗi dòng phải có "approved": true mới được dùng.
SYNONYMS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lexicon", "drug_synonyms.json")

# Một mình những chữ này không gọi tên thuốc nào ("acid", "vitamin"): chỉ
# được khớp khi đi kèm phần còn lại của tên ("acid ascorbic", "vitamin c").
_GENERIC_WORDS = {
    "acid", "vitamin", "alpha", "beta", "gamma", "complex", "forte", "fort", "plus",
    "retard", "extra", "baby", "kid", "kids", "sirop", "siro", "drops", "cream", "gel",
    "tab", "tabs", "caps", "inj", "oral", "sr", "xr", "mr",
}

# Tên muối/gốc tiếng Anh -> tiếng Việt (dạng đã fold). Hậu tố -ide/-ate tự về
# -id/-at nhờ quy tắc bỏ đuôi -e, nên chỉ cần những từ đổi hẳn gốc.
_SALT_WORDS = {
    "sodium": "natri", "potassium": "kali", "calcium": "calci", "magnesium": "magnesi",
    "aluminium": "nhom", "aluminum": "nhom", "zinc": "kem", "iron": "sat", "ferrous": "sat",
    "mesylate": "mesilat", "mesilate": "mesilat", "besylate": "besilat",
}

# Hậu tố muối: "Warfarin 5 mg" nghĩa là warfarin natri. Giữ đồng bộ với
# drug_interaction._MUOI (đã dịch qua inn_key).
_SALTS_RAW = (
    "natri kali calci magnesi hydroclorid clorid hydrobromid bromid sulfat maleat "
    "besilat mesylat mesilat tartrat citrat acetat phosphat succinat fumarat "
    "lactat gluconat nitrat dihydrat monohydrat trihydrat hyclat sodium potassium "
    "calcium hydrochloride sulfate dipropionat propionat valerat hcl"
)


def _token_key(tok: str) -> str:
    """Một token (đã fold, chữ thường) -> dạng chính tả INN chuẩn."""
    t = _SALT_WORDS.get(tok, tok)
    if not t.isalpha():
        return t
    t = re.sub(r"(.)\1+", r"\1", t)          # amoxicillin -> amoxicilin
    t = t.replace("ph", "f")                  # cephalexin -> cefalexin
    t = t.replace("chl", "cl").replace("chr", "cr")
    t = t.replace("th", "t")                  # methyl -> metyl
    t = t.replace("y", "i")                   # cyclosporin -> ciclosporin
    if len(t) > 4 and t.endswith("e"):        # morphine -> morphin
        t = t[:-1]
    t = re.sub(r"(.)\1+", r"\1", t)          # gộp lại lần nữa sau khi đổi
    return t


def tokens(text: str) -> List[str]:
    """Cắt chữ thành token đã fold. Gạch nối và dấu câu là ranh giới."""
    return [t for t in re.split(r"[^0-9a-z]+", fold(text or "")) if t]


def inn_key(text: str) -> Tuple[str, ...]:
    """Khoá so khớp của một tên: các token INN chuẩn, sắp xếp (bỏ ảnh hưởng trật tự từ)."""
    return tuple(sorted(_token_key(t) for t in tokens(text)))


_SALTS = {_token_key(t) for t in _SALTS_RAW.split()}
_GENERIC_KEYS = {_token_key(w) for w in _GENERIC_WORDS}


def _base_variants(name: str) -> Set[Tuple[str, ...]]:
    """Khoá đủ và khoá bỏ hậu tố muối ("clorpheniramin maleat" -> "clorpheniramin")."""
    key = inn_key(name)
    if not key:
        return set()
    out = {key}
    base = tuple(t for t in key if t not in _SALTS)
    if base and base != key and (len(base) > 1 or len(base[0]) >= 5):
        out.add(base)
    return out


# ----------------------------------------------------------------------------
# Tách danh sách biệt dược "Tên (Hãng, Nước), Tên khác {Hãng}, …"
# ----------------------------------------------------------------------------

_OPEN = "({["
_CLOSE = ")}]"


def split_brands(raw: str) -> List[str]:
    """Danh sách biệt dược OCR -> các tên biệt dược.

    Bỏ phần trong ngoặc (hãng, nước). OCR hay làm mất dấu đóng ngoặc, nên phần
    sau một dấu mở ngoặc chưa đóng được coi là hết ngoặc ở dấu phẩy kế tiếp —
    đoạn sau dấu phẩy mà kết thúc bằng dấu đóng ngoặc là đuôi của ngoặc, bỏ.
    """
    out = []
    for piece in re.split(r"[,;]", raw or ""):
        piece = piece.strip()
        if not piece:
            continue
        if any(c in piece for c in _CLOSE) and not any(c in piece for c in _OPEN):
            continue  # "Pháp)" — đuôi ngoặc của mục trước
        name = re.split(r"[({\[]", piece, maxsplit=1)[0]
        name = re.sub(r"[\"“”'`~*|]+", " ", name)
        name = re.sub(r"\s+", " ", name).strip(" .-–—:")
        if name and not name.lower().startswith(("dẫn xuất", "dan xuat")):
            out.append(name)
    return out


def _split_synonyms(raw) -> List[str]:
    if isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        items = re.split(r"[,;]", raw or "")
    out = []
    for s in items:
        s = re.sub(r"[()]", " ", str(s))
        s = re.sub(r"\s+", " ", s).strip()
        if s:
            out.append(s)
    return out


def vietnamese_syllables(unigrams: Dict[str, int], min_count: int = 3) -> Set[str]:
    """Âm tiết tiếng Việt của kho (từ QueryLexicon.unigrams), ở dạng khoá INN.

    Chỉ lấy chữ có dấu: chữ mang dấu chắc chắn là tiếng Việt, còn tên thuốc thì
    không bao giờ mang dấu. Dạng đã fold của nó ("phap", "nhat") là thứ OCR và
    người gõ không dấu sẽ để lại.
    """
    out = set()
    for word, count in unigrams.items():
        if count >= min_count and fold(word) != word.lower():
            out.add(_token_key(fold(word)))
    return out


# ----------------------------------------------------------------------------
# Kho
# ----------------------------------------------------------------------------

@dataclass
class Entity:
    key: Tuple[str, ...]          # inn_key của tên chuyên luận
    name: str                     # tên hiển thị: tên chuyên luận Dược thư nếu có
    generic_names: Set[str] = field(default_factory=set)  # generic_name y nguyên trong metadata


@dataclass
class Mention:
    text: str                     # đoạn trong câu hỏi
    start: int                    # vị trí token
    end: int
    entities: List[Tuple[str, ...]]
    kind: str                     # "inn" | "synonym" | "brand" | "curated"


class DrugAliasStore:
    def __init__(self):
        self.entities: Dict[Tuple[str, ...], Entity] = {}
        # khoá bí danh -> {khoá thực thể: loại}
        self.alias: Dict[Tuple[str, ...], Dict[Tuple[str, ...], str]] = {}
        self.max_len = 1

    # ---------- dựng ----------

    @classmethod
    def build(cls, metadatas: Iterable[dict], vietnamese_syllables: Optional[Set[str]] = None,
              synonyms_path: Optional[str] = SYNONYMS_PATH) -> "DrugAliasStore":
        """Dựng từ metadata chunk. `vietnamese_syllables`: các âm tiết đã fold
        có dạng mang dấu trong kho — dùng để loại bí danh là chữ thường."""
        store = cls()
        raw_alias: Dict[Tuple[str, ...], Dict[Tuple[str, ...], str]] = defaultdict(dict)
        seen = set()
        for meta in metadatas:
            generic = (meta.get("generic_name") or "").strip()
            if not generic or generic == "UNKNOWN_DRUG" or meta.get("name_suspect"):
                continue
            sig = (generic, meta.get("doc_name"))
            if sig in seen:
                continue
            seen.add(sig)
            key = inn_key(generic)
            if not key:
                continue
            ent = store.entities.get(key)
            if ent is None:
                ent = store.entities[key] = Entity(key=key, name=generic.title())
            ent.generic_names.add(generic)
            if meta.get("doc_series") == "DTQGVN-2022" or str(meta.get("doc_name", "")).startswith("DTQG"):
                ent.name = generic.title()  # tên Dược thư là tên hiển thị chuẩn

            def add(name, kind):
                for v in _base_variants(name):
                    raw_alias[v].setdefault(key, kind)

            add(generic, "inn")
            if meta.get("intl_name"):
                add(meta["intl_name"], "inn")
            for s in _split_synonyms(meta.get("synonyms")):
                add(s, "synonym")
            for b in split_brands(meta.get("brand_names") or ""):
                add(b, "brand")

        if synonyms_path and os.path.exists(synonyms_path):
            with open(synonyms_path, encoding="utf-8") as f:
                for row in json.load(f).get("pairs", []):
                    if not row.get("approved"):
                        continue
                    target = inn_key(row["canonical"])
                    if target in store.entities:
                        for v in _base_variants(row["alias"]):
                            raw_alias[v].setdefault(target, "curated")

        vn = vietnamese_syllables or set()
        for akey, targets in raw_alias.items():
            named = {k: v for k, v in targets.items() if v != "brand"}
            if named and len(named) < len(targets):
                # Tên hoạt chất / tên khác thắng tên lấy từ danh sách biệt dược:
                # "noradrenalin" là tên khác của norepinephrin, còn việc nó lọt
                # vào danh sách biệt dược của nordazepam là lỗi OCR.
                targets = named
            if len(targets) > MAX_ENTITIES_PER_ALIAS:
                continue  # tên hãng / nơi chốn dính vào nhiều thuốc
            if len(akey) > MAX_ALIAS_TOKENS:
                continue
            letters = [t for t in akey if t.isalpha()]
            if not letters:
                continue
            if len(akey) == 1 and (len(akey[0]) < MIN_SINGLE_TOKEN_LEN
                                   or akey[0] in _GENERIC_KEYS or akey[0] in _SALTS):
                continue
            kinds = set(targets.values())
            if "inn" not in kinds and all(t in vn for t in akey):
                # "Nhat Bản" (nước sản xuất), "THUOC NHO MAT" (tiêu đề OCR lọt
                # vào ô tên khác): mọi token đều là chữ tiếng Việt. Tên chuyên
                # luận thì giữ — sách Thuốc Biệt Dược có thuốc đông dược tên Việt.
                continue
            store.alias[akey] = targets
            store.max_len = max(store.max_len, len(akey))
        return store

    # ---------- tra ----------

    def link(self, text: str) -> List[Mention]:
        """Tìm tên thuốc trong câu hỏi. Khớp dài nhất trước, không chồng nhau.

        Khoá đã sắp xếp nên cửa sổ token cũng sắp xếp trước khi tra — "acid
        acetylsalicylic" và "acetylsalicylic acid" khớp cùng một bí danh.
        """
        raw = tokens(text)
        keys = [_token_key(t) for t in raw]
        used = [False] * len(raw)
        found: List[Mention] = []
        for n in range(min(self.max_len, len(raw)), 0, -1):
            for i in range(len(raw) - n + 1):
                if any(used[i:i + n]):
                    continue
                window = tuple(sorted(keys[i:i + n]))
                targets = self.alias.get(window)
                if not targets:
                    continue
                for j in range(i, i + n):
                    used[j] = True
                kinds = set(targets.values())
                kind = next(k for k in ("inn", "synonym", "curated", "brand") if k in kinds)
                found.append(Mention(" ".join(raw[i:i + n]), i, i + n, sorted(targets), kind))
        found.sort(key=lambda m: m.start)
        return found

    def entity(self, key: Tuple[str, ...]) -> Optional[Entity]:
        return self.entities.get(key)

    def canonical_names(self, mention: Mention) -> List[str]:
        return [self.entities[k].name for k in mention.entities if k in self.entities]

    def resolve_name(self, text: str) -> Optional[str]:
        """Tên kê đơn ("Mucodyne 375mg") -> tên chuyên luận, nếu nhận ra và khác
        tên gõ. Dùng cho bộ đối chiếu dị ứng / tương tác."""
        for m in self.link(text):
            if m.kind == "inn":
                return None  # đã là tên hoạt chất; hai bộ đối chiếu tự nhận ra
            names = self.canonical_names(m)
            if len(names) == 1:
                return names[0]
        return None


# Kho đang dùng — vector_store gán sau mỗi lần dựng chỉ mục. Hai bộ đối chiếu
# dị ứng / tương tác đọc qua đây để không phải dựng lại kho riêng.
_current: Optional[DrugAliasStore] = None


def set_current(store: Optional[DrugAliasStore]) -> None:
    global _current
    _current = store


def current() -> Optional[DrugAliasStore]:
    return _current


def with_resolved_name(name: str) -> str:
    """"Mucodyne 375mg" -> "Mucodyne 375mg (Carbocistein)" khi kho nhận ra biệt dược.

    Thêm, không thay: tên gốc vẫn còn nguyên để bác sĩ đọc lại đúng chữ mình kê.
    """
    store = _current
    if not store or not name:
        return name
    resolved = store.resolve_name(name)
    return f"{name} ({resolved})" if resolved else name
