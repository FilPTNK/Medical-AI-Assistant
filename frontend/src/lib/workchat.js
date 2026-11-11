import { readSseStream } from './sse';

export function turnMessages(turn) {
  const time = new Date(turn.createdAt).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
  const { reply, attachment } = turn;
  return [
    { role: 'user', text: turn.question, time, turnId: turn.id, ...(attachment ? { attachment } : {}) },
    { role: 'assistant', text: reply.text || '', time, turnId: turn.id, sources: reply.sources || [], workchat: reply },
  ];
}

export async function sendWorkchatTurn(id, body, { signal, apiKey, onStatus } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (apiKey) headers['X-DeepSeek-Key'] = apiKey;
  const url = id ? '/api/workchat/threads/' + encodeURIComponent(id) + '/turns' : '/api/workchat/guest/turns';
  const response = await fetch(url, {
    method: 'POST', headers, signal, body: JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(typeof data?.detail === 'string' ? data.detail : 'Chưa kết nối được Hỏi đáp y khoa. Hãy thử lại sau.');
  }
  let completed;
  await readSseStream(response, (event, data) => {
    if (event === 'error') throw new Error(data.message || 'Lượt hỏi chưa hoàn tất.');
    if (event === 'status') onStatus?.(data);
    if (event === 'turn') completed = data;
  });
  if (!completed?.turn || (id && !completed.thread)) throw new Error('Mất kết nối trước khi nhận kết quả. Bạn có thể gửi lại.');
  return completed;
}
