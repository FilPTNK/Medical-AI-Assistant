import { useEffect, useRef, useState } from 'react';
import { apiJson } from '../lib/apiClient';
import { readSseStream } from '../lib/sse';
import useWorkchat from './useWorkchat';

export default function useClinicalData(ownerId) {
  const workchat = useWorkchat(ownerId);
  const [apiKey, setApiKey] = useState(() => {
    try { return localStorage.getItem('deepseek_api_key') || ''; } catch { return ''; }
  });
  const [config, setConfig] = useState(null);
  const [sourceState, setSourceState] = useState({ ownerId: null, documents: [], error: '', loading: false });
  const documents = sourceState.ownerId === ownerId ? sourceState.documents : [];
  const documentError = sourceState.ownerId === ownerId ? sourceState.error : '';
  const documentsLoading = !!ownerId && (sourceState.ownerId !== ownerId || sourceState.loading);
  const [upload, setUpload] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const uploadRequest = useRef(null);
  const documentRequest = useRef(null);

  async function refreshDocuments() {
    documentRequest.current?.abort();
    const controller = new AbortController();
    documentRequest.current = controller;
    setSourceState(previous => ({ ownerId, documents: previous.ownerId === ownerId ? previous.documents : [], error: '', loading: true }));
    try {
      const list = await apiJson('/api/workchat/sources', { signal: controller.signal });
      if (!controller.signal.aborted) setSourceState({ ownerId, documents: list, error: '', loading: false });
    } catch (error) {
      if (!controller.signal.aborted) setSourceState(previous => ({ ...previous, error: error.message, loading: false }));
    }
  }

  function addNotification(message) {
    setNotifications(previous => [{ message, time: new Date(), unread: true }, ...previous].slice(0, 12));
  }

  async function uploadDocument(file, notify) {
    if (uploadRequest.current) return null;
    if (!/\.pdf$/i.test(file.name) || !file.size || file.size > 64 * 1024 * 1024) {
      setUpload({ error: 'Chọn tệp PDF có nội dung, tối đa 64 MiB.' });
      return null;
    }
    const controller = new AbortController();
    uploadRequest.current = controller;
    setUpload({ pending: true, name: file.name, stage: 'Đang tải lên…' });
    try {
      const body = new FormData();
      body.append('file', file);
      const { job_id, doc_name } = await apiJson('/api/documents/ingest?workchat=true', {
        method: 'POST', body, signal: controller.signal,
      });
      const response = await fetch(`/api/documents/ingest/${encodeURIComponent(job_id)}/events`, {
        signal: controller.signal,
      });
      if (!response.ok) throw new Error('Không theo dõi được tiến trình nạp PDF.');
      let finished;
      await readSseStream(response, (event, data) => {
        if (event === 'error' || data.status === 'error') {
          throw new Error(data.error || data.message || 'Không nạp được PDF.');
        }
        if (event !== 'progress') return;
        finished = data.status === 'done' ? data : finished;
        setUpload({
          pending: true, name: file.name, stage: data.stage,
          current: data.current, total: data.total,
        });
      });
      if (controller.signal.aborted) return null;
      if (!finished) throw new Error('Mất kết nối theo dõi. Tải lại danh sách tài liệu để kiểm tra.');
      const message = `Đã nạp ${file.name}.`;
      setUpload({ message });
      if (notify) addNotification(message);
      await refreshDocuments();
      return controller.signal.aborted ? null : { doc_name, doc_title: file.name };
    } catch (error) {
      if (!controller.signal.aborted) setUpload({ error: error.message });
      return null;
    } finally {
      if (uploadRequest.current === controller) uploadRequest.current = null;
    }
  }

  useEffect(() => {
    if (!ownerId) {
      setConfig(null);
      setSourceState({ ownerId: null, documents: [], error: '', loading: false });
      setUpload(null);
      setNotifications([]);
      return;
    }
    const controller = new AbortController();
    const options = { signal: controller.signal };
    const load = (path, save) => apiJson(path, options)
      .then(data => { if (!controller.signal.aborted) save(data); })
      .catch(error => { if (!controller.signal.aborted) console.error(error); });
    load('/api/config', setConfig);
    refreshDocuments();
    return () => {
      controller.abort();
      documentRequest.current?.abort();
      uploadRequest.current?.abort();
      uploadRequest.current = null;
    };
  }, [ownerId]);

  return {
    ...workchat, documents, apiKey, config,
    documentError, documentsLoading, refreshDocuments, upload, uploadDocument, notifications, addNotification,
    markNotificationsRead() {
      setNotifications(previous => previous.map(item => ({ ...item, unread: false })));
    },
    saveApiKey(value) {
      localStorage.setItem('deepseek_api_key', value);
      setApiKey(value);
    },
  };
}
