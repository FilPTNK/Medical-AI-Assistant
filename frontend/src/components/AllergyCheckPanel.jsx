import React, { useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronRight, HelpCircle, Info, ShieldAlert } from 'lucide-react';
import './AllergyCheckPanel.css';

/**
 * Kết quả đối chiếu dị ứng ↔ thuốc, hiện ngay trên phiếu khám TRƯỚC khi bác sĩ
 * bấm Lưu.
 *
 * BỐN MỨC HIỆN KHÁC HẲN NHAU — ĐÂY LÀ TOÀN BỘ GIÁ TRỊ CỦA KHỐI NÀY
 *
 * Gộp bốn mức thành một chữ "cảnh báo" đỏ là cách chắc chắn nhất để biến lưới
 * an toàn thành tiếng ồn. Đo được trên 101.492 cảnh báo dị ứng (JAMIA Open
 * 2026): chỉ 9,7% là khớp đúng hoạt chất, 90,3% còn lại là khớp nhóm hoặc khớp
 * chéo, và 98,9% tổng số bị bác sĩ bỏ qua. Soi lại bệnh án thì 94-96,5% lần bỏ
 * qua đó là ĐÚNG VỀ LÂM SÀNG (BMJ Qual Saf 2016) — tức lỗi nằm ở chỗ cảnh báo
 * nổ, không nằm ở chỗ bác sĩ lười đọc.
 *
 *   exact  — trùng đúng hoạt chất. Đây là mức duy nhất y văn coi là đủ căn cứ
 *            cho một rào chặn cứng, và kể cả thế thì hiệu quả vẫn chưa được đo.
 *   group  — cùng nhóm dị ứng.
 *   cross  — chéo giữa hai nhóm. Kèm TỈ LỆ và NGUỒN, vì "penicilin nên tránh
 *            mọi cephalosporin" là dạy sai: 16,5% với nhóm chung chuỗi R1 và
 *            2,1% với nhóm còn lại là hai chuyện hoàn toàn khác nhau.
 *   chưa kiểm — ô dị ứng trống, ghi "không rõ", hoặc có chữ mà máy không đọc
 *            ra. Phải hiện, và phải trông KHÁC với "đã kiểm và không thấy gì".
 *
 * KHÔNG DÙNG HỘP THOẠI CHẶN. Rào chặn cứng trong y văn chỉ được đặt cho khớp
 * đúng hoạt chất KÈM phản ứng nặng đã ghi, và kết quả của nó vẫn đang chờ đo.
 * Thêm vào đó, thí nghiệm 2025 (n=281 và n=373) KHÔNG lặp lại được kết quả của
 * Buçinca 2021 về "cognitive forcing function": ba kiểu ma sát chủ ý đều không
 * giảm được thiên lệch. Nên ma sát ở đây chỉ vừa đủ — khối nằm chắn trên đường
 * mắt đi tới nút Lưu, và không tự mở sẵn phần không cần thiết.
 *
 * MÀU KHÔNG BAO GIỜ ĐỨNG MỘT MÌNH. Mỗi mức mang bốn kênh: biểu tượng, chữ
 * nhãn, vạch dày bên trái, và màu. Bỏ màu đi vẫn đọc được thứ bậc.
 */

const TIER = {
  exact: {
    cls: 'exact',
    label: 'TRÙNG HOẠT CHẤT',
    Icon: ShieldAlert,
    sr: 'Mức nghiêm trọng nhất:',
  },
  group: {
    cls: 'group',
    label: 'CÙNG NHÓM',
    Icon: ShieldAlert,
    sr: 'Cùng nhóm dị ứng:',
  },
  cross: {
    cls: 'cross',
    label: 'CHÉO NHÓM',
    Icon: AlertTriangle,
    sr: 'Dị ứng chéo giữa hai nhóm:',
  },
};

export default function AllergyCheckPanel({ check }) {
  const [openPhamVi, setOpenPhamVi] = useState(false);
  const [openDaXet, setOpenDaXet] = useState(false);

  if (!check) return null;

  const { ket_luan: ketLuan, muc_di_ung: muc, ket_qua: ketQua,
          da_xet_khong_cheo: daXet, pham_vi: phamVi, so_thuoc: soThuoc } = check;

  // Phần phạm vi dùng chung cho cả ba trạng thái: công cụ hỗ trợ quyết định
  // lâm sàng phải tự công bố chỗ nó KHÔNG với tới được. Gập sẵn vì đọc một lần
  // là đủ, nhưng luôn có mặt chứ không phải chỉ hiện khi có cảnh báo.
  const phamViBlock = (
    <div className="ac-pv">
      <button
        type="button"
        className="ac-pv-toggle"
        onClick={() => setOpenPhamVi((v) => !v)}
        aria-expanded={openPhamVi}
      >
        {openPhamVi ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <span>Máy kiểm được gì, và không kiểm được gì</span>
      </button>
      {openPhamVi && (
        <div className="ac-pv-body">
          <p className="ac-pv-line">
            <strong>Có số đo dị ứng chéo:</strong> {phamVi.nhom_co_so_lieu.join(' · ')}
          </p>
          <p className="ac-pv-line">
            <strong>Chỉ khớp theo tên, không suy chéo:</strong>{' '}
            {phamVi.nhom_chi_khop_ten.join(' · ')}
          </p>
          <ul className="ac-pv-list">
            {phamVi.gioi_han.map((g, i) => <li key={i}>{g}</li>)}
          </ul>
        </div>
      )}
    </div>
  );

  // ---------------------------------------------------------------- chưa kiểm
  if (ketLuan === 'chua_kiem') {
    const khongDocDuoc = muc.trang_thai === 'khong_doc_duoc';
    return (
      <section className="ac-panel unknown">
        <div className="ac-head">
          <HelpCircle size={16} className="ac-head-icon" aria-hidden="true" />
          <h4 className="ac-head-title">Chưa đối chiếu được dị ứng</h4>
        </div>
        <p className="ac-head-sub">
          {khongDocDuoc ? (
            <>
              Ô dị ứng có ghi <q className="ac-quote">{muc.raw}</q> nhưng máy không nhận
              ra tên thuốc nào trong đó. {soThuoc > 0 && `${soThuoc} thuốc trong phiếu chưa được đối chiếu.`}
            </>
          ) : (
            <>
              Bệnh án chưa ghi tình trạng dị ứng.{' '}
              <strong>Trống không có nghĩa là không dị ứng</strong> — nghĩa là chưa ai hỏi.
              {soThuoc > 0 && ` ${soThuoc} thuốc trong phiếu chưa được đối chiếu.`}
            </>
          )}
        </p>
        {phamViBlock}
      </section>
    );
  }

  // --------------------------------------------------- đã đối chiếu, không khớp
  if (ketLuan === 'khong_thay_khop') {
    return (
      <section className="ac-panel clear">
        <div className="ac-head">
          <Info size={16} className="ac-head-icon" aria-hidden="true" />
          <h4 className="ac-head-title">Không khớp gì trong phần đọc được</h4>
        </div>
        <p className="ac-head-sub">
          {muc.trang_thai === 'trong' ? (
            <>Bệnh án ghi rõ là không có dị ứng.</>
          ) : (
            <>
              Đã đối chiếu {soThuoc} thuốc với <q className="ac-quote">{muc.raw}</q>.
            </>
          )}{' '}
          Đây <strong>không phải</strong> lời bảo đảm là đơn thuốc an toàn — chỉ là
          không có mục nào khớp trong phần chữ máy đọc được.
        </p>
        {phamViBlock}
      </section>
    );
  }

  // ------------------------------------------------------------------- có khớp
  const nangNhat = ketQua.some((k) => k.khop.some((m) => m.tier === 'exact'))
    ? 'exact'
    : ketQua.some((k) => k.khop.some((m) => m.tier === 'group'))
      ? 'group'
      : 'cross';

  return (
    <section className={`ac-panel hit ${nangNhat}`} role="alert">
      <div className="ac-head">
        <ShieldAlert size={16} className="ac-head-icon" aria-hidden="true" />
        <h4 className="ac-head-title">
          Đối chiếu dị ứng — {ketQua.length} / {soThuoc} thuốc cần xem lại
        </h4>
      </div>
      <p className="ac-head-sub">
        Bệnh án ghi: <q className="ac-quote">{muc.raw}</q>
        {muc.nhan_nang && <> · phản ứng đã ghi: <strong>{muc.nhan_nang}</strong></>}
        {!muc.nhan_nang && <> · <span className="ac-dim">chưa ghi phản ứng cụ thể</span></>}
      </p>

      <ul className="ac-hits">
        {ketQua.map((k) => k.khop.map((m, j) => {
          const t = TIER[m.tier] || TIER.cross;
          const { Icon } = t;
          return (
            <li key={`${k.index}-${j}`} className={`ac-hit ${t.cls}`}>
              <span className="ac-hit-tier">
                <Icon size={13} aria-hidden="true" />
                <span className="ac-sr">{t.sr}</span>
                {t.label}
              </span>
              <span className="ac-hit-body">
                <span className="ac-hit-drug">{k.ten}</span>
                <span className="ac-hit-why">{m.vi_sao}</span>
                {m.ty_le && <span className="ac-hit-rate">Mức chéo đo được: {m.ty_le}</span>}
                {m.luu_y && <span className="ac-hit-note">{m.luu_y}</span>}
                {m.nguon && <span className="ac-hit-src">{m.nguon}</span>}
              </span>
            </li>
          );
        }))}
      </ul>

      {/* Nhãn dị ứng trong bệnh án phần lớn KHÔNG phải dị ứng thật, và tránh
          thuốc quá tay gây hại đo được. Câu này đứng ngay dưới danh sách để bác
          sĩ đọc nó cùng lúc với cảnh báo, không phải sau khi đã quyết. */}
      <p className="ac-caveat">
        Đây là <strong>gợi ý xem lại</strong>, không phải chống chỉ định. Hơn 90% người
        mang nhãn dị ứng penicilin dung nạp được khi làm test, và tránh kháng sinh quá
        tay có hại đo được (nguy cơ MRSA cao hơn 1,69 lần). Quyết định là của bác sĩ.
      </p>

      {daXet && daXet.length > 0 && (
        <div className="ac-pv">
          <button
            type="button"
            className="ac-pv-toggle"
            onClick={() => setOpenDaXet((v) => !v)}
            aria-expanded={openDaXet}
          >
            {openDaXet ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
            <span>Đã xét và KHÔNG báo ({daXet.length})</span>
          </button>
          {openDaXet && (
            <div className="ac-pv-body">
              {daXet.map((d, i) => (
                <p key={i} className="ac-pv-line">
                  <strong>{d.allergen}</strong> không dị ứng chéo với {d.nhung_khong_voi}.{' '}
                  <span className="ac-dim">{d.why} — {d.src}</span>
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {phamViBlock}
    </section>
  );
}
