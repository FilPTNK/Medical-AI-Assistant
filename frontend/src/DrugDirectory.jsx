import React, { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, BookOpen, ChevronDown, ChevronLeft, ChevronRight, FileText, Pill, Search, X } from 'lucide-react';
import { apiJson } from './lib/apiClient';
import { foldWithMap } from './lib/fold';
import PageViewer from './components/PageViewer';

const groups = ['A–D', 'E–H', 'I–L', 'M–P', 'Q–T', 'U–Z', 'Khác'];
const pageSize = 24;
const fold = value => foldWithMap(value).folded;
const collator = new Intl.Collator('vi', { numeric: true });
let snapshotRequest;

function searchRank(name, aliases, query) {
  if (!query || name === query) return 0;
  if (aliases.includes(query)) return 1;
  if (name.startsWith(query)) return 2;
  if (aliases.some(alias => alias.startsWith(query))) return 3;
  if (name.includes(query) || aliases.some(alias => alias.includes(query))) return 4;
  return -1;
}

async function loadCatalog(url, signal) {
  try {
    return await apiJson(url, { signal });
  } catch (error) {
    // A frontend-only deployment can still serve the published reference index.
    if (!import.meta.env.PROD || signal.aborted ||
        (error.status && ![404, 502, 503, 504].includes(error.status))) throw error;
    snapshotRequest ??= apiJson('/drug-catalog-public.json').then(records =>
      records.map(record => ({ ...record, referenceOnly: true }))
    ).catch(failure => {
      snapshotRequest = null;
      throw failure;
    });
    const records = await snapshotRequest;
    const id = url.split('/')[3];
    if (!id) return records;
    const record = records.find(item => item.id === decodeURIComponent(id));
    if (!record) throw error;
    return record;
  }
}

function useCatalogData(url) {
  const [state, setState] = useState({ data: null, error: '' });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setState({ data: null, error: '' });
    loadCatalog(url, controller.signal)
      .then(data => { if (!controller.signal.aborted) setState({ data, error: '' }); })
      .catch(error => {
        if (!controller.signal.aborted) setState({ data: null, error: error.message });
      });
    return () => controller.abort();
  }, [url, attempt]);
  return { ...state, retry: () => setAttempt(value => value + 1) };
}

function CatalogStatus({ error, retry }) {
  return error
    ? <div className="fil-state" role="alert"><p>{error}</p><button className="fil-button" onClick={retry}>Thử lại</button></div>
    : <p className="fil-state" role="status">Đang tải dữ liệu thuốc…</p>;
}

function detailLink(id, query) {
  const params = new URLSearchParams({ drug: id });
  if (query) params.set('q', query);
  return `/thuoc?${params}`;
}

function readingSections(sections) {
  const result = [];
  for (const section of sections) {
    const pages = section.pages ?? (section.page ? [{ page: section.page, pdf_page: section.pdf_page }] : []);
    const blocks = section.blocks ?? [{ type: 'paragraph', text: section.text }];
    const previous = result.at(-1);
    if (!section.blocks && previous?.label === section.label) {
      previous.blocks.push(...blocks);
      for (const page of pages) {
        if (!previous.pages.some(source => source.pdf_page === page.pdf_page && source.page === page.page)) {
          previous.pages.push(page);
        }
      }
    } else {
      result.push({ label: section.label, pages: [...pages], blocks: [...blocks] });
    }
  }
  return result;
}

function pageLabel(pages) {
  if (!pages.length) return '';
  return `Tr. ${[...new Set(pages.map(page => page.page))].join(', ')}`;
}

function highlightText(text, highlights) {
  if (!highlights?.length) return text;
  const phrases = new Set(highlights);
  const pattern = [...phrases]
    .sort((a, b) => b.length - a.length)
    .map(phrase => phrase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
    .join('|');
  return text.split(new RegExp(`(${pattern})`, 'g')).map((part, index) =>
    phrases.has(part) ? <mark key={index}>{part}</mark> : part
  );
}

function ReadingBlock({ block }) {
  if (block.type === 'heading') return <h3>{block.text}</h3>;
  if (block.type === 'table') {
    return (
      <div className="fil-reading-table" role="region" aria-label="Bảng trong chuyên luận" tabIndex={0}>
        <table>
          <thead><tr>{block.columns.map((column, index) => <th key={index} scope="col">{column}</th>)}</tr></thead>
          <tbody>
            {block.rows.map(([label, ...cells]) => (
              <tr key={label}>
                <th scope="row">{label}</th>
                {cells.map((cell, index) => <td key={index}>{cell}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  if (block.type === 'list') {
    return <ul>{block.items.map((item, index) => <li key={index}>{highlightText(item, block.highlights)}</li>)}</ul>;
  }
  return <p>{block.lead && <><strong>{block.lead}</strong>{' '}</>}{highlightText(block.text, block.highlights)}</p>;
}

function revealSection(id) {
  const section = document.getElementById(id);
  if (section) section.open = true;
  return section;
}

function DrugDetails({ drugId, query }) {
  const { data: drug, error, retry } = useCatalogData(`/api/drug-catalog/${encodeURIComponent(drugId)}`);
  const [scan, setScan] = useState(null);
  const [activeSection, setActiveSection] = useState('muc-1');
  const back = query ? `/thuoc?${new URLSearchParams({ q: query })}` : '/thuoc';
  const sections = useMemo(() => drug ? readingSections(drug.sections) : [], [drug]);
  const sourcePages = [...new Set(sections.flatMap(section => section.pages.map(source => source.page)))];

  useEffect(() => {
    if (!drug) return;
    document.title = `${drug.name} | Fil`;
    const hash = window.location.hash.slice(1);
    const section = /^muc-\d+$/.test(hash) ? revealSection(hash) : null;
    if (section) {
      setActiveSection(hash);
      section.scrollIntoView();
    }
  }, [drug]);

  function jumpFromSelect(event) {
    const id = event.target.value;
    const section = revealSection(id);
    if (section) {
      setActiveSection(id);
      window.history.replaceState(null, '', `#${id}`);
      section.scrollIntoView();
      section.querySelector('summary')?.focus({ preventScroll: true });
    }
    event.target.value = '';
  }

  return (
    <div className="fil-wrap fil-detail">
      <a className="fil-back" href={back}><ArrowLeft size={18} aria-hidden="true" /> Danh mục thuốc</a>
      {drug ? (
        <>
          <header className="fil-detail-header">
            <div className="fil-drug-title">
              <span className="fil-tile"><Pill size={24} aria-hidden="true" /></span>
              <h1>{drug.name}</h1>
            </div>
            <dl className="fil-drug-facts">
              {drug.intl_name && <div><dt>Tên chung quốc tế</dt><dd>{drug.intl_name}</dd></div>}
              {drug.atc_code && <div><dt>Mã ATC</dt><dd>{drug.atc_code}</dd></div>}
              {drug.drug_class && <div><dt>Loại thuốc</dt><dd>{drug.drug_class}</dd></div>}
              {drug.aliases.length > 0 && <div><dt>Tên khác</dt><dd>{drug.aliases.join(', ')}</dd></div>}
            </dl>
          </header>
          <aside className="fil-source-note">
            <BookOpen size={21} aria-hidden="true" />
            <div>
              <strong>{drug.source_title}</strong>
              {drug.source_page && <span className="fil-source-pages">Tr. {drug.source_page}</span>}
              {drug.transcribed && <>
                <span className="fil-source-pages">{pageLabel(sourcePages.map(page => ({ page })))}</span>
                <p>Bản chép từ trang sách. Mở bản quét trong từng mục để đối chiếu.</p>
              </>}
              {drug.ocr && <p>Văn bản từ bản quét có thể sai ký tự. Đối chiếu trang sách, đặc biệt với liều lượng và đơn vị.</p>}
              {drug.source_url && <p><a href={drug.source_url} target="_blank" rel="noreferrer">Mở tài liệu nguồn</a></p>}
            </div>
          </aside>
          {drug.referenceOnly ? <p className="fil-state">Bản online có thông tin nhận diện và trang tham chiếu. Bạn có thể đọc chuyên luận trong ấn bản ghi trên.</p> : <div className="fil-monograph">
            <nav aria-label="Mục lục chuyên luận" className="fil-section-links">
              <h2>Mục lục</h2>
              {sections.map((section, index) => {
                const id = `muc-${index + 1}`;
                return <a key={id} href={`#${id}`} aria-current={activeSection === id ? 'location' : undefined}
                  onClick={() => { revealSection(id); setActiveSection(id); }}>
                  {section.label}
                </a>;
              })}
            </nav>
            <div className="fil-reading-pane">
              <label className="fil-section-picker">
                <span>Chuyển đến mục</span>
                <select defaultValue="" onChange={jumpFromSelect}>
                  <option value="" disabled>Chọn mục trong chuyên luận</option>
                  {sections.map((section, index) => <option key={index} value={`muc-${index + 1}`}>{section.label}</option>)}
                </select>
              </label>
              {sections.map((section, index) => {
                const currentScan = scan?.index === index ? scan.source : null;
                return (
                  <details className="fil-monograph-section" id={`muc-${index + 1}`} key={index} open={index === 0 || undefined}>
                    <summary onClick={() => setActiveSection(`muc-${index + 1}`)}>
                      <h2>{section.label}</h2>
                      {section.pages.length > 0 && <span className="fil-section-page">{pageLabel(section.pages)}</span>}
                      <ChevronDown size={19} aria-hidden="true" />
                    </summary>
                    <div className="fil-reading-body">
                      {section.blocks.map((block, blockIndex) => <ReadingBlock key={blockIndex} block={block} />)}
                      {drug.doc_name && section.pages.length > 0 && (
                        <div className="fil-scan-links" aria-label="Trang sách gốc">
                          {section.pages.map(source => {
                            const opened = currentScan === source;
                            return <button key={`${source.page}-${source.pdf_page}`} type="button" aria-expanded={opened}
                              onClick={() => setScan(opened ? null : { index, source })}>
                              <FileText size={16} aria-hidden="true" />
                              {opened ? `Ẩn bản quét tr. ${source.page}` : `Bản quét tr. ${source.page}`}
                            </button>;
                          })}
                        </div>
                      )}
                      {currentScan && <PageViewer key={currentScan.pdf_page || currentScan.page}
                        docName={drug.doc_name} pageNum={currentScan.page} sourcePdfPage={currentScan.pdf_page}
                        alt={`Bản quét trang ${currentScan.page}`} />}
                    </div>
                  </details>
                );
              })}
              {drug.source_updated && <p className="fil-source-date">Cập nhật lần cuối: {drug.source_updated}.</p>}
            </div>
          </div>}
        </>
      ) : <CatalogStatus error={error} retry={retry} />}
    </div>
  );
}

function DrugList({ initialQuery }) {
  const { data, error, retry } = useCatalogData('/api/drug-catalog');
  const [query, setQuery] = useState(initialQuery);
  const [group, setGroup] = useState('');
  const [page, setPage] = useState(1);
  const searchRef = React.useRef(null);

  const index = useMemo(() => (data || []).map(drug => ({
    drug,
    name: fold(drug.name),
    aliases: [...drug.aliases, drug.intl_name, ...(drug.atc_code || '').split(/[,; ]+/)].filter(Boolean).map(fold),
  })).sort((a, b) => collator.compare(a.drug.name, b.drug.name) || a.drug.id.localeCompare(b.drug.id)), [data]);

  const results = useMemo(() => {
    const term = fold(query);
    const [start, end] = group.split('–');
    return index.flatMap(({ drug, name, aliases }) => {
      const first = name[0]?.toUpperCase();
      if (group === 'Khác' ? /^[A-Z]$/.test(first) : group && !(first >= start && first <= end)) return [];
      const rank = searchRank(name, aliases, term);
      return rank < 0 ? [] : [{ drug, rank }];
    }).sort((a, b) => a.rank - b.rank);
  }, [index, query, group]);

  const totalPages = Math.ceil(results.length / pageSize);
  const visible = results.slice((page - 1) * pageSize, page * pageSize);

  function updateQuery(next) {
    setQuery(next);
    setPage(1);
    const url = new URL(window.location.href);
    if (next) url.searchParams.set('q', next);
    else url.searchParams.delete('q');
    window.history.replaceState(null, '', url);
  }

  return (
    <>
      <section className="fil-directory-hero">
        <div className="fil-wrap">
          <span className="fil-kicker"><Pill size={17} aria-hidden="true" /> Danh mục dược phẩm</span>
          <h1>Tra cứu thuốc</h1>
          <p>Tìm theo tên hoạt chất hoặc tên khác để đọc chuyên luận và đối chiếu nguồn.</p>
          <div className="fil-search fil-directory-search" role="search">
            <label className="sr-only" htmlFor="drug-query">Tìm tên thuốc hoặc hoạt chất</label>
            <Search size={22} aria-hidden="true" />
            <input id="drug-query" ref={searchRef} type="search" value={query} maxLength={200}
              placeholder="Tìm thuốc, ví dụ: Paracetamol…" onChange={event => updateQuery(event.target.value)} />
            {query && <button type="button" className="fil-clear" aria-label="Xóa từ khóa"
              onClick={() => { updateQuery(''); searchRef.current.focus(); }}><X size={19} aria-hidden="true" /></button>}
          </div>
          <div className="fil-alphabet" role="group" aria-label="Lọc theo chữ cái đầu">
            {['', ...groups].map(label => (
              <button type="button" key={label} aria-pressed={group === label}
                onClick={() => { setGroup(label); setPage(1); }}>{label || 'Tất cả'}</button>
            ))}
          </div>
        </div>
      </section>
      <section className="fil-wrap fil-directory-results" aria-label="Kết quả tra cứu">
        {!data ? <CatalogStatus error={error} retry={retry} /> : (
          <>
            <p className="fil-result-count" role="status">
              {results.length.toLocaleString('vi-VN')} chuyên luận{totalPages > 1 ? ` · Trang ${page}/${totalPages}` : ''}
            </p>
            {visible.length ? (
              <ul className="fil-result-grid">
                {visible.map(({ drug }) => (
                  <li key={drug.id}>
                    <a className="fil-result" href={detailLink(drug.id, query)}>
                      <span className="fil-tile"><Pill size={19} aria-hidden="true" /></span>
                      <div>
                        <h2>{drug.name}</h2>
                        {drug.drug_class && <p>{drug.drug_class}</p>}
                        {drug.aliases.length > 0 && <p>Tên khác: {drug.aliases.join(', ')}</p>}
                        <small>{drug.source_title}</small>
                      </div>
                      <ChevronRight size={19} aria-hidden="true" />
                    </a>
                  </li>
                ))}
              </ul>
            ) : <div className="fil-state">
              <h2>{data.length ? 'Không tìm thấy thuốc phù hợp' : 'Danh mục chưa có dữ liệu'}</h2>
              <p>{data.length ? 'Thử tên hoạt chất khác hoặc bỏ bộ lọc chữ cái.' : 'Dữ liệu sẽ xuất hiện sau khi quản trị viên nhập danh mục thuốc.'}</p>
              {data.length > 0 && <button className="fil-button" type="button" onClick={() => { updateQuery(''); setGroup(''); searchRef.current.focus(); }}>Xóa bộ lọc</button>}
            </div>}
            {totalPages > 1 && (
              <nav className="fil-pagination" aria-label="Trang kết quả">
                <button type="button" disabled={page === 1} onClick={() => { setPage(page - 1); searchRef.current.focus(); }}>
                  <ChevronLeft size={18} aria-hidden="true" /> Trang trước
                </button>
                <button type="button" disabled={page === totalPages} onClick={() => { setPage(page + 1); searchRef.current.focus(); }}>
                  Trang sau <ChevronRight size={18} aria-hidden="true" />
                </button>
              </nav>
            )}
          </>
        )}
      </section>
    </>
  );
}

export default function DrugDirectory({ initialQuery }) {
  const drugId = new URLSearchParams(window.location.search).get('drug');
  return drugId ? <DrugDetails drugId={drugId} query={initialQuery} /> : <DrugList initialQuery={initialQuery} />;
}
