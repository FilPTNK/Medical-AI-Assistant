import { describe, it, expect } from 'vitest';
import {
  MAX_COMPARE_DOCS, filterAndSortDocuments, toggleLibrarySelection,
  uploadProgress, libraryDescription, formatLibraryDate, documentScopeLabel
} from './library';

const docs = [
  { doc_name: 'B.pdf', page_count: 5, uploaded_at: 200 },
  { doc_name: 'A.pdf', page_count: 9, uploaded_at: 100 },
  { doc_name: 'C.pdf', page_count: 1, uploaded_at: 300 },
];

describe('Thư viện: logic không phụ thuộc DOM', () => {
  it('lọc không phân biệt hoa thường và không sửa mảng đầu vào', () => {
    const copy = [...docs];
    expect(filterAndSortDocuments(docs, '  a.PDF ', 'newest').map(d => d.doc_name)).toEqual(['A.pdf']);
    expect(docs).toEqual(copy);
    expect(filterAndSortDocuments(docs, '', 'newest').map(d => d.doc_name)).toEqual(['C.pdf', 'B.pdf', 'A.pdf']);
  });

  it('giữ mọi chế độ sắp xếp khi số trang hoặc ngày trống', () => {
    expect(filterAndSortDocuments(docs, '', 'oldest').map(d => d.doc_name)).toEqual(['A.pdf', 'B.pdf', 'C.pdf']);
    expect(filterAndSortDocuments(docs, '', 'name').map(d => d.doc_name)).toEqual(['A.pdf', 'B.pdf', 'C.pdf']);
    expect(filterAndSortDocuments(docs, '', 'pages').map(d => d.doc_name)).toEqual(['A.pdf', 'B.pdf', 'C.pdf']);
    expect(filterAndSortDocuments([{ doc_name: 'Z' }, ...docs], '', 'pages')[3].doc_name).toBe('Z');
  });

  it('chặn lựa chọn thứ sáu nhưng vẫn bỏ chọn được khi đã đủ năm', () => {
    const selected = Array.from({ length: MAX_COMPARE_DOCS }, (_, i) => `doc-${i}`);
    const blocked = toggleLibrarySelection(selected, 'doc-5');
    expect(blocked).toEqual({ selected, limitReached: true });
    expect(blocked.selected).toBe(selected);
    expect(toggleLibrarySelection(selected, 'doc-2')).toEqual({
      selected: ['doc-0', 'doc-1', 'doc-3', 'doc-4'], limitReached: false
    });
    expect(toggleLibrarySelection(['doc-1'], 'doc-2')).toEqual({
      selected: ['doc-1', 'doc-2'], limitReached: false
    });
  });

  it('giữ phần trăm SSE, kể cả tổng trang chưa biết', () => {
    expect(uploadProgress({ current: 3, total: 8, status: 'running' })).toBe(38);
    expect(uploadProgress({ current: 0, total: 0, status: 'done' })).toBe(100);
    expect(uploadProgress({ current: 0, total: 0, status: 'queued' })).toBe(5);
  });

  it('câu mô tả và ngày hiển thị', () => {
    expect(libraryDescription('header')).toContain('sách và tài liệu gốc');
    expect(libraryDescription('empty')).toContain('Tải lên tệp PDF đầu tiên');
    expect(formatLibraryDate(null)).toBe('');
    expect(formatLibraryDate(0)).toBe('');
  });
});

describe('Thư viện: phạm vi tài liệu', () => {
  it('phân biệt tài liệu riêng, tài liệu chung và sách tham khảo', () => {
    expect(documentScopeLabel({ visibility: 'private', source_type: 'self_uploaded', uploaded_by: 'BS A' })).toBe('Riêng của tôi');
    expect(documentScopeLabel({ visibility: 'shared', source_type: 'self_uploaded', uploaded_by: 'Quản trị' })).toBe('Tài liệu chung • Quản trị');
    expect(documentScopeLabel({ visibility: 'shared', source_type: 'self_uploaded' })).toBe('Tài liệu chung');
    expect(documentScopeLabel({ source_type: 'reference' })).toBe('Sách tham khảo');
  });
});
