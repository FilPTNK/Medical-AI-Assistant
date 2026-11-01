"""
Một chỗ DUY NHẤT biến "tình trạng bệnh nhân trước đó" thành chữ gửi ra mô hình.

App không còn lưu hồ sơ bệnh nhân. Thay vào đó, ở tab Chẩn đoán bác sĩ có một ô
KHÔNG BẮT BUỘC để gõ tình trạng trước đó (bệnh nền, dị ứng, thuốc đang dùng,
lần khám trước…). Cả bốn bước của cây chẩn đoán nhận đúng chuỗi đó.

Chữ này do bác sĩ tự gõ và đi thẳng ra mô hình ngoài, nên giao diện nhắc
không ghi tên, số điện thoại hay địa chỉ. Ở đây chỉ cắt độ dài và bọc thẻ.

Khối được ĐẶT LÊN ĐẦU prompt: "Lost in the Middle" (Liu và cộng sự, TACL 2024)
đo được rằng thông tin nằm giữa ngữ cảnh bị bỏ sót nhiều hơn hẳn so với nằm ở
đầu hoặc cuối. Dị ứng thuốc là thứ không được phép rơi vào khúc giữa.
"""

import re
from typing import Optional

# Thẻ bao quanh khối tiền sử. Có thẻ thì mô hình phân biệt được đâu là dữ liệu
# bác sĩ cung cấp, đâu là lời dặn của hệ thống.
CONTEXT_TAG = "tien_su_benh_nhan"
MAX_CHARS = 3000

_ALLERGY_RE = re.compile(r"d[iị]\s*[uứ]ng|allerg", re.IGNORECASE)


def clean_history(history: Optional[str]) -> Optional[str]:
    """Chuỗi tiền sử đã gọn, hoặc None nếu bác sĩ để trống."""
    text = (history or "").strip()
    if not text:
        return None
    return text[:MAX_CHARS]


def wrap_for_prompt(context: Optional[str]) -> str:
    if not context:
        return ""
    return (
        f"<{CONTEXT_TAG}>\n{context}\n</{CONTEXT_TAG}>\n\n"
        "Khối trên là tình trạng bệnh nhân trước đó do bác sĩ ghi lại. "
        "Nếu có dị ứng thuốc hoặc bệnh nền liên quan, PHẢI nêu trong phần lập luận "
        "và PHẢI tránh thuốc chống chỉ định.\n\n"
    )


def build_prompt_block(history: Optional[str]) -> tuple[Optional[str], str]:
    """(chuỗi thô để hiện lại cho bác sĩ, khối đã bọc để ghép vào prompt)."""
    context = clean_history(history)
    return context, wrap_for_prompt(context)


def allergy_text(history: Optional[str]) -> Optional[str]:
    """
    Chỉ những câu/dòng nói về dị ứng trong ô tiền sử, để đối chiếu với thuốc.

    Không đưa CẢ ô vào bộ đối chiếu dị ứng: ô thường có cả thuốc đang dùng
    ("đang uống metformin"), và bộ đối chiếu sẽ tưởng đó là chất gây dị ứng.
    None = bác sĩ không nhắc gì tới dị ứng, tức là CHƯA KIỂM được.
    """
    text = clean_history(history)
    if not text:
        return None
    parts = re.split(r"[\n;.]+", text)
    hits = [p.strip() for p in parts if _ALLERGY_RE.search(p)]
    return "; ".join(hits) if hits else None
