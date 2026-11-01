import React, { useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronRight, HelpCircle, Info, ShieldAlert } from 'lucide-react';
import './AllergyCheckPanel.css';

/**
 * Tương tác thuốc–thuốc trong đơn, đọc từ mục "Tương tác thuốc" của Dược thư
 * (backend/drug_interaction.py). Đứng ngay dưới khối dị ứng, cùng bộ kiểu
 * dáng, cùng nguyên tắc:
 *
 * - Mỗi mức mang bốn kênh: biểu tượng, chữ nhãn, vạch dày bên trái, màu.
 * - Không hộp thoại chặn: chỉ chắn tầm mắt trên đường tới nút Lưu.
 * - Không bao giờ nói "an toàn". Không thấy gì = sách không nhắc cặp nào.
 * - Mỗi cảnh báo kèm NGUYÊN CÂU trong sách và số trang. Mức độ đọc từ chính câu
 *   đó, nên bác sĩ phải thấy câu để tự cân — "Thận trọng" của một câu nói về
 *   xuất huyết khác hẳn một câu nói về giảm hấp thu.
 */

// Ánh xạ sang lớp màu sẵn có của khối dị ứng: đỏ / cam / trung tính.
const MUC = {
  chong_chi_dinh: { cls: 'exact', label: 'CHỐNG CHỈ ĐỊNH', Icon: ShieldAlert },
  tranh: { cls: 'group', label: 'TRÁNH PHỐI HỢP', Icon: ShieldAlert },
  than_trong: { cls: 'cross', label: 'THẬN TRỌNG', Icon: AlertTriangle },
  co_nhac: { cls: 'mention', label: 'CÓ NHẮC TỚI', Icon: Info },
  khong_tuong_tac: { cls: 'mention', label: 'SÁCH GHI KHÔNG TƯƠNG TÁC', Icon: Info },
};

export default function InteractionCheckPanel({ check, loading }) {
  const [openPhamVi, setOpenPhamVi] = useState(false);
  const [openCap, setOpenCap] = useState({});

  if (!check) {
    return loading ? (
      <section className="ac-panel clear" aria-busy="true">
        <p className="ac-head-sub">Đang đối chiếu tương tác thuốc…</p>
      </section>
    ) : null;
  }

  const { ket_luan: ketLuan, cap, nhan_ra: nhanRa, khong_nhan_ra: khongNhanRa, pham_vi: phamVi } = check;

  const phamViBlock = (
    <div className="ac-pv">
      <button type="button" className="ac-pv-toggle" onClick={() => setOpenPhamVi(v => !v)} aria-expanded={openPhamVi}>
        {openPhamVi ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <span>Máy kiểm được gì, và không kiểm được gì</span>
      </button>
      {openPhamVi && (
        <div className="ac-pv-body">
          <p className="ac-pv-line"><strong>Nguồn:</strong> {phamVi.nguon}</p>
          <ul className="ac-pv-list">
            {phamVi.gioi_han.map((g, i) => <li key={i}>{g}</li>)}
          </ul>
        </div>
      )}
    </div>
  );

  // Thuốc không nhận ra phải nói thành tiếng ở MỌI trạng thái: im lặng ở đây
  // là để bác sĩ tưởng thuốc đó đã được kiểm.
  const chuaKiem = khongNhanRa.length > 0 && (
    <p className="ac-head-sub">
      <strong>Chưa kiểm:</strong> {khongNhanRa.map(k => k.ten).join(', ')} — không nhận ra
      hoạt chất trong Dược thư (tên biệt dược hoặc thuốc phối hợp). Ghi kèm tên hoạt chất để máy đối chiếu được.
    </p>
  );

  if (ketLuan === 'chua_kiem') {
    return (
      <section className="ac-panel unknown">
        <div className="ac-head">
          <HelpCircle size={16} className="ac-head-icon" aria-hidden="true" />
          <h4 className="ac-head-title">Chưa đối chiếu được tương tác thuốc</h4>
        </div>
        <p className="ac-head-sub">Cần ít nhất hai thuốc nhận ra được hoạt chất để đối chiếu.</p>
        {chuaKiem}
        {phamViBlock}
      </section>
    );
  }

  const canhBao = cap.filter(c => c.muc !== 'khong_tuong_tac');
  if (ketLuan === 'khong_thay') {
    return (
      <section className="ac-panel clear">
        <div className="ac-head">
          <Info size={16} className="ac-head-icon" aria-hidden="true" />
          <h4 className="ac-head-title">Dược thư không nhắc tương tác nào giữa {nhanRa.length} thuốc này</h4>
        </div>
        <p className="ac-head-sub">
          Đây <strong>không phải</strong> lời bảo đảm là phối hợp an toàn — sách không liệt kê
          mọi tương tác, và máy chỉ đọc được phần chữ OCR.
        </p>
        {chuaKiem}
        {phamViBlock}
      </section>
    );
  }

  const nangNhat = MUC[canhBao[0].muc]?.cls || 'cross';

  return (
    <section className={`ac-panel hit ${nangNhat === 'mention' ? 'cross' : nangNhat}`} role="alert">
      <div className="ac-head">
        <ShieldAlert size={16} className="ac-head-icon" aria-hidden="true" />
        <h4 className="ac-head-title">Tương tác thuốc — {canhBao.length} cặp cần xem lại</h4>
      </div>
      {chuaKiem}

      <ul className="ac-hits">
        {cap.map((c, i) => {
          const m = MUC[c.muc] || MUC.co_nhac;
          const { Icon } = m;
          const open = !!openCap[i];
          const [dau, ...con] = c.bang_chung;
          return (
            <li key={`${c.a.index}-${c.b.index}`} className={`ac-hit ${m.cls}`}>
              <span className="ac-hit-tier">
                <Icon size={13} aria-hidden="true" />
                {m.label}
              </span>
              <span className="ac-hit-body">
                <span className="ac-hit-drug">{c.a.ten} × {c.b.ten}</span>
                <span className="ac-hit-why">
                  <q className="ac-quote">{dau.cau}</q>
                </span>
                <span className="ac-hit-src">
                  {dau.citation} · chuyên luận {dau.trong_chuyen_luan}
                  {dau.kieu === 'nhom' && ` · sách nhắc theo nhóm "${dau.khop}"`}
                </span>
                {con.length > 0 && (
                  <button type="button" className="ac-pv-toggle"
                          onClick={() => setOpenCap(s => ({ ...s, [i]: !open }))} aria-expanded={open}>
                    {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                    <span>{con.length} câu khác trong sách</span>
                  </button>
                )}
                {open && con.map((b, j) => (
                  <span key={j} className="ac-hit-note">
                    <q className="ac-quote">{b.cau}</q> — {b.citation}
                  </span>
                ))}
              </span>
            </li>
          );
        })}
      </ul>

      <p className="ac-caveat">
        Mức độ đọc từ chữ trong câu của sách, không phải phân hạng của một cơ sở dữ liệu
        tương tác chuẩn. Đọc câu trích để tự cân; quyết định là của bác sĩ.
      </p>
      {phamViBlock}
    </section>
  );
}
