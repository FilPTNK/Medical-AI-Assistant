import React, { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { Activity, ArrowRight, Bell, BookOpen, ChevronRight, MessageSquare, Moon, Pill, Search, Stethoscope, Sun } from 'lucide-react';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import LoginScreen from './components/LoginScreen';
import useAuth from './components/useAuth';
import useSettings from './components/useSettings';
import useProfiles from './components/useProfiles';
import useClinicalData from './components/useClinicalData';

const App = lazy(() => import('./App'));
const SharedConversationView = lazy(() => import('./App').then(module => ({ default: module.SharedConversationView })));
const SiteAccount = lazy(() => import('./components/SiteAccount'));
const DrugDirectory = lazy(() => import('./DrugDirectory'));
const DrugAdmin = lazy(() => import('./DrugAdmin'));

const tools = [
  { path: '/thuoc', title: 'Tra cứu thuốc', Icon: Pill, text: 'Tìm hoạt chất, tên khác và đọc chuyên luận kèm nguồn.' },
  { path: '/hoi-dap', title: 'Hỏi đáp y khoa', Icon: MessageSquare, text: 'Đặt câu hỏi và đối chiếu câu trả lời với tài liệu gốc.' },
  { path: '/chan-doan', title: 'Hỗ trợ chẩn đoán', Icon: Stethoscope, text: 'Sắp xếp triệu chứng và xem các hướng chẩn đoán để cân nhắc.' },
];

function Homepage() {
  return (
    <>
      <section className="fil-hero">
        <div className="fil-hero-inner">
          <div className="fil-hero-copy">
            <span className="fil-kicker"><Activity size={17} aria-hidden="true" /> Công cụ dành cho bác sĩ</span>
            <h1>Tra cứu y khoa <em>mỗi ngày.</em></h1>
            <p>Tìm thông tin thuốc, đọc nguồn tham khảo và đặt câu hỏi y khoa ngay tại một nơi.</p>
            <form className="fil-search fil-home-search" action="/thuoc" role="search">
              <label className="sr-only" htmlFor="home-drug">Tên thuốc hoặc hoạt chất</label>
              <Search size={21} aria-hidden="true" />
              <input id="home-drug" name="q" placeholder="Nhập tên thuốc hoặc hoạt chất…" maxLength={200} />
              <button className="fil-button" type="submit">Tra cứu <ArrowRight size={17} aria-hidden="true" /></button>
            </form>
          </div>
          <div className="fil-hero-art" aria-hidden="true">
            <svg viewBox="0 0 340 270" fill="none">
              <defs>
                <pattern id="reference-grid" width="25" height="25" patternUnits="userSpaceOnUse">
                  <path d="M25 0H0V25" stroke="currentColor" stroke-opacity=".19" />
                </pattern>
              </defs>
              <rect width="340" height="270" rx="24" fill="url(#reference-grid)" />
              <circle cx="175" cy="127" r="108" stroke="currentColor" stroke-opacity=".28" />
              <circle cx="175" cy="127" r="86" stroke="currentColor" stroke-opacity=".28" stroke-dasharray="3 5" />
              <path d="M14 179h44l12-18 12 34 19-55 18 39h205" stroke="currentColor" stroke-width="2" opacity=".5" />
              <g transform="rotate(-11 168 130)">
                <rect x="99" y="43" width="144" height="175" rx="13" fill="#78c5b6" stroke="#075750" stroke-width="2" />
                <rect x="85" y="52" width="144" height="175" rx="13" fill="#fff" stroke="#075750" stroke-width="2" />
                <path d="M104 53v173" stroke="#b9ded7" stroke-width="2" />
                <rect x="126" y="84" width="46" height="46" rx="10" fill="#e1f4ee" />
                <path d="M149 96v22m-11-11h22" stroke="#0b7468" stroke-width="3" stroke-linecap="round" />
                <path d="M127 152h73m-73 17h63m-63 17h50" stroke="#87bdb5" stroke-width="3" stroke-linecap="round" />
              </g>
              <g transform="rotate(-36 247 177)">
                <rect x="205" y="157" width="85" height="40" rx="20" fill="#fff" stroke="#075750" stroke-width="2" />
                <path d="M247 158h23a19 19 0 0 1 0 38h-23z" fill="#0b7468" />
                <path d="M247 158v38" stroke="#075750" stroke-width="2" />
              </g>
            </svg>
          </div>
        </div>
      </section>
      <section className="fil-wrap fil-tools" aria-labelledby="tool-heading">
        <div className="fil-section-heading">
          <h2 id="tool-heading">Công cụ thực hành</h2>
          <p>Chọn công cụ phù hợp với việc bác sĩ đang làm.</p>
        </div>
        <div className="fil-tool-grid">
          {tools.map(({ path, title, Icon, text }) => (
            <a className="fil-tool" key={path} href={path}>
              <span className="fil-tile"><Icon size={24} aria-hidden="true" /></span>
              <h3>{title}</h3>
              <p>{text}</p>
              <span className="fil-tool-link">Mở công cụ <ChevronRight size={16} aria-hidden="true" /></span>
            </a>
          ))}
        </div>
      </section>
      <footer className="fil-wrap fil-footer">
        <span><BookOpen size={17} aria-hidden="true" /> Fil · Tra cứu y khoa</span>
        <a href="/quan-tri">Quản trị dữ liệu</a>
      </footer>
    </>
  );
}

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
    const title = shared ? 'Cuộc trò chuyện' : tool?.title;
    document.title = title ? `${title} | Fil`
      : path === '/quan-tri' ? 'Quản trị dữ liệu thuốc | Fil' : 'Fil | Tra cứu y khoa';
  }, [path, shared, tool]);

  let page;
  if (shared) page = <SharedConversationView shareId={url.searchParams.get('share')} />;
  else if (clinicalPage) page = (
    <AccountGate auth={auth}>
      <article className={toolPath === '/hoi-dap' ? 'fil-clinical fil-qa-page' : 'fil-wrap fil-clinical'}>
        {toolPath === '/chan-doan' && <h1 className="sr-only">Hỗ trợ chẩn đoán</h1>}
        <App user={auth.user} settings={settings} clinical={clinical}
          activeTab={toolPath === '/chan-doan' ? 'diagnosisTree' : 'chat'}
          onOpenChat={() => navigate('/hoi-dap')} />
      </article>
    </AccountGate>
  );
  else if (path === '/') page = <Homepage />;
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
          <a className="fil-brand" href="/" onClick={followLink} aria-label="Fil, trang chủ">
            <img className="fil-logo" src="/fil-logo.svg" alt="Fil" width="118" height="50" />
          </a>
          <nav className="fil-nav" aria-label="Điều hướng chính">
            {tools.map(({ path: href, title }) => (
              <a key={href} href={href} onClick={followLink} aria-current={!shared && toolPath === href ? 'page' : undefined}>{title}</a>
            ))}
          </nav>
          <div className="fil-header-actions">
            {auth.permissions.isAdmin && <a href="/quan-tri" onClick={followLink} aria-current={path === '/quan-tri' ? 'page' : undefined}>Quản trị</a>}
            <button className="fil-theme-toggle" type="button"
              aria-label={settings.isDarkMode ? 'Chuyển sang nền sáng' : 'Chuyển sang nền tối'}
              title={settings.isDarkMode ? 'Chuyển sang nền sáng' : 'Chuyển sang nền tối'}
              onClick={() => settings.setAppearance(settings.isDarkMode ? 'light' : 'dark')}>
              {settings.isDarkMode ? <Sun size={19} aria-hidden="true" /> : <Moon size={19} aria-hidden="true" />}
            </button>
            {ready && clinicalPage && toolPath === '/hoi-dap' && (
              <DropdownMenu.Root onOpenChange={open => { if (open) clinical.markNotificationsRead(); }}>
                <DropdownMenu.Trigger className="fil-theme-toggle fil-notification-trigger" aria-label="Thông báo" title="Thông báo">
                  <Bell size={19} aria-hidden="true" />
                  {clinical.notifications.some(item => item.unread) && <span className="fil-unread-dot" aria-label="Có thông báo mới" />}
                </DropdownMenu.Trigger>
                <DropdownMenu.Portal>
                  <DropdownMenu.Content align="end" sideOffset={8} className="dropdown-menu-content fil-notification-menu">
                    <DropdownMenu.Label>Thông báo hỏi đáp</DropdownMenu.Label>
                    {clinical.notifications.length === 0
                      ? <p>Chưa có thông báo trong phiên này.</p>
                      : clinical.notifications.map((item, index) => <div key={index} className="fil-notification">
                        <span>{item.message}</span><time>{item.time.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })}</time>
                      </div>)}
                  </DropdownMenu.Content>
                </DropdownMenu.Portal>
              </DropdownMenu.Root>
            )}
            {ready
              ? <Suspense fallback={null}><SiteAccount key={auth.user.id} auth={auth} settings={settings} profiles={profiles} clinical={clinical} /></Suspense>
              : <a href="/dang-nhap" onClick={followLink}>Đăng nhập</a>}
          </div>
        </div>
      </header>
      <main id="fil-content" ref={contentRef} className="fil-content" tabIndex={-1}>
        <Suspense fallback={<p className="fil-state" role="status">Đang tải trang…</p>}>{page}</Suspense>
      </main>
    </div>
  );
}
