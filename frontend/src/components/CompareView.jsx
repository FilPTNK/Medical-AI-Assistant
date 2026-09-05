import React, { useMemo, useState } from 'react';
import {
  Scale,
  Send,
  Loader2,
  Check,
  CheckCircle2,
  GitCompareArrows,
  FileText,
  BookOpen,
  Lightbulb,
  AlertTriangle,
  ChevronDown,
  ChevronUp
} from 'lucide-react';
import './CompareView.css';

const MAX_DOCS = 5;

const COVERAGE_CLASS = {
  'Đầy đủ': 'full',
  'Một phần': 'partial',
  'Không đề cập': 'none'
};

const SAMPLE_QUESTIONS = [
  'Kháng sinh ưu tiên trong viêm xoang cấp do vi khuẩn?',
  'Liều corticoid đường uống cho đợt cấp hen phế quản ở người lớn?',
  'Khi nào chỉ định kháng sinh trong viêm họng cấp?'
];

/** Tab "Đối chiếu": hỏi cùng một câu hỏi trên nhiều tài liệu và so sánh câu trả lời. */
export default function CompareView({ documents, apiKey, onOpenSource, onNotify }) {
  const [question, setQuestion] = useState('');
  const [selectedDocs, setSelectedDocs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [expandedDoc, setExpandedDoc] = useState(null);

  const canRun = question.trim().length > 0 && selectedDocs.length >= 2 && !loading;

  const retrievedByDoc = useMemo(() => {
    const map = new Map();
    for (const entry of result?.retrieved || []) map.set(entry.doc_name, entry.chunks || []);
    return map;
  }, [result]);

  const toggleDoc = (docName) => {
    setSelectedDocs(prev => {
      if (prev.includes(docName)) return prev.filter(d => d !== docName);
      if (prev.length >= MAX_DOCS) {
        onNotify?.('error', `Chỉ đối chiếu tối đa ${MAX_DOCS} tài liệu cùng lúc.`);
        return prev;
      }
      return [...prev, docName];
    });
  };

  const runCompare = async () => {
    if (!canRun) return;
    setLoading(true);
    setResult(null);
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (apiKey) headers['X-DeepSeek-Key'] = apiKey;

      const res = await fetch('/api/compare', {
        method: 'POST',
        headers,
        body: JSON.stringify({ query: question.trim(), doc_names: selectedDocs })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || 'Không đối chiếu được các tài liệu.');
      }
      setResult(await res.json());
    } catch (err) {
      onNotify?.('error', err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="cmp-view animate-fade-in">
      <div className="view-header">
        <h2>Đối chiếu nguồn</h2>
        <p>Đặt cùng một câu hỏi lâm sàng cho nhiều tài liệu, xem các guideline đồng thuận và khác nhau ở điểm nào.</p>
      </div>

      <div className="cmp-form">
        <div className="cmp-question-row">
          <textarea
            className="cmp-question-input"
            placeholder="Ví dụ: Kháng sinh ưu tiên trong viêm xoang cấp do vi khuẩn?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); runCompare(); }
            }}
          />
          <button type="button" className="cmp-run-btn" onClick={runCompare} disabled={!canRun}>
            {loading ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
            {loading ? 'Đang đối chiếu…' : 'Đối chiếu'}
          </button>
        </div>

        {!question && (
          <div className="cmp-samples">
            {SAMPLE_QUESTIONS.map(s => (
              <button key={s} type="button" className="cmp-sample-chip" onClick={() => setQuestion(s)}>
                {s}
              </button>
            ))}
          </div>
        )}

        <div className="cmp-doc-picker">
          <div className="cmp-doc-picker-label">
            <Scale size={13} />
            Chọn tài liệu để đối chiếu ({selectedDocs.length}/{MAX_DOCS}) — cần ít nhất 2
          </div>
          {documents.length < 2 ? (
            <div className="cmp-doc-warning">
              <AlertTriangle size={14} />
              Thư viện mới có {documents.length} tài liệu. Hãy tải lên thêm ít nhất một tài liệu nữa để đối chiếu.
            </div>
          ) : (
            <div className="cmp-doc-list">
              {documents.map(doc => {
                const active = selectedDocs.includes(doc.doc_name);
                return (
                  <button
                    key={doc.doc_name}
                    type="button"
                    className={`cmp-doc-chip ${active ? 'active' : ''}`}
                    onClick={() => toggleDoc(doc.doc_name)}
                    title={doc.doc_name}
                  >
                    <span className="cmp-doc-check">{active ? <Check size={12} /> : <FileText size={12} />}</span>
                    <span className="cmp-doc-name">{doc.doc_name}</span>
                    <span className="cmp-doc-pages">{doc.page_count} tr.</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {loading && (
        <div className="cmp-loading">
          <Loader2 size={20} className="animate-spin" />
          <p>Đang tìm đoạn liên quan trong từng tài liệu và so sánh…</p>
        </div>
      )}

      {result && !loading && (
        <div className="cmp-result">
          <div className="cmp-result-head">
            <GitCompareArrows size={16} />
            <div>
              <h3>{result.question}</h3>
              <p>{result.summary}</p>
            </div>
            <span className="cmp-result-time">{result.created_at}</span>
          </div>

          <div className="cmp-columns">
            {result.per_document.map(doc => {
              const chunks = retrievedByDoc.get(doc.doc_name) || [];
              const isOpen = expandedDoc === doc.doc_name;
              return (
                <div className={`cmp-column coverage-${COVERAGE_CLASS[doc.coverage] || 'partial'}`} key={doc.doc_name}>
                  <div className="cmp-column-head">
                    <FileText size={14} />
                    <span className="cmp-column-title" title={doc.doc_name}>{doc.doc_name}</span>
                    <span className="cmp-coverage-tag">{doc.coverage}</span>
                  </div>

                  <p className="cmp-column-stance">{doc.stance || '—'}</p>

                  {doc.key_points.length > 0 && (
                    <ul className="cmp-key-points">
                      {doc.key_points.map((p, i) => <li key={i}>{p}</li>)}
                    </ul>
                  )}

                  {doc.pages.length > 0 && (
                    <div className="cmp-pages">
                      {doc.pages.map(p => {
                        const pageNum = parseInt(String(p).replace(/[^\d]/g, ''), 10);
                        return (
                          <button
                            key={p}
                            type="button"
                            className="cmp-page-pill"
                            onClick={() => pageNum && onOpenSource?.(doc.doc_name, pageNum)}
                            title="Mở trang tài liệu"
                          >
                            <BookOpen size={10} /> tr.{p}
                          </button>
                        );
                      })}
                    </div>
                  )}

                  {chunks.length > 0 && (
                    <>
                      <button
                        type="button"
                        className="cmp-excerpt-toggle"
                        onClick={() => setExpandedDoc(isOpen ? null : doc.doc_name)}
                      >
                        {isOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                        Đoạn trích đã dùng ({chunks.length})
                      </button>
                      {isOpen && (
                        <div className="cmp-excerpts">
                          {chunks.map((c, i) => (
                            <div className="cmp-excerpt" key={i}>
                              <button
                                type="button"
                                className="cmp-excerpt-page"
                                onClick={() => onOpenSource?.(doc.doc_name, c.page_num)}
                              >
                                Trang {c.page_num}
                              </button>
                              <p>{c.text}</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </div>
              );
            })}
          </div>

          <div className="cmp-analysis">
            <section className="cmp-panel cmp-panel-agree">
              <h4><CheckCircle2 size={15} /> Điểm đồng thuận</h4>
              {result.agreements.length === 0 ? (
                <p className="cmp-panel-empty">Không tìm thấy điểm đồng thuận rõ ràng giữa các tài liệu.</p>
              ) : (
                <ul>{result.agreements.map((a, i) => <li key={i}>{a}</li>)}</ul>
              )}
            </section>

            <section className="cmp-panel cmp-panel-differ">
              <h4><AlertTriangle size={15} /> Điểm khác biệt</h4>
              {result.differences.length === 0 ? (
                <p className="cmp-panel-empty">Các tài liệu không mâu thuẫn nhau ở câu hỏi này.</p>
              ) : (
                <div className="cmp-diff-list">
                  {result.differences.map((d, i) => (
                    <div className="cmp-diff" key={i}>
                      <div className="cmp-diff-topic">{d.topic}</div>
                      <div className="cmp-diff-positions">
                        {d.positions.map((p, j) => (
                          <div className="cmp-diff-position" key={j}>
                            <span className="cmp-diff-doc" title={p.doc_name}>{p.doc_name}</span>
                            <span className="cmp-diff-text">{p.position}</span>
                          </div>
                        ))}
                      </div>
                      {d.impact && <div className="cmp-diff-impact">Ý nghĩa lâm sàng: {d.impact}</div>}
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>

          {result.conclusion && (
            <div className="cmp-conclusion">
              <h4><Lightbulb size={15} /> Khuyến nghị thực hành</h4>
              <p>{result.conclusion}</p>
            </div>
          )}

          <p className="cmp-disclaimer">
            Kết quả do AI tổng hợp từ chính các tài liệu bạn chọn. Luôn kiểm chứng lại trang gốc trước khi áp dụng lâm sàng.
          </p>
        </div>
      )}
    </div>
  );
}
