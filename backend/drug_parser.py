import re
import json
from typing import List, Dict, Any, Optional, Tuple

from drug_name import normalize_drug_name


class DrugChunkParser:
    """
    Parser chuyên dụng bóc tách văn bản thô từ tài liệu 'Thuốc Biệt Dược & Cách Sử Dụng'
    thành các đối tượng JSON Metadata (Field-Centric Chunks) nạp vào Vector Database.
    """

    # Bản đồ ánh xạ các trường thông tin y khoa sang Enum & Tên hiển thị chuẩn
    FIELD_DEFINITIONS: Dict[str, Dict[str, str]] = {
        "TD": {
            "field_type": "TARGET_ACTION",
            "field_name": "Tác dụng - Dược lý",
            "short_code": "TD",
        },
        "CĐ": {
            "field_type": "INDICATIONS",
            "field_name": "Chỉ định",
            "short_code": "CD",
        },
        "CD": {
            "field_type": "INDICATIONS",
            "field_name": "Chỉ định",
            "short_code": "CD",
        },
        "LD": {
            "field_type": "DOSAGE",
            "field_name": "Liều dùng - Cách dùng",
            "short_code": "LD",
        },
        "CCĐ": {
            "field_type": "CONTRAINDICATION",
            "field_name": "Chống chỉ định",
            "short_code": "CCD",
        },
        "CCD": {
            "field_type": "CONTRAINDICATION",
            "field_name": "Chống chỉ định",
            "short_code": "CCD",
        },
        "CB": {
            "field_type": "INDICATIONS",
            "field_name": "Chỉ định",
            "short_code": "CD",
        },
        "LD": {
            "field_type": "DOSAGE",
            "field_name": "Liều dùng - Cách dùng",
            "short_code": "LD",
        },
        "LO": {
            "field_type": "DOSAGE",
            "field_name": "Liều dùng - Cách dùng",
            "short_code": "LD",
        },
        "LĐ": {
            "field_type": "DOSAGE",
            "field_name": "Liều dùng - Cách dùng",
            "short_code": "LD",
        },
        "CCĐ": {
            "field_type": "CONTRAINDICATION",
            "field_name": "Chống chỉ định",
            "short_code": "CCD",
        },
        "CCD": {
            "field_type": "CONTRAINDICATION",
            "field_name": "Chống chỉ định",
            "short_code": "CCD",
        },
        "CCB": {
            "field_type": "CONTRAINDICATION",
            "field_name": "Chống chỉ định",
            "short_code": "CCD",
        },
        "LY": {
            "field_type": "WARNINGS",
            "field_name": "Lưu ý - Thận trọng",
            "short_code": "LY",
        },
        "TƯƠNG TÁC THUỐC": {
            "field_type": "WARNINGS",
            "field_name": "Tương tác thuốc",
            "short_code": "TT",
        },
        "TƯƠNG TÁC": {
            "field_type": "WARNINGS",
            "field_name": "Tương tác thuốc",
            "short_code": "TT",
        },
        "DT": {
            "field_type": "DOSAGE_FORM",
            "field_name": "Dạng thuốc - Trình bày",
            "short_code": "DT",
        },
        "OT": {
            "field_type": "DOSAGE_FORM",
            "field_name": "Dạng thuốc - Trình bày",
            "short_code": "DT",
        },
        "TO": {
            "field_type": "TARGET_ACTION",
            "field_name": "Tác dụng - Dược lý",
            "short_code": "TD",
        },
    }

    # Regex nhận diện mốc trang: [Trang 45] hoặc [Page 45]
    PAGE_PATTERN = re.compile(r'\[\s*(?:Trang|Page)\s*(\d+)\s*\]', re.IGNORECASE)

    # Regex nhận diện định dạng dòng tên thuốc (chữ in hoa kèm biệt dược/quốc gia trong ngoặc đơn nếu có)
    DRUG_HEADER_PATTERN = re.compile(
        r'^[ \t]*([A-ZÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬĐÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ0-9\s\-\+\/\.]+?)(?:\s*\((.*?)\))?[ \t]*$'
    )

    # Regex nhận diện nhãn bắt đầu các trường (BD:, DT:, TD:, CĐ:, CD:, CB:, LD:, LO:, LĐ:, CCĐ:, CCD:, CCB:, LY:, Tương tác:)
    FIELD_TAG_PATTERN = re.compile(
        r'(?:^|\n)[ \t]*(BD|DT|OT|TD|TO|CĐ|CD|CB|LD|LO|LĐ|CCĐ|CCD|CCB|LY|Tương tác thuốc|Tương tác)\s*[:;\.]',
        re.IGNORECASE,
    )

    @classmethod
    def _is_drug_header_line(cls, line: str) -> bool:
        """Kiểm tra một dòng text có phải là tiêu đề tên thuốc mới hay không."""
        line_clean = line.strip()
        if not line_clean or len(line_clean) < 2:
            return False

        if cls.FIELD_TAG_PATTERN.match(line_clean) or cls.PAGE_PATTERN.match(line_clean):
            return False

        if line_clean.lower().startswith("dẫn xuất") or line_clean.endswith(":"):
            return False

        match = cls.DRUG_HEADER_PATTERN.match(line_clean)
        if not match:
            return False

        main_part = match.group(1).strip()
        letters = [c for c in main_part if c.isalpha()]
        if not letters:
            return False

        # Đảm bảo phần lớn tên thuốc là chữ in hoa (tối thiểu 70%)
        uppercase_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        return uppercase_ratio >= 0.7

    @classmethod
    def _extract_brand_names(cls, raw_bd_text: str, header_extra: Optional[str] = None) -> List[str]:
        """Trích xuất danh sách tên biệt dược sạch từ trường BD: và phần bổ sung trong tiêu đề."""
        brand_names: List[str] = []

        # 1. Trích xuất tên biệt dược trong ngoặc đơn ở tiêu đề nếu có (ví dụ: ARGINOTRI - B (Bouchara))
        if header_extra and header_extra.strip():
            header_clean = re.sub(r'[\(\)]', '', header_extra).strip()
            excluded_countries = {
                'pháp', 'nga', 'mỹ', 'đức', 'ý', 'italia', 'hàn quốc',
                'ấn độ', 'nhật', 'anh', 'thụy sĩ', 'bỉ', 'ba lan', 'áo'
            }
            if header_clean.lower() not in excluded_countries:
                brand_names.append(header_clean)

        if not raw_bd_text:
            return brand_names

        # 2. Xử lý chuỗi BD:
        clean_bd = re.sub(r'^BD\s*:\s*', '', raw_bd_text.strip(), flags=re.IGNORECASE)
        parts = re.split(r'[,;\n]+', clean_bd)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # Bỏ thông tin quốc gia/hãng sản xuất trong ngoặc đơn, vd: "Lukadin (Italia)" -> "Lukadin"
            brand = re.sub(r'\(.*?\)', '', part).strip()
            brand = re.sub(r'[\.\:\-\,\;]$', '', brand).strip()
            if brand and brand not in brand_names and len(brand) > 1:
                brand_names.append(brand)

        return brand_names

    @classmethod
    def parse_pdf_text_to_chunks(
        cls,
        raw_text: str,
        source_file_name: str = "part_1_150.pdf",
        monograph_page_range: Optional[Tuple[int, int]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Phân tích toàn bộ chuỗi text sạch từ PDF thành danh sách các Field-Centric Chunk JSON.
        
        :param raw_text: Văn bản thô đầu vào chứa các mốc [Trang X] và thông tin thuốc.
        :param source_file_name: Tên tệp PDF nguồn.
        :param monograph_page_range: (đầu, cuối) dải trang PDF chứa chuyên luận thuốc.
            Ngoài dải này sách còn phụ lục văn xuôi và mục lục tra cứu; nhãn trường
            (LD:, DT:...) vẫn khớp lung trong phần đó và sinh chunk rác — vd. dòng mục
            lục "Idoxuridin" bị OCR đọc thành "LD.U.LR - ..." rồi thành một chunk
            "Liều dùng". None = không giới hạn, giữ nguyên hành vi cũ.
        :return: Danh sách các đối tượng JSON Metadata Chunk theo Schema chuẩn RAG.
        """
        chunks: List[Dict[str, Any]] = []
        if not raw_text or not raw_text.strip():
            return chunks

        # 1. Phân đoạn văn bản theo từng trang [Trang X]
        page_splits = []
        last_idx = 0
        current_page = 1

        matches = list(cls.PAGE_PATTERN.finditer(raw_text))
        if matches:
            for match in matches:
                start = match.start()
                if start > last_idx:
                    page_splits.append((current_page, raw_text[last_idx:start]))
                current_page = int(match.group(1))
                last_idx = match.end()
            if last_idx < len(raw_text):
                page_splits.append((current_page, raw_text[last_idx:]))
        else:
            page_splits.append((current_page, raw_text))

        # 2. Xử lý từng trang văn bản
        # Tên thuốc được giữ qua ranh giới trang. Chuyên luận trong sách này thường
        # tràn sang trang sau, và phần tràn lại hay là mục "Liều dùng" — nằm cuối
        # chuyên luận nên dễ rơi sang trang kế. Khởi tạo hai biến này BÊN TRONG vòng
        # lặp trang là nguyên nhân 3 341/18 717 chunk (17,9%) mang tên UNKNOWN_DRUG:
        # đo được 100% số chunk đó nằm ở trang mà chunk đầu tiên đã là UNKNOWN, tức
        # đúng dấu hiệu văn bản tràn từ trang trước, không phải nhận tiêu đề sai.
        current_drug_name = "UNKNOWN_DRUG"
        current_header_extra: Optional[str] = None
        prev_page_num: Optional[int] = None

        for page_num, page_content in page_splits:
            # Ngoài dải chuyên luận thì bỏ hẳn trang, không chỉ bỏ chunk: nếu vẫn đọc
            # thì một dòng mục lục có thể bị nhận là tiêu đề và ghi vào current_drug_name.
            if monograph_page_range and not (
                monograph_page_range[0] <= page_num <= monograph_page_range[1]
            ):
                continue

            # Trang không liền kề ⇒ đã nhảy sang phần khác của sách (phụ lục, mục lục),
            # không được mang tên thuốc của chuyên luận cũ đi theo.
            if prev_page_num is not None and page_num != prev_page_num + 1:
                current_drug_name = "UNKNOWN_DRUG"
                current_header_extra = None
            prev_page_num = page_num

            page_content = page_content.strip()
            if not page_content:
                continue

            # Phân đoạn các mục thuốc trên trang
            lines = page_content.split('\n')
            drug_blocks: List[Dict[str, Any]] = []
            current_lines: List[str] = []

            for line in lines:
                line_str = line.strip()
                if cls._is_drug_header_line(line_str):
                    if current_lines:
                        drug_blocks.append({
                            "generic_name": current_drug_name,
                            "header_extra": current_header_extra,
                            "text": "\n".join(current_lines).strip(),
                        })
                        current_lines = []

                    match_hdr = cls.DRUG_HEADER_PATTERN.match(line_str)
                    if match_hdr:
                        current_drug_name = match_hdr.group(1).strip()
                        current_header_extra = match_hdr.group(2)
                    else:
                        current_drug_name = line_str
                        current_header_extra = None
                else:
                    current_lines.append(line)

            if current_lines:
                drug_blocks.append({
                    "generic_name": current_drug_name,
                    "header_extra": current_header_extra,
                    "text": "\n".join(current_lines).strip(),
                })

            # 3. Phân tách các trường trong từng mục thuốc
            for drug in drug_blocks:
                generic_name = drug["generic_name"]
                header_extra = drug["header_extra"]
                block_text = drug["text"]

                if not block_text:
                    continue

                field_matches = list(cls.FIELD_TAG_PATTERN.finditer(block_text))
                if not field_matches:
                    continue

                fields = []
                for i in range(len(field_matches)):
                    tag = field_matches[i].group(1).upper()
                    start_pos = field_matches[i].start()
                    end_pos = field_matches[i + 1].start() if i + 1 < len(field_matches) else len(block_text)
                    field_raw = block_text[start_pos:end_pos].strip()
                    fields.append({
                        "tag": tag,
                        "text": field_raw,
                    })

                # Trích xuất danh sách biệt dược (brand_names)
                brand_names: List[str] = []
                for f in fields:
                    if f["tag"] == "BD":
                        brand_names = cls._extract_brand_names(f["text"], header_extra)
                        break
                if not brand_names and header_extra:
                    brand_names = cls._extract_brand_names("", header_extra)

                # 4. Sinh các đối tượng Chunk theo từng trường dữ liệu
                field_counter: Dict[str, int] = {}

                for f in fields:
                    tag = f["tag"]
                    # BD đã được cấu trúc vào mảng metadata brand_names
                    if tag == "BD":
                        continue

                    field_meta = cls.FIELD_DEFINITIONS.get(tag)
                    if not field_meta:
                        continue

                    field_type = field_meta["field_type"]
                    field_name = field_meta["field_name"]
                    short_code = field_meta["short_code"]

                    field_counter[short_code] = field_counter.get(short_code, 0) + 1
                    idx_str = f"{field_counter[short_code]:02d}"

                    # Sinh Chunk ID: [GENERIC_NAME]_[SHORT_CODE]_[INDEX]
                    clean_name_code = re.sub(r'[^A-Z0-9]', '', generic_name.upper())
                    if not clean_name_code:
                        clean_name_code = "DRUG"
                    chunk_id = f"{clean_name_code}_{short_code}_{idx_str}"

                    chunk_obj: Dict[str, Any] = {
                        "chunk_id": chunk_id,
                        # Cắt rác dấu câu OCR bám ở rìa tên ('.AMEFLU',
                        # '- ALIMEMAZIN'). Không sửa ký tự bên trong — lý do đo
                        # được ghi trong backend/drug_name.py.
                        "generic_name": normalize_drug_name(generic_name) or generic_name,
                        "brand_names": brand_names,
                        "field_type": field_type,
                        "field_name": field_name,
                        "content": f["text"],
                        "source_file": source_file_name,
                        "page_in_file": page_num,
                        "book_page_display": page_num,
                        "bounding_boxes": [],
                    }
                    chunks.append(chunk_obj)

        return chunks


def parse_pdf_text_to_chunks(
    raw_text: str,
    source_file_name: str = "part_1_150.pdf",
    monograph_page_range: Optional[Tuple[int, int]] = None,
) -> List[Dict[str, Any]]:
    """
    Entrypoint wrapper chuẩn để parse PDF Text thành danh sách Field-Centric Chunk JSON.
    """
    return DrugChunkParser.parse_pdf_text_to_chunks(
        raw_text, source_file_name, monograph_page_range
    )


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    # Dữ liệu thử nghiệm mẫu (AMIKACIN & ARGINOTRI - B từ sách THUOC-BIET-DUOC-VA-CACH-SU-DUNG.pdf)
    sample_raw_text = """[Trang 45]
AMIKACIN
BD: Lukadin (Italia), Acemycin (Pháp), Amiklin (Mỹ).
DT: Lọ thuốc bột tiêm 250mg, 500mg kèm ống dung môi 2ml hoặc 4ml.
TD: Kháng sinh bán tổng hợp họ aminosid, phổ diệt khuẩn rộng bao gồm trực khuẩn Gram âm và tụ cầu khuẩn kháng methicillin.
CĐ: Các nhiễm khuẩn nặng nghi do trực khuẩn Gram âm nhạy cảm: nhiễm khuẩn huyết, viêm màng trong tim, nhiễm khuẩn hô hấp dưới, nhiễm khuẩn ổ bụng và đường tiết niệu có biến chứng.
LD: Người có chức năng thận bình thường: 15mg/kg/ngày chia làm 2-3 lần (tiêm bắp hoặc truyền tĩnh mạch chậm trong 30-60 phút). Trẻ sơ sinh: liều nạp 10mg/kg, sau đó 7.5mg/kg mỗi 12 giờ.
CCĐ: Mẫn cảm với các Aminosid. Phụ nữ có thai và cho con bú. Nhược cơ nặng.
LY: Độc tính trên thính giác (thần kinh VIII) và thận. Cần theo dõi chức năng thận và giảm liều khi có suy thận.
Tương tác thuốc: Tránh phối hợp với các thuốc gây độc trên thận và tai khác như Furosemid, Cisplatin, Vancomycin.

[Trang 71]
ARGINOTRI - B (Bouchara)
DT: Viên bao:
L - arginin HCl 250mg
Thiamin HCl 100mg
Pyridoxin HCl 100mg
Hydroxocobalamin khan 250mcg
TD: Giải độc gan - Giảm đau - Bảo vệ thần kinh - Điều hoà amoniac cao bất thường trong máu ở một số bệnh gan.
CĐ: - Rối loạn chức năng gan do ngộ độc: tiền xơ gan, xơ gan - Bệnh não do gan.
- Rối loạn tâm thần ở người nghiện rượu: tình trạng say rượu cấp.
LD: Uống 6 - 8 viên/ngày.
CCĐ: Dị ứng với cobalamin.
LY: Không phối hợp với levodopa (ức chế men dopadecarboxylase ngoại biên).
"""

    parsed_chunks = parse_pdf_text_to_chunks(
        raw_text=sample_raw_text,
        source_file_name="THUOC-BIET-DUOC-VA-CACH-SU-DUNG.pdf"
    )

    print(f"--- ĐÃ TRÍCH XUẤT THÀNH CÔNG {len(parsed_chunks)} FIELD-CENTRIC CHUNKS ---")
    print(json.dumps(parsed_chunks, ensure_ascii=False, indent=2))
