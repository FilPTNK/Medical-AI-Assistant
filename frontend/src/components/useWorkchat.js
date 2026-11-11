import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiJson, apiSend } from '../lib/apiClient';
import { turnMessages } from '../lib/workchat';

const THREADS = '/api/workchat/threads';
const urlFor = id => THREADS + '/' + encodeURIComponent(id);
const isServerThread = id => /^wc-[a-f0-9]{32}$/.test(id || '');

function readLegacy() {
  try {
    const saved = JSON.parse(localStorage.getItem('med_conversations'));
    return Array.isArray(saved) ? saved.filter(item => item?.id && Array.isArray(item.messages)) : [];
  } catch { return []; }
}

export default function useWorkchat(ownerId) {
  const [legacy, setLegacy] = useState(readLegacy);
  const [remote, setRemote] = useState({ ownerId: null, items: [], error: '', loading: false });
  const listRequest = useRef(null);
  const revision = useRef(0);
  const ownerRef = useRef(ownerId);
  ownerRef.current = ownerId;

  useEffect(() => {
    try { localStorage.setItem('med_conversations', JSON.stringify(legacy)); } catch { /* Keep history for this tab. */ }
  }, [legacy]);

  const loadList = useCallback(async () => {
    listRequest.current?.abort();
    if (!ownerId) {
      setRemote({ ownerId: null, items: [], error: '', loading: false });
      return;
    }
    const controller = new AbortController();
    listRequest.current = controller;
    const startedAt = revision.current;
    setRemote(previous => ({ ownerId, items: previous.ownerId === ownerId ? previous.items : [], error: '', loading: true }));
    try {
      const items = await apiJson(THREADS, { signal: controller.signal });
      if (controller.signal.aborted || ownerRef.current !== ownerId) return;
      if (revision.current !== startedAt) return loadList();
      setRemote(previous => ({
        ownerId, error: '', loading: false,
        items: items.filter(item => item.ownerId === ownerId).map(item => ({
          ...previous.items.find(current => current.id === item.id), ...item,
        })),
      }));
    } catch (error) {
      if (controller.signal.aborted || ownerRef.current !== ownerId) return;
      setRemote(previous => ({ ...previous, error: error.message, loading: false }));
    }
  }, [ownerId]);

  useEffect(() => {
    loadList();
    return () => listRequest.current?.abort();
  }, [loadList]);

  const conversations = useMemo(() => [
    ...(ownerId && remote.ownerId === ownerId ? remote.items : []),
    ...legacy.filter(item => ownerId && item.ownerId === ownerId),
  ], [ownerId, remote, legacy]);

  function patchRemote(summary, edit = item => item) {
    if (summary.ownerId !== ownerId || ownerRef.current !== ownerId) return;
    revision.current += 1;
    setRemote(previous => {
      const state = previous.ownerId === ownerId ? previous : { ownerId, items: [], error: '', loading: false };
      const match = state.items.find(item => item.id === summary.id);
      const updated = edit({ ...match, ...summary });
      return { ...state, items: [updated, ...state.items.filter(item => item.id !== summary.id)] };
    });
  }

  async function createConversation({ title, specialty }, { signal } = {}) {
    const summary = await apiJson(THREADS, {
      method: 'POST', signal, headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, specialty: specialty || null }),
    });
    const item = { ...summary, messages: [] };
    patchRemote(item);
    return item;
  }

  async function readConversation(id, { signal } = {}) {
    if (!isServerThread(id)) return conversations.find(item => item.id === id) || null;
    const { turns, ...summary } = await apiJson(urlFor(id), { signal });
    const messages = turns.flatMap(turnMessages);
    if (!signal?.aborted) patchRemote({ ...summary, messages });
    return { ...summary, messages };
  }

  async function updateConversation(id, patch) {
    if (isServerThread(id)) {
      patchRemote(await apiSend(urlFor(id), 'PATCH', patch));
    } else {
      setLegacy(previous => previous.map(item => item.id === id && item.ownerId === ownerId ? { ...item, ...patch } : item));
    }
  }

  async function removeConversation(id) {
    if (isServerThread(id)) {
      await apiSend(urlFor(id), 'DELETE');
      revision.current += 1;
      setRemote(previous => previous.ownerId === ownerId
        ? { ...previous, items: previous.items.filter(item => item.id !== id) } : previous);
    } else {
      setLegacy(previous => previous.filter(item => item.id !== id || item.ownerId !== ownerId));
    }
  }

  async function changeAll(action) {
    await apiSend(action === 'archive' ? '/api/workchat/archive-all' : THREADS, action === 'archive' ? 'POST' : 'DELETE');
    revision.current += 1;
    const edit = items => action === 'archive' ? items.map(item => ({ ...item, archived: true, pinned: false })) : [];
    setRemote(previous => previous.ownerId === ownerId ? { ...previous, items: edit(previous.items) } : previous);
    setLegacy(previous => [...previous.filter(item => item.ownerId !== ownerId),
      ...edit(previous.filter(item => item.ownerId === ownerId))]);
  }

  async function exportConversations() {
    const summaries = await apiJson(THREADS);
    const exported = legacy.filter(item => item.ownerId === ownerId);
    for (let i = 0; i < summaries.length; i += 4) {
      if (ownerRef.current !== ownerId) throw new Error('Phiên đăng nhập đã thay đổi.');
      const group = await Promise.all(summaries.slice(i, i + 4).map(async item => {
        const { turns, ...summary } = await apiJson(urlFor(item.id));
        return { ...summary, messages: turns.flatMap(turnMessages) };
      }));
      exported.push(...group);
    }
    if (ownerRef.current !== ownerId) throw new Error('Phiên đăng nhập đã thay đổi.');
    return exported;
  }

  return {
    conversations, createConversation, readConversation, updateConversation, removeConversation,
    changeAll, exportConversations, refreshConversations: loadList,
    conversationError: remote.ownerId === ownerId ? remote.error : '',
    conversationsLoading: !!ownerId && (remote.ownerId !== ownerId || remote.loading),
    setLegacyConversations: setLegacy,
    acceptTurn(summary, turn) {
      patchRemote(summary, item => ({
        ...item, messages: [...(item.messages || []).filter(message => message.turnId !== turn.id), ...turnMessages(turn)],
      }));
    },
  };
}
