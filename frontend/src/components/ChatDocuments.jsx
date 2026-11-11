import React, { useRef, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { Download, Eye, FileText, MoreHorizontal, PanelLeftClose, PanelLeftOpen, Plus, Trash2, Upload, X } from 'lucide-react';
import { documentScopeLabel } from '../lib/library';

export default function ChatDocuments({
  clinical, readOnly, pickerOpen, setPickerOpen, selectedNames, onToggleSource, onToggleAll,
  onUpload, onPreview, onDownload, onDelete,
}) {
  const inputRef = useRef(null);
  const [collapsed, setCollapsed] = useState(false);
  const { documents, documentError, documentsLoading, refreshDocuments, upload } = clinical;
  const allSelected = documents.length > 0 && selectedNames.length === documents.length;
  const someSelected = selectedNames.length > 0 && !allSelected;

  function chooseFile() {
    inputRef.current?.click();
  }

  return (
    <section className="fil-chat-documents" aria-labelledby="chat-documents-title">
      <div className="fil-source-heading">
        <h2 id="chat-documents-title">Nguồn tài liệu</h2>
        <button type="button" className="fil-source-collapse" aria-label={collapsed ? 'Mở danh sách nguồn' : 'Thu gọn danh sách nguồn'}
          aria-expanded={!collapsed} aria-controls="fil-source-content" onClick={() => setCollapsed(value => !value)}>
          {collapsed ? <PanelLeftOpen size={19} /> : <PanelLeftClose size={19} />}
        </button>
      </div>
      <div id="fil-source-content" hidden={collapsed}>
      <button className="fil-source-add" type="button" disabled={upload?.pending}
        onClick={() => readOnly ? setPickerOpen(true) : chooseFile()}>
        <Plus size={20} aria-hidden="true" /> Thêm nguồn
      </button>
      {documentError && <div role="alert" className="fil-doc-status">
        {documentError} <button type="button" onClick={refreshDocuments}>Tải lại</button>
      </div>}
      {documentsLoading && <p className="fil-chat-empty" role="status">Đang tải nguồn…</p>}
      {!documentError && !documentsLoading && documents.length === 0 && <p className="fil-chat-empty">Chưa có PDF để đối chiếu.</p>}
      {documents.length > 0 && <div className="fil-source-select-all">
        <span aria-live="polite">{selectedNames.length} nguồn đã chọn</span>
        <label>Chọn tất cả <input ref={element => {
          if (element) element.indeterminate = someSelected;
        }} type="checkbox" checked={allSelected} onChange={() => onToggleAll(!allSelected)} /></label>
      </div>}
      <ul className="fil-chat-doc-list" aria-label="Nguồn dùng để trả lời">
        {documents.map(doc => (
          <li key={doc.doc_name} className="fil-chat-doc">
            <button type="button" className="fil-chat-doc-open" onClick={() => onPreview(doc)}>
              <span className="fil-pdf-icon"><FileText size={19} aria-hidden="true" /></span>
              <span><strong title={doc.doc_title || doc.doc_name}>{doc.doc_title || doc.doc_name}</strong>
                <small>{[doc.page_count && `${doc.page_count} trang`, documentScopeLabel(doc)].filter(Boolean).join(' · ')}</small>
              </span>
            </button>
            <DropdownMenu.Root>
              <DropdownMenu.Trigger className="fil-chat-doc-menu" aria-label={`Tùy chọn ${doc.doc_title || doc.doc_name}`}>
                <MoreHorizontal size={17} aria-hidden="true" />
              </DropdownMenu.Trigger>
              <DropdownMenu.Portal>
                <DropdownMenu.Content className="dropdown-menu-content" align="end" sideOffset={5}>
                  <DropdownMenu.Item className="dropdown-menu-item" onSelect={() => onPreview(doc)}>
                    <Eye size={15} /> Xem tài liệu
                  </DropdownMenu.Item>
                  {onDownload && <DropdownMenu.Item className="dropdown-menu-item" onSelect={() => onDownload(doc.doc_name)}>
                    <Download size={15} /> Tải xuống PDF
                  </DropdownMenu.Item>}
                  {!readOnly && doc.can_delete && <DropdownMenu.Item className="dropdown-menu-item danger" onSelect={() => onDelete(doc)}>
                    <Trash2 size={15} /> Xóa tài liệu
                  </DropdownMenu.Item>}
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
            <label className="fil-source-check">
              <span className="sr-only">Dùng nguồn {doc.doc_title || doc.doc_name}</span>
              <input type="checkbox" checked={selectedNames.includes(doc.doc_name)} onChange={() => onToggleSource(doc.doc_name)} />
            </label>
          </li>
        ))}
      </ul>
      {!readOnly && <>
        <input ref={inputRef} type="file" accept=".pdf,application/pdf" hidden onChange={event => {
          const file = event.target.files?.[0];
          event.target.value = '';
          if (!file) return;
          setPickerOpen(false);
          onUpload(file);
        }} />
      </>}
      {upload && <div className="fil-doc-status" role={upload.error ? 'alert' : 'status'}>
        {upload.error || upload.message || `${upload.stage || 'Đang xử lý…'} · ${upload.name}`}
        {upload.pending && upload.total > 0 && <progress value={upload.current} max={upload.total} aria-label="Tiến độ nạp PDF" />}
      </div>}
      </div>
      <Dialog.Root open={pickerOpen} onOpenChange={setPickerOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="dialog-content fil-attachment-dialog">
            <Dialog.Title className="dialog-title">Nguồn tài liệu</Dialog.Title>
            <Dialog.Description className="dialog-description">
              Chọn các tài liệu được dùng để trả lời. Bạn cũng có thể quản lý nguồn ở cột bên trái.
            </Dialog.Description>
            <div className="fil-attachment-list">
              {documents.map(doc => <label className="fil-source-picker-row" key={doc.doc_name}>
                <FileText size={18} aria-hidden="true" />
                <span>{doc.doc_title || doc.doc_name}</span>
                <input type="checkbox" checked={selectedNames.includes(doc.doc_name)} onChange={() => onToggleSource(doc.doc_name)} />
              </label>)}
              {documents.length === 0 && <p>{documentsLoading ? 'Đang tải nguồn…' : 'Chưa có PDF để chọn.'}</p>}
            </div>
            <div className="dialog-actions">
              <Dialog.Close asChild><button type="button" className="btn-dialog-secondary"><X size={15} /> Đóng</button></Dialog.Close>
              {!readOnly && <button type="button" className="btn-dialog-secondary" disabled={upload?.pending} onClick={chooseFile}>
                <Upload size={15} /> Tải PDF mới
              </button>}
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </section>
  );
}
