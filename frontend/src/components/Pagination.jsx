import React, { useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import './Pagination.css';

/**
 * Các số trang cần hiện: trang đầu, trang cuối, và hai trang quanh trang hiện
 * tại; chỗ bị lược đi là "…". Ví dụ (12 / 948): 1 … 11 12 13 … 948.
 */
export function pageItems(current, total) {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const pages = new Set([1, total, current - 1, current, current + 1]);
  if (current <= 3) [2, 3, 4].forEach((p) => pages.add(p));
  if (current >= total - 2) [total - 3, total - 2, total - 1].forEach((p) => pages.add(p));
  const sorted = [...pages].filter((p) => p >= 1 && p <= total).sort((a, b) => a - b);
  const items = [];
  sorted.forEach((p, i) => {
    if (i > 0 && p - sorted[i - 1] > 1) items.push('gap-' + p);
    items.push(p);
  });
  return items;
}

export default function Pagination({ current, total, onChange }) {
  const [typed, setTyped] = useState(String(current));
  useEffect(() => setTyped(String(current)), [current]);

  const go = (p) => {
    const n = Math.min(Math.max(1, p), total);
    if (n !== current) onChange(n);
    else setTyped(String(current));
  };

  const submit = (e) => {
    e.preventDefault();
    const n = parseInt(typed, 10);
    if (Number.isFinite(n)) go(n);
    else setTyped(String(current));
  };

  return (
    <nav className="pager" aria-label="Chọn trang">
      <button type="button" className="pager-btn pager-step" onClick={() => go(current - 1)} disabled={current <= 1}>
        <ChevronLeft size={18} aria-hidden="true" /> Trước
      </button>
      {pageItems(current, total).map((item) =>
        typeof item === 'string' ? (
          <span key={item} className="pager-gap" aria-hidden="true">…</span>
        ) : (
          <button
            key={item}
            type="button"
            className={`pager-btn${item === current ? ' active' : ''}`}
            onClick={() => go(item)}
            aria-current={item === current ? 'page' : undefined}
            aria-label={`Trang ${item}`}
          >
            {item}
          </button>
        )
      )}
      <button type="button" className="pager-btn pager-step" onClick={() => go(current + 1)} disabled={current >= total}>
        Sau <ChevronRight size={18} aria-hidden="true" />
      </button>
      <form className="pager-jump" onSubmit={submit}>
        <label htmlFor="pager-input" className="sr-only">Nhập số trang</label>
        <input
          id="pager-input"
          type="number"
          inputMode="numeric"
          min={1}
          max={total}
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          onFocus={(e) => e.target.select()}
        />
        <span className="pager-total">/ {total}</span>
        <button type="submit" className="pager-go">Đến trang</button>
      </form>
    </nav>
  );
}
