import React, { useEffect, useRef, useState } from 'react';
import {
  Pill, Loader2, Eye, EyeOff, ShieldCheck, AlertCircle, RefreshCw,
  MailCheck, ArrowLeft, Terminal,
} from 'lucide-react';
import './LoginScreen.css';

/**
 * Cổng vào của phòng khám. Bốn chế độ dùng chung một khung thẻ:
 *
 *   setup    — lần chạy đầu tiên, đặt mật khẩu quản trị
 *   login    — đăng nhập bằng *tên đăng nhập + mật khẩu* (không hỏi email)
 *   register — đăng ký: tên đăng nhập + email + mật khẩu
 *   verify   — nhập mã 6 chữ số vừa gửi tới email
 *
 * Email chỉ xuất hiện ở bước đăng ký: nó dùng để xác nhận người thật và để liên
 * hệ sau này, còn đăng nhập hằng ngày thì gõ tên đăng nhập cho nhanh.
 */

const CODE_LENGTH = 6;
const APP_NAME = 'Trợ lý Fil';

/** Chữ G bốn màu của Google — vẽ tay để nút hoà vào khung của mình. */
function GoogleMark({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#4285F4" d="M45.1 24.5c0-1.6-.1-3.2-.4-4.7H24v8.9h11.8c-.5 2.8-2.1 5.1-4.4 6.7v5.6h7.1c4.2-3.8 6.6-9.5 6.6-16.5z" />
      <path fill="#34A853" d="M24 46c6 0 11-2 14.6-5.4l-7.1-5.6c-2 1.3-4.5 2.1-7.5 2.1-5.8 0-10.7-3.9-12.4-9.1H4.3v5.8C7.9 41.1 15.4 46 24 46z" />
      <path fill="#FBBC05" d="M11.6 28c-.4-1.3-.7-2.6-.7-4s.3-2.7.7-4v-5.8H4.3C2.8 17.1 2 20.4 2 24s.8 6.9 2.3 9.8L11.6 28z" />
      <path fill="#EA4335" d="M24 10.9c3.3 0 6.2 1.1 8.5 3.3l6.3-6.3C35 4.4 30 2 24 2 15.4 2 7.9 6.9 4.3 14.2l7.3 5.8c1.7-5.2 6.6-9.1 12.4-9.1z" />
    </svg>
  );
}

/** Nạp thư viện Google Identity Services một lần cho cả vòng đời trang. */
let gsiPromise = null;
function loadGoogleScript() {
  if (window.google?.accounts?.id) return Promise.resolve();
  if (gsiPromise) return gsiPromise;
  gsiPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.defer = true;
    script.onload = resolve;
    script.onerror = () => {
      gsiPromise = null;
      reject(new Error('Không tải được thư viện đăng nhập của Google.'));
    };
    document.head.appendChild(script);
  });
  return gsiPromise;
}

/**
 * Nút "Đăng nhập bằng Google" mang dáng của thiết kế này.
 *
 * Luồng popup chỉ chạy nếu cú bấm rơi đúng vào nút do thư viện GIS dựng, nên ta
 * vẫn render nút đó rồi phủ nó trong suốt lên khung mình vẽ: người dùng thấy nút
 * của mình, Google nhận cú bấm của mình. Bấm trúng viền ngoài thì ta chuyển tiếp
 * bằng tay — vẫn nằm trong cử chỉ bấm nên trình duyệt không chặn popup.
 *
 * Token nhận về gửi thẳng cho máy chủ kiểm chữ ký; phía trình duyệt không đọc,
 * không tin gì trong đó.
 */
function GoogleButton({ clientId, label, onCredential, onError }) {
  const holder = useRef(null);
  const latest = useRef(onCredential);
  latest.current = onCredential;

  useEffect(() => {
    if (!clientId || !holder.current) return undefined;
    let cancelled = false;

    loadGoogleScript()
      .then(() => {
        if (cancelled || !holder.current) return;
        window.google.accounts.id.initialize({
          client_id: clientId,
          callback: (response) => latest.current(response.credential),
        });
        holder.current.innerHTML = '';
        window.google.accounts.id.renderButton(holder.current, {
          type: 'standard',
          theme: 'outline',
          size: 'large',
          text: 'continue_with',
          locale: 'vi',
          width: 392,
        });
      })
      .catch((err) => { if (!cancelled) onError?.(err.message); });

    return () => { cancelled = true; };
  }, [clientId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!clientId) return null;

  return (
    <div className="lg-google">
      <button type="button" className="lg-gbtn" tabIndex={-1}>
        <GoogleMark />
        <span className="lg-gbtn-label">{label}</span>
      </button>
      <div
        className="lg-google-slot"
        ref={holder}
        onClick={(e) => {
          if (e.target === e.currentTarget) {
            holder.current?.querySelector('div[role="button"]')?.click();
          }
        }}
      />
      <p className="lg-privacy">
        Thư viện đăng nhập của Google được tải ngay khi bạn mở trang này, nên từ thời
        điểm đó Google có thể ghi nhận địa chỉ IP và thông tin trình duyệt của bạn.
        Email, tên và ảnh đại diện Google chỉ được chuyển cho chúng tôi nếu bạn chủ
        động bấm đăng nhập bằng Google.
      </p>
    </div>
  );
}

export default function LoginScreen({
  mode, onLogin, onSetup, onRetry,
  serverAuth = {}, onGoogleLogin,
  onRegister, onVerifyRegistration, onResendCode,
}) {
  const isSetup = mode === 'setup';
  const isOffline = mode === 'offline';

  // 'login' | 'register' | 'verify' — chỉ có nghĩa khi mode === 'login'.
  const [view, setView] = useState('login');

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  const [pending, setPending] = useState(null); // { pending_id, email, delivered }
  const [code, setCode] = useState('');
  const [cooldown, setCooldown] = useState(0);

  const isRegister = !isSetup && view === 'register';
  const isVerify = !isSetup && view === 'verify';
  const isLogin = !isSetup && view === 'login';

  // Đồng hồ đếm ngược cho nút "Gửi lại mã".
  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const timer = setTimeout(() => setCooldown((n) => n - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  const goto = (next) => {
    setView(next);
    setError('');
    setNotice('');
    setPassword('');
    setConfirm('');
    setCode('');
  };

  const handleGoogle = async (credential) => {
    setError('');
    setBusy(true);
    try {
      await onGoogleLogin(credential);
    } catch (err) {
      setError(err.message || 'Không đăng nhập được bằng Google.');
    } finally {
      setBusy(false);
    }
  };

  const submitSetup = async () => {
    if (password.length < 6) throw new Error('Mật khẩu phải có ít nhất 6 ký tự.');
    if (password !== confirm) throw new Error('Hai lần nhập mật khẩu không khớp.');
    await onSetup({
      password,
      display_name: displayName.trim() || undefined,
      username: username.trim() || undefined,
    });
  };

  const submitLogin = async () => {
    if (!username.trim() || !password) {
      throw new Error('Vui lòng nhập tên đăng nhập và mật khẩu.');
    }
    await onLogin(username.trim(), password);
  };

  const submitRegister = async () => {
    if (!username.trim()) throw new Error('Vui lòng nhập tên đăng nhập.');
    if (!email.trim()) throw new Error('Vui lòng nhập địa chỉ email.');
    if (password.length < 6) throw new Error('Mật khẩu phải có ít nhất 6 ký tự.');
    if (password !== confirm) throw new Error('Hai lần nhập mật khẩu không khớp.');

    const result = await onRegister({
      email: email.trim(),
      username: username.trim(),
      password,
    });
    setPending(result);
    setCooldown(result.resend_in || 60);
    setView('verify');
    setCode('');
    setNotice('');
  };

  const submitVerify = async () => {
    if (code.trim().length !== CODE_LENGTH) {
      throw new Error(`Mã xác nhận gồm ${CODE_LENGTH} chữ số.`);
    }
    await onVerifyRegistration(pending.pending_id, code.trim());
  };

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    setNotice('');
    setBusy(true);
    try {
      if (isSetup) await submitSetup();
      else if (isRegister) await submitRegister();
      else if (isVerify) await submitVerify();
      else await submitLogin();
    } catch (err) {
      setError(err.message || 'Đã xảy ra lỗi, vui lòng thử lại.');
      if (isSetup || isLogin) { setPassword(''); setConfirm(''); }
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    setError('');
    setNotice('');
    try {
      const result = await onResendCode(pending.pending_id);
      setPending((prev) => ({ ...prev, delivered: result.delivered }));
      setCooldown(result.resend_in || 60);
      setNotice(result.delivered
        ? 'Đã gửi lại mã xác nhận.'
        : 'Đã tạo mã mới — xem trong cửa sổ chạy máy chủ.');
    } catch (err) {
      setError(err.message || 'Không gửi lại được mã.');
      setCooldown(30);
    }
  };

  const brandMark = <div className="lg-mark"><Pill size={26} /></div>;

  if (isOffline) {
    return (
      <div className="lg-screen">
        <div className="lg-card lg-card-offline">
          <div className="lg-offline-icon"><AlertCircle size={26} /></div>
          <h1>Không kết nối được máy chủ</h1>
          <p className="lg-sub">
            Máy chủ {APP_NAME} chưa chạy hoặc đã dừng. Hãy khởi động lại
            <code>run.py</code> rồi thử lại.
          </p>
          <button type="button" className="lg-submit" onClick={onRetry}>
            <RefreshCw size={16} /> Thử kết nối lại
          </button>
        </div>
      </div>
    );
  }

  /* ---------- Bước nhập mã xác nhận gửi về email ---------- */
  if (isVerify) {
    return (
      <div className="lg-screen">
        <div className="lg-card">
          {brandMark}
          <h1>Xác nhận email</h1>
          <p className="lg-sub">
            Chúng tôi đã gửi mã gồm {CODE_LENGTH} chữ số tới <strong>{pending?.email}</strong>.
            Nhập mã để hoàn tất đăng ký. Mã có hiệu lực trong 15 phút.
          </p>

          {pending && !pending.delivered && (
            <div className="lg-hint">
              <Terminal size={15} />
              <span>
                Máy chủ chưa cấu hình dịch vụ gửi thư (<code>RESEND_API_KEY</code>),
                nên mã được in ra cửa sổ đang chạy <code>run.py</code>.
              </span>
            </div>
          )}

          <form className="lg-form" onSubmit={submit}>
            <label className="lg-field">
              <span>Mã xác nhận</span>
              <input
                className="lg-code"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={CODE_LENGTH}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                placeholder="••••••"
                autoFocus
              />
            </label>

            {error && <div className="lg-error"><AlertCircle size={15} /> {error}</div>}
            {notice && <div className="lg-notice"><MailCheck size={15} /> {notice}</div>}

            <button type="submit" className="lg-submit" disabled={busy}>
              {busy
                ? <><Loader2 size={16} className="lg-spin" /> Đang xác nhận…</>
                : 'Hoàn tất đăng ký'}
            </button>
          </form>

          <div className="lg-verify-actions">
            <button
              type="button"
              className="lg-link"
              onClick={resend}
              disabled={cooldown > 0 || busy}
            >
              {cooldown > 0 ? `Gửi lại mã sau ${cooldown}s` : 'Gửi lại mã'}
            </button>
            <button type="button" className="lg-link" onClick={() => goto('register')}>
              <ArrowLeft size={14} /> Đổi thông tin đăng ký
            </button>
          </div>
        </div>

        <footer className="lg-footer">Dữ liệu bệnh nhân được lưu ngay trên máy này.</footer>
      </div>
    );
  }

  /* ---------- Thiết lập lần đầu / Đăng nhập / Đăng ký ---------- */
  return (
    <div className="lg-screen">
      <div className="lg-card">
        {brandMark}

        {isSetup && (
          <>
            <h1>Thiết lập {APP_NAME}</h1>
            <p className="lg-sub">
              Đây là lần khởi động đầu tiên. Hãy đặt mật khẩu cho tài khoản quản trị —
              tài khoản này quản lý các bác sĩ khác và xem được toàn bộ hồ sơ bệnh nhân.
            </p>
          </>
        )}
        {isLogin && (
          <>
            <h1>Đăng nhập {APP_NAME}</h1>
            <p className="lg-sub">Tiếp tục công việc khám chữa của bạn</p>
          </>
        )}
        {isRegister && (
          <>
            <h1>Tạo tài khoản {APP_NAME}</h1>
            <p className="lg-sub lg-sub-gold">Hoàn toàn miễn phí</p>
          </>
        )}

        {!isSetup && serverAuth.googleClientId && (
          <>
            <GoogleButton
              clientId={serverAuth.googleClientId}
              label={isRegister ? 'Đăng ký bằng Google' : 'Đăng nhập bằng Google'}
              onCredential={handleGoogle}
              onError={setError}
            />
            <div className="lg-divider"><span>Hoặc dùng email</span></div>
          </>
        )}

        <form className="lg-form" onSubmit={submit}>
          {isSetup && (
            <label className="lg-field">
              <span>Tên hiển thị</span>
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="BS. Nguyễn Văn A"
                autoFocus
              />
            </label>
          )}

          <label className="lg-field">
            <span>Tên đăng nhập</span>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={isLogin ? 'Tên đăng nhập' : 'nguyen.vana'}
              autoComplete="username"
              autoFocus={isLogin || isRegister}
            />
          </label>

          {isRegister && (
            <label className="lg-field">
              <span>Email</span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="bacsi@email.com"
                autoComplete="email"
              />
            </label>
          )}

          <label className="lg-field">
            <div className="lg-label-row">
              <span>{isSetup ? 'Mật khẩu quản trị' : 'Mật khẩu'}</span>
              {isLogin && (
                <button
                  type="button"
                  className="lg-link"
                  onClick={() => {
                    setError('');
                    setNotice('Liên hệ quản trị viên phòng khám để được đặt lại mật khẩu.');
                  }}
                >
                  Quên mật khẩu?
                </button>
              )}
            </div>
            <div className="lg-password">
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={isLogin ? 'Mật khẩu' : 'Tối thiểu 6 ký tự'}
                autoComplete={isLogin ? 'current-password' : 'new-password'}
              />
              <button
                type="button"
                className="lg-eye"
                onClick={() => setShowPassword((v) => !v)}
                title={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
                aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </label>

          {(isSetup || isRegister) && (
            <label className="lg-field">
              <span>Xác nhận mật khẩu</span>
              <input
                type={showPassword ? 'text' : 'password'}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="Nhập lại mật khẩu"
                autoComplete="new-password"
              />
            </label>
          )}

          {error && <div className="lg-error"><AlertCircle size={15} /> {error}</div>}
          {notice && <div className="lg-notice"><ShieldCheck size={15} /> {notice}</div>}

          <button type="submit" className="lg-submit" disabled={busy}>
            {busy && <><Loader2 size={16} className="lg-spin" /> Đang xử lý…</>}
            {!busy && isSetup && 'Tạo tài khoản quản trị'}
            {!busy && isLogin && 'Đăng nhập'}
            {!busy && isRegister && 'Đăng ký'}
          </button>
        </form>

        {isRegister && (
          <p className="lg-terms">
            Bằng việc đăng ký, bạn đồng ý với <b>Điều khoản sử dụng</b> và{' '}
            <b>Chính sách bảo mật</b> của {APP_NAME}.
          </p>
        )}

        {isLogin && (
          <p className="lg-switch">
            Chưa có tài khoản?{' '}
            <button type="button" className="lg-link" onClick={() => goto('register')}>
              Đăng ký miễn phí
            </button>
          </p>
        )}

        {isRegister && (
          <p className="lg-switch">
            Đã có tài khoản?{' '}
            <button type="button" className="lg-link" onClick={() => goto('login')}>
              Đăng nhập
            </button>
          </p>
        )}

        {isSetup && (
          <p className="lg-note">
            Sau bước này, quản trị viên có thể tạo tài khoản cho từng bác sĩ trong
            mục <strong>Quản lý tài khoản</strong>.
          </p>
        )}
      </div>

      <footer className="lg-footer">Dữ liệu bệnh nhân được lưu ngay trên máy này.</footer>
    </div>
  );
}
