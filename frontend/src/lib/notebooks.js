import { foldWithMap } from './fold';

export const notebookHref = id => `/hoi-dap?${new URLSearchParams({ conversation: id })}`;

export function notebookActivity(notebook) {
  for (const date of [notebook.updatedAt, notebook.createdAt]) {
    if (date === undefined || date === null || date === '') continue;
    const time = new Date(date).getTime();
    if (Number.isFinite(time)) return time;
  }
  return 0;
}

export function citedSourceCount(notebook) {
  const sources = new Set();
  for (const message of notebook.messages || []) {
    for (const source of message.sources || []) {
      const identity = source.doc_name || source.url || source.link;
      if (identity) sources.add(identity);
    }
  }
  return sources.size;
}

export function recentNotebooks(conversations, { userId, query = '', sort = 'recent' } = {}) {
  if (!userId) return [];
  const term = foldWithMap(query.trim()).folded;
  return conversations
    .filter(item => item.id && !item.archived && (!item.ownerId || item.ownerId === userId))
    .filter(item => foldWithMap(`${item.title || ''} ${item.specialty || ''}`).folded.includes(term))
    .sort(sort === 'name'
      ? (a, b) => (a.title || '').localeCompare(b.title || '', 'vi')
      : (a, b) => notebookActivity(b) - notebookActivity(a));
}
