import React, { useEffect, useMemo, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import {
  X, FileText, Stethoscope, Send, Loader2, AlertCircle, Download, ChevronRight,
} from 'lucide-react';
import { apiDownload } from '../lib/apiClient';
import './ExportPdfDialog.css';

/**
 * Xuất hồ sơ bệnh nhân ra PDF: bệnh án tổng hợp, phiếu khám một lần khám, hoặc
 * giấy chuyển tuyến.
 *
 * Giấy chuyển tuyến cần vài thông tin không nằm sẵn trong hồ sơ (nơi chuyển đến,
 * lý do chuyển, tình trạng lúc chuyển) nên bước này có một biểu mẫu ngắn; phần
 * tóm tắt bệnh án được lấy tự động từ lần khám đã chọn.
 */

const DOC_TYPES = [
  {
    id: 'full',
    icon: FileText,
    title: 'Bệnh án tổng hợp',
    description: 'Hành chính, tiền sử, toàn bộ lần khám, đơn thuốc và lịch theo dõi. Dùng để lưu hồ sơ giấy.',
  },
  {
    id: 'visit',
    icon: Stethoscope,
    title: 'Phiếu khám bệnh',
    description: 'Một lần khám kèm đơn thuốc, có chỗ ký tên bác sĩ. Đưa cho bệnh nhân mang về.',
  },
  {
    id: 'referral',
    icon: Send,
    title: 'Giấy chuyển tuyến',
    description: 'Mẫu hành chính có quốc hiệu và phần ký đóng dấu, để gửi bệnh nhân lên tuyến trên.',
  },
];

const formatDate = (iso) => {
  if (!iso) return '--';
  const d = new Date(`${String(iso).slice(0, 10)}T00:00:00`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('vi-VN');
};

export default function ExportPdfDialog({ open, onOpenChange, patient }) {
  const [docType, setDocType] = useState('full');
  const [visitId, setVisitId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState('');
  const [referral, setReferral] = useState({
    destination: '', destination_address: '', reason: '',
    condition_on_transfer: '', recommendation: '', transport: '', escort: '',
    insurance_number: '',
  });

  const visits = useMemo(() => patient?.visits || [], [patient]);

  useEffect(() => {
    if (open) {
      setDocType('full');
      setVisitId(visits[0]?.id || '');
      setError('');
      setDone('');
      setReferral({
        destination: '', destination_address: '', reason: '',
        condition_on_transfer: '', recommendation: '', transport: '', escort: '',
        insurance_number: '',
      });
    }
  }, [open, visits]);

  const needsVisit = docType === 'visit' || docType === 'referral';

  const submit = async () => {
    if (docType === 'visit' && !visits.length) {
      setError('Bệnh nhân chưa có lần khám nào để xuất phiếu.');
      return;
    }
    if (docType === 'referral' && !referral.destination.trim()) {
      setError('Hãy nhập nơi chuyển bệnh nhân đến.');
      return;
    }

    setBusy(true);
    setError('');
    setDone('');
    try {
      let filename;
      if (docType === 'referral') {
        filename = await apiDownload(`/api/patients/${patient.id}/export/referral`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ...referral, visit_id: visitId || null }),
        });
      } else {
        const params = new URLSearchParams({ doc_type: docType });
        if (docType === 'visit' && visitId) params.set('visit_id', visitId);
        filename = await apiDownload(`/api/patients/${patient.id}/export/pdf?${params.toString()}`);
      }
      setDone(filename);
    } catch (err) {
      setError(err.message || 'Không tạo được tệp PDF.');
    } finally {
      setBusy(false);
    }
  };

  if (!patient) return null;

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="ex-overlay" />
        <Dialog.Content className="ex-dialog" aria-describedby={undefined}>
          <Dialog.Title asChild><h3>Xuất hồ sơ ra PDF</h3></Dialog.Title>
          <p className="ex-sub">
            {patient.name} · {patient.code}
            {patient.age != null ? ` · ${patient.age} tuổi` : ''}
          </p>

          <div className="ex-types">
            {DOC_TYPES.map((type) => (
              <button
                key={type.id}
                type="button"
                className={`ex-type ${docType === type.id ? 'active' : ''}`}
                onClick={() => { setDocType(type.id); setDone(''); setError(''); }}
              >
                <span className="ex-type-icon"><type.icon size={17} /></span>
                <span className="ex-type-text">
                  <strong>{type.title}</strong>
                  <small>{type.description}</small>
                </span>
              </button>
            ))}
          </div>

          {needsVisit && (
            <div className="ex-field">
              <label htmlFor="ex-visit">
                {docType === 'referral' ? 'Lấy tóm tắt bệnh án từ lần khám' : 'Lần khám cần in'}
              </label>
              {visits.length === 0 ? (
                <div className="ex-note-empty">Bệnh nhân chưa có lần khám nào được ghi nhận.</div>
              ) : (
                <select id="ex-visit" value={visitId} onChange={(e) => setVisitId(e.target.value)}>
                  {visits.map((v) => (
                    <option key={v.id} value={v.id}>
                      {formatDate(v.visit_date)} — {v.diagnosis_primary || v.title || 'Khám bệnh'}
                    </option>
                  ))}
                </select>
              )}
            </div>
          )}

          {docType === 'referral' && (
            <div className="ex-referral">
              <div className="ex-field">
                <label htmlFor="ex-dest">Chuyển đến <span className="ex-required">*</span></label>
                <input
                  id="ex-dest" type="text" value={referral.destination}
                  onChange={(e) => setReferral((r) => ({ ...r, destination: e.target.value }))}
                  placeholder="Bệnh viện Đa khoa tỉnh — Khoa Nội"
                />
              </div>

              <div className="ex-field-row">
                <div className="ex-field">
                  <label htmlFor="ex-dest-addr">Địa chỉ nơi đến</label>
                  <input
                    id="ex-dest-addr" type="text" value={referral.destination_address}
                    onChange={(e) => setReferral((r) => ({ ...r, destination_address: e.target.value }))}
                    placeholder="Không bắt buộc"
                  />
                </div>
                <div className="ex-field">
                  <label htmlFor="ex-bhyt">Số thẻ BHYT</label>
                  <input
                    id="ex-bhyt" type="text" value={referral.insurance_number}
                    onChange={(e) => setReferral((r) => ({ ...r, insurance_number: e.target.value }))}
                    placeholder="Không bắt buộc"
                  />
                </div>
              </div>

              <div className="ex-field">
                <label htmlFor="ex-reason">Lý do chuyển tuyến</label>
                <textarea
                  id="ex-reason" rows={2} value={referral.reason}
                  onChange={(e) => setReferral((r) => ({ ...r, reason: e.target.value }))}
                  placeholder="Vượt quá khả năng chuyên môn kỹ thuật của tuyến dưới…"
                />
              </div>

              <div className="ex-field">
                <label htmlFor="ex-condition">Tình trạng người bệnh lúc chuyển</label>
                <textarea
                  id="ex-condition" rows={2} value={referral.condition_on_transfer}
                  onChange={(e) => setReferral((r) => ({ ...r, condition_on_transfer: e.target.value }))}
                  placeholder="Tỉnh, tiếp xúc tốt, mạch 88 l/p, HA 150/95 mmHg…"
                />
              </div>

              <div className="ex-field">
                <label htmlFor="ex-recommend">Hướng điều trị đề nghị</label>
                <textarea
                  id="ex-recommend" rows={2} value={referral.recommendation}
                  onChange={(e) => setReferral((r) => ({ ...r, recommendation: e.target.value }))}
                  placeholder="Không bắt buộc"
                />
              </div>

              <div className="ex-field-row">
                <div className="ex-field">
                  <label htmlFor="ex-transport">Phương tiện vận chuyển</label>
                  <input
                    id="ex-transport" type="text" value={referral.transport}
                    onChange={(e) => setReferral((r) => ({ ...r, transport: e.target.value }))}
                    placeholder="Xe cứu thương"
                  />
                </div>
                <div className="ex-field">
                  <label htmlFor="ex-escort">Người hộ tống</label>
                  <input
                    id="ex-escort" type="text" value={referral.escort}
                    onChange={(e) => setReferral((r) => ({ ...r, escort: e.target.value }))}
                    placeholder="Điều dưỡng…"
                  />
                </div>
              </div>

              <p className="ex-hint">
                Ô để trống sẽ in thành dòng chấm để điền tay. Tên phòng khám in ở đầu giấy
                lấy từ <strong>Cài đặt → Phòng khám</strong>.
              </p>
            </div>
          )}

          {error && <div className="ex-error"><AlertCircle size={14} /> {error}</div>}
          {done && (
            <div className="ex-done">
              <Download size={14} /> Đã tải xuống <strong>{done}</strong>
            </div>
          )}

          <div className="ex-actions">
            <Dialog.Close asChild>
              <button type="button" className="ex-btn" disabled={busy}>Đóng</button>
            </Dialog.Close>
            <button type="button" className="ex-btn ex-btn-primary" onClick={submit} disabled={busy}>
              {busy
                ? <><Loader2 size={14} className="ex-spin" /> Đang tạo tệp…</>
                : <><Download size={14} /> Tạo và tải PDF</>}
            </button>
          </div>

          <Dialog.Close asChild>
            <button type="button" className="ex-close" aria-label="Đóng"><X size={16} /></button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
