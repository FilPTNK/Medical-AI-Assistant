"""Xuất hồ sơ bệnh nhân ra PDF chuẩn để in hoặc gửi chuyển viện (ReportLab).

Ba loại văn bản:

    full      — Bệnh án tổng hợp: hành chính, tiền sử, toàn bộ lần khám, đơn
                thuốc, sinh hiệu, ghi chú lâm sàng, lịch tái khám.
    visit     — Phiếu khám bệnh của một lần khám, kèm đơn thuốc.
    referral  — Giấy chuyển tuyến khám bệnh, chữa bệnh: bố cục theo mẫu hành
                chính Việt Nam (quốc hiệu, tiêu ngữ, phần ký tên đóng dấu).

Tiếng Việt cần font Unicode có đủ dấu. Font mặc định của ReportLab (Helvetica)
chỉ có Latin-1 nên sẽ mất dấu; `_register_fonts()` tìm lần lượt DejaVu Sans →
Arial → Times New Roman → Tahoma trong thư mục font của hệ điều hành và nhúng
vào PDF, chỉ lùi về Helvetica khi máy không có font nào trong số đó.
"""
import json
import os
from datetime import date, datetime
from io import BytesIO
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph,
    Spacer, Table, TableStyle,
)

import config

# Bộ font ưu tiên: (tên đăng ký, file thường, file đậm, file nghiêng, file đậm-nghiêng)
FONT_CANDIDATES = [
    ("DejaVuSans", "DejaVuSans.ttf", "DejaVuSans-Bold.ttf",
     "DejaVuSans-Oblique.ttf", "DejaVuSans-BoldOblique.ttf"),
    ("Arial", "arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
    ("TimesNewRoman", "times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
    ("Tahoma", "tahoma.ttf", "tahomabd.ttf", "tahoma.ttf", "tahomabd.ttf"),
]

FONT_DIRS = [
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
    os.path.join(os.path.expanduser("~"), "AppData", "Local", "Microsoft", "Windows", "Fonts"),
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/truetype",
    "/usr/share/fonts",
    "/Library/Fonts",
    "/System/Library/Fonts/Supplemental",
    os.path.join(config.BASE_DIR, "fonts"),
]

CLINIC_FILE = os.path.join(config.DATA_DIR, "clinic.json")

DEFAULT_CLINIC = {
    "name": "PHÒNG KHÁM ĐA KHOA",
    "parent_org": "SỞ Y TẾ",
    "address": "",
    "phone": "",
    "email": "",
    "department": "",
}

# Màu nhấn của văn bản in — xanh mực, đủ tương phản khi in trắng đen.
ACCENT = colors.HexColor("#1e4e79")
MUTED = colors.HexColor("#5a6470")
RULE = colors.HexColor("#c8d0d8")

_FONT_CACHE: Optional[Dict[str, str]] = None


def _find_font_file(filename: str) -> Optional[str]:
    for directory in FONT_DIRS:
        if not directory or not os.path.isdir(directory):
            continue
        path = os.path.join(directory, filename)
        if os.path.exists(path):
            return path
        # Linux xếp font trong thư mục con; quét một cấp là đủ.
        for entry in os.scandir(directory):
            if entry.is_dir():
                nested = os.path.join(entry.path, filename)
                if os.path.exists(nested):
                    return nested
    return None


def _register_fonts() -> Dict[str, str]:
    """Đăng ký bộ font hỗ trợ tiếng Việt, trả về {'regular','bold','italic','bold_italic'}."""
    global _FONT_CACHE
    if _FONT_CACHE is not None:
        return _FONT_CACHE

    for name, regular, bold, italic, bold_italic in FONT_CANDIDATES:
        regular_path = _find_font_file(regular)
        if not regular_path:
            continue
        try:
            faces = {"regular": name}
            pdfmetrics.registerFont(TTFont(name, regular_path))
            for suffix, filename, key in (
                ("-Bold", bold, "bold"), ("-Italic", italic, "italic"),
                ("-BoldItalic", bold_italic, "bold_italic"),
            ):
                path = _find_font_file(filename) or regular_path
                pdfmetrics.registerFont(TTFont(name + suffix, path))
                faces[key] = name + suffix
            pdfmetrics.registerFontFamily(
                name, normal=name, bold=faces["bold"],
                italic=faces["italic"], boldItalic=faces["bold_italic"],
            )
            _FONT_CACHE = faces
            return faces
        except Exception:
            continue  # font hỏng hoặc không đọc được — thử bộ tiếp theo

    # Không máy nào nên rơi vào đây; giữ để module không sập khi thiếu font.
    _FONT_CACHE = {
        "regular": "Helvetica", "bold": "Helvetica-Bold",
        "italic": "Helvetica-Oblique", "bold_italic": "Helvetica-BoldOblique",
    }
    return _FONT_CACHE


# --- Thông tin cơ sở khám chữa bệnh --------------------------------------

def get_clinic_info() -> Dict[str, Any]:
    info = dict(DEFAULT_CLINIC)
    if os.path.exists(CLINIC_FILE):
        try:
            with open(CLINIC_FILE, "r", encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                info.update({k: v for k, v in stored.items() if k in DEFAULT_CLINIC})
        except (OSError, ValueError):
            pass  # file hỏng — dùng mặc định thay vì chặn việc in giấy tờ
    return info


def save_clinic_info(data: Dict[str, Any]) -> Dict[str, Any]:
    info = get_clinic_info()
    info.update({k: (v or "") for k, v in data.items() if k in DEFAULT_CLINIC})
    with open(CLINIC_FILE, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    return info


# --- Tiện ích định dạng ---------------------------------------------------

def _fmt_date(value: Optional[str]) -> str:
    if not value:
        return "……/……/………"
    try:
        return datetime.fromisoformat(str(value)[:19]).strftime("%d/%m/%Y")
    except ValueError:
        try:
            return date.fromisoformat(str(value)[:10]).strftime("%d/%m/%Y")
        except ValueError:
            return str(value)


def _fmt_datetime(value: Optional[str]) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(str(value)[:19]).strftime("%H:%M %d/%m/%Y")
    except ValueError:
        return _fmt_date(value)


def _text(value: Any, fallback: str = "—") -> str:
    """Chuỗi an toàn cho Paragraph: thoát ký tự XML và thay rỗng bằng gạch ngang."""
    if value is None:
        return fallback
    s = str(value).strip()
    if not s:
        return fallback
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _multiline(value: Any, fallback: str = "—") -> str:
    """Như _text nhưng giữ ngắt dòng của bác sĩ (Paragraph hiểu thẻ <br/>)."""
    s = _text(value, fallback)
    return s.replace("\n", "<br/>")


# --- Bộ khung tài liệu ----------------------------------------------------

class _Styles:
    def __init__(self):
        fonts = _register_fonts()
        self.font = fonts["regular"]
        self.bold = fonts["bold"]
        self.italic = fonts["italic"]
        base = getSampleStyleSheet()["Normal"]

        def style(name, **kwargs):
            attrs = {"fontName": self.font, "fontSize": 10, "leading": 14}
            attrs.update(kwargs)
            return ParagraphStyle(name, parent=base, **attrs)

        self.body = style("body")
        self.small = style("small", fontSize=8.5, leading=11.5, textColor=MUTED)
        self.cell = style("cell", fontSize=9.5, leading=13)
        self.cell_bold = style("cellBold", fontSize=9.5, leading=13, fontName=self.bold)
        self.label = style("label", fontSize=9.5, leading=13, fontName=self.bold, textColor=MUTED)
        self.h1 = style("h1", fontSize=16, leading=21, fontName=self.bold,
                        alignment=TA_CENTER, spaceAfter=2)
        self.h2 = style("h2", fontSize=11.5, leading=15, fontName=self.bold,
                        textColor=ACCENT, spaceBefore=10, spaceAfter=4)
        self.h3 = style("h3", fontSize=10, leading=14, fontName=self.bold, spaceBefore=6)
        self.center = style("center", alignment=TA_CENTER)
        self.center_bold = style("centerBold", alignment=TA_CENTER, fontName=self.bold)
        self.right_italic = style("rightItalic", alignment=TA_RIGHT, fontName=self.italic)
        self.justify = style("justify", alignment=TA_JUSTIFY)


def _build(story: List[Any], title: str, footer_note: str = "") -> bytes:
    """Dựng PDF A4 có đánh số trang; trả về bytes để FastAPI stream thẳng về client."""
    styles = _Styles()
    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=16 * mm,
        title=title, author="Trợ lý Fil",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body")

    def paint_footer(canvas, document):
        canvas.saveState()
        canvas.setFont(styles.font, 7.5)
        canvas.setFillColor(MUTED)
        canvas.setStrokeColor(RULE)
        y = doc.bottomMargin - 6 * mm
        canvas.line(doc.leftMargin, y + 4 * mm, doc.leftMargin + doc.width, y + 4 * mm)
        if footer_note:
            canvas.drawString(doc.leftMargin, y, footer_note)
        canvas.drawRightString(doc.leftMargin + doc.width, y, f"Trang {document.page}")
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=paint_footer)])
    doc.build(story)
    return buffer.getvalue()


def _section(styles: _Styles, title: str) -> List[Any]:
    """Tiêu đề mục kèm gạch chân — mọi mục trong tài liệu dùng chung kiểu này."""
    line = Table([[""]], colWidths=[176 * mm], rowHeights=[0.6])
    line.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.6, RULE)]))
    return [Paragraph(title.upper(), styles.h2), line, Spacer(1, 3)]


def _field_table(styles: _Styles, rows: List[List[tuple]], col_widths=None) -> Table:
    """Bảng nhãn–giá trị hai cột cặp (label, value) mỗi ô."""
    data = []
    for row in rows:
        cells = []
        for label, value in row:
            cells.append(Paragraph(f"{label}:", styles.label))
            cells.append(Paragraph(_multiline(value), styles.cell))
        data.append(cells)
    widths = col_widths or ([30 * mm, 58 * mm] * (len(rows[0]) if rows else 1))
    table = Table(data, colWidths=widths[:len(data[0])] if data else widths)
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _clinic_header(styles: _Styles, clinic: Dict[str, Any], with_national: bool = False) -> List[Any]:
    """Đầu trang hành chính: cơ sở bên trái, quốc hiệu–tiêu ngữ bên phải."""
    left = [
        Paragraph(_text(clinic.get("parent_org"), ""), styles.center),
        Paragraph(f"<b>{_text(clinic.get('name'), 'PHÒNG KHÁM')}</b>", styles.center),
    ]
    if clinic.get("department"):
        left.append(Paragraph(_text(clinic["department"]), styles.center))
    contact = " · ".join(filter(None, [clinic.get("address"), clinic.get("phone")]))
    if contact:
        left.append(Paragraph(_text(contact), styles.small))

    if with_national:
        right = [
            Paragraph("<b>CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM</b>", styles.center),
            Paragraph("<b>Độc lập - Tự do - Hạnh phúc</b>", styles.center),
            Paragraph("_______________________", styles.center),
        ]
    else:
        right = [Paragraph("", styles.center)]

    table = Table([[left, right]], colWidths=[80 * mm, 96 * mm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [table, Spacer(1, 8)]


def _signature_block(styles: _Styles, left_label: str, right_label: str,
                     right_name: str = "") -> Table:
    """Khối ký tên cuối văn bản — chừa khoảng trống ký tay và đóng dấu."""
    today = date.today()
    right = [
        Paragraph(f"Ngày {today.day} tháng {today.month} năm {today.year}", styles.center),
        Paragraph(f"<b>{right_label}</b>", styles.center),
        Paragraph("(Ký, ghi rõ họ tên)", styles.small),
        Spacer(1, 20 * mm),
        Paragraph(f"<b>{_text(right_name, '')}</b>", styles.center),
    ]
    left = [
        Paragraph(f"<b>{left_label}</b>", styles.center),
        Paragraph("(Ký, ghi rõ họ tên)", styles.small),
    ] if left_label else [Paragraph("", styles.center)]

    table = Table([[left, right]], colWidths=[88 * mm, 88 * mm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return table


def _patient_identity_rows(patient: Dict[str, Any]) -> List[List[tuple]]:
    age = f"{patient['age']} tuổi" if patient.get("age") is not None else "—"
    return [
        [("Họ và tên", patient.get("name")), ("Mã hồ sơ", patient.get("code"))],
        [("Ngày sinh", _fmt_date(patient.get("dob")) if patient.get("dob") else None),
         ("Tuổi / Giới tính", f"{age} / {patient.get('gender') or '—'}")],
        [("Điện thoại", patient.get("phone")), ("Nghề nghiệp", patient.get("occupation"))],
        [("Địa chỉ", patient.get("address")), ("Nhóm máu", patient.get("blood_type"))],
    ]


def _medication_table(styles: _Styles, medications: List[Dict[str, Any]]) -> Any:
    if not medications:
        return Paragraph("<i>Không kê thuốc.</i>", styles.cell)
    header = ["TT", "Tên thuốc – hàm lượng", "Liều dùng – cách dùng", "SL"]
    data = [[Paragraph(f"<b>{h}</b>", styles.cell) for h in header]]
    for i, med in enumerate(medications, 1):
        if not isinstance(med, dict):
            continue
        name = _text(med.get("name"))
        if med.get("form"):
            name += f"<br/><font size=8 color='#5a6470'>{_text(med['form'])}</font>"
        usage_parts = [p for p in (med.get("dosage"), med.get("frequency")) if p]
        usage = _text(", ".join(usage_parts), "—")
        if med.get("instructions"):
            usage += f"<br/><font size=8 color='#5a6470'>{_multiline(med['instructions'])}</font>"
        data.append([
            Paragraph(str(i), styles.cell),
            Paragraph(name, styles.cell),
            Paragraph(usage, styles.cell),
            Paragraph(_text(med.get("quantity")), styles.cell),
        ])
    table = Table(data, colWidths=[10 * mm, 62 * mm, 84 * mm, 20 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f6")),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (3, 0), (3, -1), "CENTER"),
    ]))
    return table


def _visit_block(styles: _Styles, visit: Dict[str, Any], index: Optional[int] = None) -> List[Any]:
    """Một lần khám: chẩn đoán, khám thực thể, hướng điều trị, đơn thuốc."""
    heading = f"Lần khám {index}: {_fmt_date(visit.get('visit_date'))}" if index \
        else f"Ngày khám {_fmt_date(visit.get('visit_date'))}"
    if visit.get("title"):
        heading += f" — {_text(visit['title'], '')}"

    block: List[Any] = [Paragraph(heading, styles.h3), Spacer(1, 2)]

    rows = [
        [("Lý do / Triệu chứng", visit.get("symptoms"))],
        [("Chẩn đoán chính", visit.get("diagnosis_primary"))],
    ]
    if visit.get("diagnosis_secondary"):
        rows.append([("Chẩn đoán kèm theo", visit.get("diagnosis_secondary"))])
    if visit.get("exam_findings"):
        rows.append([("Khám thực thể", visit.get("exam_findings"))])
    if visit.get("subclinical_orders"):
        rows.append([("Cận lâm sàng", visit.get("subclinical_orders"))])
    if visit.get("treatment"):
        rows.append([("Hướng điều trị", visit.get("treatment"))])
    if visit.get("treatment_method"):
        rows.append([("Phương pháp", visit.get("treatment_method"))])
    if visit.get("diet_regimen"):
        rows.append([("Chế độ ăn", visit.get("diet_regimen"))])
    if visit.get("precautions"):
        rows.append([("Lưu ý / Chống chỉ định", visit.get("precautions"))])
    if visit.get("care_instructions"):
        rows.append([("Dặn dò chăm sóc", visit.get("care_instructions"))])
    if visit.get("followup_date"):
        rows.append([("Hẹn tái khám",
                      f"{_fmt_date(visit['followup_date'])}"
                      + (f" — {visit['followup_purpose']}" if visit.get("followup_purpose") else ""))])
    if visit.get("doctor_name"):
        rows.append([("Bác sĩ điều trị", visit.get("doctor_name"))])
    if visit.get("doctor_notes"):
        rows.append([("Ghi chú của bác sĩ", visit.get("doctor_notes"))])

    block.append(_field_table(styles, rows, col_widths=[38 * mm, 138 * mm]))

    goals = visit.get("goals") or []
    if goals:
        block.append(Spacer(1, 3))
        block.append(Paragraph("<b>Mục tiêu điều trị</b>", styles.cell))
        for goal in goals:
            block.append(Paragraph(f"• {_text(goal)}", styles.cell))

    medications = visit.get("medications") or []
    if medications:
        block.append(Spacer(1, 4))
        block.append(Paragraph("<b>Đơn thuốc</b>", styles.cell))
        block.append(Spacer(1, 2))
        block.append(_medication_table(styles, medications))

    if visit.get("no_drug_recommendations"):
        block.append(Spacer(1, 3))
        block.append(_field_table(
            styles, [[("Điều trị không dùng thuốc", visit["no_drug_recommendations"])]],
            col_widths=[45 * mm, 131 * mm]))

    block.append(Spacer(1, 8))
    return block


def _clinical_note_block(styles: _Styles, note: Dict[str, Any]) -> List[Any]:
    heading = f"{_fmt_date(note.get('visit_date'))} — {_text(note.get('title'), 'Ghi chú thăm khám')}"
    block = [Paragraph(heading, styles.h3)]

    vitals = [p for p in (
        f"Mạch {note['vital_pulse']}" if note.get("vital_pulse") else None,
        f"HA {note['vital_blood_pressure']}" if note.get("vital_blood_pressure") else None,
        f"Nhịp thở {note['vital_resp_rate']}" if note.get("vital_resp_rate") else None,
        f"Nhiệt độ {note['vital_temperature']}" if note.get("vital_temperature") else None,
    ) if p]

    rows = []
    if note.get("reason_for_visit"):
        rows.append([("Lý do khám", note["reason_for_visit"])])
    if vitals:
        rows.append([("Sinh hiệu", " · ".join(vitals))])
    for label, key in (
        ("Toàn thân", "general_exam"), ("Tim mạch", "cardio_exam"),
        ("Hô hấp", "resp_exam"), ("Bụng", "abdomen_exam"), ("Khác", "other_exam"),
        ("Tai", "ent_ear"), ("Mũi", "ent_nose"), ("Họng", "ent_throat"),
        ("TMH khác", "ent_other"), ("Nội soi mũi", "ent_scope_nose"),
        ("Nội soi tai", "ent_scope_ear"), ("Nội soi họng", "ent_scope_throat"),
    ):
        if note.get(key):
            rows.append([(label, note[key])])

    if rows:
        block.append(_field_table(styles, rows, col_widths=[32 * mm, 144 * mm]))
    if note.get("doctor_name"):
        block.append(Paragraph(f"<i>Người khám: {_text(note['doctor_name'])}</i>", styles.small))
    block.append(Spacer(1, 6))
    return block


# --- Các loại văn bản -----------------------------------------------------

def build_full_record(patient: Dict[str, Any], reminders: Optional[List[Dict[str, Any]]] = None,
                      exported_by: Optional[str] = None) -> bytes:
    """Bệnh án tổng hợp — bản in đầy đủ để lưu hồ sơ giấy."""
    styles = _Styles()
    clinic = get_clinic_info()
    story: List[Any] = []

    story += _clinic_header(styles, clinic)
    story.append(Paragraph("HỒ SƠ BỆNH ÁN", styles.h1))
    story.append(Paragraph(
        f"Mã hồ sơ: <b>{_text(patient.get('code'))}</b> · "
        f"Xuất ngày {date.today().strftime('%d/%m/%Y')}", styles.center))
    story.append(Spacer(1, 10))

    story += _section(styles, "I. Hành chính")
    story.append(_field_table(styles, _patient_identity_rows(patient),
                              col_widths=[30 * mm, 58 * mm, 30 * mm, 58 * mm]))

    body = []
    if patient.get("height_cm") or patient.get("weight_kg"):
        body.append([("Chiều cao", f"{patient['height_cm']} cm" if patient.get("height_cm") else None),
                     ("Cân nặng", f"{patient['weight_kg']} kg" if patient.get("weight_kg") else None)])
    if patient.get("email"):
        body.append([("Email", patient.get("email")), ("", "")])
    if body:
        story.append(_field_table(styles, body, col_widths=[30 * mm, 58 * mm, 30 * mm, 58 * mm]))

    story += _section(styles, "II. Tiền sử")
    story.append(_field_table(styles, [
        [("Dị ứng", patient.get("allergies"))],
        [("Bệnh mãn tính", patient.get("chronic_conditions"))],
        [("Tiền sử phẫu thuật", patient.get("surgical_history"))],
        [("Tiền sử gia đình", patient.get("family_history"))],
    ], col_widths=[38 * mm, 138 * mm]))

    vitals = patient.get("vitals") or []
    if vitals:
        story += _section(styles, "III. Sinh hiệu gần nhất")
        data = [[Paragraph("<b>Chỉ số</b>", styles.cell),
                 Paragraph("<b>Giá trị</b>", styles.cell),
                 Paragraph("<b>Thời điểm đo</b>", styles.cell)]]
        for v in vitals:
            data.append([
                Paragraph(_text(v.get("vital_type")), styles.cell),
                Paragraph(_text(v.get("value")), styles.cell),
                Paragraph(_fmt_datetime(v.get("recorded_at")), styles.cell),
            ])
        table = Table(data, colWidths=[56 * mm, 60 * mm, 60 * mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f6")),
            ("GRID", (0, 0), (-1, -1), 0.4, RULE),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)

    visits = patient.get("visits") or []
    story += _section(styles, f"IV. Diễn biến khám bệnh ({len(visits)} lần)")
    if not visits:
        story.append(Paragraph("<i>Chưa ghi nhận lần khám nào.</i>", styles.cell))
    else:
        # Bản in đọc theo thời gian tăng dần, ngược với thứ tự mới-nhất-trước của giao diện.
        for i, visit in enumerate(reversed(visits), 1):
            story.append(KeepTogether(_visit_block(styles, visit, i)))

    notes = patient.get("notes") or []
    if notes:
        story += _section(styles, "V. Ghi chú thăm khám lâm sàng")
        for note in reversed(notes):
            story.append(KeepTogether(_clinical_note_block(styles, note)))

    pending = [r for r in (reminders or []) if r.get("status") == "pending"]
    if pending:
        story += _section(styles, "VI. Lịch theo dõi / tái khám")
        data = [[Paragraph("<b>Ngày hẹn</b>", styles.cell),
                 Paragraph("<b>Loại</b>", styles.cell),
                 Paragraph("<b>Nội dung</b>", styles.cell)]]
        for r in pending:
            data.append([
                Paragraph(_fmt_date(r.get("effective_date")), styles.cell),
                Paragraph(_text(r.get("kind_label")), styles.cell),
                Paragraph(_text(r.get("note") or r.get("title")), styles.cell),
            ])
        table = Table(data, colWidths=[30 * mm, 42 * mm, 104 * mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f6")),
            ("GRID", (0, 0), (-1, -1), 0.4, RULE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)

    if patient.get("quick_note"):
        story += _section(styles, "Ghi chú nhanh")
        story.append(Paragraph(_multiline(patient["quick_note"]), styles.justify))
        if patient.get("quick_note_updated_by"):
            story.append(Paragraph(
                f"<i>{_text(patient['quick_note_updated_by'])} · "
                f"{_fmt_datetime(patient.get('quick_note_updated_at'))}</i>", styles.small))

    story.append(Spacer(1, 14))
    story.append(_signature_block(styles, "", "BÁC SĨ ĐIỀU TRỊ", exported_by or ""))

    footer = f"Hồ sơ {patient.get('code')} · {patient.get('name')}"
    if exported_by:
        footer += f" · Xuất bởi {exported_by}"
    return _build(story, f"Ho so benh an - {patient.get('code')}", footer)


def build_visit_record(patient: Dict[str, Any], visit: Dict[str, Any],
                       exported_by: Optional[str] = None) -> bytes:
    """Phiếu khám bệnh của một lần khám, kèm đơn thuốc."""
    styles = _Styles()
    clinic = get_clinic_info()
    story: List[Any] = []

    story += _clinic_header(styles, clinic)
    story.append(Paragraph("PHIẾU KHÁM BỆNH", styles.h1))
    story.append(Paragraph(f"Ngày khám {_fmt_date(visit.get('visit_date'))}", styles.center))
    story.append(Spacer(1, 10))

    story += _section(styles, "Thông tin bệnh nhân")
    story.append(_field_table(styles, _patient_identity_rows(patient),
                              col_widths=[30 * mm, 58 * mm, 30 * mm, 58 * mm]))
    if patient.get("allergies"):
        story.append(_field_table(styles, [[("Dị ứng cần lưu ý", patient["allergies"])]],
                                  col_widths=[38 * mm, 138 * mm]))

    story += _section(styles, "Nội dung khám")
    story += _visit_block(styles, visit)

    story.append(Spacer(1, 10))
    story.append(_signature_block(styles, "", "BÁC SĨ KHÁM BỆNH",
                                  visit.get("doctor_name") or exported_by or ""))

    return _build(story, f"Phieu kham - {patient.get('code')}",
                  f"Phiếu khám · {patient.get('code')} · {patient.get('name')}")


def build_referral(patient: Dict[str, Any], visit: Optional[Dict[str, Any]],
                   referral: Dict[str, Any], exported_by: Optional[str] = None) -> bytes:
    """Giấy chuyển tuyến khám bệnh, chữa bệnh (mẫu hành chính Việt Nam).

    `referral` chứa phần do bác sĩ nhập khi bấm xuất: nơi chuyển đến, lý do
    chuyển, tình trạng người bệnh lúc chuyển, phương tiện vận chuyển, người
    hộ tống.
    """
    styles = _Styles()
    clinic = get_clinic_info()
    visit = visit or {}
    story: List[Any] = []

    story += _clinic_header(styles, clinic, with_national=True)
    story.append(Paragraph("GIẤY CHUYỂN TUYẾN", styles.h1))
    story.append(Paragraph("KHÁM BỆNH, CHỮA BỆNH", styles.center_bold))
    story.append(Spacer(1, 10))

    story.append(Paragraph(
        f"Kính gửi: <b>{_text(referral.get('destination'), '……………………………………………………')}</b>",
        styles.body))
    if referral.get("destination_address"):
        story.append(Paragraph(f"Địa chỉ: {_text(referral['destination_address'])}", styles.body))
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        f"{_text(clinic.get('name'), 'Cơ sở khám bệnh')} trân trọng giới thiệu người bệnh "
        f"đến khám và điều trị tại quý đơn vị:", styles.justify))
    story.append(Spacer(1, 6))

    story.append(_field_table(styles, _patient_identity_rows(patient),
                              col_widths=[30 * mm, 58 * mm, 30 * mm, 58 * mm]))
    if referral.get("insurance_number"):
        story.append(_field_table(styles, [[("Số thẻ BHYT", referral["insurance_number"])]],
                                  col_widths=[38 * mm, 138 * mm]))

    story += _section(styles, "1. Tóm tắt bệnh án")
    summary_rows = [
        [("Dấu hiệu lâm sàng", visit.get("symptoms") or referral.get("clinical_signs"))],
        [("Kết quả cận lâm sàng", visit.get("subclinical_orders") or referral.get("lab_results"))],
        [("Chẩn đoán", visit.get("diagnosis_primary") or referral.get("diagnosis"))],
    ]
    if visit.get("diagnosis_secondary"):
        summary_rows.append([("Bệnh kèm theo", visit["diagnosis_secondary"])])
    if patient.get("chronic_conditions"):
        summary_rows.append([("Bệnh mãn tính", patient["chronic_conditions"])])
    if patient.get("allergies"):
        summary_rows.append([("Tiền sử dị ứng", patient["allergies"])])
    summary_rows.append([("Phương pháp, thuốc đã dùng",
                          visit.get("treatment") or referral.get("treatment_given"))])
    story.append(_field_table(styles, summary_rows, col_widths=[45 * mm, 131 * mm]))

    medications = visit.get("medications") or []
    if medications:
        story.append(Spacer(1, 4))
        story.append(Paragraph("<b>Thuốc đã sử dụng</b>", styles.cell))
        story.append(Spacer(1, 2))
        story.append(_medication_table(styles, medications))

    story += _section(styles, "2. Tình trạng người bệnh lúc chuyển tuyến")
    story.append(Paragraph(_multiline(referral.get("condition_on_transfer"),
                                      "…………………………………………………………………………………………"), styles.justify))

    story += _section(styles, "3. Lý do chuyển tuyến")
    story.append(Paragraph(_multiline(referral.get("reason"),
                                      "…………………………………………………………………………………………"), styles.justify))

    story += _section(styles, "4. Hướng điều trị đề nghị")
    story.append(Paragraph(_multiline(referral.get("recommendation"),
                                      "…………………………………………………………………………………………"), styles.justify))

    story.append(Spacer(1, 6))
    story.append(_field_table(styles, [
        [("Phương tiện vận chuyển", referral.get("transport")),
         ("Người hộ tống", referral.get("escort"))],
    ], col_widths=[38 * mm, 50 * mm, 30 * mm, 58 * mm]))

    story.append(Spacer(1, 12))
    story.append(_signature_block(
        styles, "NGƯỜI ĐƯA NGƯỜI BỆNH", "BÁC SĨ / NGƯỜI CHUYỂN TUYẾN",
        referral.get("doctor_name") or visit.get("doctor_name") or exported_by or ""))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "<i>Ghi chú: Giấy chuyển tuyến có giá trị sử dụng trong thời hạn theo quy định "
        "hiện hành kể từ ngày ký.</i>", styles.small))

    return _build(story, f"Giay chuyen tuyen - {patient.get('code')}",
                  f"Giấy chuyển tuyến · {patient.get('code')} · {patient.get('name')}")
