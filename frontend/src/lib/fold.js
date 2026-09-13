// Gấp dấu tiếng Việt — bản JS của backend/text_fold.py. Hai bên PHẢI cùng luật,
// nếu không thì backend bảo trang 297 có khớp mà trình xem lại không tô sáng
// được chỗ nào, và bác sĩ không biết tin bên nào.
//
// đ (U+0111) và Đ (U+0110) là CHỮ CÁI riêng, không phải d có dấu: NFD không hề
// đụng tới chúng, nên phải thay bằng bảng tra TRƯỚC. Đây cũng là bước cứu được
// đúng lớp hỏng OCR của kho này — bản scan làm rụng nét ngang của đ, sinh ra
// "Giảm dau"; đo trên Dược thư Quyển 1, riêng cụm "đau đầu" có 33 trang chỉ tìm
// thấy được nhờ bước này.
//
// GỘP KHOẢNG TRẮNG: mọi chuỗi dấu cách/xuống dòng liên tiếp về đúng một dấu
// cách. Đo mới thấy là bắt buộc — chữ OCR vắt dòng giữa câu, nên đoạn trích
// liền mạch "Thường gặp TKTW" không khớp nổi trang ghi "Thường gặp\nTKTW".

const D_MAP = { 'đ': 'd', 'Đ': 'D' };

/**
 * Chuỗi đã gấp, kèm bảng chỉ số: ký tự thứ i của chuỗi đã gấp nằm ở đâu trong
 * chuỗi GỐC. Cần để tô sáng đúng chỗ trên chữ CÒN NGUYÊN DẤU — bác sĩ đọc bản
 * gốc, không đọc bản đã bỏ dấu.
 *
 * Gấp từng ký tự một chứ không gấp cả chuỗi rồi suy ngược theo độ dài: một ký
 * tự có thể nở ra hoặc biến mất khi chuẩn hoá, nên suy theo độ dài sai đúng ở
 * những chỗ khó nhất.
 */
export function foldWithMap(s) {
  let folded = '';
  const map = [];
  let prevSpace = false;
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    if (/\s/.test(ch)) {
      if (!prevSpace && folded.length > 0) {
        folded += ' ';
        map.push(i);
        prevSpace = true;
      }
      continue;
    }
    const piece = (D_MAP[ch] || ch).normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
    for (const c of piece) {
      folded += c;
      map.push(i);
    }
    prevSpace = false;
  }
  if (folded.endsWith(' ')) {
    folded = folded.slice(0, -1);
    map.pop();
  }
  return { folded, map };
}

/** Bỏ dấu + hạ chữ thường + gộp khoảng trắng, để so khớp. */
export function fold(s) {
  if (!s) return '';
  return foldWithMap(s).folded;
}

/**
 * Mọi khoảng [start, end) trong chuỗi GỐC khớp với `query` sau khi gấp dấu.
 * Trả về mảng rỗng nếu không có gì — người gọi cứ hiển thị chữ như thường.
 */
export function findMatches(text, query, limit = 200) {
  const needle = fold(query || '');
  if (!text || !needle) return [];
  const { folded, map } = foldWithMap(text);
  const out = [];
  let from = 0;
  while (out.length < limit) {
    const hit = folded.indexOf(needle, from);
    if (hit === -1) break;
    const start = map[hit];
    const endIdx = Math.min(hit + needle.length, map.length) - 1;
    out.push({ start, end: map[endIdx] + 1 });
    from = hit + needle.length;
  }
  return out;
}

/**
 * Tìm một mỏ neo từ đoạn trích của kết quả tìm kiếm sang chữ của trang.
 *
 * Đoạn chunk trong chỉ mục KHÔNG khớp từng byte với chữ của trang: chunk được
 * cắt theo ranh giới riêng, và hai đường đọc chữ (chỉ mục vs endpoint trang)
 * có thể lệch nhau vài ký tự. Nên thử cả câu trước, rồi ngắn dần theo TỪ cho
 * tới khi có chỗ khớp — bản rút gọn của lối neo mờ mà Hypothesis dùng cho
 * TextQuoteSelector của W3C: neo theo NỘI DUNG, không theo vị trí.
 *
 * Bỏ qua vài từ ĐẦU nếu cần: chunk hay bị cắt ngang giữa một từ ("ộ amiodaron",
 * "in (các"), nên từ đầu tiên thường là mảnh vỡ không tồn tại trên trang.
 *
 * Đo trên 300 chunk thật của Dược thư Quyển 1, tỉ lệ neo được:
 *     neo thô, chưa gộp khoảng trắng          79,3%
 *     + gộp khoảng trắng                      88,3%
 *     + bỏ tới 3 từ đầu có thể là mảnh vỡ     90,7%
 * Gần 9% còn trượt là những chunk mà chữ khác hẳn chữ của trang tương ứng —
 * với chúng thì không tô sáng gì, đúng như thiết kế.
 *
 * Trả về '' khi không neo được. Không neo được thì thà không tô sáng gì, còn
 * hơn tô sáng nhầm chỗ — trong app này một đoạn sai trông y hệt một đoạn đúng.
 */
export function bestAnchor(pageText, quote, { maxWords = 16, minWords = 3, maxSkip = 3 } = {}) {
  if (!pageText || !quote) return '';
  const words = quote.trim().split(/\s+/).filter(Boolean);
  if (words.length < minWords) return '';
  for (let skip = 0; skip <= maxSkip; skip++) {
    const rest = words.slice(skip);
    if (rest.length < minWords) break;
    for (let n = Math.min(rest.length, maxWords); n >= minWords; n--) {
      const candidate = rest.slice(0, n).join(' ');
      if (findMatches(pageText, candidate, 1).length > 0) return candidate;
    }
  }
  return '';
}
