import React, { useRef } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { BookOpen, Download, Eye, FileText, MoreHorizontal, Paperclip, Trash2, Upload, X } from 'lucide-react';
import { documentScopeLabel } from '../lib/library';

export default function ChatDocuments({
  clinical, readOnly, pickerOpen, setPickerOpen, onAttach, onUpload, onPreview, onDownload, onDelete,
}) {
  const inputRef = useRef(null);
  const attachUpload = useRef(false);
  const { documents, documentError, refreshDocuments, upload } = clinical;

  function chooseFile(attach) {
    attachUpload.current = attach;
    inputRef.current?.click();
  }

  return (
    <section className="fil-chat-documents" aria-labelledby="chat-documents-title">
      <h2 id="chat-documents-title"><BookOpen size={21} aria-hidden="true" /> Tài liệu y khoa</h2>
      <p>Tài liệu dùng để tra cứu và đối chứng câu trả lời.</p>
      {documentError && <div role="alert" className="fil-doc-status">
        {documentError} <button type="button" onClick={refreshDocuments}>Tải lại</button>
      </div>}
      {!documentError && documents.length === 0 && <p className="fil-chat-empty">Danh sách tài liệu đang trống.</p>}
      <ul className="fil-chat-doc-list">
        {documents.map(doc => (
          <li key={doc.doc_name} className="fil-chat-doc">
            <button type="button" className="fil-chat-doc-open" onClick={() => onPreview(doc)}>
              <span className="fil-pdf-icon"><FileText size={19} aria-hidden="true" /></span>
              <span><strong>{doc.doc_title || doc.doc_name}</strong>
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
                  <DropdownMenu.Item className="dropdown-menu-item" onSelect={() => onAttach(doc)}>
                    <Paperclip size={15} /> Đính kèm vào câu hỏi
                  </DropdownMenu.Item>
                  <DropdownMenu.Item className="dropdown-menu-item" onSelect={() => onDownload(doc.doc_name)}>
                    <Download size={15} /> Tải xuống PDF
                  </DropdownMenu.Item>
                  {!readOnly && doc.can_delete && <DropdownMenu.Item className="dropdown-menu-item danger" onSelect={() => onDelete(doc)}>
                    <Trash2 size={15} /> Xóa tài liệu
                  </DropdownMenu.Item>}
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
          </li>
        ))}
      </ul>
      {!readOnly && <>
        <input ref={inputRef} type="file" accept=".pdf,application/pdf" hidden onChange={event => {
          const file = event.target.files?.[0];
          event.target.value = '';
          if (!file) return;
          setPickerOpen(false);
          onUpload(file, attachUpload.current);
        }} />
        <button className="fil-tool-action fil-doc-upload" type="button" disabled={upload?.pending} onClick={() => chooseFile(false)}>
          <Upload size={17} aria-hidden="true" /> Thêm tài liệu (PDF)
        </button>
      </>}
      {upload && <div className="fil-doc-status" role={upload.error ? 'alert' : 'status'}>
        {upload.error || upload.message || `${upload.stage || 'Đang xử lý…'} · ${upload.name}`}
        {upload.pending && upload.total > 0 && <progress value={upload.current} max={upload.total} aria-label="Tiến độ nạp PDF" />}
      </div>}
      <Dialog.Root open={pickerOpen} onOpenChange={setPickerOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="dialog-content fil-attachment-dialog">
            <Dialog.Title className="dialog-title">Đính kèm PDF</Dialog.Title>
            <Dialog.Description className="dialog-description">
              Chọn một tài liệu để giới hạn câu hỏi tiếp theo trong tài liệu đó.
            </Dialog.Description>
            <div className="fil-attachment-list">
              {documents.map(doc => <button type="button" className="fil-tool-action" key={doc.doc_name} onClick={() => {
                setPickerOpen(false);
                onAttach(doc);
              }}><FileText size={17} aria-hidden="true" /> {doc.doc_title || doc.doc_name}</button>)}
              {documents.length === 0 && <p>Chưa có PDF để chọn.</p>}
            </div>
            <div className="dialog-actions">
              <Dialog.Close asChild><button type="button" className="btn-dialog-secondary"><X size={15} /> Đóng</button></Dialog.Close>
              {!readOnly && <button type="button" className="btn-dialog-secondary" disabled={upload?.pending} onClick={() => chooseFile(true)}>
                <Upload size={15} /> Tải PDF mới
              </button>}
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </section>
  );
}
