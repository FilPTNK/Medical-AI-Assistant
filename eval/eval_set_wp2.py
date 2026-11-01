# -*- coding: utf-8 -*-
"""80 nhãn ứng viên. TOÀN BỘ CẦN DƯỢC SĨ DUYỆT trước khi dùng làm chuẩn lâm sàng."""
REVIEW = "CẦN DƯỢC SĨ DUYỆT"

INGREDIENTS = (
    "Paracetamol", "Ibuprofen", "Hydroxyzin", "Metformin", "Omeprazol",
    "Atorvastatin", "Amlodipin", "Amoxicilin", "Cetirizin", "Zolpidem",
)
# Tên quan sát trong ví dụ đo của người dùng; chưa xác minh là biệt dược hay OCR đúng.
BRANDS = ("ALKA-SELTZER", "DIMETICON", "KAOLOGEAIS", "MEBEVERIN", "ROFECOXIB")
# Cặp chủ đề–tên thuốc chỉ là ứng viên đánh giá, không phải chỉ định điều trị.
SYMPTOMS = (
    ("đau bụng", "MEBEVERIN", "ROFECOXIB"),
    ("đầy hơi", "DIMETICON", "ROFECOXIB"),
    ("sốt", "Paracetamol", "ROFECOXIB"),
    ("dị ứng", "Hydroxyzin", "ROFECOXIB"),
    ("đau dạ dày", "Omeprazol", "ROFECOXIB"),
)

QUERIES = []
for i, drug in enumerate(INGREDIENTS):
    trap = INGREDIENTS[(i + 5) % len(INGREDIENTS)]
    for pattern in ("{d}", "tra cứu hoạt chất {d}"):
        QUERIES.append((pattern.format(d=drug), [drug], [trap], "hoạt chất", REVIEW))
for i, brand in enumerate(BRANDS):
    trap = BRANDS[(i + 2) % len(BRANDS)]
    for pattern in ("{d}", "thuốc {d}", "thông tin {d}", "tìm {d} trong sách"):
        QUERIES.append((pattern.format(d=brand), [brand], [trap], "tên biệt dược/thuốc", REVIEW))
for subject, drug, trap in SYMPTOMS:
    for pattern in ("thuốc giảm {s}", "thuốc điều trị {s}", "thuốc cho {s}", "thuốc chữa {s}"):
        QUERIES.append((pattern.format(s=subject), [drug], [trap], "triệu chứng/chỉ định", REVIEW))
for i, drug in enumerate(INGREDIENTS):
    trap = INGREDIENTS[(i + 5) % len(INGREDIENTS)]
    for pattern in ("{d} thời kỳ mang thai", "{d} khi suy thận"):
        QUERIES.append((pattern.format(d=drug), [drug], [trap], "thận trọng", REVIEW))
assert len(QUERIES) == 80
