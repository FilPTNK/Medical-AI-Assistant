# -*- coding: utf-8 -*-
"""Bộ GIỮ RIÊNG (held-out) — viết TRƯỚC khi chọn tham số, không sửa sau khi đo.

Khác bộ chính ở chỗ: câu hỏi đặt theo LỜI NGƯỜI BỆNH (triệu chứng, hỏi tự nhiên),
ít trùng từ vựng với tiêu đề trong sách. Đây đúng là chỗ dense lẽ ra phải giỏi hơn
BM25, nên nó là phép thử thật sự cho việc nghiêng RRF về BM25.
"""
QUERIES = [
    ("bị đau đầu thì uống thuốc gì",        ["đau đầu", "nhức đầu", "đau nửa đầu", "giảm đau", "migraine"], []),
    ("trẻ em bị tiêu chảy dùng thuốc nào",  ["tiêu chảy", "ỉa chảy", "mất nước", "oresol", "bù nước"], []),
    ("thuốc bôi ngoài da trị nấm",          ["nấm", "chống nấm", "kháng nấm", "bôi ngoài da"], []),
    ("làm sao hết buồn nôn khi đi tàu xe",  ["buồn nôn", "nôn", "say tàu xe", "chống nôn"], []),
    ("thuốc nhỏ mắt chữa viêm kết mạc",     ["mắt", "kết mạc", "nhỏ mắt", "nhãn khoa"], []),
    ("mỡ máu cao cholesterol cần uống gì",  ["cholesterol", "lipid", "mỡ máu", "statin", "lipid huyết"], []),
    ("khó ngủ mất ngủ kéo dài",             ["mất ngủ", "an thần", "gây ngủ", "giấc ngủ"], []),
    ("lên cơn hen khó thở phải làm gì",     ["hen", "suyễn", "phế quản", "khó thở"], []),
    ("bệnh động kinh co giật uống thuốc gì",["động kinh", "co giật", "chống co giật"], []),
    ("thiếu máu cần bổ sung chất gì",       ["thiếu máu", "sắt", "hồng cầu", "acid folic", "vitamin b12"], []),
]
