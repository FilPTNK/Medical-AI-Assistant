"""
Danh mục tài liệu MIỄN PHÍ, được phép dùng, để bổ sung thư viện — kèm giấy phép,
chia theo CHUYÊN KHOA.

Nguồn: báo cáo reports/Medical assistant redesign research.md (mục "Feed the
library government text first, licensed books never").

Quy tắc chọn:
  * Văn bản của Bộ Y tế (Hướng dẫn chẩn đoán và điều trị ban hành kèm Quyết
    định QĐ-BYT) không thuộc đối tượng bảo hộ quyền tác giả (Luật SHTT, Điều 15).
  * WHO: CC BY-NC-SA 3.0 IGO — dùng phi thương mại, ghi nguồn.
  * KHÔNG nạp: NICE (phải xin phép cho mọi dùng AI), MSD Manuals, UpToDate, BNF.
  * Dược thư Quốc gia, sách của bệnh viện: chỉ dùng nội bộ, không phân phối lại.

Dùng:
    python backend/library_sources.py                          # liệt kê theo chuyên khoa
    python backend/library_sources.py --download               # tải tất cả về data/incoming/
    python backend/library_sources.py --download --specialty "Tai Mũi Họng"

Tải xong, nạp từng tệp qua tab "Tra cứu thuốc" → "Sách & tài liệu gốc" → Tải
lên (pipeline generic_ingest: tối đa 64 MiB / 300 trang mỗi tệp). Hướng dẫn
nhiều chuyên khoa thường dày hơn 300 trang — tách theo chương trước khi nạp.
"""

import argparse
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config

INCOMING_DIR = os.path.join(config.DATA_DIR, "incoming")

# Chia theo chuyên khoa như cách bác sĩ tìm sách: mở đúng "ngăn" Tai Mũi Họng,
# Cơ xương khớp… Chỉ ghi đường dẫn đã kiểm tra trả về PDF (HEAD, 28/10/2026).
# Văn bản đã bị thay thế phải ghi rõ trong "note" để không nạp nhầm bản cũ.
BYT = "Văn bản hành chính nhà nước — không thuộc đối tượng bảo hộ quyền tác giả (Luật SHTT Đ.15)"
KCB_PUBLISHER = "Cục Quản lý Khám, chữa bệnh — Bộ Y tế"
KCB = "https://kcb.vn/upload/2005611/"

SOURCES = [
    {
        "specialty": "Tai Mũi Họng",
        "file": "BYT-HDCDT-Tai-mui-hong-5643-2015.pdf",
        "title": "Hướng dẫn chẩn đoán và điều trị một số bệnh về tai mũi họng (QĐ 5643/QĐ-BYT, 2015)",
        "url": KCB + "20210723//HD%C4%90T-TMH.pdf",
        "publisher": KCB_PUBLISHER,
        "license": BYT,
        "size_mb": 2.7,
    },
    {
        "specialty": "Cơ xương khớp",
        "file": "BYT-HDCDT-Co-xuong-khop-361-2014.pdf",
        "title": "Hướng dẫn chẩn đoán và điều trị các bệnh cơ xương khớp (QĐ 361/QĐ-BYT, 2014)",
        "url": "https://storage-vnportal.vnpt.vn/bpc-khdn/3170/PH%C3%81C%20%C4%90%E1%BB%92%20%C4%90I%E1%BB%80U%20TR%E1%BB%8A/"
               "H%C6%B0%E1%BB%9Bng%20d%E1%BA%ABn%20ch%E1%BA%A9n%20%C4%91o%C3%A1n%20v%C3%A0%20%C4%91i%E1%BB%81u%20tr%E1%BB%8B%20"
               "b%E1%BB%87nh%20C%C6%A1%20x%C6%B0%C6%A1ng%20kh%E1%BB%9Bp%20BYT.pdf",
        "publisher": "Bộ Y tế (bản sao trên cổng thông tin một bệnh viện, hạ tầng VNPT)",
        "license": BYT,
        "size_mb": 1.3,
    },
    {
        "specialty": "Thận – Tiết niệu",
        "file": "BYT-HDCDT-Than-tiet-nieu.pdf",
        "title": "Hướng dẫn chẩn đoán và điều trị một số bệnh về thận – tiết niệu (Bộ Y tế)",
        "url": KCB + "20210723//H%C6%B0%E1%BB%9Bng-d%E1%BA%ABn-ch%E1%BA%A9n-%C4%91o%C3%A1n-v%C3%A0-%C4%91i%E1%BB%81u-tr%E1%BB%8B-"
                     "c%C3%A1c-b%E1%BB%87nh-Th%E1%BA%ADn-Ti%E1%BA%BFt-ni%E1%BB%87u.pdf",
        "publisher": KCB_PUBLISHER,
        "license": BYT,
        "size_mb": 2.5,
        "note": "Bản cũ; bệnh thận mạn đã có hướng dẫn mới 2388/QĐ-BYT (2024) — xem TO_FIND_MANUALLY.",
    },
    {
        "specialty": "Hô hấp",
        "file": "BYT-HDCDT-Benh-phoi-mo-ke-2023.pdf",
        "title": "Hướng dẫn chẩn đoán và điều trị bệnh phổi mô kẽ (Bộ Y tế, 2023)",
        "url": KCB + "20230421/QD_2023_1005__Ban_hanh_Huong_dan_chan_doan_va_dieu_tri_Benh_phoi_mo_ke__36b7a.pdf",
        "publisher": KCB_PUBLISHER,
        "license": BYT,
        "size_mb": 10.2,
    },
    {
        "specialty": "Hồi sức – Cấp cứu – Chống độc",
        "file": "BYT-HDCDT-Hoi-suc-tich-cuc.pdf",
        "title": "Hướng dẫn chẩn đoán và xử trí hồi sức tích cực (Bộ Y tế)",
        "url": KCB + "20210723//H%C6%B0%E1%BB%9Bng-d%E1%BA%ABn-ch%E1%BA%A9n-%C4%91o%C3%A1n-%C4%91i%E1%BB%81u-tr%E1%BB%8B-"
                     "h%E1%BB%93i-s%E1%BB%A9c-t%C3%ADch-c%E1%BB%B1c.pdf",
        "publisher": KCB_PUBLISHER,
        "license": BYT,
        "size_mb": 3.3,
    },
    {
        "specialty": "Hồi sức – Cấp cứu – Chống độc",
        "file": "BYT-HDCDT-Ngo-doc.pdf",
        "title": "Hướng dẫn chẩn đoán và xử trí ngộ độc (Bộ Y tế)",
        "url": KCB + "20210723/d6b3c2e365022cb575807206d4f4be20Huong-dan-chan-doan-va-xu-tri-Ngo-doc.pdf",
        "publisher": KCB_PUBLISHER,
        "license": BYT,
        "size_mb": 3.9,
    },
    {
        "specialty": "Truyền nhiễm",
        "file": "BYT-HDCDT-Truyen-nhiem-2021.pdf",
        "title": "Hướng dẫn chẩn đoán và điều trị các bệnh truyền nhiễm (Bộ Y tế)",
        "url": KCB + "20210723//Truyen-nhiem-1.pdf",
        "publisher": KCB_PUBLISHER,
        "license": BYT,
        "size_mb": 0.5,
    },
    {
        "specialty": "Ung bướu",
        "file": "BYT-HDCDT-Ung-thu-vu-3128-2020.pdf",
        "title": "Hướng dẫn chẩn đoán và điều trị ung thư vú (QĐ 3128/QĐ-BYT, 2020)",
        "url": KCB + "20210723/3128_QD-BYT_Huong-dan-chan-doan-va-dieu-tri-ung-thu-vu.pdf",
        "publisher": KCB_PUBLISHER,
        "license": BYT,
        "size_mb": 1.1,
    },
    {
        "specialty": "Ung bướu",
        "file": "BYT-HDCDT-Ung-thu-gan-3129-2020.pdf",
        "title": "Hướng dẫn chẩn đoán và điều trị ung thư biểu mô tế bào gan (QĐ 3129/QĐ-BYT, 2020)",
        "url": KCB + "20210723//3129_QD-BYT_Huong-dan-chan-doan-va-dieu-tri-ung-thu-bieu-mo-te-bao-gan.pdf",
        "publisher": KCB_PUBLISHER,
        "license": BYT,
        "size_mb": 1.3,
    },
    {
        "specialty": "Ung bướu",
        "file": "BYT-HDCDT-Ung-thu-tuyen-tien-liet-3130-2020.pdf",
        "title": "Hướng dẫn chẩn đoán và điều trị ung thư tuyến tiền liệt (QĐ 3130/QĐ-BYT, 2020)",
        "url": KCB + "20210723//3130_QD-BYT_Huong-dan-chan-doan-va-dieu-tri-UT-tuyen-tien-li%E1%BA%B9t.pdf",
        "publisher": KCB_PUBLISHER,
        "license": BYT,
        "size_mb": 1.2,
    },
    {
        "specialty": "Dược – Thuốc thiết yếu",
        "file": "WHO-EML-2025-technical-report.pdf",
        "title": "WHO — The selection and use of essential medicines 2025 (EML 24 / EMLc 10)",
        "url": "https://www.iccp-portal.org/sites/default/files/2025-09/B09474-eng.pdf",
        "publisher": "World Health Organization (bản sao trên iccp-portal.org)",
        "license": "CC BY-NC-SA 3.0 IGO — phi thương mại, ghi nguồn WHO",
        "size_mb": 1.2,
    },
]

# Có giá trị nhưng chưa có đường dẫn PDF chính thức kiểm tra được (trang Sở Y tế
# Bắc Giang không phản hồi, các trang tổng hợp đòi đăng nhập) — tải tay từ trang
# .gov.vn rồi nạp như trên.
TO_FIND_MANUALLY = [
    ("Tim mạch", "Suy tim cấp và mạn — 1857/QĐ-BYT (2022), thay 1762/QĐ-BYT"),
    ("Nội tiết – Chuyển hóa", "Bệnh nội tiết – chuyển hóa — 3879/QĐ-BYT (2014)"),
    ("Nội tiết – Chuyển hóa", "Đái tháo đường típ 2 — 5481/QĐ-BYT (2020), thay 3319/QĐ-BYT"),
    ("Hô hấp", "Bệnh hô hấp — 4235/QĐ-BYT (2012)"),
    ("Hô hấp", "Bệnh phổi tắc nghẽn mạn tính — 2767/QĐ-BYT (2023)"),
    ("Thận – Tiết niệu", "Bệnh thận mạn và một số bệnh lý thận — 2388/QĐ-BYT (2024)"),
    ("Huyết học", "Một số bệnh lý huyết học — 1832/QĐ-BYT (2022)"),
    ("Da liễu", "Các bệnh da liễu — 75/QĐ-BYT (2015); bản cập nhật 4416/QĐ-BYT (2023) có trên syt.bacgiang.gov.vn"),
    ("Mắt", "Các bệnh về mắt — 40/QĐ-BYT (2015)"),
    ("Răng Hàm Mặt", "Một số bệnh về răng hàm mặt — 3108/QĐ-BYT (2015)"),
    ("Sản phụ khoa", "Các bệnh sản phụ khoa — 315/QĐ-BYT (2015)"),
    ("Nhi khoa", "Một số bệnh thường gặp ở trẻ em — 3312/QĐ-BYT (2015)"),
    ("Nhi khoa", "Sách hướng dẫn chẩn đoán và điều trị bệnh trẻ em 2020 — BV Nhi Trung ương "
                 "(benhviennhitrunguong.gov.vn, 9,9 MB; sách của bệnh viện, chỉ dùng nội bộ)"),
    ("Tâm thần", "Một số rối loạn tâm thần thường gặp — 2058/QĐ-BYT (2020)"),
    ("Tiêu hóa – Gan mật", "Viêm gan vi rút B — 1740/QĐ-BYT"),
    ("Ung bướu", "Một số bệnh ung bướu — 1514/QĐ-BYT (2020)"),
]


def list_sources() -> None:
    for sp in dict.fromkeys(s["specialty"] for s in SOURCES):
        print(f"\n[{sp}]")
        for s in SOURCES:
            if s["specialty"] == sp:
                print(f"- {s['title']}\n    {s['url']}\n    ~{s['size_mb']} MB · {s['license']}")
                if s.get("note"):
                    print(f"    Lưu ý: {s['note']}")
    print("\nCần tìm bản PDF chính thức (.gov.vn) rồi nạp tay:")
    for topic, decision in TO_FIND_MANUALLY:
        print(f"- [{topic}] {decision}")


def download(specialty: str = "") -> None:
    os.makedirs(INCOMING_DIR, exist_ok=True)
    for s in SOURCES:
        if specialty and s["specialty"] != specialty:
            continue
        dest = os.path.join(INCOMING_DIR, s["file"])
        if os.path.exists(dest):
            print(f"Đã có: {dest}")
            continue
        req = urllib.request.Request(s["url"], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(dest + ".part", "wb") as out:
            if "pdf" not in (resp.headers.get("Content-Type") or ""):
                raise RuntimeError(f"{s['url']} không trả về PDF")
            out.write(resp.read())
        os.replace(dest + ".part", dest)
        print(f"Đã tải: {dest}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--download", action="store_true", help="Tải các tệp trong danh mục về data/incoming/")
    parser.add_argument("--specialty", default="", help="Chỉ tải một chuyên khoa, ví dụ \"Tai Mũi Họng\"")
    args = parser.parse_args()
    download(args.specialty) if args.download else list_sources()
