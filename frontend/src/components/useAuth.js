import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiJson, apiSend, getToken, setToken, clearToken } from '../lib/apiClient';

/**
 * Trạng thái đăng nhập của phiên làm việc.
 *
 *   loading — đang hỏi máy chủ (hiện màn hình chờ)
 *   setup   — chưa tài khoản nào có mật khẩu: mở luồng thiết lập quản trị
 *   login   — cần đăng nhập
 *   ready   — đã đăng nhập, App hiển thị bình thường
 *   offline — không gọi được máy chủ
 */
export default function useAuth() {
  const [status, setStatus] = useState('loading');
  const [user, setUser] = useState(null);
  const [roles, setRoles] = useState([]);
  // Cấu hình máy chủ quyết định màn hình đăng nhập dựng được những gì: có
  // GOOGLE_CLIENT_ID thì mới hiện nút Google, có RESEND_API_KEY thì mã xác nhận
  // mới thật sự bay tới hộp thư (nếu không, nó nằm trong console máy chủ).
  const [serverAuth, setServerAuth] = useState({ googleClientId: '', emailDelivery: false });
  const checkRequest = useRef(null);

  const check = useCallback(async () => {
    checkRequest.current?.abort();
    const controller = new AbortController();
    checkRequest.current = controller;
    const timeout = setTimeout(() => controller.abort(), 14000);
    setStatus('loading');
    try {
      const data = await apiJson('/api/auth/status', { signal: controller.signal });
      if (checkRequest.current !== controller) return;
      setRoles(data.roles || []);
      setServerAuth({
        googleClientId: data.google_client_id || '',
        emailDelivery: !!data.email_delivery,
      });
      if (data.needs_setup) {
        setUser(null);
        setStatus('setup');
      } else if (data.authenticated) {
        setUser(data.user);
        setStatus('ready');
      } else {
        setUser(null);
        setStatus('login');
      }
    } catch {
      if (checkRequest.current === controller) setStatus('offline');
    } finally {
      clearTimeout(timeout);
    }
  }, []);

  useEffect(() => {
    check();
    return () => {
      const current = checkRequest.current;
      checkRequest.current = null;
      current?.abort();
    };
  }, [check]);

  // apiClient phát sự kiện này khi máy chủ trả 401 — phiên hết hạn giữa chừng.
  useEffect(() => {
    const onUnauthorized = () => {
      setUser(null);
      setStatus((prev) => (prev === 'setup' ? prev : 'login'));
    };
    window.addEventListener('fil:unauthorized', onUnauthorized);
    return () => window.removeEventListener('fil:unauthorized', onUnauthorized);
  }, []);

  const login = useCallback(async (username, password) => {
    const data = await apiSend('/api/auth/login', 'POST', { username, password });
    setToken(data.token);
    setUser(data.user);
    setStatus('ready');
    return data.user;
  }, []);

  /** Bước 1 của đăng ký: gửi thông tin, máy chủ gửi mã xác nhận về email. */
  const startRegistration = useCallback((fields) =>
    apiSend('/api/auth/register', 'POST', fields), []);

  /** Bước 2: đúng mã thì tài khoản ra đời và vào thẳng ứng dụng. */
  const verifyRegistration = useCallback(async (pendingId, code) => {
    const data = await apiSend('/api/auth/register/verify', 'POST', {
      pending_id: pendingId, code,
    });
    setToken(data.token);
    setUser(data.user);
    setStatus('ready');
    return data.user;
  }, []);

  const resendRegistrationCode = useCallback((pendingId) =>
    apiSend('/api/auth/register/resend', 'POST', { pending_id: pendingId }), []);

  /** Đổi ID token của Google Identity Services lấy phiên đăng nhập. */
  const loginWithGoogle = useCallback(async (credential) => {
    const data = await apiSend('/api/auth/google', 'POST', { credential });
    setToken(data.token);
    setUser(data.user);
    setStatus('ready');
    return data.user;
  }, []);

  const setup = useCallback(async (fields) => {
    const data = await apiSend('/api/auth/setup', 'POST', fields);
    setToken(data.token);
    setUser(data.user);
    setStatus('ready');
    return data.user;
  }, []);

  const logout = useCallback(async () => {
    if (getToken()) {
      try {
        await apiSend('/api/auth/logout', 'POST');
      } catch {
        /* máy chủ không phản hồi — vẫn xóa token phía máy trạm */
      }
    }
    clearToken();
    setUser(null);
    setStatus('login');
  }, []);

  const changePassword = useCallback((currentPassword, newPassword) =>
    apiSend('/api/auth/change-password', 'POST', {
      current_password: currentPassword,
      new_password: newPassword,
    }), []);

  /** Hồ sơ vừa sửa ở nơi khác (EditProfileDialog) — đồng bộ lại tên/ảnh trên thanh bên. */
  const absorbProfile = useCallback((profile) => {
    setUser((prev) => (prev && profile && prev.id === profile.id ? { ...prev, ...profile } : prev));
  }, []);

  const permissions = useMemo(() => ({
    isAdmin: user?.role === 'admin',
    isReadOnly: !!user?.read_only,
    seesAllPatients: !!user?.can_see_all_patients,
  }), [user]);

  return {
    status, user, roles, permissions, serverAuth,
    login, setup, logout, changePassword, absorbProfile, recheck: check,
    startRegistration, verifyRegistration, resendRegistrationCode,
    loginWithGoogle,
  };
}
