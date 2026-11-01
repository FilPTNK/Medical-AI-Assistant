import React from 'react';
import { AlertTriangle, CheckCircle2 } from 'lucide-react';
import './NumberCheck.css';

/**
 * Kết quả cổng số liệu (backend/answer_verify.py) dưới câu trả lời.
 *
 * Không xoá hay sửa chữ nào của câu trả lời: chỉ nói thật con số nào đã tìm
 * thấy trong trang được trích, con số nào chưa — để bác sĩ biết chỗ nào phải
 * mở sách đối chiếu trước khi dùng.
 */
const LABEL = {
  unit_mismatch: 'sai đơn vị so với sách',
  ungrounded: 'không thấy trong trang trích dẫn',
  other_source: 'có trong sách, nhưng ở nguồn khác với nguồn được trích',
};

export default function NumberCheck({ verify }) {
  const { checked = 0, flags = [] } = verify || {};
  if (!checked) return null;

  if (flags.length === 0) {
    return (
      <p className="numcheck numcheck-ok">
        <CheckCircle2 size={14} aria-hidden="true" />
        {checked === 1 ? 'Con số liều' : `Cả ${checked} con số liều`} trong câu trả lời đều có trong trang được trích.
      </p>
    );
  }

  // Lỗi đơn vị lên đầu: sai gấp nghìn lần.
  const order = { unit_mismatch: 0, ungrounded: 1, other_source: 2 };
  const sorted = [...flags].sort((a, b) => order[a.status] - order[b.status]);
  const serious = flags.some(f => f.status !== 'other_source');

  return (
    <div className={`numcheck ${serious ? 'numcheck-warn' : 'numcheck-note'}`} role={serious ? 'alert' : 'note'}>
      <p className="numcheck-title">
        <AlertTriangle size={14} aria-hidden="true" />
        Đối chiếu với sách trước khi dùng — {flags.length}/{checked} con số chưa khớp:
      </p>
      <ul>
        {sorted.map((f, i) => (
          <li key={i}>
            <strong>{f.text}</strong> — {LABEL[f.status] || f.status}
            {f.status === 'other_source' && f.found_in?.length > 0 && ` (nguồn [${f.found_in.join('], [')}])`}
          </li>
        ))}
      </ul>
    </div>
  );
}
