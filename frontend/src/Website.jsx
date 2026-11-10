import React, { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { Grid2X2, List, Moon, Search, Settings, Sun, UserRound, X } from 'lucide-react';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import LoginScreen from './components/LoginScreen';
import useAuth from './components/useAuth';
import useSettings from './components/useSettings';
import useProfiles from './components/useProfiles';
import useClinicalData from './components/useClinicalData';
import FilLogo from './components/FilLogo';
import Homepage from './Homepage';
import { specialties } from './lib/specialties';
import { notebookHref } from './lib/notebooks';

const App = lazy(() => import('./App'));
const SharedConversationView = lazy(() => import('./App').then(module => ({ default: module.SharedConversationView })));
const SiteAccount = lazy(() => import('./components/SiteAccount'));
const DrugDirectory = lazy(() => import('./DrugDirectory'));
const DrugAdmin = lazy(() => import('./DrugAdmin'));

const tools = [
  { path: '/thuoc', title: 'Tra cứu thuốc' },
  { path: '/hoi-dap', title: 'Hỏi đáp y khoa' },
  { path: '/chan-doan', title: 'Hỗ trợ chẩn đoán' },
];


function AccountGate({ auth, children, admin = false }) {
  if (auth.status === 'loading') return <p className="fil-state" role="status">Đang kiểm tra phiên đăng nhập…</p>;
  if (auth.status !== 'ready') {
    return (
      <LoginScreen
        mode={auth.status}
        onLogin={auth.login}
        onSetup={auth.setup}
        onRetry={auth.recheck}
        serverAuth={auth.serverAuth}
        onGoogleLogin={auth.loginWithGoogle}
        onRegister={admin ? undefined : auth.startRegistration}
        onVerifyRegistration={auth.verifyRegistration}
        onResendCode={auth.resendRegistrationCode}
      />
    );
  }
  if (admin && !auth.permissions.isAdmin) {
    return (
      <section className="fil-state">
        <h1>Yêu cầu tài khoản quản trị</h1>
        <p>Đăng nhập bằng tài khoản quản trị để cập nhật dữ liệu thuốc.</p>
        <button className="fil-button" type="button" onClick={auth.logout}>Đổi tài khoản</button>
      </section>
    );
  }
  return children;
}

export default function Website() {
  const auth = useAuth();
  const ready = auth.status === 'ready';
  const settings = useSettings();
  const profiles = useProfiles(ready);
  const clinical = useClinicalData(ready);
  const [location, setLocation] = useState(() => window.location.href);
  const siteRef = useRef(null);
  const contentRef = useRef(null);
  const focusPage = useRef(false);
  const url = new URL(location);
  const path = url.pathname.replace(/\/$/, '') || '/';
  const shared = url.searchParams.has('share') && Boolean(url.searchParams.get('share'));
  const legacyReader = path === '/' && url.searchParams.has('doc') && url.searchParams.has('page');
  const toolPath = legacyReader ? '/hoi-dap' : path;
  const clinicalPage = !shared && ['/hoi-dap', '/chan-doan'].includes(toolPath);
  const tool = tools.find(item => item.path === toolPath);
  const specialty = specialties.find(item => item.id === url.searchParams.get('chuyen-khoa'));
  const [notebookQuery, setNotebookQuery] = useState(() => path === '/' ? url.searchParams.get('q') || '' : '');
  const [notebookView, setNotebookView] = useState(() => {
    try { return localStorage.getItem('fil_notebook_view') === 'list' ? 'list' : 'grid'; } catch { return 'grid'; }
  });

  useEffect(() => {
    if (path === '/') setNotebookQuery(new URL(location).searchParams.get('q') || '');
  }, [location, path]);

  function changeView(next) {
    setNotebookView(next);
    try { localStorage.setItem('fil_notebook_view', next); } catch { /* Use the preference for this session. */ }
    if (path !== '/') navigate('/');
  }

  function clearNotebookSearch() {
    setNotebookQuery('');
    if (path === '/' && url.searchParams.has('q')) navigate('/');
  }


  function navigate(href) {
    const next = new URL(href, window.location.href).href;
    if (next === window.location.href) return;
    window.history.pushState(null, '', next);
    focusPage.current = true;
    setLocation(next);
  }

  function followLink(event) {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    if (new URL(event.currentTarget.href).pathname === '/') setNotebookQuery('');
    navigate(event.currentTarget.href);
  }

  useEffect(() => {
    const onPopState = () => {
      focusPage.current = true;
      setLocation(window.location.href);
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  useEffect(() => {
    if (!focusPage.current) return;
    focusPage.current = false;
    siteRef.current?.scrollTo(0, 0);
    contentRef.current?.focus({ preventScroll: true });
  }, [location]);

  useEffect(() => {
    window.__bootDone?.();
    const title = shared ? 'Cuộc trò chuyện' : specialty && toolPath === '/hoi-dap' ? specialty.name : tool?.title;
    document.title = title ? `${title} | Fil`
      : path === '/quan-tri' ? 'Quản trị dữ liệu thuốc | Fil' : 'Fil | Tra cứu y khoa';
  }, [path, shared, tool, specialty, toolPath]);

  let page;
  if (shared) page = <SharedConversationView shareId={url.searchParams.get('share')} />;
  else if (clinicalPage) page = (
    <AccountGate auth={auth}>
      <article className={toolPath === '/hoi-dap' ? 'fil-wrap fil-clinical fil-qa-page' : 'fil-wrap fil-clinical fil-diagnosis-page'}>
        {toolPath === '/chan-doan' && <h1 className="sr-only">Hỗ trợ chẩn đoán</h1>}
        <App user={auth.user} settings={settings} clinical={clinical}
          activeTab={toolPath === '/chan-doan' ? 'diagnosisTree' : 'chat'}
          onOpenChat={() => navigate('/hoi-dap')} specialty={specialty}
          conversationId={url.searchParams.get('conversation')}
          onConversationChange={id => navigate(id ? notebookHref(id) : specialty ? `/hoi-dap?${new URLSearchParams({ 'chuyen-khoa': specialty.id })}` : '/hoi-dap')}
          onClearSpecialty={() => navigate('/hoi-dap')} />
      </article>
    </AccountGate>
  );
  else if (path === '/') page = <Homepage key={auth.user?.id || 'guest'} user={ready ? auth.user : null} query={notebookQuery} view={notebookView}
    conversations={clinical.conversations} onUpdateConversations={clinical.setConversations} onNavigate={navigate} onClearSearch={clearNotebookSearch} />;
  else if (path === '/thuoc') page = <AccountGate auth={auth}><DrugDirectory initialQuery={url.searchParams.get('q') || ''} /></AccountGate>;
  else if (path === '/quan-tri') page = <AccountGate auth={auth} admin><DrugAdmin /></AccountGate>;
  else if (path === '/dang-nhap') page = <AccountGate auth={auth}><section className="fil-state">
    <h1>Đã đăng nhập</h1><a className="fil-button" href="/thuoc">Tra cứu thuốc</a>
  </section></AccountGate>;
  else page = <section className="fil-state"><h1>Không tìm thấy trang</h1><a href="/">Về trang chủ</a></section>;

  return (
    <div className={ready && clinicalPage && toolPath === '/hoi-dap' ? 'fil-site fil-qa-site' : 'fil-site'} ref={siteRef}>
      <a className="fil-skip" href="#fil-content">Đến nội dung chính</a>
      <header className="fil-header">
        <div className="fil-wrap fil-header-inner">
          <a className="fil-brand" href="/" onClick={followLink} aria-label="Fil, trang chủ" aria-current={!shared && path === '/' ? 'page' : undefined}><FilLogo /></a>
          <nav className="fil-nav" aria-label="Điều hướng chính">
            {tools.map(({ path: href, title }) => (
              <a key={href} href={href} onClick={followLink} aria-current={!shared && toolPath === href ? 'page' : undefined}>{title}</a>
            ))}
          </nav>
          <div className="fil-header-actions">
            <form className="fil-header-search" role="search" onSubmit={event => {
              event.preventDefault();
              navigate(notebookQuery.trim() ? `/?${new URLSearchParams({ q: notebookQuery.trim() })}` : '/');
            }}>
              <Search size={18} aria-hidden="true" />
              <label className="sr-only" htmlFor="notebook-search">Tìm sổ tay</label>
              <input id="notebook-search" type="search" placeholder="Tìm sổ tay" maxLength={100}
                value={notebookQuery} onChange={event => setNotebookQuery(event.target.value)} />
              {notebookQuery && <button type="button" aria-label="Xóa tìm kiếm sổ tay" onClick={clearNotebookSearch}><X size={15} aria-hidden="true" /></button>}
            </form>
            <div className="fil-view-switch" role="group" aria-label="Cách hiển thị sổ tay">
              <button type="button" aria-label="Hiển thị sổ tay dạng lưới" aria-pressed={notebookView === 'grid'} onClick={() => changeView('grid')}><Grid2X2 size={18} aria-hidden="true" /></button>
              <button type="button" aria-label="Hiển thị sổ tay dạng danh sách" aria-pressed={notebookView === 'list'} onClick={() => changeView('list')}><List size={20} aria-hidden="true" /></button>
            </div>
            {ready ? <Suspense fallback={null}><SiteAccount key={auth.user.id} auth={auth} settings={settings} profiles={profiles} clinical={clinical} showHeaderSettings /></Suspense>
              : <>
                <DropdownMenu.Root>
                  <DropdownMenu.Trigger className="fil-header-icon" aria-label="Cài đặt giao diện"><Settings size={20} aria-hidden="true" /></DropdownMenu.Trigger>
                  <DropdownMenu.Portal><DropdownMenu.Content align="end" sideOffset={8} className="dropdown-menu-content">
                    <DropdownMenu.Item className="dropdown-menu-item" onSelect={() => settings.setAppearance(settings.isDarkMode ? 'light' : 'dark')}>
                      {settings.isDarkMode ? <Sun size={17} /> : <Moon size={17} />} {settings.isDarkMode ? 'Chuyển sang nền sáng' : 'Chuyển sang nền tối'}
                    </DropdownMenu.Item>
                  </DropdownMenu.Content></DropdownMenu.Portal>
                </DropdownMenu.Root>
                <a className="fil-header-login" href="/dang-nhap" onClick={followLink} aria-label="Đăng nhập" title="Đăng nhập"><UserRound size={20} aria-hidden="true" /></a>
              </>}
          </div>
        </div>
      </header>
      <main id="fil-content" ref={contentRef} className="fil-content" tabIndex={-1}>
        <Suspense fallback={<p className="fil-state" role="status">Đang tải trang…</p>}>{page}</Suspense>
      </main>
    </div>
  );
}
