# -*- coding: utf-8 -*-
"""Bộ truy vấn đánh giá CHÍNH — truy vấn kiểu từ khoá ("thuốc <nhóm>").

`expect` = dấu hiệu chunk ĐÚNG chủ đề, `trap` = chủ đề hay bị nhầm sang.
Giữ nguyên từ phiên trước để mọi số đo trước/sau còn so sánh được với nhau.
"""

QUERIES = [
    ("thuốc hạ sốt",               ["hạ sốt", "hạ nhiệt", "giảm sốt", "cảm sốt", "paracetamol", "ibuprofen", "aspirin"], ["sốt rét", "sốt xuất huyết"]),
    ("thuốc trị sốt rét",          ["sốt rét", "plasmodium", "ký sinh trùng"], []),
    ("thuốc kháng sinh",           ["kháng sinh", "kháng khuẩn", "nhiễm khuẩn"], []),
    ("thuốc điều trị cao huyết áp",["huyết áp", "tăng huyết áp"], []),
    ("thuốc tiểu đường",           ["đái tháo đường", "tiểu đường", "insulin", "glucose huyết"], []),
    ("thuốc giảm đau",             ["giảm đau", "đau"], []),
    ("thuốc ho",                   ["ho", "long đờm", "giảm ho"], []),
    ("thuốc chống dị ứng",         ["dị ứng", "kháng histamin", "mề đay"], []),
    ("thuốc đau dạ dày",           ["dạ dày", "loét", "tá tràng"], []),
    ("thuốc chống đông máu",       ["đông máu", "chống đông", "huyết khối"], []),
]
