"""
Một chỗ DUY NHẤT biến hồ sơ bệnh nhân thành chữ gửi ra mô hình ngoài.

Hai đường chẩn đoán (agent ReAct ở agent.py và cây chẩn đoán bốn bước ở
llm_client.py) trước đây có hai định nghĩa khác nhau về "tiền sử bệnh nhân".
Hai định nghĩa là cách một trong hai lặng lẽ trôi đi và bắt đầu bỏ sót dị ứng,
nên gộp về đây.

KHỬ DANH THEO DANH SÁCH CHO PHÉP, không phải danh sách cấm.
Chỉ những trường liệt kê trong _FIELDS_* mới được vào chuỗi. Thêm cột mới vào
bảng patients — số điện thoại, địa chỉ, nghề nghiệp — thì mặc định nó KHÔNG
đi ra ngoài, phải sửa tệp này mới ra được. Làm ngược lại (dựng chuỗi có tên
rồi lọc bỏ sau) là lớp lỗi mà các bộ lọc PHI vẫn hỏng: Philter đạt 99,46%
trên corpus của chính nó nhưng tụt còn ~92,4% trên bệnh án nước khác, còn
Presidio chỉ 0,74 trên văn bản ngoại thần kinh. Không dựng ra thì không phải
lọc.

Giữ lại tuổi, giới tính và mốc thời gian khám: bỏ chúng đi thì chẩn đoán kém
đi thật, đổi lấy một rủi ro chỉ có trên lý thuyết. Hình dạng này gần đúng
"Limited Data Set" của HIPAA (45 CFR 164.514(e)): bỏ tên và mã hồ sơ, giữ
ngày tháng. Các nghiên cứu tái định danh (Sweeney 87%, Golle 63%) đều cần
thêm mã vùng địa lý — thứ mà tệp này không bao giờ gửi.
"""

from typing import Any, Dict, List, Optional

import patient_db

# Trường hồ sơ được phép ra ngoài. Tên, mã hồ sơ, điện thoại, email, địa chỉ,
# nghề nghiệp, id KHÔNG có trong đây và không được thêm vào.
_FIELDS_HISTORY = [
    ("allergies", "Dị ứng"),
    ("chronic_conditions", "Bệnh nền/bệnh mạn tính"),
    ("surgical_history", "Tiền sử phẫu thuật"),
    ("family_history", "Tiền sử gia đình"),
]

MAX_VISITS = 5
MAX_NOTES = 3

# Thẻ bao quanh khối tiền sử. Có thẻ thì mô hình phân biệt được đâu là dữ liệu
# hồ sơ, đâu là lời dặn của hệ thống.
CONTEXT_TAG = "tien_su_benh_nhan"


def build_patient_context(patient_id: Optional[str]) -> Optional[str]:
    """
    Tóm tắt tiền sử ĐÃ KHỬ DANH, hoặc None nếu không có bệnh nhân.

    None và chuỗi rỗng là hai chuyện khác nhau: None nghĩa là bác sĩ không chọn
    hồ sơ nào (đường tra tự do, giữ nguyên hành vi cũ), còn chuỗi có chữ nghĩa
    là có hồ sơ và đây đúng là những gì mô hình đọc được.
    """
    if not patient_id:
        return None

    patient = patient_db.get_patient(patient_id)
    if not patient:
        return None

    lines: List[str] = []

    # Mở đầu bằng tuổi và giới, KHÔNG có tên và KHÔNG có mã hồ sơ.
    age = patient.get("age")
    gender = (patient.get("gender") or "").strip() or "chưa rõ"
    lines.append(
        f"Bệnh nhân {f'{age} tuổi' if age is not None else 'chưa rõ tuổi'}, giới tính {gender}."
    )

    for field, label in _FIELDS_HISTORY:
        value = (patient.get(field) or "").strip()
        if value:
            lines.append(f"{label}: {value}")

    visits = patient.get("visits") or []
    past_visits = [
        v for v in visits if (v.get("symptoms") or v.get("diagnosis_primary"))
    ][:MAX_VISITS]
    if past_visits:
        lines.append("Lịch sử khám gần đây:")
        for v in past_visits:
            date = v.get("visit_date") or "?"
            symptoms = (v.get("symptoms") or "").strip() or "(chưa ghi)"
            diagnosis = (v.get("diagnosis_primary") or "").strip() or "(chưa có chẩn đoán)"
            lines.append(f'- {date}: triệu chứng "{symptoms}" -> chẩn đoán "{diagnosis}"')

    vitals = patient.get("vitals") or []
    if vitals:
        lines.append("Sinh hiệu gần nhất:")
        for v in vitals:
            lines.append(f"- {v.get('vital_type')}: {v.get('value')}")

    notes = patient.get("notes") or []
    if notes:
        note_lines = []
        for n in notes[:MAX_NOTES]:
            reason = (n.get("reason_for_visit") or "").strip()
            if reason:
                note_lines.append(f"- {n.get('visit_date') or ''}: {reason}")
        if note_lines:
            lines.append("Ghi chú lâm sàng gần đây:")
            lines.extend(note_lines)

    if len(lines) == 1:
        lines.append("Chưa có tiền sử khám hoặc ghi chú nào trước đó.")

    return "\n".join(lines)


def wrap_for_prompt(context: Optional[str]) -> str:
    """
    Bọc khối tiền sử để ĐẶT LÊN ĐẦU prompt, trên cả lời dặn lẫn câu hỏi.

    "Lost in the Middle" (Liu và cộng sự, TACL 2024) đo được rằng thông tin nằm
    giữa ngữ cảnh bị bỏ sót nhiều hơn hẳn so với nằm ở đầu hoặc cuối, và điều
    đó đúng với cả mô hình ngữ cảnh dài. Dị ứng thuốc là thứ không được phép
    rơi vào khúc giữa.
    """
    if not context:
        return ""
    return (
        f"<{CONTEXT_TAG}>\n{context}\n</{CONTEXT_TAG}>\n\n"
        "Khối trên là tiền sử đã lấy từ bệnh án, KHÔNG phải do bác sĩ gõ lại. "
        "Nếu có dị ứng thuốc hoặc bệnh nền liên quan, PHẢI nêu trong phần lập luận "
        "và PHẢI tránh thuốc chống chỉ định.\n\n"
    )


def build_prompt_block(patient_id: Optional[str]) -> tuple[Optional[str], str]:
    """
    Trả về (chuỗi thô để hiện cho bác sĩ, khối đã bọc để ghép vào prompt).

    Bác sĩ nhìn thấy đúng chuỗi thô này trên giao diện. Đó là cách kiểm rằng
    tên bệnh nhân không lọt ra, mà không phải mở nhật ký agent.
    """
    context = build_patient_context(patient_id)
    return context, wrap_for_prompt(context)
