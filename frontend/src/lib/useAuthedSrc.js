import { useEffect, useRef, useState } from 'react';
import { apiBlobUrl } from './apiClient';

/**
 * Nguồn ảnh cho tài nguyên cần đăng nhập.
 *
 * Trả về { src, loading, error } — src là object URL của blob đã tải, dùng
 * được ngay trong <img src>. Xem apiBlobUrl để biết vì sao không trỏ src thẳng
 * vào /api/ được.
 *
 * Hai chi tiết đáng lưu ý trong cách quản lý object URL:
 *
 * - Ảnh cũ được giữ hiển thị trong lúc tải ảnh mới. Bác sĩ bấm chuyển trang
 *   liên tục trong reader; nếu xoá src ngay thì mỗi lần bấm là một lần nháy
 *   trắng, trong khi ảnh trang trước vẫn còn dùng được để đối chiếu.
 * - Object URL cũ chỉ thu hồi SAU khi ảnh mới đã sẵn sàng. Thu hồi trong hàm
 *   cleanup của effect thì nó chạy trước lần render mang src mới, tức có một
 *   nhịp <img> trỏ vào URL vừa bị vô hiệu.
 *
 * URL không thuộc /api/ (blob: của bản xem trước khi chọn tệp, data:, ảnh ngoài)
 * được trả lại nguyên vẹn: chúng không cần xác thực, và fetch về blob lần nữa
 * chỉ nhân bản dữ liệu đã có.
 */
function needsAuth(url) {
  if (!url) return false;
  try {
    const parsed = new URL(url, window.location.origin);
    return parsed.origin === window.location.origin && parsed.pathname.startsWith('/api/');
  } catch {
    return String(url).startsWith('/api/');
  }
}

export default function useAuthedSrc(url) {
  const [state, setState] = useState(() => ({
    src: needsAuth(url) ? null : (url || null),
    loading: needsAuth(url),
    error: null,
  }));
  // Object URL đang được <img> dùng — chỉ những URL do hook này tạo ra.
  const ownedUrl = useRef(null);

  useEffect(() => {
    const releaseOwned = () => {
      if (ownedUrl.current) {
        URL.revokeObjectURL(ownedUrl.current);
        ownedUrl.current = null;
      }
    };

    if (!needsAuth(url)) {
      releaseOwned();
      setState({ src: url || null, loading: false, error: null });
      return undefined;
    }

    let cancelled = false;
    setState((prev) => ({ src: prev.src, loading: true, error: null }));

    apiBlobUrl(url)
      .then((created) => {
        if (cancelled) {
          // Người dùng đã đổi trang trước khi ảnh này về — bỏ luôn.
          URL.revokeObjectURL(created);
          return;
        }
        const previous = ownedUrl.current;
        ownedUrl.current = created;
        setState({ src: created, loading: false, error: null });
        if (previous) URL.revokeObjectURL(previous);
      })
      .catch((err) => {
        if (cancelled) return;
        const previous = ownedUrl.current;
        ownedUrl.current = null;
        setState({ src: null, loading: false, error: err.message || 'Không tải được ảnh.' });
        if (previous) URL.revokeObjectURL(previous);
      });

    return () => { cancelled = true; };
  }, [url]);

  // Thu hồi lần cuối khi component rời khỏi cây. Tách riêng khỏi effect trên vì
  // effect đó chạy lại mỗi lần đổi url, còn đây chỉ được phép chạy khi unmount.
  useEffect(() => () => {
    if (ownedUrl.current) {
      URL.revokeObjectURL(ownedUrl.current);
      ownedUrl.current = null;
    }
  }, []);

  return state;
}
