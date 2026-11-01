import React, { useEffect, useRef, useState } from 'react';
import { Loader2, LocateFixed, ZoomIn, ZoomOut } from 'lucide-react';
import AuthedImage from './AuthedImage';
import './PageViewer.css';

/**
 * Ảnh trang sách gốc, có tô sáng đúng đoạn được trích dẫn.
 *
 * Toạ độ tô sáng do backend tính (POST /pages/{n}/locate — xem
 * backend/page_locate.py), chuẩn hoá 0–1 theo khổ trang, nên vẽ được bằng phần
 * trăm lên ảnh ở bất kỳ mức phóng nào.
 *
 * Không tìm được vị trí thì NÓI THẬT và vẫn hiện đúng trang — tô nhầm chỗ còn
 * tệ hơn không tô.
 */
const ZOOMS = [1, 1.35, 1.75, 2.25];

export default function PageViewer({ docName, pageNum, quote, alt }) {
  const [locate, setLocate] = useState({ status: quote ? 'loading' : 'none', rects: [] });
  const [zoomIdx, setZoomIdx] = useState(0);
  const firstRectRef = useRef(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (!quote) {
      setLocate({ status: 'none', rects: [] });
      return undefined;
    }
    let cancelled = false;
    setLocate({ status: 'loading', rects: [] });
    fetch(`/api/documents/${encodeURIComponent(docName)}/pages/${pageNum}/locate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ quote }),
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (cancelled) return;
        const rects = data?.rects || [];
        setLocate({ status: rects.length ? 'found' : 'notfound', rects });
      })
      .catch(() => { if (!cancelled) setLocate({ status: 'notfound', rects: [] }); });
    return () => { cancelled = true; };
  }, [docName, pageNum, quote]);

  // Cuộn RIÊNG khung ảnh trang. scrollIntoView sẽ cuộn cả các khung cha (kể cả
  // khung overflow:hidden) và đẩy lệch cả bố cục app.
  const scrollToQuote = () => {
    const box = scrollRef.current;
    const mark = firstRectRef.current;
    if (!box || !mark) return;
    const boxRect = box.getBoundingClientRect();
    const markRect = mark.getBoundingClientRect();
    box.scrollTo({
      top: box.scrollTop + (markRect.top - boxRect.top) - boxRect.height / 3,
      left: box.scrollLeft + (markRect.left - boxRect.left) - 24,
      behavior: 'smooth',
    });
  };

  // Tô xong thì tự cuộn tới đoạn trích — bác sĩ không phải tự dò.
  useEffect(() => {
    if (locate.status === 'found') {
      const t = setTimeout(scrollToQuote, 150);
      return () => clearTimeout(t);
    }
    return undefined;
  }, [locate.status, zoomIdx]);

  const zoom = ZOOMS[zoomIdx];

  return (
    <div className="page-viewer">
      <div className="page-viewer-toolbar">
        <div className="page-viewer-status" role="status">
          {locate.status === 'loading' && (
            <><Loader2 size={16} className="animate-spin" /> Đang tìm đoạn trích dẫn trên trang…</>
          )}
          {locate.status === 'found' && (
            <><span className="page-viewer-swatch" aria-hidden="true" /> Đoạn trích dẫn được tô vàng</>
          )}
          {locate.status === 'notfound' && 'Không tìm thấy vị trí chính xác — đoạn trích dẫn hiển thị bên dưới.'}
        </div>
        <div className="page-viewer-actions">
          {locate.status === 'found' && (
            <button type="button" className="pv-btn" onClick={scrollToQuote}>
              <LocateFixed size={18} aria-hidden="true" /> Về đoạn trích dẫn
            </button>
          )}
          <button
            type="button"
            className="pv-btn pv-btn-icon"
            onClick={() => setZoomIdx((i) => Math.max(0, i - 1))}
            disabled={zoomIdx === 0}
            aria-label="Thu nhỏ trang"
            title="Thu nhỏ"
          >
            <ZoomOut size={18} aria-hidden="true" /> <span>Nhỏ</span>
          </button>
          <button
            type="button"
            className="pv-btn pv-btn-icon"
            onClick={() => setZoomIdx((i) => Math.min(ZOOMS.length - 1, i + 1))}
            disabled={zoomIdx === ZOOMS.length - 1}
            aria-label="Phóng to trang"
            title="Phóng to"
          >
            <ZoomIn size={18} aria-hidden="true" /> <span>To</span>
          </button>
        </div>
      </div>

      <div className="page-viewer-scroll" ref={scrollRef}>
        <div className="page-viewer-page" style={{ width: `${zoom * 100}%` }}>
          <AuthedImage
            className="page-viewer-image"
            url={`/api/documents/${encodeURIComponent(docName)}/pages/${pageNum}/image?dpi=${zoom > 1.4 ? 220 : 150}`}
            alt={alt}
          />
          {locate.rects.map((r, i) => (
            <span
              key={i}
              ref={i === 0 ? firstRectRef : undefined}
              className="page-viewer-hl"
              style={{
                left: `${r.x * 100}%`,
                top: `${r.y * 100}%`,
                width: `${r.w * 100}%`,
                height: `${r.h * 100}%`,
              }}
              aria-hidden="true"
            />
          ))}
        </div>
      </div>

      {locate.status === 'notfound' && quote && (
        <blockquote className="page-viewer-fallback">{quote}</blockquote>
      )}
    </div>
  );
}
