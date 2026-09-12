/**
 * Đọc luồng Server-Sent Events từ một Response của fetch.
 *
 * Không dùng được `EventSource` của trình duyệt: nó chỉ biết gửi GET, không gắn
 * được header, và không hủy được theo `AbortSignal`. Đường tra cứu y văn cần cả
 * ba thứ đó — POST kèm câu hỏi, header khoá API, và nút dừng.
 *
 * @param {Response} response  kết quả fetch, phải còn body chưa đọc
 * @param {(event: string, data: any) => void} onEvent  gọi cho từng sự kiện
 */
export async function readSseStream(response, onEvent) {
  if (!response.body) throw new Error('Máy chủ không trả về luồng dữ liệu.');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      // stream: true là bắt buộc. Một ký tự tiếng Việt chiếm nhiều byte, và mẩu
      // dữ liệu có thể cắt ngang giữa chúng — giải mã từng mẩu độc lập sẽ sinh
      // ra ký tự thay thế ngay giữa câu trả lời.
      buffer += decoder.decode(value, { stream: true });

      // Một sự kiện kết thúc ở dòng trống. Chỉ xử lý những sự kiện đã trọn vẹn,
      // phần đuôi giữ lại trong buffer chờ mẩu sau.
      let sep;
      while ((sep = buffer.search(/\r?\n\r?\n/)) !== -1) {
        const block = buffer.slice(0, sep);
        buffer = buffer.slice(sep + buffer.match(/\r?\n\r?\n/)[0].length);
        const parsed = parseSseBlock(block);
        if (parsed) onEvent(parsed.event, parsed.data);
      }
    }
  } finally {
    // Hủy giữa luồng: nhả reader để kết nối đóng thật, nếu không server không
    // nhận được tín hiệu ngắt và vẫn chạy tới cùng.
    try { reader.releaseLock(); } catch { /* đã đóng rồi */ }
  }
}

function parseSseBlock(block) {
  let event = 'message';
  const dataLines = [];

  for (const raw of block.split(/\r?\n/)) {
    const line = raw.trimEnd();
    if (!line || line.startsWith(':')) continue;
    if (line.startsWith('event:')) {
      event = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).replace(/^ /, ''));
    }
  }

  if (dataLines.length === 0) return null;

  const raw = dataLines.join('\n');
  try {
    return { event, data: JSON.parse(raw) };
  } catch {
    return { event, data: raw };
  }
}
