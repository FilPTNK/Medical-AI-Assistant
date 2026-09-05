import React from 'react';
import useAuthedSrc from '../lib/useAuthedSrc';
import './AuthedImage.css';

/**
 * Thẻ ảnh cho tài nguyên nằm sau lớp đăng nhập.
 *
 * Dùng thay cho <img src="/api/..."> ở mọi nơi — thẻ img trần không mang được
 * header Authorization nên luôn nhận 401 (xem lib/apiClient.js#apiBlobUrl).
 * URL không thuộc /api/ vẫn dùng được bình thường, nên component này là bản
 * thay thế trực tiếp, không cần phân nhánh ở nơi gọi.
 *
 * `fallback` là nội dung thay thế khi ảnh hỏng — ví dụ chữ cái tên viết tắt của
 * avatar. Không truyền thì hiện một ô báo lỗi kèm thông báo từ máy chủ.
 */
export default function AuthedImage({
  url,
  alt = '',
  className = '',
  fallback = null,
  ...imgProps
}) {
  const { src, loading, error } = useAuthedSrc(url);

  if (error && !src) {
    if (fallback !== null) return fallback;
    return (
      <div className={`authed-image-state authed-image-error ${className}`.trim()} role="img" aria-label={alt}>
        <span>{error}</span>
      </div>
    );
  }

  if (!src) {
    return (
      <div
        className={`authed-image-state authed-image-loading ${className}`.trim()}
        role="img"
        aria-label={alt}
        aria-busy={loading}
      />
    );
  }

  return (
    <img
      className={className}
      src={src}
      alt={alt}
      // Ảnh cũ còn hiển thị trong lúc ảnh trang mới đang về — làm mờ để người
      // dùng biết cái đang nhìn chưa phải trang vừa chọn.
      data-loading={loading ? 'true' : undefined}
      {...imgProps}
    />
  );
}
