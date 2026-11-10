import React, { useMemo, useState } from 'react';
import { ArrowUpRight, BookOpen, Bookmark, ChevronRight, MessageSquare, Search, X } from 'lucide-react';
import { matchingSpecialties, specialties, specialtyHref } from './lib/specialties';
import './homepage.css';

function readSaved(key) {
  try {
    const ids = JSON.parse(localStorage.getItem(key));
    return Array.isArray(ids) ? ids.filter(id => specialties.some(item => item.id === id)) : [];
  } catch { return []; }
}

export default function Homepage({ user, query, view, onNavigate, onClearSearch }) {
  const storageKey = `fil_saved_specialties_v1:${user?.id || 'guest'}`;
  const [saved, setSaved] = useState(() => readSaved(storageKey));
  const [filter, setFilter] = useState('all');
  const [sort, setSort] = useState('default');
  const matching = useMemo(() => matchingSpecialties(query), [query]);
  const results = useMemo(() => {
    const list = matching.filter(item => filter !== 'saved' || saved.includes(item.id));
    return sort === 'name' ? [...list].sort((a, b) => a.name.localeCompare(b.name, 'vi')) : list;
  }, [matching, filter, saved, sort]);

  function follow(event) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    onNavigate(event.currentTarget.href);
  }

  function toggleSaved(id) {
    setSaved(previous => {
      const next = previous.includes(id) ? previous.filter(value => value !== id) : [...previous, id];
      try { localStorage.setItem(storageKey, JSON.stringify(next)); } catch { /* Keep the current selection if storage is unavailable. */ }
      return next;
    });
  }

  return (
    <div className="fil-wrap fil-notebook-home">
      <h1 className="sr-only">Sổ tay y khoa Fil</h1>
      {!query && filter === 'all' && <section className="fil-featured" aria-labelledby="featured-heading">
        <div className="fil-gallery-heading">
          <div><h2 id="featured-heading">Khám phá chuyên khoa</h2><p>Không gian tra cứu cho từng lĩnh vực y khoa.</p></div>
          <a href="#specialty-notebooks">Xem tất cả <ChevronRight size={17} aria-hidden="true" /></a>
        </div>
        <div className="fil-featured-grid">
          {specialties.filter(item => item.cover).map((item, index) => (
            <a key={item.id} href={specialtyHref(item)} onClick={follow} className={`fil-featured-notebook fil-notebook-${item.color}`}>
              <div className="fil-notebook-cover">
                <img src={item.cover} alt="" width="1536" height="1024" fetchPriority={index === 0 ? 'high' : 'auto'} decoding="async" />
                <span className="fil-cover-open"><ArrowUpRight size={19} aria-hidden="true" /></span>
              </div>
              <div className="fil-featured-copy">
                <span className="fil-notebook-type"><BookOpen size={14} aria-hidden="true" /> Sổ tay chuyên khoa</span>
                <h3>{item.name}</h3>
                <p>{item.description}</p>
              </div>
            </a>
          ))}
        </div>
      </section>}

      <section id="specialty-notebooks" className="fil-notebook-section" aria-labelledby="notebooks-heading">
        <div className="fil-gallery-heading fil-notebooks-toolbar">
          <h2 id="notebooks-heading">{query ? 'Kết quả tìm kiếm' : 'Sổ tay chuyên khoa'}</h2>
          <a className="fil-notebook-new" href="/hoi-dap" onClick={follow}><MessageSquare size={17} aria-hidden="true" /> Đặt câu hỏi</a>
        </div>
        <div className="fil-notebook-controls">
          <div className="fil-notebook-filters" role="group" aria-label="Lọc sổ tay">
            <button type="button" aria-pressed={filter === 'all'} onClick={() => setFilter('all')}>Tất cả</button>
            <button type="button" aria-pressed={filter === 'saved'} onClick={() => setFilter('saved')}><Bookmark size={15} aria-hidden="true" /> Đã lưu{saved.length > 0 && <span>{saved.length}</span>}</button>
          </div>
          <label className="fil-notebook-sort"><span className="sr-only">Sắp xếp sổ tay</span>
            <select aria-label="Sắp xếp sổ tay" value={sort} onChange={event => setSort(event.target.value)}>
              <option value="default">Theo chuyên khoa</option><option value="name">Tên từ A đến Z</option>
            </select>
          </label>
        </div>
        {query && <div className="fil-notebook-search-summary" role="status">
          <span>{results.length} kết quả cho “{query}”</span>
          <button type="button" onClick={onClearSearch}><X size={15} aria-hidden="true" /> Xóa tìm kiếm</button>
        </div>}
        {results.length > 0 ? <ul className={`fil-notebook-grid ${view === 'list' ? 'is-list' : ''}`}>
          {results.map(item => (
            <li key={item.id} className={`fil-notebook-card fil-notebook-${item.color}`}>
              <a href={specialtyHref(item)} onClick={follow} aria-label={`Mở sổ tay ${item.name}`}>
                <div className="fil-notebook-card-top"><span className="fil-notebook-symbol"><item.Icon size={28} strokeWidth={1.6} aria-hidden="true" /></span></div>
                <div className="fil-notebook-card-copy"><h3>{item.name}</h3><p>{item.description}</p>
                  <span className="fil-notebook-card-footer"><BookOpen size={14} aria-hidden="true" /> Sổ tay chuyên khoa <ArrowUpRight size={15} aria-hidden="true" /></span>
                </div>
              </a>
              <button type="button" className="fil-notebook-save" aria-label={`${saved.includes(item.id) ? 'Bỏ lưu' : 'Lưu'} sổ tay ${item.name}`}
                aria-pressed={saved.includes(item.id)} onClick={() => toggleSaved(item.id)}>
                <Bookmark size={18} fill={saved.includes(item.id) ? 'currentColor' : 'none'} aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul> : <div className="fil-notebook-empty">
          {query ? <Search size={30} aria-hidden="true" /> : <Bookmark size={30} aria-hidden="true" />}
          <h3>{query ? 'Chưa tìm thấy chuyên khoa phù hợp' : 'Chưa có sổ tay đã lưu'}</h3>
          <p>{query ? 'Thử tên chuyên khoa khác hoặc xóa tìm kiếm.' : 'Chọn biểu tượng lưu trên sổ tay để tìm lại tại đây.'}</p>
          <button type="button" className="fil-button" onClick={() => { setFilter('all'); onClearSearch(); }}>Xem tất cả chuyên khoa</button>
        </div>}
      </section>
      <footer className="fil-notebook-footer"><span>Fil · Đồng hành cùng thực hành y khoa</span><a href="/thuoc" onClick={follow}>Tra cứu danh mục thuốc <ArrowUpRight size={14} aria-hidden="true" /></a></footer>
    </div>
  );
}
