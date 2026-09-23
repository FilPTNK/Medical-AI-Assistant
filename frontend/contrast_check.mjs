/**
 * Đo tương phản WCAG cho bộ token màu của cả hai chế độ.
 *
 * Không có test nào cho giao diện, nên đây là phép kiểm duy nhất bắt được lỗi
 * "chữ đúng màu nhưng không đọc được". Nó đọc thẳng hai khối token trong
 * index.css, nên đổi màu ở đó là chạy lại có số ngay.
 *
 *   node frontend/contrast_check.mjs
 *
 * Thoát với mã 1 nếu có cặp nào dưới ngưỡng, để cắm vào CI sau này được.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(join(here, 'src', 'index.css'), 'utf8');

/**
 * Gom MỌI khối có bộ chọn `selector`, không chỉ khối đầu tiên.
 *
 * index.css khai báo token ở nhiều chỗ: bảng màu chính ở đầu file, còn bộ
 * --node-* của cây chẩn đoán ở giữa file trong một khối `:root` thứ hai. Bản
 * đầu của script chỉ đọc khối đầu nên bốn nút của cây chẩn đoán không bao giờ
 * được đo.
 */
function readAllBlocks(selector) {
  const out = {};
  let from = 0;
  for (;;) {
    const start = css.indexOf(selector + ' {', from);
    if (start === -1) break;
    const end = css.indexOf('\n}', start);
    for (const m of css.slice(start, end).matchAll(/--([\w-]+)\s*:\s*([^;]+);/g)) {
      out[m[1]] = m[2].trim();
    }
    from = end + 1;
  }
  return out;
}

const light = readAllBlocks(':root');
const dark = { ...light, ...readAllBlocks('html.dark, .dark') };

/**
 * Giải một giá trị token về [r, g, b], đi theo var(--x) lồng nhau nếu cần.
 *
 * Chế độ tối dùng rất nhiều nền pha trong suốt, kiểu rgba(241,147,140,0.12).
 * Bản đầu của script này bỏ qua chúng, nghĩa là **ô Dị ứng ở chế độ tối hoàn
 * toàn không được đo** — đúng ô quan trọng nhất màn hình. Nay màu pha được
 * chồng lên `under` (thứ thật sự nằm dưới nó) rồi mới đo.
 */
function resolve(theme, value, under = null, depth = 0) {
  if (depth > 8) return null;
  const v = String(value).trim();

  const varRef = v.match(/^var\(\s*--([\w-]+)/);
  if (varRef) return resolve(theme, theme[varRef[1]], under, depth + 1);

  const rgba = v.match(/rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:[\s,/]+([\d.]+))?\s*\)/i);
  if (rgba) {
    const c = [+rgba[1], +rgba[2], +rgba[3]];
    const a = rgba[4] === undefined ? 1 : +rgba[4];
    if (a >= 1) return c;
    if (!under) return null;
    return c.map((ch, i) => Math.round(ch * a + under[i] * (1 - a)));
  }

  const hex = v.match(/#([0-9a-f]{8}|[0-9a-f]{6}|[0-9a-f]{3})\b/i);
  if (hex) {
    let h = hex[1];
    if (h.length === 3) h = h.split('').map((c) => c + c).join('');
    const c = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
    if (h.length === 8) {
      const a = parseInt(h.slice(6, 8), 16) / 255;
      if (!under) return null;
      return c.map((ch, i) => Math.round(ch * a + under[i] * (1 - a)));
    }
    return c;
  }
  return null; // gradient, none… — không đo được
}

function luminance([r, g, b]) {
  const f = (c) => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

function ratio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/**
 * Cặp cần đo. Mỗi dòng: [màu chữ, màu nền, ngưỡng, mô tả].
 *
 * Ngưỡng 4,5 là chữ thường theo WCAG AA. Ngưỡng 3,0 dùng cho chữ lớn và cho
 * ranh giới đồ hoạ (viền ô nhập, vạch mức độ) theo tiêu chí 1.4.11.
 */
const PAIRS = [
  // Đợt 4 — trình xem hai cột
  ['text-muted', 'bg-card', 4.5, 'nhãn cột ảnh scan / bản OCR'],
  ['text-primary', 'bg-card', 4.5, 'chữ OCR trong cột văn bản'],
  ['primary', 'bg-card', 4.5, 'chữ ghi chú "đã tô sáng"'],
  ['text-secondary', 'bg-card', 4.5, 'đoạn trích trong danh sách trang khớp'],
  ['primary', 'bg-card', 4.5, 'số trang trong danh sách trang khớp'],
  ['text-secondary', 'bg-sunk', 4.5, 'bảng báo phạm vi quyển sách'],
  ['text-on-fill', 'primary', 4.5, 'chữ trên nút Tìm'],
  ['text-primary', 'bg-card', 4.5, 'số trang trong ô nhảy trang'],
  // Đợt 3 — panel "AI đã đọc gì từ bệnh án" (tiền sử đã khử danh)
  ['text-primary', 'bg-sunk', 4.5, 'nhãn mở/gập panel tiền sử'],
  ['text-muted', 'bg-sunk', 4.5, 'chữ phụ "đã bỏ tên" trên panel tiền sử'],
  ['text-secondary', 'bg-card', 4.5, 'nội dung tiền sử nguyên văn'],
  ['text-primary', 'bg-hover', 4.5, 'nhãn panel tiền sử khi rê chuột'],
  ['border-active', 'bg-sunk', 3, 'vòng tiêu điểm trên panel tiền sử'],
  ['text-primary', 'bg-app', 4.5, 'chữ chính trên nền app'],
  ['text-primary', 'bg-card', 4.5, 'chữ chính trên thẻ'],
  ['text-primary', 'bg-sidebar', 4.5, 'chữ chính trên thanh bên'],
  ['text-secondary', 'bg-card', 4.5, 'chữ phụ trên thẻ'],
  ['text-secondary', 'bg-app', 4.5, 'chữ phụ trên nền app'],
  ['text-muted', 'bg-card', 4.5, 'chữ mờ trên thẻ'],
  ['text-muted', 'bg-app', 4.5, 'chữ mờ trên nền app'],
  ['primary', 'bg-card', 4.5, 'liên kết / nhấn trên thẻ'],
  ['primary', 'bg-app', 4.5, 'liên kết / nhấn trên nền app'],
  ['accent', 'bg-card', 4.5, 'xanh xác nhận trên thẻ'],
  ['danger', 'bg-card', 4.5, 'màu nguy hiểm trên thẻ'],
  ['warning', 'bg-card', 4.5, 'màu cảnh báo trên thẻ'],
  ['violet', 'bg-card', 4.5, 'màu tím trên thẻ'],
  ['text-on-fill', 'primary', 4.5, 'chữ trên nút chính'],
  ['text-on-fill', 'danger', 4.5, 'chữ trên nút nguy hiểm'],
  ['text-on-fill', 'accent', 4.5, 'chữ trên mảng xanh xác nhận'],
  ['text-on-fill', 'warning', 4.5, 'chữ trên mảng cảnh báo'],
  ['pp-red-text-strong', 'pp-red-bg', 4.5, 'chữ dị ứng trên nền đỏ nhạt'],
  ['pp-red-icon', 'pp-red-bg', 4.5, 'biểu tượng dị ứng trên nền đỏ nhạt'],
  ['pp-green-text-strong', 'pp-green-bg', 4.5, 'chữ trên nền xanh nhạt'],
  ['pp-orange-icon', 'pp-orange-bg', 4.5, 'biểu tượng trên nền cam nhạt'],
  ['pp-blue-icon', 'pp-blue-bg', 4.5, 'biểu tượng trên nền xanh nhạt'],
  ['pp-purple-icon', 'pp-purple-bg', 4.5, 'biểu tượng trên nền tím nhạt'],
  ['pp-neutral-icon', 'pp-neutral-bg', 4.5, 'biểu tượng ô trống'],
  ['pp-pill-green-text', 'pp-pill-green-bg', 4.5, 'chữ trên chip xanh'],
  ['pp-pill-gray-text', 'pp-pill-gray-bg', 4.5, 'chữ trên chip xám'],
  ['pp-badge-blue-text', 'pp-badge-blue-bg', 4.5, 'chữ trên huy hiệu xanh'],

  // Đợt 2 — tra cứu chảy dần. Khối báo lỗi nằm trong bong bóng trả lời, tức là
  // trên nền thẻ, nhưng tự tô nền riêng nên đo trên nền đó.
  ['text-primary', 'pp-orange-bg', 4.5, 'chữ khối "còn dùng được" trên nền cam nhạt'],
  ['text-secondary', 'pp-orange-bg', 4.5, 'dòng gợi ý trong khối "còn dùng được"'],
  ['text-secondary', 'pp-orange-bg', 4.5, 'chi tiết kỹ thuật trong khối "còn dùng được"'],
  ['pp-red-text-strong', 'pp-red-bg', 4.5, 'chữ khối lỗi hẳn'],
  ['text-secondary', 'pp-red-bg', 4.5, 'dòng gợi ý trong khối lỗi hẳn'],
  ['primary', 'bg-card', 4.5, 'con trỏ chữ đang chảy trên thẻ'],
  ['text-secondary', 'bg-card', 4.5, 'chữ nút dừng tra cứu'],
  ['pp-red-text', 'bg-card', 4.5, 'chữ nút dừng khi trỏ vào'],
  ['pp-orange-icon', 'bg-card', 4.5, 'cờ tên thuốc hỏng OCR trên thẻ nguồn'],
  ['pp-orange-icon', 'bg-right-panel', 4.5, 'cờ tên thuốc hỏng OCR ở cột nguồn'],
  // KHÔNG đo viền thẻ trang trí ở đây. Bản đầu của script có đo, và cả hai chế
  // độ đều "hỏng" ở mức 1,3:1. Nhưng đó là phép đo sai, không phải màu sai:
  // WCAG 1.4.11 đòi 3:1 cho ranh giới mà thiếu nó thì KHÔNG nhận ra được thành
  // phần. Thẻ ở đây đã tự phân biệt bằng nền khác sắc độ với nền app, nên viền
  // chỉ là đường tinh chỉnh. Ép mọi viền lên 3:1 sẽ cho ra một giao diện đầy
  // gạch đen. Thứ thật sự phải đạt là VÒNG TIÊU ĐIỂM bàn phím:
  ['border-active', 'bg-card', 3.0, 'vòng tiêu điểm bàn phím trên thẻ'],
  ['border-active', 'bg-app', 3.0, 'vòng tiêu điểm bàn phím trên nền app'],
  ['primary', 'bg-sidebar', 3.0, 'mục đang chọn ở thanh bên'],
  ['node-high-text', 'node-high-bg', 4.5, 'nút cây chẩn đoán — cao'],
  ['node-med-text', 'node-med-bg', 4.5, 'nút cây chẩn đoán — vừa'],
  ['node-low-text', 'node-low-bg', 4.5, 'nút cây chẩn đoán — thấp'],
  ['node-root-text', 'node-root-bg', 4.5, 'nút cây chẩn đoán — gốc'],

  // Đợt 5 — khối đối chiếu dị ứng trên phiếu khám.
  // Khối tự tô nền theo mức khớp, nên chữ nằm trên nền TINH chứ không phải
  // nền thẻ. Đó đúng là chỗ đợt giao diện trước đã bắt được lỗi: một màu chữ
  // đạt trên nền thẻ vẫn có thể tụt xuống dưới ngưỡng trên nền có sắc độ.
  ['pp-red-text-strong', 'pp-red-bg', 4.5, 'tiêu đề khối dị ứng mức trùng hoạt chất'],
  ['text-secondary', 'pp-red-bg', 4.5, 'dòng "bệnh án ghi:" trên nền đỏ nhạt'],
  ['text-primary', 'pp-red-bg', 4.5, 'chữ nguyên văn ô dị ứng trên nền đỏ nhạt'],
  // KHÔNG có cặp text-muted trên nền tinh. Đã thử và đo: 4,14:1 trên nền đỏ
  // nhạt, 4,10:1 trên nền cam nhạt — cả hai trượt. Nền tinh sáng hơn nền thẻ
  // nên chữ nhạt tụt qua ngưỡng ở đúng chỗ này; khối dùng text-secondary.
  ['text-primary', 'pp-orange-bg', 4.5, 'tiêu đề khối dị ứng mức chéo nhóm'],
  ['text-secondary', 'pp-orange-bg', 4.5, 'dòng "bệnh án ghi:" trên nền cam nhạt'],
  ['text-primary', 'pp-neutral-bg', 4.5, 'tiêu đề khối "chưa đối chiếu được"'],
  ['text-secondary', 'pp-neutral-bg', 4.5, 'lời giải thích khối "chưa đối chiếu được"'],
  ['pp-neutral-icon', 'pp-neutral-bg', 4.5, 'biểu tượng khối "chưa đối chiếu được"'],
  ['text-muted', 'bg-sunk', 4.5, 'chữ mờ khối "không khớp gì trong phần đọc được"'],
  // Dòng từng thuốc tự tô nền bg-card ĐÈ LÊN nền tinh của khối, nên nhãn mức
  // phải đo trên bg-card chứ không phải trên nền khối.
  ['pp-red-text', 'bg-card', 4.5, 'nhãn "TRÙNG HOẠT CHẤT" / "CÙNG NHÓM"'],
  ['pp-orange-icon', 'bg-card', 4.5, 'nhãn "CHÉO NHÓM" trên dòng thuốc'],
  ['text-primary', 'bg-card', 4.5, 'tên thuốc và tỉ lệ chéo đo được'],
  ['text-secondary', 'bg-card', 4.5, 'lý do khớp trên dòng thuốc'],
  ['text-muted', 'bg-card', 4.5, 'nguồn y văn trên dòng thuốc'],
  // Vòng tiêu điểm của nút gập nằm trên nền tinh của khối.
  ['border-active', 'pp-red-bg', 3.0, 'vòng tiêu điểm nút gập trên nền đỏ nhạt'],
  ['border-active', 'pp-orange-bg', 3.0, 'vòng tiêu điểm nút gập trên nền cam nhạt'],
  ['border-active', 'pp-neutral-bg', 3.0, 'vòng tiêu điểm nút gập trên nền trung tính'],
];

let failed = 0;
let skipped = 0;

for (const [label, theme] of [['SÁNG', light], ['TỐI', dark]]) {
  console.log(`\n=== Chế độ ${label} ===`);
  for (const [fg, bg, min, desc] of PAIRS) {
    // Các nền pha trong suốt đều nằm trên thẻ, nên thẻ là lớp dưới của chúng.
    const card = resolve(theme, theme['bg-card']);
    const b = resolve(theme, theme[bg], card);
    const a = resolve(theme, theme[fg], b);
    if (!a || !b) {
      console.log(`  BỎ QUA  ${desc} (${fg} / ${bg} không giải được về màu)`);
      skipped++;
      continue;
    }
    const r = ratio(a, b);
    const ok = r >= min;
    if (!ok) failed++;
    const mark = ok ? 'ĐẠT  ' : 'HỎNG ';
    console.log(`  ${mark} ${r.toFixed(2).padStart(5)}:1  (cần ${min})  ${desc}`);
  }
}

console.log(`\nHỏng: ${failed} · Bỏ qua vì nền trong suốt: ${skipped}`);
process.exit(failed > 0 ? 1 : 0);
