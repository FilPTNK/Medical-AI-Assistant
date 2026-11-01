import React from 'react';
import { CheckCircle2, AlertTriangle, XCircle } from 'lucide-react';
import './CoverageChecklist.css';

/**
 * Bảng kiểm từng điều kiện của câu hỏi, đối chiếu thẳng với sách
 * (backend/query_plan.py).
 *
 *   ✓ Trẻ em — Amoxicilin · Dược thư Q.1 — tr. 206
 *     « câu nguyên văn trong sách »   ← bấm: mở trang, tô đúng câu
 *   ⚠ Suy gan — chỉ nhắc ở mục Thận trọng, sách không ghi riêng ở mục chính
 *   ✗ Suy thận — Thư viện không có thông tin cho thuốc này
 *
 * Câu trích được chép từ chữ của sách, KHÔNG qua mô hình AI — đây là chỗ bác
 * sĩ đọc con số liều. Chữ là bản OCR nên có thể lỗi chính tả; bấm vào để đối
 * chiếu với ảnh trang.
 */
export default function CoverageChecklist({ items, sources, onOpen, citationOf }) {
  if (!items?.length) return null;

  return (
    <div className="coverage" aria-label="Đối chiếu từng điều kiện với sách">
      <p className="coverage-title">Đối chiếu với sách</p>
      <ul className="coverage-list">
        {items.map((it, i) => {
          const src = it.source_index != null ? sources?.[it.source_index] : null;
          const partial = it.found && it.in_preferred_section === false;
          const state = !it.found ? 'missing' : partial ? 'partial' : 'found';
          const Icon = state === 'found' ? CheckCircle2 : state === 'partial' ? AlertTriangle : XCircle;
          return (
            <li key={`${it.condition}-${it.drug}-${i}`} className={`coverage-item is-${state}`}>
              <div className="coverage-head">
                <Icon size={16} aria-hidden="true" className="coverage-icon" />
                <span className="coverage-label">{it.label}</span>
                <span className="coverage-drug">— {it.drug}</span>
                {src && (
                  <button type="button" className="coverage-cite" onClick={() => onOpen(src, it.source_index)}>
                    {citationOf(src)}
                  </button>
                )}
              </div>
              {state === 'missing' && (
                <p className="coverage-note">Thư viện không có thông tin về điều kiện này cho thuốc này.</p>
              )}
              {state === 'partial' && (
                <p className="coverage-note">
                  Sách không ghi riêng ở mục chính; chỉ nhắc ở mục “{it.section}”.
                </p>
              )}
              {it.found && src && (it.quotes || []).map((q, qi) => (
                <button
                  key={qi}
                  type="button"
                  className="coverage-quote"
                  onClick={() => onOpen({ ...src, quote: q }, it.source_index)}
                  title="Mở trang sách và tô đúng câu này"
                >
                  {q}
                </button>
              ))}
            </li>
          );
        })}
      </ul>
      {items.some(it => it.quotes?.length) && (
        <p className="coverage-foot">Câu trích chép nguyên văn từ bản quét của sách — bấm để xem trên trang.</p>
      )}
    </div>
  );
}
