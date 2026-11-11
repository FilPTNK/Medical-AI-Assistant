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
  const response = await fetch('/api/workchat/threads/' + encodeURIComponent(id) + '/turns', {
    method: 'POST', headers, signal, body: JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(typeof data?.detail === 'string' ? data.detail : 'Kiểm tra nội dung câu hỏi rồi gửi lại.');
  }
  let completed;
  await readSseStream(response, (event, data) => {
    if (event === 'error') throw new Error(data.message || 'Lượt hỏi chưa hoàn tất.');
    if (event === 'status') onStatus?.(data);
    if (event === 'turn') completed = data;
  });
  if (!completed?.thread || !completed?.turn) throw new Error('Mất kết nối trước khi nhận kết quả. Bạn có thể gửi lại.');
  return completed;
}
