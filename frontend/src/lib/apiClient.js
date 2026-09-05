/**
 * Phiên đăng nhập phía trình duyệt.
 *
 * App.jsx gọi `fetch('/api/...')` ở hàng trăm chỗ. Thay vì sửa từng chỗ để đính
 * kèm token, ta vá `window.fetch` một lần: mọi request tới /api/ tự động mang
 * header Authorization, và mọi phản hồi 401 tự động đăng xuất rồi báo cho App
 * qua sự kiện `fil:unauthorized`.
 *
 * Token nằm trong localStorage nên bác sĩ không phải đăng nhập lại mỗi lần tải
 * lại trang; máy chủ vẫn là nơi quyết định phiên còn hiệu lực hay không
 * (auth_db.SESSION_TTL_SECONDS), token cũ chỉ đơn giản bị từ chối.
 */

const TOKEN_KEY = 'fil.auth.token';

// Các đường dẫn tự xử lý lỗi 401 của mình — không kích hoạt đăng xuất toàn cục.
const AUTH_PATHS = [
  '/api/auth/login', '/api/auth/setup', '/api/auth/status', '/api/auth/google',
  '/api/auth/register', '/api/auth/register/verify',
  '/api/auth/register/resend',
];

let memoryToken = null; // dự phòng khi trình duyệt chặn localStorage

export function getToken() {
  if (memoryToken) return memoryToken;
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token) {
  memoryToken = token || null;
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* chế độ riêng tư: giữ token trong bộ nhớ cho tới khi đóng tab */
  }
}

export function clearToken() {
  setToken(null);
}

/** Chuỗi ký tự nhận diện request nội bộ, chấp nhận cả URL tuyệt đối cùng origin. */
function apiPathOf(input) {
  const raw = typeof input === 'string' ? input : (input?.url || '');
  if (!raw) return null;
  try {
    const url = new URL(raw, window.location.origin);
    if (url.origin !== window.location.origin) return null;
    return url.pathname.startsWith('/api/') ? url.pathname : null;
  } catch {
    return raw.startsWith('/api/') ? raw.split('?')[0] : null;
  }
}

let patched = false;

/** Vá window.fetch. Gọi một lần duy nhất, trước khi React render. */
export function installAuthFetch() {
  if (patched) return;
  patched = true;

  const originalFetch = window.fetch.bind(window);

  window.fetch = async (input, init = {}) => {
    const path = apiPathOf(input);
    if (!path) return originalFetch(input, init);

    const token = getToken();
    if (token) {
      // Headers có thể là object, mảng cặp, hoặc Headers — bọc lại cho đồng nhất.
      const headers = new Headers(init.headers || (input instanceof Request ? input.headers : undefined));
      if (!headers.has('Authorization')) headers.set('Authorization', `Bearer ${token}`);
      init = { ...init, headers };
    }

    const response = await originalFetch(input, init);

    if (response.status === 401 && !AUTH_PATHS.includes(path)) {
      clearToken();
      window.dispatchEvent(new CustomEvent('fil:unauthorized'));
    }
    return response;
  };
}

/** fetch JSON có kiểm lỗi, ném Error mang thông báo tiếng Việt của API. */
export async function apiJson(url, options = {}) {
  const response = await fetch(url, options);
  if (response.ok) {
    return response.status === 204 ? null : response.json();
  }
  let detail = 'Không thể kết nối máy chủ.';
  try {
    const body = await response.json();
    if (body?.detail) detail = body.detail;
  } catch {
    /* thân lỗi không phải JSON — giữ thông báo chung */
  }
  const error = new Error(detail);
  error.status = response.status;
  throw error;
}

/** POST/PUT/PATCH JSON gọn một dòng. */
export function apiSend(url, method, body) {
  return apiJson(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

/**
 * Tải một tệp do API sinh ra (PDF xuất hồ sơ).
 *
 * Không dùng được thẻ <a href> thẳng vì request cần header Authorization, nên
 * phải fetch về blob rồi mới kích hoạt tải xuống. Tên tệp lấy từ header
 * Content-Disposition để giữ đúng tên có dấu do máy chủ đặt.
 */
export async function apiDownload(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = 'Không thể tạo tệp.';
    try {
      const body = await response.json();
      if (body?.detail) detail = body.detail;
    } catch { /* giữ thông báo chung */ }
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }

  const disposition = response.headers.get('Content-Disposition') || '';
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  const plainMatch = disposition.match(/filename="?([^";]+)"?/i);
  let filename = 'tai-lieu.pdf';
  if (utf8Match) {
    try { filename = decodeURIComponent(utf8Match[1]); } catch { /* dùng tên mặc định */ }
  } else if (plainMatch) {
    filename = plainMatch[1];
  }

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Chờ trình duyệt bắt đầu tải rồi mới thu hồi URL tạm.
  setTimeout(() => URL.revokeObjectURL(objectUrl), 30_000);
  return filename;
}

/**
 * Tải một ảnh nằm sau lớp xác thực và trả về object URL để gắn vào <img src>.
 *
 * Thẻ <img> của trình duyệt không đi qua window.fetch, nên bản vá
 * installAuthFetch() không chạm tới nó và không có cách nào đính header
 * Authorization vào một request ảnh thông thường. Ảnh scan tài liệu và ảnh đại
 * diện vì vậy luôn nhận 401 nếu trỏ src trực tiếp vào /api/. Cách còn lại là tự
 * fetch về blob rồi dựng URL tạm trong bộ nhớ trang.
 *
 * Người gọi chịu trách nhiệm URL.revokeObjectURL khi thôi dùng, nếu không blob
 * ở lại trong bộ nhớ tới khi đóng tab. Hook useAuthedSrc lo việc này.
 */
export async function apiBlobUrl(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = 'Không tải được ảnh.';
    try {
      const body = await response.json();
      if (body?.detail) detail = body.detail;
    } catch { /* thân lỗi không phải JSON — giữ thông báo chung */ }
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}
