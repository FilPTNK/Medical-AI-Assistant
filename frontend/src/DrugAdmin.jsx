import React, { useState } from 'react';
import { CheckCircle2, Download, FileUp, ShieldCheck } from 'lucide-react';
import { apiJson } from './lib/apiClient';

const csvTemplate = [
  'id,name,aliases,drug_class,atc_code,source_title,source_url,source_page,dosage_form,indications,dosage,contraindications,warnings,adverse_effects,interactions,pregnancy,lactation,storage',
  ['ma-thuoc', 'Thay bằng tên thuốc', '', '', '', 'Thay bằng tên tài liệu', '', '', '',
    'Thay bằng nội dung đã đối chiếu', '', '', '', '', '', '', '', ''].join(','),
].join('\r\n');
const jsonTemplate = JSON.stringify([{
  id: 'ma-thuoc', name: 'Thay bằng tên thuốc', aliases: [],
  source_title: 'Thay bằng tên tài liệu', source_url: '', source_page: '',
  sections: [{ label: 'Chỉ định', text: 'Thay bằng nội dung đã đối chiếu.' }],
}], null, 2);

export default function DrugAdmin() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [published, setPublished] = useState(0);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  async function submit(publish) {
    const format = file?.name.toLowerCase().split('.').pop();
    if (format !== 'csv' && format !== 'json') {
      setError('Chọn một tệp .csv hoặc .json.');
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      setError('Tệp vượt quá giới hạn 8 MB.');
      return;
    }
    setBusy(publish ? 'publish' : 'preview');
    setError('');
    try {
      const result = await apiJson(`/api/admin/drug-import?file_format=${format}&publish=${publish}`, {
        method: 'POST', body: file,
      });
      if (publish) {
        setPublished(result.count);
        setPreview(null);
      } else {
        setPublished(0);
        setPreview(result);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  }

  return (
    <div className="fil-wrap fil-admin">
      <span className="fil-kicker"><ShieldCheck size={18} aria-hidden="true" /> Khu vực quản trị</span>
      <h1>Quản trị dữ liệu thuốc</h1>
      <p>Kiểm tra tệp CSV hoặc JSON rồi cập nhật danh mục tra cứu.</p>
      <div className="fil-admin-grid">
        <section className="fil-admin-panel">
          <h2><FileUp size={23} aria-hidden="true" /> Nhập dữ liệu</h2>
          <form onSubmit={event => { event.preventDefault(); submit(false); }}>
            <label htmlFor="catalog-file">Tệp danh mục thuốc</label>
            <input id="catalog-file" type="file" accept=".csv,.json" required disabled={Boolean(busy)}
              aria-describedby="catalog-file-help"
              onChange={event => {
                setFile(event.target.files[0] || null);
                setPreview(null);
                setPublished(0);
                setError('');
              }} />
            <p id="catalog-file-help">CSV hoặc JSON mã hóa UTF-8. Tối đa 8 MB và 5.000 bản ghi.</p>
            {error && <p className="fil-error" role="alert">{error}</p>}
            {!preview && <button className="fil-button" type="submit" disabled={!file || Boolean(busy) || published > 0}>
              {busy === 'preview' ? 'Đang kiểm tra…' : 'Kiểm tra tệp'}
            </button>}
          </form>
          {preview && (
            <div className="fil-import-preview">
              <h3>{preview.count.toLocaleString('vi-VN')} bản ghi hợp lệ</h3>
              <p>Mẫu tên thuốc và nguồn trong tệp</p>
              <ul>{preview.sample.map((row, index) => <li key={index}>{row.name} · {row.source_title}</li>)}</ul>
              <button className="fil-button" type="button" onClick={() => submit(true)} disabled={Boolean(busy)}>
                {busy === 'publish' ? 'Đang cập nhật…' : 'Cập nhật danh mục'}
              </button>
            </div>
          )}
          {published > 0 && <p className="fil-import-success" role="status">
            <CheckCircle2 size={20} aria-hidden="true" /> Đã cập nhật {published.toLocaleString('vi-VN')} bản ghi. <a href="/thuoc">Mở danh mục thuốc</a>
          </p>}
        </section>
        <aside className="fil-admin-panel">
          <h2>Mẫu dữ liệu</h2>
          <p>Mỗi bản ghi cần một mã ổn định, tên thuốc, tên nguồn và ít nhất một mục nội dung. Cùng mã sẽ cập nhật toàn bộ bản ghi đã nhập.</p>
          <p>Trong CSV, phân tách tên khác bằng dấu <code>|</code>. Trong JSON, dùng mảng <code>aliases</code>.</p>
          <div className="fil-template-links">
            <a href={`data:text/csv;charset=utf-8,${encodeURIComponent('\uFEFF' + csvTemplate)}`} download="mau-danh-muc-thuoc.csv"><Download size={17} aria-hidden="true" /> Mẫu CSV</a>
            <a href={`data:application/json;charset=utf-8,${encodeURIComponent(jsonTemplate)}`} download="mau-danh-muc-thuoc.json"><Download size={17} aria-hidden="true" /> Mẫu JSON</a>
          </div>
        </aside>
      </div>
    </div>
  );
}
