import React, { useCallback, useEffect, useRef, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import {
  History,
  Search,
  Trash2,
  X,
  RotateCcw,
  Sparkles,
  BookOpen,
  Loader2
} from 'lucide-react';
import './SearchHistory.css';

function formatWhen(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const today = new Date();
  const sameDay = d.toDateString() === today.toDateString();
  return sameDay
    ? `Hôm nay ${d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })}`
    : d.toLocaleString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

const METHOD_LABEL = {
  exact: 'Trùng khớp',
  embedding: 'Gần nghĩa',
  keyword: 'Trùng từ khóa'
};

/**
 * Gợi ý "câu hỏi tương tự đã hỏi trước đây" ngay phía trên ô nhập câu hỏi.
 * Bấm vào một gợi ý sẽ dùng lại câu trả lời đã lưu, không tốn thêm một lượt gọi LLM.
 */
export function SimilarQuestions({ query, onReuse, disabled }) {
  const [items, setItems] = useState([]);
  const [dismissed, setDismissed] = useState('');
  const abortRef = useRef(null);

  useEffect(() => {
    const q = (query || '').trim();
    if (disabled || q.length < 8 || q === dismissed) {
      setItems([]);
      return undefined;
    }

    const timer = setTimeout(async () => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const res = await fetch('/api/search-history/similar', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: q, limit: 3 }),
          signal: controller.signal
        });
        if (!res.ok) return;
        setItems(await res.json());
      } catch {
        /* bỏ qua: gợi ý là tính năng phụ trợ, không chặn luồng hỏi đáp */
      }
    }, 450);

    return () => clearTimeout(timer);
  }, [query, disabled, dismissed]);

  if (items.length === 0) return null;

  return (
    <div className="sq-wrap">
      <div className="sq-head">
        <History size={12} />
        <span>Câu hỏi tương tự đã tra cứu trước đây</span>
        <button
          type="button"
          className="sq-dismiss"
          onClick={() => { setDismissed((query || '').trim()); setItems([]); }}
          title="Ẩn gợi ý"
        >
          <X size={12} />
        </button>
      </div>
      <div className="sq-list">
        {items.map(item => (
          <button
            key={item.id}
            type="button"
            className="sq-chip"
            onClick={() => onReuse(item)}
            title="Dùng lại câu trả lời đã lưu (không gọi lại AI)"
          >
            <span className="sq-chip-text">{item.query}</span>
            <span className="sq-chip-meta">
              {METHOD_LABEL[item.match_method] || 'Gần nghĩa'} · {Math.round(item.similarity * 100)}%
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

/** Hộp thoại duyệt lại toàn bộ lịch sử tra cứu và dùng lại kết quả cũ. */
export function SearchHistoryDialog({ open, onOpenChange, onReuse, onNotify }) {
  const [records, setRecords] = useState([]);
  const [keyword, setKeyword] = useState('');
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState(null);

  const notify = useCallback((type, message) => {
    if (onNotify) onNotify(type, message);
  }, [onNotify]);

  const load = useCallback(async (q = '') => {
    setLoading(true);
    try {
      const res = await fetch(`/api/search-history${q ? `?q=${encodeURIComponent(q)}` : ''}`);
      if (!res.ok) throw new Error('Không tải được lịch sử tra cứu.');
      setRecords(await res.json());
    } catch (err) {
      notify('error', err.message);
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    if (open) {
      setKeyword('');
      setExpandedId(null);
      load();
    }
  }, [open, load]);

  useEffect(() => {
    if (!open) return undefined;
    const timer = setTimeout(() => load(keyword), 300);
    return () => clearTimeout(timer);
  }, [keyword, open, load]);

  const deleteRecord = async (id) => {
    try {
      const res = await fetch(`/api/search-history/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Không xóa được lượt tra cứu.');
      setRecords(prev => prev.filter(r => r.id !== id));
    } catch (err) {
      notify('error', err.message);
    }
  };

  const clearAll = async () => {
    try {
      const res = await fetch('/api/search-history', { method: 'DELETE' });
      if (!res.ok) throw new Error('Không xóa được lịch sử.');
      setRecords([]);
      notify('success', 'Đã xóa toàn bộ lịch sử tra cứu.');
    } catch (err) {
      notify('error', err.message);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="sh-dialog">
          <div className="sh-header">
            <div className="sh-header-left">
              <History size={17} />
              <div>
                <Dialog.Title className="sh-title">Lịch sử tra cứu</Dialog.Title>
                <Dialog.Description className="sh-subtitle">
                  Mọi câu hỏi đã hỏi cùng câu trả lời và nguồn — bấm để dùng lại mà không cần hỏi lại AI.
                </Dialog.Description>
              </div>
            </div>
            <Dialog.Close asChild>
              <button className="icon-btn-action" title="Đóng"><X size={16} /></button>
            </Dialog.Close>
          </div>

          <div className="sh-toolbar">
            <div className="sh-search">
              <Search size={14} />
              <input
                type="text"
                placeholder="Tìm trong lịch sử tra cứu…"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
              />
            </div>
            <button
              type="button"
              className="sh-clear-btn"
              onClick={clearAll}
              disabled={records.length === 0}
            >
              <Trash2 size={13} />
              Xóa tất cả
            </button>
          </div>

          <div className="sh-body">
            {loading ? (
              <div className="sh-empty"><Loader2 size={16} className="animate-spin" /> Đang tải…</div>
            ) : records.length === 0 ? (
              <div className="sh-empty">
                <History size={20} />
                <p>{keyword ? `Không có lượt tra cứu nào khớp "${keyword}".` : 'Chưa có lượt tra cứu nào được ghi lại.'}</p>
              </div>
            ) : (
              records.map(rec => (
                <div className={`sh-item ${expandedId === rec.id ? 'expanded' : ''}`} key={rec.id}>
                  <div
                    className="sh-item-head"
                    onClick={() => setExpandedId(expandedId === rec.id ? null : rec.id)}
                  >
                    <div className="sh-item-main">
                      <div className="sh-item-query">{rec.query}</div>
                      <div className="sh-item-meta">
                        <span>{formatWhen(rec.created_at)}</span>
                        {rec.created_by && <span>· {rec.created_by}</span>}
                        {rec.sources?.length > 0 && (
                          <span className="sh-source-count">
                            <BookOpen size={11} /> {rec.sources.length} nguồn
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="sh-item-actions">
                      <button
                        type="button"
                        className="sh-reuse-btn"
                        onClick={(e) => { e.stopPropagation(); onReuse(rec); }}
                        title="Đưa lại câu trả lời này vào cuộc trò chuyện"
                      >
                        <RotateCcw size={13} />
                        Dùng lại
                      </button>
                      <button
                        type="button"
                        className="sh-icon-btn danger"
                        onClick={(e) => { e.stopPropagation(); deleteRecord(rec.id); }}
                        title="Xóa khỏi lịch sử"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>

                  {expandedId === rec.id && (
                    <div className="sh-item-answer">
                      <div className="sh-answer-label"><Sparkles size={12} /> Câu trả lời đã lưu</div>
                      <div className="sh-answer-text">{rec.answer}</div>
                      {rec.sources?.length > 0 && (
                        <div className="sh-answer-sources">
                          {rec.sources.map((s, i) => (
                            <span className="sh-source-pill" key={i}>
                              {s.doc_name} · tr.{s.page_num}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
