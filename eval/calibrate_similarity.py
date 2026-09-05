# -*- coding: utf-8 -*-
"""Chọn ngưỡng cosine cho "câu hỏi tương tự đã hỏi trước đây".

Vì sao cần chạy lại mỗi khi đổi model embedding: ngưỡng không mang nghĩa tuyệt
đối. Mỗi model trải điểm cosine trên một khoảng riêng — họ e5 nén hết lên vùng
cao, hai câu chẳng liên quan gì vẫn quanh 0,85. Bê nguyên ngưỡng 0,55 của model
cũ sang thì mọi câu hỏi trong lịch sử đều bị coi là gần nghĩa.

Cách chọn: lấy ngưỡng tách sạch hai nhóm — cặp DIỄN ĐẠT KHÁC (phải khớp) và
cặp KHÁC CHỦ ĐỀ (không được khớp). Kết quả điền vào _EMBEDDING_THRESHOLDS
trong backend/library_db.py.

Chạy:  python eval/calibrate_similarity.py
"""

import os
import sys
import warnings

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))
os.chdir(os.path.join(BASE_DIR, "backend"))
warnings.filterwarnings("ignore")

import config          # noqa: E402
from vector_store import VectorStore  # noqa: E402

# Cặp CÙNG ý, diễn đạt khác — đây chính là thứ tính năng cần bắt được.
SAME = [
    ("thuốc hạ sốt cho trẻ em", "trẻ con sốt thì uống thuốc gì"),
    ("điều trị tăng huyết áp", "thuốc chữa cao huyết áp"),
    ("thuốc trị đau dạ dày", "đau bao tử uống thuốc gì"),
    ("kháng sinh cho viêm họng", "viêm họng dùng kháng sinh nào"),
    ("thuốc tiểu đường type 2", "điều trị đái tháo đường tuýp 2"),
    ("thuốc chống dị ứng mề đay", "nổi mề đay uống thuốc gì"),
]
# Cặp KHÁC chủ đề — không được coi là giống nhau.
DIFF = [
    ("thuốc hạ sốt cho trẻ em", "thuốc điều trị sốt rét"),
    ("điều trị tăng huyết áp", "thuốc nhỏ mắt viêm kết mạc"),
    ("thuốc trị đau dạ dày", "thuốc chống đông máu"),
    ("kháng sinh cho viêm họng", "bổ sung sắt cho người thiếu máu"),
    ("thuốc tiểu đường type 2", "thuốc bôi ngoài da trị nấm"),
    ("thuốc chống dị ứng mề đay", "thuốc an thần gây ngủ"),
    ("thuốc hạ sốt cho trẻ em", "thuốc chống co giật động kinh"),
    ("thuốc trị đau dạ dày", "thuốc hạ mỡ máu cholesterol"),
]


def main():
    db = VectorStore(config.VECTOR_DB_DIR)
    print(f"model: {db.embedding_model}\n")

    def cos(a, b):
        va, vb = np.array(db.embed_text(a)), np.array(db.embed_text(b))
        return float(va @ vb / (np.linalg.norm(va) * np.linalg.norm(vb)))

    same = [(a, b, cos(a, b)) for a, b in SAME]
    diff = [(a, b, cos(a, b)) for a, b in DIFF]

    print("CÙNG ý, diễn đạt khác (cần ĐẠT ngưỡng):")
    for a, b, s in sorted(same, key=lambda x: x[2]):
        print(f"  {s:.4f}  {a}  ||  {b}")
    print("\nKHÁC chủ đề (cần TRƯỢT ngưỡng):")
    for a, b, s in sorted(diff, key=lambda x: -x[2]):
        print(f"  {s:.4f}  {a}  ||  {b}")

    lo_same = min(s for _, _, s in same)
    hi_diff = max(s for _, _, s in diff)
    print(f"\nthấp nhất của nhóm CÙNG : {lo_same:.4f}")
    print(f"cao nhất  của nhóm KHÁC : {hi_diff:.4f}")
    if lo_same > hi_diff:
        thr = round((lo_same + hi_diff) / 2, 2)
        print(f"=> hai nhóm tách rời. Ngưỡng đề nghị: {thr}")
    else:
        # Không tách được thì ưu tiên không báo nhầm: thà bỏ sót một gợi ý còn
        # hơn đưa cho bác sĩ một câu hỏi cũ chẳng liên quan.
        thr = round(hi_diff + 0.01, 2)
        print(f"=> hai nhóm CHỒNG nhau. Chọn ngưỡng chặn hết nhóm KHÁC: {thr}")
        print(f"   (sẽ bỏ sót {sum(1 for _,_,s in same if s < thr)}/{len(same)} cặp cùng ý)")
    print(f"\nĐiền vào _EMBEDDING_THRESHOLDS trong backend/library_db.py:")
    print(f'    "{db.embedding_model}": {thr},')


if __name__ == "__main__":
    main()
