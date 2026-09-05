import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Highlighter,
  StickyNote,
  Trash2,
  X,
  Check,
  PencilLine,
  Loader2,
  FileText
} from 'lucide-react';
import './DocumentAnnotator.css';

export const HIGHLIGHT_COLORS = [
  { id: 'yellow', label: 'Vàng' },
  { id: 'green', label: 'Xanh lá' },
  { id: 'blue', label: 'Xanh dương' },
  { id: 'pink', label: 'Hồng' },
  { id: 'purple', label: 'Tím' }
];

/** Chiều dài text đứng trước `node` bên trong `root`, tính theo ký tự thuần. */
function textOffsetWithin(root, node, offsetInNode) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let total = 0;
  let current = walker.nextNode();
  while (current) {
    if (current === node) return total + offsetInNode;
    total += current.textContent.length;
    current = walker.nextNode();
  }
  return -1;
}

/**
 * Chuyển danh sách highlight của một trang thành các đoạn liên tiếp không chồng lấn
 * để render: [{ text, highlight | null }].
 *
 * Offset được lưu theo văn bản trang lúc tô sáng. Nếu văn bản trang đã thay đổi
 * (tài liệu được index lại), ta dò lại vị trí bằng chính đoạn trích đã lưu.
 */
export function buildSegments(pageText, highlights) {
  const text = pageText || '';
  const resolved = [];

  for (const h of highlights) {
    let start = h.start_offset;
    let end = h.end_offset;
    if (text.slice(start, end) !== h.quote) {
      const found = text.indexOf(h.quote);
      if (found === -1 || !h.quote) continue; // đoạn trích không còn trong trang
      start = found;
      end = found + h.quote.length;
    }
    resolved.push({ ...h, start, end });
  }

  resolved.sort((a, b) => a.start - b.start || b.end - a.end);

  const segments = [];
  let cursor = 0;
  for (const h of resolved) {
    if (h.start < cursor) continue; // bỏ qua phần chồng lấn với highlight trước
    if (h.start > cursor) segments.push({ text: text.slice(cursor, h.start), highlight: null });
    segments.push({ text: text.slice(h.start, h.end), highlight: h });
    cursor = h.end;
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor), highlight: null });
  return segments;
}

export default function DocumentAnnotator({
  docName,
  pageNum,
  pageText,
  doctorName,
  onNotify
}) {
  const [highlights, setHighlights] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selection, setSelection] = useState(null); // { start, end, quote, x, y }
  const [activeHighlightId, setActiveHighlightId] = useState(null);
  const [noteDraft, setNoteDraft] = useState('');
  const [sidePanel, setSidePanel] = useState('highlights'); // 'highlights' | 'docnote'
  const [docNote, setDocNote] = useState({ content: '', updated_at: null });
  const [docNoteDraft, setDocNoteDraft] = useState('');
  const [savingDocNote, setSavingDocNote] = useState(false);

  const textRef = useRef(null);
  const noteInputRef = useRef(null);

  const notify = useCallback((type, message) => {
    if (onNotify) onNotify(type, message);
  }, [onNotify]);

  // Nạp toàn bộ highlight + ghi chú của tài liệu (một lần mỗi tài liệu)
  useEffect(() => {
    if (!docName) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([
      fetch(`/api/documents/${encodeURIComponent(docName)}/highlights`).then(r => (r.ok ? r.json() : [])),
      fetch(`/api/documents/${encodeURIComponent(docName)}/note`).then(r => (r.ok ? r.json() : null))
    ])
      .then(([hs, note]) => {
        if (cancelled) return;
        setHighlights(Array.isArray(hs) ? hs : []);
        setDocNote(note || { content: '', updated_at: null });
        setDocNoteDraft(note?.content || '');
      })
      .catch(() => { if (!cancelled) notify('error', 'Không tải được ghi chú của tài liệu.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [docName, notify]);

  // Đổi trang thì bỏ vùng chọn đang treo
  useEffect(() => { setSelection(null); }, [pageNum, docName]);

  const pageHighlights = useMemo(
    () => highlights.filter(h => Number(h.page_num) === Number(pageNum)),
    [highlights, pageNum]
  );

  const segments = useMemo(
    () => buildSegments(pageText, pageHighlights),
    [pageText, pageHighlights]
  );

  const handleMouseUp = () => {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !textRef.current) {
      setSelection(null);
      return;
    }
    const range = sel.getRangeAt(0);
    if (!textRef.current.contains(range.commonAncestorContainer)) {
      setSelection(null);
      return;
    }
    const quote = sel.toString();
    if (!quote.trim()) {
      setSelection(null);
      return;
    }

    const start = textOffsetWithin(textRef.current, range.startContainer, range.startOffset);
    const end = textOffsetWithin(textRef.current, range.endContainer, range.endOffset);
    if (start < 0 || end < 0 || end <= start) {
      setSelection(null);
      return;
    }

    const rect = range.getBoundingClientRect();
    const containerRect = textRef.current.getBoundingClientRect();
    // Giữ thanh công cụ nằm trọn trong khung đọc (nó rộng khoảng 180px, canh giữa)
    const rawX = rect.left - containerRect.left + rect.width / 2;
    setSelection({
      start,
      end,
      quote,
      x: Math.min(Math.max(rawX, 96), Math.max(containerRect.width - 96, 96)),
      y: rect.top - containerRect.top + textRef.current.scrollTop
    });
  };

  const createHighlight = async (color, withNote = false) => {
    if (!selection) return;
    try {
      const res = await fetch(`/api/documents/${encodeURIComponent(docName)}/highlights`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          page_num: pageNum,
          quote: selection.quote,
          start_offset: selection.start,
          end_offset: selection.end,
          color,
          created_by: doctorName || null
        })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || 'Không lưu được đoạn tô sáng.');
      }
      const created = await res.json();
      setHighlights(prev => [...prev, created]);
      setSelection(null);
      window.getSelection()?.removeAllRanges();
      if (withNote) {
        setSidePanel('highlights');
        setActiveHighlightId(created.id);
        setNoteDraft('');
        setTimeout(() => noteInputRef.current?.focus(), 60);
      }
    } catch (err) {
      notify('error', err.message);
    }
  };

  const saveNote = async (highlightId, note) => {
    try {
      const res = await fetch(`/api/highlights/${highlightId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note })
      });
      if (!res.ok) throw new Error('Không lưu được ghi chú.');
      const updated = await res.json();
      setHighlights(prev => prev.map(h => (h.id === updated.id ? updated : h)));
      setActiveHighlightId(null);
    } catch (err) {
      notify('error', err.message);
    }
  };

  const changeColor = async (highlightId, color) => {
    try {
      const res = await fetch(`/api/highlights/${highlightId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ color })
      });
      if (!res.ok) throw new Error('Không đổi được màu đánh dấu.');
      const updated = await res.json();
      setHighlights(prev => prev.map(h => (h.id === updated.id ? updated : h)));
    } catch (err) {
      notify('error', err.message);
    }
  };

  const removeHighlight = async (highlightId) => {
    try {
      const res = await fetch(`/api/highlights/${highlightId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Không xóa được đánh dấu.');
      setHighlights(prev => prev.filter(h => h.id !== highlightId));
      if (activeHighlightId === highlightId) setActiveHighlightId(null);
    } catch (err) {
      notify('error', err.message);
    }
  };

  const saveDocNote = async () => {
    setSavingDocNote(true);
    try {
      const res = await fetch(`/api/documents/${encodeURIComponent(docName)}/note`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: docNoteDraft, updated_by: doctorName || null })
      });
      if (!res.ok) throw new Error('Không lưu được ghi chú tài liệu.');
      const saved = await res.json();
      setDocNote(saved);
      notify('success', 'Đã lưu ghi chú tài liệu.');
    } catch (err) {
      notify('error', err.message);
    } finally {
      setSavingDocNote(false);
    }
  };

  const groupedHighlights = useMemo(() => {
    const byPage = new Map();
    for (const h of highlights) {
      const page = Number(h.page_num);
      if (!byPage.has(page)) byPage.set(page, []);
      byPage.get(page).push(h);
    }
    return [...byPage.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([page, items]) => ({
        page,
        items: items.slice().sort((a, b) => a.start_offset - b.start_offset)
      }));
  }, [highlights]);

  const docNoteDirty = docNoteDraft !== (docNote.content || '');

  return (
    <div className="annot-layout">
      <div className="annot-main">
        <div
          className="annot-page-text"
          ref={textRef}
          onMouseUp={handleMouseUp}
        >
          {segments.length === 0 ? (
            <span className="annot-empty-page">Trang này chưa có nội dung văn bản.</span>
          ) : (
            segments.map((seg, idx) => (
              seg.highlight ? (
                <mark
                  key={idx}
                  className={`annot-mark annot-mark-${seg.highlight.color} ${activeHighlightId === seg.highlight.id ? 'active' : ''}`}
                  title={seg.highlight.note || 'Nhấp để xem / thêm ghi chú'}
                  onClick={() => {
                    setSidePanel('highlights');
                    setActiveHighlightId(seg.highlight.id);
                    setNoteDraft(seg.highlight.note || '');
                    setTimeout(() => noteInputRef.current?.focus(), 60);
                  }}
                >
                  {seg.text}
                </mark>
              ) : (
                <span key={idx}>{seg.text}</span>
              )
            ))
          )}

          {selection && (
            <div
              className="annot-selection-toolbar"
              style={{ left: `${selection.x}px`, top: `${Math.max(selection.y - 46, 0)}px` }}
              onMouseDown={(e) => e.preventDefault()}
            >
              {HIGHLIGHT_COLORS.map(c => (
                <button
                  key={c.id}
                  type="button"
                  className={`annot-color-dot annot-color-${c.id}`}
                  title={`Tô sáng màu ${c.label.toLowerCase()}`}
                  onClick={() => createHighlight(c.id)}
                />
              ))}
              <span className="annot-toolbar-divider" />
              <button
                type="button"
                className="annot-toolbar-btn"
                onClick={() => createHighlight('yellow', true)}
                title="Tô sáng và thêm ghi chú"
              >
                <StickyNote size={13} />
                Ghi chú
              </button>
            </div>
          )}
        </div>
      </div>

      <aside className="annot-rail">
        <div className="annot-rail-tabs">
          <button
            type="button"
            className={sidePanel === 'highlights' ? 'active' : ''}
            onClick={() => setSidePanel('highlights')}
          >
            <Highlighter size={14} />
            Đánh dấu ({highlights.length})
          </button>
          <button
            type="button"
            className={sidePanel === 'docnote' ? 'active' : ''}
            onClick={() => setSidePanel('docnote')}
          >
            <FileText size={14} />
            Ghi chú tài liệu
          </button>
        </div>

        {sidePanel === 'highlights' ? (
          <div className="annot-rail-body">
            {loading ? (
              <div className="annot-rail-empty"><Loader2 size={15} className="animate-spin" /> Đang tải…</div>
            ) : groupedHighlights.length === 0 ? (
              <div className="annot-rail-empty">
                <Highlighter size={18} />
                <p>Bôi đen một đoạn văn bản bên trái để tô sáng và ghi chú riêng cho bạn.</p>
              </div>
            ) : (
              groupedHighlights.map(group => (
                <div className="annot-group" key={group.page}>
                  <div className="annot-group-label">
                    Trang {group.page}
                    {group.page === Number(pageNum) && <span className="annot-current-tag">đang xem</span>}
                  </div>
                  {group.items.map(h => (
                    <div
                      key={h.id}
                      className={`annot-item annot-item-${h.color} ${activeHighlightId === h.id ? 'active' : ''}`}
                      onClick={() => {
                        setActiveHighlightId(h.id);
                        setNoteDraft(h.note || '');
                      }}
                    >
                      <div className="annot-item-quote">"{h.quote}"</div>

                      {activeHighlightId === h.id ? (
                        <div className="annot-item-editor" onClick={(e) => e.stopPropagation()}>
                          <textarea
                            ref={noteInputRef}
                            className="annot-note-input"
                            value={noteDraft}
                            placeholder="Ghi chú của bạn cho đoạn này…"
                            onChange={(e) => setNoteDraft(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) saveNote(h.id, noteDraft);
                              if (e.key === 'Escape') setActiveHighlightId(null);
                            }}
                          />
                          <div className="annot-item-colors">
                            {HIGHLIGHT_COLORS.map(c => (
                              <button
                                key={c.id}
                                type="button"
                                className={`annot-color-dot annot-color-${c.id} ${h.color === c.id ? 'selected' : ''}`}
                                title={c.label}
                                onClick={() => changeColor(h.id, c.id)}
                              />
                            ))}
                            <div className="annot-item-editor-actions">
                              <button type="button" className="annot-mini-btn" onClick={() => setActiveHighlightId(null)} title="Hủy">
                                <X size={13} />
                              </button>
                              <button type="button" className="annot-mini-btn primary" onClick={() => saveNote(h.id, noteDraft)} title="Lưu ghi chú">
                                <Check size={13} />
                              </button>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <>
                          {h.note && <div className="annot-item-note">{h.note}</div>}
                          <div className="annot-item-actions">
                            <button
                              type="button"
                              title={h.note ? 'Sửa ghi chú' : 'Thêm ghi chú'}
                              onClick={(e) => {
                                e.stopPropagation();
                                setActiveHighlightId(h.id);
                                setNoteDraft(h.note || '');
                                setTimeout(() => noteInputRef.current?.focus(), 60);
                              }}
                            >
                              <PencilLine size={13} />
                              {h.note ? 'Sửa' : 'Ghi chú'}
                            </button>
                            <button
                              type="button"
                              className="danger"
                              title="Xóa đánh dấu"
                              onClick={(e) => { e.stopPropagation(); removeHighlight(h.id); }}
                            >
                              <Trash2 size={13} />
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              ))
            )}
          </div>
        ) : (
          <div className="annot-rail-body annot-docnote-body">
            <p className="annot-docnote-hint">
              Ghi chú chung cho tài liệu này — ví dụ phần nào đáng tin, phiên bản nào, cần đối chiếu với guideline nào.
            </p>
            <textarea
              className="annot-docnote-input"
              value={docNoteDraft}
              placeholder="Nhập ghi chú cá nhân về tài liệu…"
              onChange={(e) => setDocNoteDraft(e.target.value)}
            />
            <div className="annot-docnote-footer">
              <span className="annot-docnote-meta">
                {docNote.updated_at
                  ? `Cập nhật ${new Date(docNote.updated_at).toLocaleString('vi-VN')}`
                  : 'Chưa có ghi chú'}
              </span>
              <button
                type="button"
                className="annot-save-btn"
                disabled={!docNoteDirty || savingDocNote}
                onClick={saveDocNote}
              >
                {savingDocNote ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
                Lưu
              </button>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}
