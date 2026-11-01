import React from 'react';
import { X } from 'lucide-react';
import './AttachmentCard.css';

/**
 * Thẻ tệp đính kèm theo kiểu ChatGPT: ô màu hồng có biểu tượng tài liệu, tên
 * tệp một dòng, dòng phụ "PDF". Số đo lấy theo LibreChat FileContainer (bản
 * sao gần nhất của ChatGPT) — xem reports/Thiết kế giao diện chat kiểu ChatGPT.md.
 *
 * onRemove có  → thẻ trong ô nhập, có nút ✕.
 * onRemove không có → thẻ trong tin nhắn đã gửi, bấm để mở trang.
 */
export default function AttachmentCard({ title, subtitle = 'PDF', onOpen, onRemove }) {
  return (
    <div className="att-card">
      <button type="button" className="att-card-surface" onClick={onOpen} title={title}>
        <span className="att-card-tile" aria-hidden="true">
          <svg viewBox="0 0 36 36" width="40" height="40" fill="none">
            <rect width="36" height="36" rx="6" fill="currentColor" />
            <path
              d="M19.6663 9.66663H12.9997C12.5576 9.66663 12.1337 9.84222 11.8212 10.1548C11.5086 10.4673 11.333 10.8913 11.333 11.3333V24.6666C11.333 25.1087 11.5086 25.5326 11.8212 25.8451C12.1337 26.1577 12.5576 26.3333 12.9997 26.3333H22.9997C23.4417 26.3333 23.8656 26.1577 24.1782 25.8451C24.4907 25.5326 24.6663 25.1087 24.6663 24.6666V14.6666L19.6663 9.66663Z M19.667 9.66663V14.6666H24.667 M21.3337 18.8334H14.667 M21.3337 22.1666H14.667 M16.3337 15.5H14.667"
              stroke="white"
              strokeWidth="1.66667"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        <span className="att-card-text">
          <span className="att-card-name">{title}</span>
          <span className="att-card-sub">{subtitle}</span>
        </span>
      </button>
      {onRemove && (
        <button
          type="button"
          className="att-card-remove"
          onClick={onRemove}
          aria-label={`Bỏ đính kèm ${title}`}
          title="Bỏ đính kèm"
        >
          <X size={14} strokeWidth={2.25} aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
