import React, { useEffect, useState } from 'react';
import { AlertTriangle, BookOpen, Calculator, ChevronDown, ChevronRight, Loader2, X } from 'lucide-react';
import { tinhLieu, dienVaoDon, tuLieuSach } from '../lib/doseCalc';
import './DoseCalculator.css';

/**
 * Máy tính liều theo cân nặng, mở ngay trong ô "Thêm thuốc" của phiếu khám.
 *
 * Hai nửa tách bạch:
 *   - Ô nhập + kết quả: phép tính tất định (lib/doseCalc.js). Bác sĩ thấy và
 *     sửa được MỌI ô, kể cả khi điền sẵn từ sách.
 *   - Câu liều mg/kg trong Dược thư: chỉ để đọc và bấm "Dùng liều này". Máy
 *     không bao giờ tự chọn câu nào — chọn nhóm tuổi/chỉ định/đường dùng là việc
 *     của bác sĩ (xem backend/pediatric_dose.py).
 */

const EMPTY = { mgPerKg: '', basis: 'lieu', dosesPerDay: '', maxDoseMg: '', maxDayMg: '', maxMgKgDay: '', concMg: '', concMl: '' };

const vn = (x) => String(x).replace('.', ',');

function moTaLieu(l) {
  const lieu = l.mg_kg_min === l.mg_kg_max ? vn(l.mg_kg_min) : `${vn(l.mg_kg_min)}–${vn(l.mg_kg_max)}`;
  const parts = [`${lieu} mg/kg/${l.theo === 'ngay' ? 'ngày' : 'liều'}`];
  if (l.mot_lieu) parts.push('liều duy nhất');
  else if (l.so_lan_ngay) {
    const [a, b] = l.so_lan_ngay;
    parts.push(a === b ? `${vn(a)} lần/ngày` : `${vn(a)}–${vn(b)} lần/ngày`);
  }
  if (l.toi_da_mg_lieu) parts.push(`tối đa ${vn(l.toi_da_mg_lieu)} mg/liều`);
  if (l.toi_da_mg_ngay) parts.push(`tối đa ${vn(l.toi_da_mg_ngay)} mg/ngày`);
  if (l.toi_da_mg_kg_ngay) parts.push(`tối đa ${vn(l.toi_da_mg_kg_ngay)} mg/kg/ngày`);
  return parts.join(' · ');
}

export default function DoseCalculator({ drugName, defaultWeightKg, onApply, onClose }) {
  const [weightKg, setWeightKg] = useState(defaultWeightKg ? String(defaultWeightKg) : '');
  const [form, setForm] = useState(EMPTY);
  const [showMax, setShowMax] = useState(false);
  const [ref, setRef] = useState(null);
  const [refLoading, setRefLoading] = useState(false);
  const [showAllRef, setShowAllRef] = useState(false);
  const [pickedRef, setPickedRef] = useState(null);

  const name = (drugName || '').trim();
  useEffect(() => {
    if (name.length < 2) { setRef(null); return undefined; }
    let cancelled = false;
    setRefLoading(true);
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/drugs/pediatric-dosing?name=${encodeURIComponent(name)}`);
        const data = res.ok ? await res.json() : null;
        if (!cancelled) setRef(data);
      } catch {
        if (!cancelled) setRef(null);
      } finally {
        if (!cancelled) setRefLoading(false);
      }
    }, 400);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [name]);

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }));
  const params = { ...form, weightKg };
  const touched = form.mgPerKg !== "" || !weightKg;
  const kq = tinhLieu(params);

  const applyRef = (lieu, key) => {
    const v = tuLieuSach(lieu);
    setForm(f => ({ ...f, ...Object.fromEntries(Object.entries(v).map(([k, x]) => [k, x === '' ? '' : String(x)])) }));
    setPickedRef(key);
    if (v.maxDoseMg || v.maxDayMg || v.maxMgKgDay) setShowMax(true);
  };

  const cau = ref?.cau || [];
  const shown = showAllRef ? cau : cau.slice(0, 4);

  return (
    <section className="dc-panel" aria-label="Tính liều theo cân nặng">
      <div className="dc-head">
        <Calculator size={15} aria-hidden="true" />
        <h5>Tính liều theo cân nặng{name ? ` — ${name}` : ''}</h5>
        <button type="button" className="dc-close" onClick={onClose} title="Đóng máy tính liều"><X size={14} /></button>
      </div>

      <div className="dc-grid">
        <label className="dc-field">
          <span>Cân nặng (kg)</span>
          <input type="text" inputMode="decimal" value={weightKg} onChange={e => setWeightKg(e.target.value)} placeholder="vd. 12,5" />
        </label>
        <label className="dc-field">
          <span>Liều (mg/kg)</span>
          <input type="text" inputMode="decimal" value={form.mgPerKg} onChange={set('mgPerKg')} placeholder="vd. 15" />
        </label>
        <label className="dc-field">
          <span>Tính cho</span>
          <select value={form.basis} onChange={set('basis')}>
            <option value="lieu">mỗi liều</option>
            <option value="ngay">cả ngày (chia đều)</option>
          </select>
        </label>
        <label className="dc-field">
          <span>Số lần/ngày</span>
          <input type="text" inputMode="decimal" value={form.dosesPerDay} onChange={set('dosesPerDay')} placeholder="vd. 4" />
        </label>
        <label className="dc-field">
          <span>Dạng lỏng: mg</span>
          <input type="text" inputMode="decimal" value={form.concMg} onChange={set('concMg')} placeholder="vd. 250" />
        </label>
        <label className="dc-field">
          <span>trong mL</span>
          <input type="text" inputMode="decimal" value={form.concMl} onChange={set('concMl')} placeholder="vd. 5" />
        </label>
      </div>

      <button type="button" className="dc-toggle" onClick={() => setShowMax(v => !v)} aria-expanded={showMax}>
        {showMax ? <ChevronDown size={13} /> : <ChevronRight size={13} />} Mức tối đa (để máy cảnh báo khi vượt)
      </button>
      {showMax && (
        <div className="dc-grid">
          <label className="dc-field"><span>Tối đa mg/liều</span>
            <input type="text" inputMode="decimal" value={form.maxDoseMg} onChange={set('maxDoseMg')} /></label>
          <label className="dc-field"><span>Tối đa mg/ngày</span>
            <input type="text" inputMode="decimal" value={form.maxDayMg} onChange={set('maxDayMg')} /></label>
          <label className="dc-field"><span>Tối đa mg/kg/ngày</span>
            <input type="text" inputMode="decimal" value={form.maxMgKgDay} onChange={set('maxMgKgDay')} /></label>
        </div>
      )}

      <div className="dc-result" role="status" aria-live="polite">
        {kq.ok ? (
          <>
            <p className="dc-result-main">
              Mỗi liều <strong>{vn(kq.doseMg)} mg</strong>
              {kq.doseMl !== null && <> = <strong>{vn(kq.doseMl)} mL</strong></>}
              {kq.dayMg !== null && <> · tổng ngày <strong>{vn(kq.dayMg)} mg</strong></>}
            </p>
            {kq.warnings.map((w, i) => (
              <p key={i} className="dc-warn"><AlertTriangle size={13} aria-hidden="true" /> {w}</p>
            ))}
          </>
        ) : (
          touched && <p className="dc-muted">{kq.errors.join(' ')}</p>
        )}
      </div>

      <div className="dc-actions">
        <button type="button" className="pp-btn-add pp-btn-sm" disabled={!kq.ok}
                onClick={() => onApply(dienVaoDon(kq, params))}>
          Điền vào đơn
        </button>
      </div>

      <div className="dc-ref">
        <p className="dc-ref-title"><BookOpen size={13} aria-hidden="true" /> Liều theo cân nặng trong Dược thư</p>
        {refLoading && <p className="dc-muted"><Loader2 size={12} className="animate-spin" /> Đang tra…</p>}
        {!refLoading && ref && !ref.nhan_ra && (
          <p className="dc-muted">Không nhận ra hoạt chất "{name}" trong Dược thư — nhập liều mg/kg tay.</p>
        )}
        {!refLoading && ref?.nhan_ra && cau.length === 0 && (
          <p className="dc-muted">Chuyên luận {ref.hoat_chat} không có câu liều theo mg/kg đọc được.</p>
        )}
        {shown.map((c, i) => (
          <div key={i} className="dc-ref-item">
            <p className="dc-ref-quote">
              {c.tre_em && <span className="dc-chip">Trẻ em</span>}
              <q>{c.cau}</q>
            </p>
            <p className="dc-ref-src">{c.citation}</p>
            <div className="dc-ref-doses">
              {c.lieu.map((l, j) => {
                const key = `${i}-${j}`;
                return (
                  <button key={j} type="button"
                          className={`dc-ref-use ${pickedRef === key ? 'active' : ''}`}
                          aria-pressed={pickedRef === key}
                          onClick={() => applyRef(l, key)}>
                    Dùng: {moTaLieu(l)}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
        {cau.length > 4 && (
          <button type="button" className="dc-toggle" onClick={() => setShowAllRef(v => !v)}>
            {showAllRef ? 'Thu gọn' : `Xem thêm ${cau.length - 4} câu`}
          </button>
        )}
        <p className="dc-muted dc-caveat">
          Máy chỉ đọc con số trong câu, không biết câu đó dành cho nhóm tuổi, chỉ định hay đường dùng nào —
          đọc nguyên câu trước khi bấm "Dùng". Khoảng liều được điền ở đầu dưới.
        </p>
      </div>
    </section>
  );
}
