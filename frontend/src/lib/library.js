/** Các phép tính thuần của Thư viện; thứ tự và câu chữ giữ như App.jsx cũ. */
export const MAX_COMPARE_DOCS = 5;

export function filterAndSortDocuments(documents, search, sortBy) {
  return documents
    .filter(d => d.doc_name.toLowerCase().includes(search.trim().toLowerCase()))
    .sort((a, b) => {
      if (sortBy === 'name') return a.doc_name.localeCompare(b.doc_name);
      if (sortBy === 'pages') return (b.page_count || 0) - (a.page_count || 0);
      if (sortBy === 'oldest') return (a.uploaded_at || 0) - (b.uploaded_at || 0);
      return (b.uploaded_at || 0) - (a.uploaded_at || 0);
    });
}

export function toggleLibrarySelection(selected, docName) {
  if (selected.includes(docName)) {
    return { selected: selected.filter(d => d !== docName), limitReached: false };
  }
  if (selected.length >= MAX_COMPARE_DOCS) {
    return { selected, limitReached: true };
  }
  return { selected: [...selected, docName], limitReached: false };
}

export function uploadProgress(job) {
  return job.total > 0
    ? Math.round((job.current / job.total) * 100)
    : (job.status === 'done' ? 100 : 5);
}

export function libraryDescription(kind) {
  if (kind === 'empty') {
    return 'Tải lên tệp PDF đầu tiên để hệ thống lập chỉ mục và có thể tra cứu, trò chuyện dựa trên nội dung tài liệu.';
  }
  return 'Các sách và tài liệu gốc mà trợ lý dùng để trả lời. Bấm vào một cuốn để đọc từng trang.';
}

export function formatLibraryDate(epochSeconds) {
  if (!epochSeconds) return '';
  return new Date(epochSeconds * 1000).toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

/**
 * Nhãn phạm vi của tài liệu. Tài liệu bác sĩ tự tải là kho RIÊNG của tài khoản
 * đó; tài liệu do quản trị tải lên và sách tham khảo dùng chung cả phòng khám.
 * Người tải chỉ hiện với tài liệu chung — với tài liệu riêng thì luôn là chính mình.
 */
export function documentScopeLabel(doc) {
  if (doc.visibility === 'private') return 'Riêng của tôi';
  if (doc.source_type === 'self_uploaded') {
    return doc.uploaded_by ? `Tài liệu chung • ${doc.uploaded_by}` : 'Tài liệu chung';
  }
  return 'Sách tham khảo';
}
