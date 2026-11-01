import React from 'react';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import CompareView from './CompareView';
import { AlertCircle, CheckCircle2, Square, MoreHorizontal, Eye, Download, Trash2, Search, LayoutGrid, List, GitCompareArrows, Upload, Loader2, FileText, PencilLine, Scale, X } from 'lucide-react';
import { filterAndSortDocuments, toggleLibrarySelection, uploadProgress, libraryDescription, formatLibraryDate, documentScopeLabel, MAX_COMPARE_DOCS } from '../lib/library';

// Trạng thái ở App để chuyển tab không làm mất bộ lọc hay tài liệu đang chọn.
export default function LibraryView({
  documents,
  documentsError,
  fetchDocuments,
  librarySearch,
  setLibrarySearch,
  librarySortBy,
  setLibrarySortBy,
  libraryViewMode,
  setLibraryViewMode,
  librarySelectMode,
  setLibrarySelectMode,
  librarySelectedDocs,
  setLibrarySelectedDocs,
  showComparePanel,
  setShowComparePanel,
  compareViewRef,
  fileInputRef,
  uploadJobs,
  uploading,
  handleFileUpload,
  dismissUploadJob,
  highlightCounts,
  handleOpenLibraryPreview,
  handleDownloadDocument,
  setDeleteDocTarget,
  apiKey,
  showStatus,
}) {
  const filteredLibraryDocs = filterAndSortDocuments(documents, librarySearch, librarySortBy);

  const toggleLibrarySelect = (docName) => {
    setLibrarySelectedDocs(prev => {
      const result = toggleLibrarySelection(prev, docName);
      if (result.limitReached) showStatus('error', `Chỉ đối chiếu tối đa ${MAX_COMPARE_DOCS} tài liệu cùng lúc.`);
      return result.selected;
    });
  };
  const handleLibraryCardClick = (docName) => {
    if (librarySelectMode) toggleLibrarySelect(docName);
    else handleOpenLibraryPreview(docName, 1);
  };
  const exitLibrarySelectMode = () => {
    setLibrarySelectMode(false);
    setLibrarySelectedDocs([]);
    setShowComparePanel(false);
  };
  const checkbox = (doc) => (
    <button
      type="button"
      className={`lib-select-checkbox ${librarySelectedDocs.includes(doc.doc_name) ? 'checked' : ''}`}
      onClick={(e) => { e.stopPropagation(); toggleLibrarySelect(doc.doc_name); }}
      title={librarySelectedDocs.includes(doc.doc_name) ? 'Bỏ chọn' : 'Chọn để đối chiếu'}
    >
      {librarySelectedDocs.includes(doc.doc_name) ? <CheckCircle2 size={18} /> : <Square size={18} />}
    </button>
  );

  const docMenu = (doc) => (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          className="card-menu-btn"
          onClick={(e) => e.stopPropagation()}
          title="Tùy chọn tài liệu"
        >
          <MoreHorizontal size={15} />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          className="dropdown-menu-content"
          align="start"
          sideOffset={4}
          onClick={(e) => e.stopPropagation()}
        >
          <DropdownMenu.Item className="dropdown-menu-item" onSelect={() => handleOpenLibraryPreview(doc.doc_name, 1)}>
            <Eye size={14} />
            Xem trước
          </DropdownMenu.Item>
          <DropdownMenu.Item className="dropdown-menu-item" onSelect={() => handleDownloadDocument(doc.doc_name)}>
            <Download size={14} />
            Tải xuống
          </DropdownMenu.Item>
          {/* Backend vẫn tự chặn; ẩn nút để bác sĩ không bấm vào một thao tác chắc chắn bị từ chối. */}
          {doc.can_delete && (
            <>
              <DropdownMenu.Separator className="dropdown-menu-separator" />
              <DropdownMenu.Item className="dropdown-menu-item danger" onSelect={() => setDeleteDocTarget(doc.doc_name)}>
                <Trash2 size={14} />
                Xóa
              </DropdownMenu.Item>
            </>
          )}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );

  return (
    <div className="docs-tab-view animate-fade-in">
      <div className="view-header">
        <h2>Thư viện</h2>
      </div>

      <div className="lib-toolbar">
        <div className="lib-search-wrap">
          <Search size={14} className="lib-search-icon" />
          <input
            type="text"
            className="lib-search-input"
            aria-label="Tìm tài liệu trong thư viện"
            placeholder="Tìm tài liệu..."
            value={librarySearch}
            onChange={(e) => setLibrarySearch(e.target.value)}
          />
        </div>

        <select
          className="lib-sort-select"
          aria-label="Sắp xếp tài liệu"
          value={librarySortBy}
          onChange={(e) => setLibrarySortBy(e.target.value)}
          title="Sắp xếp"
        >
          <option value="newest">Mới nhất</option>
          <option value="oldest">Cũ nhất</option>
          <option value="name">Tên A-Z</option>
          <option value="pages">Nhiều trang nhất</option>
        </select>

        <div className="lib-view-toggle">
          <button
            className={libraryViewMode === 'grid' ? 'active' : ''}
            onClick={() => setLibraryViewMode('grid')}
            aria-label="Xem dạng lưới"
            aria-pressed={libraryViewMode === 'grid'}
            title="Xem dạng lưới"
          >
            <LayoutGrid size={15} />
          </button>
          <button
            className={libraryViewMode === 'list' ? 'active' : ''}
            onClick={() => setLibraryViewMode('list')}
            aria-label="Xem dạng danh sách"
            aria-pressed={libraryViewMode === 'list'}
            title="Xem dạng danh sách"
          >
            <List size={15} />
          </button>
        </div>

        <button
          type="button"
          className={`btn-lib-compare-toggle ${librarySelectMode ? 'active' : ''}`}
          onClick={() => (librarySelectMode ? exitLibrarySelectMode() : setLibrarySelectMode(true))}
          disabled={documents.length < 2}
          title="Chọn nhiều tài liệu để đối chiếu"
        >
          <GitCompareArrows size={15} />
          {librarySelectMode ? 'Thôi chọn' : 'Chọn để đối chiếu'}
        </button>

        <button
          type="button"
          className="btn-lib-upload"
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
        >
          {uploading ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
          {uploading ? "Đang tải lên..." : "Tải tệp lên"}
        </button>
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileUpload}
          accept=".pdf"
          style={{ display: 'none' }}
          disabled={uploading}
        />
      </div>

      {uploadJobs.length > 0 && (
        <div className="lib-upload-jobs">
          {uploadJobs.map(job => {
            const pct = uploadProgress(job);
            return (
              <div key={job.jobId} className={`lib-upload-job-card ${job.status}`}>
                <div className="lib-upload-job-icon">
                  {job.status === 'error' ? <AlertCircle size={18} /> : <FileText size={18} />}
                </div>
                <div className="lib-upload-job-body">
                  <div className="lib-upload-job-title" title={job.fileName}>{job.fileName}</div>
                  <div className="lib-upload-job-stage">
                    {job.status === 'error' ? (job.error || 'Nạp thất bại.') : job.stage}
                    {job.warnings?.length > 0 && ` • Trang đọc kém: ${job.warnings.slice(0, 8).join(', ')}${job.warnings.length > 8 ? '…' : ''}`}
                  </div>
                  {job.status !== 'error' && (
                    <div className="lib-upload-job-bar" role="progressbar" aria-label={`Tiến độ nạp ${job.fileName}`} aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
                      <div className="lib-upload-job-bar-fill" style={{ width: `${pct}%` }} />
                    </div>
                  )}
                </div>
                {job.status === 'error' && (
                  <button type="button" className="lib-upload-job-dismiss" onClick={() => dismissUploadJob(job.jobId)} title="Đóng">
                    <X size={14} />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {documentsError && <div className="lib-empty" role="alert">{documentsError} <button type="button" className="btn-lib-upload" onClick={fetchDocuments}>Thử lại</button></div>}
      {documentsError && documents.length === 0 ? null : documents.length === 0 ? (
        <div className="lib-empty">
          <div className="lib-empty-icon"><FileText size={26} /></div>
          <h4>Chưa có tài liệu nào</h4>
          <p>{libraryDescription('empty')}</p>
          <button type="button" className="btn-lib-upload" onClick={() => fileInputRef.current?.click()} style={{ marginLeft: 0 }}>
            <Upload size={15} />
            Tải tệp lên
          </button>
        </div>
      ) : filteredLibraryDocs.length === 0 ? (
        <div className="lib-empty">
          <div className="lib-empty-icon"><Search size={24} /></div>
          <h4>Không tìm thấy tài liệu</h4>
          <p>Không có tài liệu nào khớp với từ khóa "{librarySearch}".</p>
        </div>
      ) : libraryViewMode === 'grid' ? (
        <div className="lib-grid">
          {filteredLibraryDocs.map((doc) => (
            <div
              key={doc.doc_name}
              className={`lib-card ${librarySelectMode && librarySelectedDocs.includes(doc.doc_name) ? 'selected' : ''}`}
              onClick={() => handleLibraryCardClick(doc.doc_name)}
            >
              {librarySelectMode ? checkbox(doc) : docMenu(doc)}
              <div className="lib-card-thumb">
                <div className="lib-card-thumb-icon"><FileText size={22} /></div>
              </div>
              <div className="lib-card-body">
                <div className="lib-card-title" title={doc.doc_name}>{doc.doc_title || doc.doc_name}</div>
                <div className="lib-card-meta">
                  {documentScopeLabel(doc)}
                  {' • '}{doc.page_count} trang • {doc.chunk_count} đoạn
                  {doc.uploaded_at ? ` • ${formatLibraryDate(doc.uploaded_at)}` : ''}
                </div>
                {highlightCounts[doc.doc_name] > 0 && (
                  <span className="lib-highlight-badge" title="Số đoạn bạn đã tô sáng trong tài liệu này">
                    <PencilLine size={11} />
                    {highlightCounts[doc.doc_name]} ghi chú
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="lib-list">
          {filteredLibraryDocs.map((doc) => (
            <div
              key={doc.doc_name}
              className={`lib-row ${librarySelectMode && librarySelectedDocs.includes(doc.doc_name) ? 'selected' : ''}`}
              onClick={() => handleLibraryCardClick(doc.doc_name)}
            >
              {librarySelectMode ? checkbox(doc) : <div className="lib-row-icon"><FileText size={17} /></div>}
              <div className="lib-row-body">
                <div className="lib-row-title" title={doc.doc_name}>{doc.doc_title || doc.doc_name}</div>
                <div className="lib-row-meta">
                  {documentScopeLabel(doc)}
                  {' • '}{doc.page_count} trang • {doc.chunk_count} đoạn
                  {doc.uploaded_at ? ` • ${formatLibraryDate(doc.uploaded_at)}` : ''}
                  {highlightCounts[doc.doc_name] > 0 && ` • ${highlightCounts[doc.doc_name]} ghi chú`}
                </div>
              </div>
              {!librarySelectMode && docMenu(doc)}
            </div>
          ))}
        </div>
      )}

      {librarySelectMode && librarySelectedDocs.length >= 2 && (
        <div className="lib-compare-bar">
          <span className="lib-compare-bar-count">
            <Scale size={14} /> Đã chọn {librarySelectedDocs.length} tài liệu
          </span>
          <button
            type="button"
            className="lib-compare-bar-btn"
            onClick={() => {
              setShowComparePanel(true);
              setTimeout(() => compareViewRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
            }}
          >
            <GitCompareArrows size={15} />
            Đối chiếu {librarySelectedDocs.length} tài liệu
          </button>
        </div>
      )}

      {showComparePanel && (
        <div className="lib-compare-panel" ref={compareViewRef}>
          <button
            type="button"
            className="lib-compare-panel-close"
            onClick={() => setShowComparePanel(false)}
            title="Đóng khung đối chiếu"
          >
            <X size={16} />
          </button>
          <CompareView
            documents={documents}
            apiKey={apiKey}
            initialSelectedDocs={librarySelectedDocs}
            onOpenSource={(docName, pageNum) => handleOpenLibraryPreview(docName, pageNum)}
            onNotify={showStatus}
          />
        </div>
      )}
    </div>
  );
}
