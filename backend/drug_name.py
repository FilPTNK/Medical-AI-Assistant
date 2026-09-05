# -*- coding: utf-8 -*-
r"""Chuẩn hoá và đánh dấu tên thuốc do parser bóc ra từ text OCR.

BỐI CẢNH ĐO ĐƯỢC (2026-09-05, trên chính hai tệp chunk đang dùng)

Tên thuốc trong cuốn "Thuốc Biệt Dược" hỏng theo ba kiểu, và chúng cần ba cách
xử lý khác hẳn nhau:

1. Rác dấu câu ở đầu/cuối, tên còn nguyên — '.AMEFLU', '- ALIMEMAZIN',
   'ALMINOPROFEN .'  →  90 tên / 430 chunk. Cắt được, an toàn tuyệt đối.

2. Ký tự đầu bị OCR thay — '3AMBUTEROL' (BAMBUTEROL), '-EFAZOLIN' (CEFAZOLIN),
   '/ISAN' (AVISAN)  →  53 tên / 236 chunk. KHÔNG sửa. Xem phần dưới.

3. Không phải tên thuốc — 'Ỉ', '77T', '566 C80', 'AL 400'  →  ~350 chunk.
   KHÔNG xoá. Xem phần dưới.


VÌ SAO KHÔNG TỰ SỬA KÝ TỰ ĐẦU

Đã thử hai cách và đo cả hai:

  a) Suy từ vần: sách xếp theo bảng chữ cái, nên chữ cái đầu có thể suy từ các
     tên lành hai bên theo số trang. Kiểm trên 3.522 tên lành: đúng 91,5%.
  b) Đối chiếu từ điển: ghép thử 26 chữ cái vào phần còn lại, chỉ nhận khi
     đúng một ứng viên khớp tên thuốc đã biết. Kiểm lần đầu ra 100% — nhưng
     phép kiểm đó bị RÒ RỈ: từ điển dựng từ chính tên đang thử, nên đáp án
     luôn có sẵn. Loại tên đang thử ra khỏi từ điển rồi kiểm lại — đúng đó mới
     là tình huống thật, vì tên hỏng chỉ xuất hiện đúng một lần ở dạng đã hỏng:

         đúng 0   SAI 7   không quyết 493   (mẫu 500)

     Bảy lần nó quyết thì sai cả bảy: COCAIN→ROCAIN, CHIAMIN→THIAMIN,
     PHYTIN→THYTIN.

Một trợ lý y khoa đổi tên COCAIN thành ROCAIN là hỏng nặng hơn nhiều so với
việc để nguyên một tên đọc không ra. Nên: chỉ cắt rác, không đoán chữ.


VÌ SAO KHÔNG XOÁ CHUNK TÊN RÁC

Bàn giao cũ gọi việc này là "lọc rác parser". Đọc thẳng nội dung thì tiền đề
đó sai: NỘI DUNG của những chunk này là dữ liệu thuốc thật, chỉ có cái nhãn là
hỏng. '- ALIMEMAZIN' chứa đúng chuyên luận alimemazin; 'AL 400' là albendazol
400mg; '566 C80' là atovaquon (mã nghiên cứu của chính thuốc đó). Xoá đi là
mất thuốc thật khỏi kho, tệ hơn hẳn việc giữ một cái nhãn xấu.

Nên chunk được GIỮ, chỉ gắn cờ `name_suspect` để giao diện và LLM biết đường
đừng khẳng định chuỗi đó là tên thuốc.

Ghi chú: việc cắt rác dấu câu gần như không đổi gì cho tìm kiếm — tokenize_text
dùng `\w+` nên đã bỏ dấu câu từ trước; '.AMEFLU' vốn đã cho token 'ameflu'.
Giá trị của nó nằm ở chỗ hiển thị và ở chuỗi 【THUỐC: …】 mà LLM đọc.
"""

import re
from typing import Tuple

# Ký tự rác hay dính vào đầu/cuối tên khi OCR: gạch đầu dòng, dấu chấm câu,
# dấu gạch chéo. KHÔNG cắt ngoặc đơn — "ATROPIN (dùng toàn thân)" và
# "ANTI THYMOCYTE GLOBULIN (THỎ)" là tên thật, ngoặc mang nghĩa.
_EDGE_JUNK = r"[\s.,;:/\|+\-–—_*`'\"]+"

_NGUYEN_AM = set("AEIOUYĂÂÊÔƠƯÀÁẢÃẠẰẮẲẴẶÈÉẺẼẸỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌỒỐỔỖỘỜỚỞỠỢÙÚỦŨỤỪỨỬỮỰỲÝỶỸỴ")


def normalize_drug_name(name: str) -> str:
    """Cắt rác dấu câu ở hai đầu và gộp khoảng trắng. Idempotent.

    Chỉ động vào phần rìa: mọi ký tự bên trong tên được giữ nguyên, kể cả khi
    trông có vẻ hỏng — sửa bên trong là đoán, mà đoán thì đã đo là sai.
    """
    stripped, _ = _normalize_and_flag(name)
    return stripped


def _normalize_and_flag(name: str) -> Tuple[str, bool]:
    """Trả về (tên đã cắt, có cắt rác ở ĐẦU hay không).

    Cần biết có cắt ở đầu hay không vì không phân biệt được hai trường hợp:
    '.AMEFLU' là rác thật (tên nguyên vẹn), còn '-EFAZOLIN' là chữ 'C' bị OCR
    đọc thành '-' (tên thật: CEFAZOLIN). Cắt cả hai thì trường hợp sau biến
    thành 'EFAZOLIN' — một cái tên trông rất chỉnh mà lại sai, tệ hơn hẳn
    '-EFAZOLIN' vì nhìn vào không ai biết là nó hỏng.

    Nên cứ cắt cho sạch phần hiển thị, nhưng hễ có cắt ở đầu là gắn cờ nghi ngờ.
    Cắt ở cuối thì không gắn — không có nguy cơ mất chữ cái nào.
    """
    if not name:
        return "", False
    out = re.sub(r"\s+", " ", str(name)).strip()
    head_trimmed = re.sub(r"^" + _EDGE_JUNK, "", out)
    lost_head = head_trimmed != out
    out = re.sub(_EDGE_JUNK + r"$", "", head_trimmed).strip()
    return out, lost_head


def is_suspect_name(name: str) -> Tuple[bool, str]:
    """Tên này có đáng ngờ không, và ngờ vì lý do gì.

    Trả về (đáng_ngờ, lý_do). Chỉ để GẮN CỜ — không nơi nào được dùng kết quả
    này để xoá chunk hay sửa tên.
    """
    s, lost_head = _normalize_and_flag(name)
    if not s:
        return True, "rỗng"

    letters = [c for c in s if c.isalpha()]
    if not letters:
        return True, "không có chữ cái"
    if not s[0].isalpha():
        # Sau khi đã cắt rác rìa mà vẫn mở đầu bằng chữ số ⇒ ký tự đầu bị thay,
        # vd '3AMBUTEROL', '566 C80'.
        return True, "ký tự đầu không phải chữ cái"
    if len(letters) < 3:
        return True, "quá ít chữ cái"
    if not any(c.upper() in _NGUYEN_AM for c in letters):
        # 'KDM', 'CBS' — có thể là viết tắt thật, nên chỉ gắn cờ chứ không loại.
        return True, "không có nguyên âm"
    hoa = sum(1 for c in letters if c.isupper()) / len(letters)
    if len(s.split()) > 6 and hoa < 0.5:
        # Câu văn bị nhận nhầm thành tiêu đề thuốc. Ràng buộc tỉ lệ chữ hoa để
        # không đụng tên dài viết hoa thật như
        # 'GLOBULIN MIỄN DỊCH KHÁNG VIÊM GAN B'.
        return True, "trông như câu văn"
    if lost_head:
        return True, "đã cắt rác ở đầu — có thể mất chữ cái đầu"
    return False, ""
