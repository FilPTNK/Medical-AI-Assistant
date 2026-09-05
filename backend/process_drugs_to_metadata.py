"""ĐÃ THAY THẾ — đừng chạy. Dùng: python backend/parse_biet_duoc.py --doc-name <ID>

Ghi ra data/vector_db/metadata.json, tệp không còn ai đọc: main.py giờ lấy chunk
trực tiếp từ data/chunks/<doc_name>.json (xem get_book_metadata). Chạy lại kịch
bản này cũng không tác động gì, ngoài việc tạo một bản sao 12 MB dễ lệch.

Ngoài ra nó không truyền monograph_page_range nên sẽ đọc cả phụ lục và mục lục
tra cứu thành chunk rác.
"""

import os
import json
import sys
from drug_parser import parse_pdf_text_to_chunks

sys.stdout.reconfigure(encoding='utf-8')

# Đường dẫn file đầu ra metadata.json
OUTPUT_METADATA_PATH = os.path.join(os.path.dirname(__file__), "data", "vector_db", "metadata.json")
SOURCE_PDF_NAME = "THUOC-BIET-DUOC-VA-CACH-SU-DUNG.pdf"

# Dữ liệu text trích xuất từ các trang của sách Dược thư (bao gồm mẫu trang 45, 70, 71 từ sách)
SAMPLE_BOOK_TEXT = """[Trang 45]
AMIKACIN
BD: Lukadin (Italia), Acemycin (Pháp), Amiklin (Mỹ), Biklin (Đức).
DT: Lọ thuốc bột tiêm 250mg, 500mg kèm ống dung môi 2ml hoặc 4ml.
TD: Kháng sinh bán tổng hợp họ aminosid, phổ diệt khuẩn rộng bao gồm trực khuẩn Gram âm và tụ cầu khuẩn kháng methicillin.
CĐ: Các nhiễm khuẩn nặng nghi do trực khuẩn Gram âm nhạy cảm: nhiễm khuẩn huyết, viêm màng trong tim, nhiễm khuẩn hô hấp dưới, nhiễm khuẩn ổ bụng và đường tiết niệu có biến chứng.
LD: Người có chức năng thận bình thường: 15mg/kg/ngày chia làm 2-3 lần (tiêm bắp hoặc truyền tĩnh mạch chậm trong 30-60 phút). Trẻ sơ sinh: liều nạp 10mg/kg, sau đó 7.5mg/kg mỗi 12 giờ.
CCĐ: Mẫn cảm với các Aminosid. Phụ nữ có thai và cho con bú. Nhược cơ nặng.
LY: Độc tính trên thính giác (thần kinh VIII) và thận. Cần theo dõi chức năng thận và giảm liều khi có suy thận.
Tương tác thuốc: Tránh phối hợp với các thuốc gây độc trên thận và tai khác như Furosemid, Cisplatin, Vancomycin.

[Trang 70]
ARGININ ASPARTAT
BD: Argihepar (Đức), Manpos (Hàn Quốc), Potenciator (Tây Ban Nha), Sargénor (Áo-Pháp-Đức), Sorbenor (Tây Ban Nha), Targifor (Roussel-Brasil).
DT: Ống thuốc 10ml/5g hoặc 5ml/1g.
TD: Tăng đường và chống dị hóa (Anticatabolisant) protid do kích thích tiết hormon tăng trưởng ở vùng đồi-tuyến yên (STH hoặc GH), insulin và glucagon.
CĐ: Trẻ em chậm lớn, người lớn suy nhược.
LD: Trẻ em: tùy theo thể trọng, ngày uống từ 1 đến 3 ống 5ml vào khoảng 2 giờ sau bữa ăn tối. Người lớn: ngày uống 2-3 ống loại 10ml vào trước bữa ăn. Trẻ em suy nhược từ 30 tháng trở lên: ngày 1/2-2 ống loại 5ml tùy theo tuổi.

ARGININ OXOGLURAT
BD: Anetil (Merck), Eucol (Pháp), Leberam (Đức).
DT: Viên nén sủi bọt 1,5g arginin oxoglurat. Lọ thuốc tiêm (bột đông khô) 2,5-5 và 10g kèm ống 10ml nước cất tiêm.
TD: Acid amin, dùng tiêm làm giảm nồng độ amoniac trong máu.
CĐ: Các chứng suy nhược, triệu chứng suy nhược chức năng gan. Điều trị bệnh não-gan (Encéphalopathie hépatique).
LD: Ngày uống 2-4 viên vào bữa ăn, hòa tan viên thuốc vào một cốc nước. Tiêm tĩnh mạch ngày 1-2 lọ 2,5g. Tiêm truyền tĩnh mạch 4-8 lọ 5g hoặc 2-4 lọ 10g.
LY: Tránh tiêm truyền với dd có nồng độ trên 10%. Điều chỉnh lưu lượng tiêm truyền với tốc độ dưới hoặc bằng 10g/125ml/giờ.

[Trang 71]
ARGINOTRI - B (Bouchara)
DT: Viên bao: L - arginin HCl 250mg, Thiamin HCl 100mg, Pyridoxin HCl 100mg, Hydroxocobalamin khan 250mcg.
TD: Giải độc gan - Giảm đau - Bảo vệ thần kinh - Điều hoà amoniac cao bất thường trong máu ở một số bệnh gan. Với sự có mặt của vitamin nhóm B tham gia vào nhiều phản ứng chuyển hoá làm giảm đau, hướng gan, bảo vệ thần kinh.
CĐ: - Rối loạn chức năng gan do ngộ độc: tiền xơ gan, xơ gan - Bệnh não do gan.
- Rối loạn tâm thần ở người nghiện rượu: tình trạng say rượu cấp.
- Các tổn thương thần kinh do chuyển hoá hoặc nhiễm khuẩn: viêm dây thần kinh, viêm đa dây thần kinh.
- Các biểu hiện đau: zôna, viêm tĩnh mạch, sau phẫu thuật, thoái hoá khớp, thần kinh hông, cổ cánh tay.
- Rối loạn dinh dưỡng: suy nhược, chán ăn, sụt cân, dưỡng bệnh, người cao tuổi.
LD: Uống 6 - 8 viên/ngày.
CCĐ: Dị ứng với cobalamin.
LY: Không phối hợp với levodopa (ức chế men dopadecarboxylase ngoại biên).

ARGIPRESSIN
BD: ADH, Vasopressin, Pitressin (Parke Davis).
DT: Ống tiêm 20 IU/ml.
TD: Hormon thuỳ sau tuyến yên, chống bài niệu, làm co mạch ngoại vi tăng huyết áp.
CĐ: Đái tháo nhạt thể trung ương, xuất huyết tiêu hóa do giãn vỡ tĩnh mạch thực quản.
LD: Tiêm dưới da hoặc tiêm bắp 5-10 đơn vị, lặp lại sau 3-4 giờ nếu cần.
CCĐ: Xơ vữa động mạch nặng, bệnh mạch vành, tăng huyết áp chưa kiểm soát.

ARGYROL
DT: Thuốc nhỏ mắt 1-3% - Dung dịch dùng ngoài da.
TD: Sát khuẩn nhẹ tại chỗ do tác dụng của muối bạc.
CĐ: Sát khuẩn niêm mạc mắt, hỗ trợ điều trị viêm kết mạc, sát trùng vết thương nông ngoài da.
LD: Nhỏ 1-2 giọt vào mắt, 2-3 lần một ngày.
CCĐ: Mẫn cảm hoặc dị ứng với muối bạc.

ARMIN (Nga)
DT: Thuốc nhỏ mắt. Dung dịch 0,10%.
TD: Thuốc ức chế men cholinesterase không hồi phục, gây co đồng tử mạnh và hạ nhãn áp.
CĐ: Thuốc co đồng tử và trị glôcôm (tăng nhãn áp), làm giảm tác dụng giãn đồng tử và tác dụng tê liệt điều chỉnh thị giác của Atropin, tương tự như Paraoxon.
LD: Nhỏ 1-2 giọt, 2-3 lần một ngày.
CCĐ: Hen phế quản, tắc nghẽn cơ học đường tiêu hóa hoặc đường niệu, viêm mống mắt thể mi cấp.

ARNILOSE (AJC)
BD: Arginin HCl, Ornithin HCl, Sorbitol.
DT: Dung dịch uống ống 5ml (chứa Arginin HCl 500mg, Ornithin HCl 50mg, Sorbitol 1,29g).
TD: Hỗ trợ chức năng khử độc gan, thúc đẩy chu trình urê, nhuận tràng nhẹ.
CĐ: Khó tiêu, chướng bụng, đầy hơi do rối loạn chức năng gan hoặc khó tiêu chức năng.
LD: Uống 1-2 ống/ngày trước các bữa ăn chính hoặc khi có triệu chứng khó tiêu.
"""

def generate_metadata_json():
    print(f"[1/3] Đang tiến hành bóc tách văn bản sách theo chuẩn Field-Centric...")
    chunks = parse_pdf_text_to_chunks(SAMPLE_BOOK_TEXT, source_file_name=SOURCE_PDF_NAME)
    print(f" -> Đã trích xuất thành công {len(chunks)} Chunks Metadata.")

    # Đảm bảo thư mục lưu trữ tồn tại
    os.makedirs(os.path.dirname(OUTPUT_METADATA_PATH), exist_ok=True)

    print(f"[2/3] Đang ghi dữ liệu vào file: {OUTPUT_METADATA_PATH}...")
    with open(OUTPUT_METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    print(f"[3/3] Hoàn tất! File metadata.json ({os.path.getsize(OUTPUT_METADATA_PATH)} bytes) đã sẵn sàng để kiểm tra.")
    return chunks

if __name__ == "__main__":
    generate_metadata_json()
