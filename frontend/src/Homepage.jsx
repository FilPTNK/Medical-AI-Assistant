import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Archive, ArrowUpRight, Bookmark, ChevronLeft, ChevronRight, Clock3, MessageSquare, MoreVertical, Pencil, Plus, Search, SlidersHorizontal, X } from 'lucide-react';
import * as Dialog from '@radix-ui/react-dialog';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { matchingSpecialties, specialties, specialtyHref } from './lib/specialties';
import { citedSourceCount, notebookActivity, notebookHref, recentNotebooks } from './lib/notebooks';
import './homepage.css';

function readSaved(key) {
  try {
    const ids = JSON.parse(localStorage.getItem(key));
    return Array.isArray(ids) ? ids.filter(id => specialties.some(item => item.id === id)) : [];
  } catch { return []; }
}

function NotebookMenu({ notebook, onRename, onArchive }) {
  return <DropdownMenu.Root>
    <DropdownMenu.Trigger className="fil-recent-menu" aria-label={`Tùy chọn sổ tay ${notebook.title || 'Chưa đặt tên'}`}><MoreVertical size={20} aria-hidden="true" /></DropdownMenu.Trigger>
    <DropdownMenu.Portal><DropdownMenu.Content className="dropdown-menu-content" align="end" sideOffset={5}>
      <DropdownMenu.Item className="dropdown-menu-item" onSelect={() => onRename(notebook)}><Pencil size={16} aria-hidden="true" /> Đổi tên</DropdownMenu.Item>
      <DropdownMenu.Item className="dropdown-menu-item" onSelect={() => onArchive(notebook)}><Archive size={16} aria-hidden="true" /> Lưu trữ</DropdownMenu.Item>
    </DropdownMenu.Content></DropdownMenu.Portal>
  </DropdownMenu.Root>;
}

export default function Homepage({ user, query, view, conversations = [], onUpdateConversations, onNavigate, onClearSearch }) {
  const storageKey = `fil_saved_specialties_v1:${user?.id || 'guest'}`;
  const [saved, setSaved] = useState(() => readSaved(storageKey));
  const [expanded, setExpanded] = useState(false);
  const [sort, setSort] = useState('recent');
  const [dialog, setDialog] = useState(null);
  const [name, setName] = useState('');
  const [specialtyId, setSpecialtyId] = useState('');
  const [archived, setArchived] = useState(null);
  const [canScroll, setCanScroll] = useState({ back: false, forward: true });
  const stripRef = useRef(null);
  const nameInputRef = useRef(null);
  const matching = useMemo(() => matchingSpecialties(query.trim()), [query]);
  const recent = useMemo(() => recentNotebooks(conversations, { userId: user?.id, query, sort }), [conversations, user?.id, query, sort]);
  const allRecent = useMemo(() => recentNotebooks(conversations, { userId: user?.id }), [conversations, user?.id]);
  const showGrid = expanded || Boolean(query.trim());

  useEffect(() => {
    const strip = stripRef.current;
    if (!strip) return;
    const update = () => setCanScroll({ back: strip.scrollLeft > 2, forward: strip.scrollLeft + strip.clientWidth < strip.scrollWidth - 2 });
    const observer = new ResizeObserver(update);
    observer.observe(strip);
    strip.addEventListener('scroll', update, { passive: true });
    update();
    return () => { observer.disconnect(); strip.removeEventListener('scroll', update); };
  }, [showGrid, matching.length]);

  function follow(event) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    onNavigate(event.currentTarget.href);
  }

  function toggleSaved(id) {
    setSaved(previous => {
      const next = previous.includes(id) ? previous.filter(value => value !== id) : [...previous, id];
      try { localStorage.setItem(storageKey, JSON.stringify(next)); } catch { /* Retain the selection for this session. */ }
      return next;
    });
  }

  function scrollStrip(direction) {
    const strip = stripRef.current;
    strip?.scrollBy({ left: direction * strip.clientWidth, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
  }

  function newNotebook() {
    if (!user) { onNavigate('/dang-nhap'); return; }
    setName(''); setSpecialtyId(''); setDialog({ type: 'new' });
  }

  function renameNotebook(notebook) {
    setName(notebook.title || ''); setDialog({ type: 'rename', id: notebook.id });
  }

  function saveNotebook(event) {
    event.preventDefault();
    const title = name.trim();
    if (!title || !user || !onUpdateConversations) return;
    if (dialog.type === 'rename') {
      onUpdateConversations(previous => previous.map(item => item.id === dialog.id ? { ...item, title } : item));
      setDialog(null);
      return;
    }
    const id = crypto.randomUUID();
    const now = Date.now();
    onUpdateConversations(previous => [{ id, title, ownerId: user.id, specialty: specialties.find(item => item.id === specialtyId)?.name || null, messages: [], pinned: false, createdAt: now, updatedAt: now }, ...previous]);
    setDialog(null);
    onNavigate(notebookHref(id));
  }

  function archiveNotebook(notebook) {
    onUpdateConversations(previous => previous.map(item => item.id === notebook.id ? { ...item, archived: true } : item));
    setArchived(notebook);
  }

  return (
    <div className="fil-wrap fil-notebook-home">
      <h1 className="sr-only">Sổ tay y khoa Fil</h1>
      {query.trim() && <div className="fil-notebook-search-summary" role="status"><span>{matching.length + recent.length} kết quả cho “{query.trim()}”</span><button type="button" onClick={onClearSearch}><X size={16} aria-hidden="true" /> Xóa tìm kiếm</button></div>}
      <section className="fil-featured" aria-labelledby="featured-heading">
        <div className="fil-gallery-heading">
          <h2 id="featured-heading">Khám phá chuyên khoa</h2>
          <div className="fil-gallery-actions">
            {!showGrid && <div className="fil-gallery-arrows" role="group" aria-label="Cuộn chuyên khoa">
              <button type="button" aria-label="Chuyên khoa trước" disabled={!canScroll.back} onClick={() => scrollStrip(-1)}><ChevronLeft size={20} aria-hidden="true" /></button>
              <button type="button" aria-label="Chuyên khoa tiếp theo" disabled={!canScroll.forward} onClick={() => scrollStrip(1)}><ChevronRight size={20} aria-hidden="true" /></button>
            </div>}
            {!query.trim() && <button type="button" className="fil-view-specialties" aria-expanded={expanded} aria-controls="specialty-covers" onClick={() => setExpanded(value => !value)}>{expanded ? 'Thu gọn' : 'Xem tất cả'}<ChevronRight size={18} className={expanded ? 'is-expanded' : ''} aria-hidden="true" /></button>}
          </div>
        </div>
        {matching.length ? <ul id="specialty-covers" ref={stripRef} className={`fil-featured-strip ${showGrid ? 'is-expanded' : ''}`}>
          {matching.map((item, index) => <li key={item.id} className="fil-featured-notebook">
            <a href={specialtyHref(item)} onClick={follow} aria-label={`Mở sổ tay ${item.name}`}>
              <img className="fil-featured-image" src={item.cover} alt="" width="1536" height="1024" loading={index < 5 ? 'eager' : 'lazy'} fetchPriority={index === 0 ? 'high' : 'auto'} decoding="async" />
              <span className="fil-cover-specialty-icon"><item.Icon size={21} strokeWidth={1.7} aria-hidden="true" /></span>
              <div className="fil-featured-copy"><h3>{item.name}</h3><span className="fil-cover-meta">{item.english}</span></div>
              <ArrowUpRight className="fil-cover-arrow" size={22} aria-hidden="true" />
            </a>
            <button type="button" className="fil-cover-save" aria-label={`${saved.includes(item.id) ? 'Bỏ lưu' : 'Lưu'} sổ tay ${item.name}`} aria-pressed={saved.includes(item.id)} onClick={() => toggleSaved(item.id)}><Bookmark size={18} fill={saved.includes(item.id) ? 'currentColor' : 'none'} aria-hidden="true" /></button>
          </li>)}
        </ul> : <div className="fil-notebook-no-results">Không tìm thấy chuyên khoa phù hợp.</div>}
      </section>

      <section className="fil-recent-section" aria-labelledby="recent-heading">
        <div className="fil-gallery-heading fil-recent-heading">
          <div className="fil-recent-title"><h2 id="recent-heading">Sổ tay gần đây</h2>
            <DropdownMenu.Root><DropdownMenu.Trigger className="fil-recent-sort" aria-label="Sắp xếp sổ tay gần đây"><SlidersHorizontal size={19} aria-hidden="true" /></DropdownMenu.Trigger>
              <DropdownMenu.Portal><DropdownMenu.Content className="dropdown-menu-content" align="start" sideOffset={6}><DropdownMenu.RadioGroup value={sort} onValueChange={setSort}>
                <DropdownMenu.RadioItem className="dropdown-menu-item" value="recent"><DropdownMenu.ItemIndicator>✓</DropdownMenu.ItemIndicator> Hoạt động gần nhất</DropdownMenu.RadioItem>
                <DropdownMenu.RadioItem className="dropdown-menu-item" value="name"><DropdownMenu.ItemIndicator>✓</DropdownMenu.ItemIndicator> Tên từ A đến Z</DropdownMenu.RadioItem>
              </DropdownMenu.RadioGroup></DropdownMenu.Content></DropdownMenu.Portal>
            </DropdownMenu.Root>
          </div>
          <button className="fil-notebook-new" type="button" onClick={newNotebook}><Plus size={21} aria-hidden="true" /> Sổ tay mới</button>
        </div>
        {archived && <div className="fil-notebook-notice" role="status"><span>Đã lưu trữ “{archived.title}”.</span><button type="button" onClick={() => { onUpdateConversations(previous => previous.map(item => item.id === archived.id ? { ...item, archived: false } : item)); setArchived(null); }}>Hoàn tác</button><button type="button" aria-label="Đóng thông báo" onClick={() => setArchived(null)}><X size={16} aria-hidden="true" /></button></div>}
        {recent.length ? <ul className={`fil-recent-grid ${view === 'list' ? 'is-list' : ''}`}>
          {recent.map(notebook => {
            const specialty = specialties.find(item => item.name === notebook.specialty);
            const Icon = specialty?.Icon || MessageSquare;
            const time = notebookActivity(notebook);
            return <li key={notebook.id} className="fil-recent-card">
              <a href={notebookHref(notebook.id)} onClick={follow} aria-label={`Mở sổ tay ${notebook.title || 'Chưa đặt tên'}`}>
                <span className={`fil-recent-symbol ${specialty ? `fil-symbol-${specialty.color}` : ''}`}><Icon size={31} strokeWidth={1.6} aria-hidden="true" /></span>
                <div className="fil-recent-copy"><h3>{notebook.title || 'Chưa đặt tên'}</h3><span className="fil-recent-meta">{time ? <time dateTime={new Date(time).toISOString()}>{new Date(time).toLocaleDateString('vi-VN', { day: 'numeric', month: 'short', year: 'numeric' })}</time> : <span>Chưa có hoạt động</span>}<span aria-hidden="true"> · </span><span>{citedSourceCount(notebook)} nguồn đã trích dẫn</span></span></div>
              </a>
              <NotebookMenu notebook={notebook} onRename={renameNotebook} onArchive={archiveNotebook} />
            </li>;
          })}
        </ul> : <div className="fil-recent-empty">
          {query.trim() ? <Search size={28} aria-hidden="true" /> : <Clock3 size={28} aria-hidden="true" />}
          <h3>{query.trim() && allRecent.length ? 'Không tìm thấy sổ tay phù hợp' : 'Chưa có sổ tay gần đây'}</h3>
          <p>{query.trim() && allRecent.length ? 'Thử tên khác hoặc xóa tìm kiếm.' : user ? 'Tạo sổ tay mới hoặc mở một chuyên khoa để bắt đầu. Các cuộc trò chuyện của bạn sẽ xuất hiện tại đây.' : 'Đăng nhập để tạo sổ tay và tiếp tục các cuộc trò chuyện của bạn.'}</p>
          {!user && <a href="/dang-nhap" onClick={follow} className="fil-button">Đăng nhập</a>}
        </div>}
      </section>

      <Dialog.Root open={Boolean(dialog)} onOpenChange={open => { if (!open) setDialog(null); }}>
        <Dialog.Portal><Dialog.Overlay className="fil-notebook-dialog-overlay" /><Dialog.Content className="fil-notebook-dialog" aria-describedby="notebook-dialog-description" onOpenAutoFocus={event => { event.preventDefault(); nameInputRef.current?.focus(); }}>
          <Dialog.Title>{dialog?.type === 'rename' ? 'Đổi tên sổ tay' : 'Tạo sổ tay mới'}</Dialog.Title>
          <Dialog.Description id="notebook-dialog-description">{dialog?.type === 'rename' ? 'Chọn một tên dễ tìm lại.' : 'Lưu câu hỏi và các nguồn trích dẫn trong một cuộc trò chuyện.'}</Dialog.Description>
          <Dialog.Close className="fil-notebook-dialog-close" aria-label="Đóng"><X size={20} aria-hidden="true" /></Dialog.Close>
          <form onSubmit={saveNotebook}><label htmlFor="notebook-name">Tên sổ tay</label><input ref={nameInputRef} id="notebook-name" value={name} onChange={event => setName(event.target.value)} maxLength={150} required autoComplete="off" placeholder="Ví dụ: Ca lâm sàng tim mạch" />
            {dialog?.type === 'new' && <><label htmlFor="notebook-specialty">Chuyên khoa (không bắt buộc)</label><select id="notebook-specialty" value={specialtyId} onChange={event => setSpecialtyId(event.target.value)}><option value="">Y khoa tổng quát</option>{specialties.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></>}
            <div className="fil-notebook-dialog-actions"><Dialog.Close className="fil-button fil-button-secondary" type="button">Hủy</Dialog.Close><button className="fil-button" type="submit" disabled={!name.trim()}>{dialog?.type === 'rename' ? 'Lưu tên' : 'Tạo sổ tay'}</button></div>
          </form>
        </Dialog.Content></Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
