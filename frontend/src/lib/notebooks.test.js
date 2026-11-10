import { describe, expect, it } from 'vitest';
import { citedSourceCount, notebookActivity, notebookHref, recentNotebooks } from './notebooks';

describe('Recent notebooks', () => {
  const entries = [
    { id: 'older', title: 'Ca tim mạch', createdAt: 100 },
    { id: 'latest', title: 'Đau đầu', ownerId: 'doctor', createdAt: 150, updatedAt: 300 },
    { id: 'archived', title: 'Đã lưu trữ', archived: true, updatedAt: 400 },
    { id: 'other', title: 'Tài khoản khác', ownerId: 'other', updatedAt: 500 },
    { id: 'undated', title: 'Chưa đặt ngày', updatedAt: 'invalid' },
  ];

  it('shows actual unarchived history only after sign-in and retains legacy entries', () => {
    expect(recentNotebooks(entries)).toEqual([]);
    expect(recentNotebooks(entries, { userId: 'doctor' }).map(item => item.id)).toEqual(['latest', 'older', 'undated']);
    expect(entries[0].id).toBe('older');
  });

  it('searches Vietnamese titles and specialty names without requiring accents', () => {
    expect(recentNotebooks(entries, { userId: 'doctor', query: ' DAU dau ' }).map(item => item.id)).toEqual(['latest']);
    expect(recentNotebooks([{ id: 'specialty', title: 'Ca 1', specialty: 'Tai mũi họng' }], { userId: 'doctor', query: 'mui hong' })).toHaveLength(1);
  });

  it('supports alphabetical ordering and does not invent dates', () => {
    expect(recentNotebooks(entries, { userId: 'doctor', sort: 'name' }).map(item => item.id)).toEqual(['older', 'undated', 'latest']);
    expect(notebookActivity({})).toBe(0);
    expect(notebookActivity({ updatedAt: 'invalid' })).toBe(0);
    expect(notebookActivity({ updatedAt: 'invalid', createdAt: 100 })).toBe(100);
  });

  it('counts distinct cited documents, not pages or repeated citations', () => {
    expect(citedSourceCount({ messages: [
      { role: 'assistant', sources: [{ doc_name: 'book.pdf', page_num: 1 }, { doc_name: 'book.pdf', page_num: 2 }, { url: 'https://example.org/paper' }] },
      { role: 'assistant', sources: [{ doc_name: 'book.pdf' }, {}, { url: 'https://example.org/paper' }] },
    ] })).toBe(2);
    expect(citedSourceCount({ messages: [] })).toBe(0);
  });

  it('encodes the existing conversation identifier in the destination', () => {
    const url = new URL(notebookHref('a/b & c'), 'https://example.org');
    expect(url.pathname).toBe('/hoi-dap');
    expect(url.searchParams.get('conversation')).toBe('a/b & c');
  });
});
