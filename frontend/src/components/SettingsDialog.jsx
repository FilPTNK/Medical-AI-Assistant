import React, { useEffect, useMemo, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import * as Switch from '@radix-ui/react-switch';
import {
  Palette, Sparkles, Plug, AudioLines, Database, HardDrive,
  ShieldCheck, Lock, UserRound, Keyboard, Search, X, ChevronDown, Check,
  Trash2, Download, AlertTriangle, Archive, KeyRound,
} from 'lucide-react';
import { ACCENT_COLORS, measureStorage, formatBytes } from './useSettings';
import { ProfileAvatar } from './AccountMenu';
import './SettingsDialog.css';

/* ---------------------------------------------------------------------
   Small presentational primitives, shaped to chatgpt.com's settings rows:
   a 14px/20 label, an optional 12px/16 muted description, and a control
   pinned right. Rows are 60px tall and separated by a 0.8px hairline.
   --------------------------------------------------------------------- */

function Row({ label, desc, children, stack = false }) {
  return (
    <div className={`st-row${stack ? ' st-row-stack' : ''}`}>
      <div className="st-row-label">
        <span>{label}</span>
        {desc && <span className="st-row-desc">{desc}</span>}
      </div>
      {children && <div className="st-row-control">{children}</div>}
    </div>
  );
}

function Toggle({ checked, onCheckedChange, disabled }) {
  return (
    <Switch.Root
      className="st-switch"
      checked={checked}
      onCheckedChange={onCheckedChange}
      disabled={disabled}
    >
      <Switch.Thumb className="st-switch-thumb" />
    </Switch.Root>
  );
}

/** Trigger + radio menu, standing in for ChatGPT's dropdown rows. */
function SelectMenu({ value, onChange, options, renderLeading }) {
  const current = options.find((o) => o.value === value) || options[0];
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger className="st-select">
        {renderLeading && renderLeading(current)}
        <span>{current?.label}</span>
        <ChevronDown size={16} />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content className="st-menu st-scope" sideOffset={4} align="end">
          {options.map((opt) => (
            <DropdownMenu.Item
              key={opt.value}
              className="st-menu-item"
              onSelect={() => onChange(opt.value)}
            >
              {renderLeading && renderLeading(opt)}
              <span className="st-menu-item-grow">{opt.label}</span>
              {opt.value === value && <Check size={16} className="st-menu-check" />}
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function Segmented({ value, onChange, options }) {
  return (
    <div className="st-segmented">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          data-active={value === opt.value}
          onClick={() => onChange(opt.value)}
        >
          {opt.icon}
          {opt.label}
        </button>
      ))}
    </div>
  );
}

/* --------------------------------------------------------------------- */

const SECTIONS = [
  { value: 'general', label: 'Chung', icon: Palette, keywords: 'giao diện theme sáng tối màu nhấn ngôn ngữ bố cục gợi ý' },
  { value: 'personalization', label: 'Cá nhân hóa', icon: Sparkles, keywords: 'hướng dẫn tùy chỉnh bộ nhớ ghi nhớ lịch sử chi tiết trả lời' },
  { value: 'integrations', label: 'Tích hợp', icon: Plug, keywords: 'api key deepseek mô hình nguồn tri thức vector' },
  { value: 'voice', label: 'Giọng nói', icon: AudioLines, keywords: 'micro giọng nói đọc chính tả nhận dạng' },
  { value: 'data', label: 'Kiểm soát dữ liệu', icon: Database, keywords: 'dữ liệu xuất lưu trữ xóa hội thoại cải thiện mô hình' },
  { value: 'storage', label: 'Lưu trữ', icon: HardDrive, keywords: 'dung lượng bộ nhớ cache trang pdf' },
  { value: 'safety', label: 'An toàn', icon: ShieldCheck, keywords: 'an toàn miễn trừ trách nhiệm liều cảnh báo kê đơn' },
  { value: 'security', label: 'Bảo mật', icon: Lock, keywords: 'bảo mật khóa pin đăng xuất phiên đăng nhập' },
  { value: 'account', label: 'Tài khoản', icon: UserRound, keywords: 'tài khoản hồ sơ bác sĩ tên chuyên khoa email mật khẩu đổi mật khẩu đăng nhập' },
  { value: 'keyboard', label: 'Phím tắt', icon: Keyboard, keywords: 'phím tắt bàn phím shortcut' },
];

const SHORTCUTS = [
  { keys: ['Ctrl', 'K'], label: 'Mở tìm kiếm nhanh' },
  { keys: ['Ctrl', 'Shift', 'O'], label: 'Cuộc trò chuyện mới' },
  { keys: ['Ctrl', 'B'], label: 'Ẩn/hiện lịch sử trên trang Hỏi đáp' },
  { keys: ['Ctrl', '/'], label: 'Mở bảng phím tắt' },
  { keys: ['Ctrl', ','], label: 'Mở cài đặt' },
  { keys: ['Esc'], label: 'Đóng hộp thoại đang mở' },
  { keys: ['Enter'], label: 'Gửi câu hỏi' },
  { keys: ['Shift', 'Enter'], label: 'Xuống dòng trong ô nhập' },
];

export default function SettingsDialog({
  open, onOpenChange, section, onSectionChange, settings, actions, profile, profileActions,
}) {
  const [query, setQuery] = useState('');
  const [ciOpen, setCiOpen] = useState(false);
  const [ciDraft, setCiDraft] = useState(settings.customInstructions);
  const [specialtyDraft, setSpecialtyDraft] = useState(profile?.specialty || '');
  const [emailDraft, setEmailDraft] = useState(profile?.email || '');
  const [apiKeyDraft, setApiKeyDraft] = useState(actions.apiKey || '');
  const [storage, setStorage] = useState(() => measureStorage());

  // Re-sync drafts and re-measure storage whenever the dialog is reopened.
  useEffect(() => {
    if (!open) return;
    setQuery('');
    setCiDraft(settings.customInstructions);
    setSpecialtyDraft(profile?.specialty || '');
    setEmailDraft(profile?.email || '');
    setApiKeyDraft(actions.apiKey || '');
    setStorage(measureStorage());
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  // Follow profile edits made from the standalone "Chỉnh sửa hồ sơ" dialog.
  useEffect(() => {
    setSpecialtyDraft(profile?.specialty || '');
    setEmailDraft(profile?.email || '');
  }, [profile?.specialty, profile?.email]);

  const saveProfileField = (field) => (value) => {
    if (!profile?.id || (profile[field] || '') === value.trim()) return;
    profileActions.updateProfile(profile.id, { [field]: value.trim() }).catch(() => {});
  };

  const visibleSections = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return SECTIONS;
    return SECTIONS.filter((s) =>
      s.label.toLowerCase().includes(q) || s.keywords.includes(q));
  }, [query]);

  // Keep the selected section reachable while a search filter is active.
  useEffect(() => {
    if (visibleSections.length && !visibleSections.some((s) => s.value === section)) {
      onSectionChange(visibleSections[0].value);
    }
  }, [visibleSections, section, onSectionChange]);

  const quotaPct = Math.min(100, Math.round((storage.bytes / (5 * 1024 * 1024)) * 100));

  const panel = (value, title, body) => (
    <div className="st-panel" hidden={section !== value}>
      <div className="st-panel-head">{title}</div>
      {body}
    </div>
  );

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="st-overlay" />
        <Dialog.Content className="st-dialog st-scope" aria-describedby={undefined}>
          <Dialog.Title className="sr-only" style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)' }}>
            Cài đặt
          </Dialog.Title>

          <div className="st-body">
            {/* left rail: close button, search, section list */}
            <div className="st-rail">
              <div className="st-rail-head">
                <Dialog.Close className="st-close" aria-label="Đóng">
                  <X size={18} />
                </Dialog.Close>
              </div>

              <div className="st-search">
                <Search size={15} />
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Tìm cài đặt"
                  aria-label="Tìm cài đặt"
                />
              </div>

              <div className="st-nav" role="tablist" aria-orientation="vertical">
                {visibleSections.map((s) => {
                  const Icon = s.icon;
                  return (
                    <button
                      key={s.value}
                      type="button"
                      role="tab"
                      aria-selected={section === s.value}
                      data-state={section === s.value ? 'active' : 'inactive'}
                      className="st-nav-item"
                      onClick={() => onSectionChange(s.value)}
                    >
                      <Icon size={17} />
                      <span>{s.label}</span>
                    </button>
                  );
                })}
                {!visibleSections.length && (
                  <div className="st-nav-empty">Không tìm thấy cài đặt phù hợp.</div>
                )}
              </div>
            </div>

            {/* ---------------- General ---------------- */}
            {panel('general', 'Chung', (
              <>
                <Row label="Giao diện">
                  <SelectMenu
                    value={settings.appearance}
                    onChange={settings.setAppearance}
                    options={[
                      { value: 'system', label: 'Hệ thống' },
                      { value: 'light', label: 'Sáng' },
                      { value: 'dark', label: 'Tối' },
                    ]}
                  />
                </Row>

                <Row label="Màu nhấn">
                  <SelectMenu
                    value={settings.accentColor}
                    onChange={settings.setAccentColor}
                    options={ACCENT_COLORS}
                    renderLeading={(opt) => (
                      <span className="st-dot" style={{ backgroundColor: opt.color }} />
                    )}
                  />
                </Row>

                <Row label="Ngôn ngữ">
                  <SelectMenu
                    value={settings.language}
                    onChange={settings.setLanguage}
                    options={[
                      { value: 'vi', label: 'Tiếng Việt' },
                      { value: 'en', label: 'English' },
                      { value: 'auto', label: 'Tự động phát hiện' },
                    ]}
                  />
                </Row>

                <Row
                  label="Gợi ý câu hỏi tiếp theo"
                  desc="Hiện các câu hỏi liên quan sau mỗi câu trả lời của trợ lý."
                >
                  <Toggle
                    checked={settings.followUpSuggestions}
                    onCheckedChange={settings.setFollowUpSuggestions}
                  />
                </Row>
              </>
            ))}

            {/* ---------------- Personalization ---------------- */}
            {panel('personalization', 'Cá nhân hóa', (
              <>
                <Row
                  label="Hướng dẫn tùy chỉnh"
                  desc="Cho trợ lý biết chuyên khoa và cách bạn muốn nhận câu trả lời."
                >
                  <button type="button" className="st-btn" onClick={() => setCiOpen(true)}>
                    Chỉnh sửa
                  </button>
                </Row>
                <Row
                  label="Ghi nhớ ngữ cảnh trò chuyện"
                  desc="Cho phép trợ lý tham chiếu thông tin đã trao đổi trong cùng cuộc trò chuyện."
                >
                  <Toggle checked={settings.memoryEnabled} onCheckedChange={settings.setMemoryEnabled} />
                </Row>
                <Row
                  label="Tham chiếu lịch sử trò chuyện"
                  desc="Dùng các cuộc trò chuyện trước làm bối cảnh cho câu trả lời mới."
                >
                  <Toggle checked={settings.referenceHistory} onCheckedChange={settings.setReferenceHistory} />
                </Row>
                <Row label="Độ chi tiết câu trả lời">
                  <Segmented
                    value={settings.answerDetail}
                    onChange={settings.setAnswerDetail}
                    options={[
                      { value: 'concise', label: 'Ngắn gọn' },
                      { value: 'balanced', label: 'Cân bằng' },
                      { value: 'detailed', label: 'Chi tiết' },
                    ]}
                  />
                </Row>
                <Row
                  label="Quản lý bộ nhớ"
                  desc={`Đang lưu ${actions.conversationCount} cuộc trò chuyện trên trình duyệt này.`}
                >
                  <button
                    type="button"
                    className="st-btn"
                    onClick={actions.onDeleteAllConversations}
                    disabled={!actions.conversationCount}
                  >
                    Xóa bộ nhớ
                  </button>
                </Row>
              </>
            ))}

            {/* ---------------- Integrations ---------------- */}
            {panel('integrations', 'Tích hợp', (
              <>
                <Row
                  label="DeepSeek API Key"
                  desc={actions.backendHasKey
                    ? 'Máy chủ đã có khóa riêng. Khóa nhập ở đây sẽ được ưu tiên dùng trên trình duyệt này.'
                    : 'Khóa được lưu cục bộ trên trình duyệt này, chỉ gửi đi khi gọi API.'}
                  stack
                >
                  <div style={{ display: 'flex', gap: 8 }}>
                    <input
                      type="password"
                      className="st-input"
                      value={apiKeyDraft}
                      onChange={(e) => setApiKeyDraft(e.target.value)}
                      placeholder={actions.backendHasKey ? 'Đã cấu hình trên máy chủ' : 'sk-...'}
                    />
                    <button
                      type="button"
                      className="st-btn st-btn-primary"
                      onClick={() => actions.onSaveApiKey(apiKeyDraft)}
                    >
                      Lưu
                    </button>
                  </div>
                </Row>

                <div className="st-group-title">Nguồn tri thức</div>
                <Row
                  label="Thư viện tài liệu y khoa"
                  desc={`${actions.documentCount} tài liệu đã được lập chỉ mục cho tìm kiếm ngữ nghĩa.`}
                >
                  <span className="st-readonly">Đang hoạt động</span>
                </Row>
                <Row
                  label="Cơ sở dữ liệu thuốc"
                  desc="Tra cứu hoạt chất, biệt dược, liều dùng và chống chỉ định."
                >
                  <span className="st-readonly">Đang hoạt động</span>
                </Row>
              </>
            ))}

            {/* ---------------- Voice ---------------- */}
            {panel('voice', 'Giọng nói', (
              <>
                <Row
                  label="Nhập liệu bằng giọng nói"
                  desc={actions.micSupported
                    ? 'Hiện nút micro trong ô nhập câu hỏi và ô tra cứu thuốc.'
                    : 'Trình duyệt này không hỗ trợ nhận dạng giọng nói.'}
                >
                  <Toggle
                    checked={settings.voiceInputEnabled && actions.micSupported}
                    onCheckedChange={settings.setVoiceInputEnabled}
                    disabled={!actions.micSupported}
                  />
                </Row>
                <Row label="Ngôn ngữ nhận dạng">
                  <SelectMenu
                    value={settings.voiceLang}
                    onChange={settings.setVoiceLang}
                    options={[
                      { value: 'vi-VN', label: 'Tiếng Việt' },
                      { value: 'en-US', label: 'English (US)' },
                      { value: 'en-GB', label: 'English (UK)' },
                    ]}
                  />
                </Row>
                <Row
                  label="Tự động gửi sau khi ngừng nói"
                  desc="Gửi câu hỏi ngay khi micro nhận diện xong, không cần bấm nút gửi."
                >
                  <Toggle
                    checked={settings.voiceAutoSend}
                    onCheckedChange={settings.setVoiceAutoSend}
                    disabled={!actions.micSupported || !settings.voiceInputEnabled}
                  />
                </Row>
              </>
            ))}

            {/* ---------------- Data controls ---------------- */}
            {panel('data', 'Kiểm soát dữ liệu', (
              <>
                <Row
                  label="Đóng góp dữ liệu cải thiện mô hình"
                  desc="Ứng dụng chạy nội bộ nên tùy chọn này luôn tắt; không có dữ liệu bệnh nhân nào rời khỏi phòng khám."
                >
                  <Toggle checked={settings.improveModel} onCheckedChange={settings.setImproveModel} disabled />
                </Row>
                <Row
                  label="Xuất dữ liệu"
                  desc="Tải về toàn bộ cuộc trò chuyện và cài đặt dưới dạng tệp JSON."
                >
                  <button type="button" className="st-btn" onClick={actions.onExportData}>
                    <Download size={15} /> Xuất
                  </button>
                </Row>
                <Row
                  label="Lưu trữ tất cả cuộc trò chuyện"
                  desc="Ẩn khỏi lịch sử gần đây nhưng vẫn giữ lại nội dung."
                >
                  <button
                    type="button"
                    className="st-btn"
                    onClick={actions.onArchiveAll}
                    disabled={!actions.conversationCount}
                  >
                    <Archive size={15} /> Lưu trữ
                  </button>
                </Row>
                <Row
                  label="Xóa toàn bộ cuộc trò chuyện"
                  desc="Hành động này không thể hoàn tác."
                >
                  <button
                    type="button"
                    className="st-btn st-btn-danger"
                    onClick={actions.onDeleteAllConversations}
                    disabled={!actions.conversationCount}
                  >
                    <Trash2 size={15} /> Xóa tất cả
                  </button>
                </Row>
                <div className="st-note">
                  <ShieldCheck size={16} />
                  <span>
                    Cuộc trò chuyện và cài đặt nằm trong trình duyệt này; hồ sơ bệnh nhân và tài liệu
                    nằm trên máy chủ nội bộ của phòng khám.
                  </span>
                </div>
              </>
            ))}

            {/* ---------------- Storage ---------------- */}
            {panel('storage', 'Lưu trữ', (
              <>
                <Row
                  label="Dung lượng trình duyệt đã dùng"
                  desc={`${formatBytes(storage.bytes)} trên hạn mức khoảng 5 MB (${quotaPct}%).`}
                  stack
                >
                  <div className="st-meter">
                    <div className="st-meter-fill" style={{ width: `${quotaPct}%` }} />
                  </div>
                </Row>
                {storage.perKey.slice(0, 5).map((entry) => (
                  <Row key={entry.key} label={entry.key}>
                    <span className="st-readonly">{formatBytes(entry.size)}</span>
                  </Row>
                ))}
                <Row
                  label="Làm mới số liệu"
                  desc="Tính lại dung lượng đang chiếm dụng."
                >
                  <button type="button" className="st-btn" onClick={() => setStorage(measureStorage())}>
                    Tính lại
                  </button>
                </Row>
                {quotaPct > 80 && (
                  <div className="st-note st-note-danger">
                    <AlertTriangle size={16} />
                    <span>Sắp đầy bộ nhớ trình duyệt. Hãy xuất dữ liệu rồi xóa bớt cuộc trò chuyện cũ.</span>
                  </div>
                )}
              </>
            ))}

            {/* ---------------- Safety ---------------- */}
            {panel('safety', 'An toàn', (
              <>
                <Row
                  label="Cảnh báo vượt liều tối đa"
                  desc="Đánh dấu khi liều đề xuất vượt ngưỡng an toàn trong tài liệu."
                >
                  <Toggle checked={settings.doseWarning} onCheckedChange={settings.setDoseWarning} />
                </Row>
                <div className="st-note st-note-danger">
                  <AlertTriangle size={16} />
                  <span>
                    Trợ lý AI không thay thế chẩn đoán lâm sàng. Luôn đối chiếu với tài liệu gốc
                    và tình trạng thực tế của bệnh nhân trước khi ra quyết định điều trị.
                  </span>
                </div>
              </>
            ))}

            {/* ---------------- Security ---------------- */}
            {panel('security', 'Bảo mật & đăng nhập', (
              <>
                <Row
                  label="Khóa ứng dụng bằng mã PIN"
                  desc="Yêu cầu nhập mã PIN khi mở lại ứng dụng trên máy này."
                >
                  <Toggle checked={settings.appLock} onCheckedChange={settings.setAppLock} />
                </Row>
                <Row
                  label="Tự động khóa khi không hoạt động"
                  desc="Khóa màn hình sau một khoảng thời gian không thao tác."
                >
                  <SelectMenu
                    value={settings.autoLogout}
                    onChange={settings.setAutoLogout}
                    options={[
                      { value: 'never', label: 'Không bao giờ' },
                      { value: '15', label: 'Sau 15 phút' },
                      { value: '30', label: 'Sau 30 phút' },
                      { value: '60', label: 'Sau 1 giờ' },
                    ]}
                  />
                </Row>
                <Row
                  label="Đăng xuất khỏi thiết bị này"
                  desc="Xóa phiên làm việc khỏi trình duyệt hiện tại."
                >
                  <button type="button" className="st-btn" onClick={actions.onLogout}>
                    Đăng xuất
                  </button>
                </Row>
                <div className="st-note">
                  <Lock size={16} />
                  <span>
                    Ứng dụng chạy nội bộ cho phòng khám và chưa có hệ thống đăng nhập nhiều người dùng.
                    Các tùy chọn trên chỉ bảo vệ ở mức thiết bị.
                  </span>
                </div>
              </>
            ))}

            {/* ---------------- Account ---------------- */}
            {panel('account', 'Tài khoản', (
              <>
                <div className="st-account-head">
                  <ProfileAvatar profile={profile} />
                  <div className="st-account-head-meta">
                    <strong>{profile?.display_name}</strong>
                    <span>{profile?.username ? `@${profile.username}` : 'Bác sĩ'}</span>
                  </div>
                </div>

                <Row
                  label="Ảnh và tên hiển thị"
                  desc="Đổi ảnh đại diện, tên hiển thị và tên đăng nhập."
                >
                  <button type="button" className="st-btn" onClick={actions.onEditProfile}>
                    Chỉnh sửa hồ sơ
                  </button>
                </Row>

                {/* Chuyển từ menu tài khoản ở thanh bên vào đây, để mọi thứ
                    thuộc về tài khoản nằm chung một chỗ. */}
                <Row
                  label="Mật khẩu"
                  desc={actions.hasPassword === false
                    ? 'Tài khoản đang đăng nhập bằng Google. Đặt mật khẩu để vào được bằng tên đăng nhập.'
                    : 'Mật khẩu dùng để đăng nhập cùng tên đăng nhập của bạn.'}
                >
                  <button type="button" className="st-btn" onClick={actions.onChangePassword}>
                    <KeyRound size={14} />
                    {actions.hasPassword === false ? 'Đặt mật khẩu' : 'Đổi mật khẩu'}
                  </button>
                </Row>

                <Row label="Chuyên khoa" desc="Dùng làm bối cảnh mặc định cho câu trả lời của trợ lý." stack>
                  <input
                    type="text"
                    className="st-input"
                    value={specialtyDraft}
                    onChange={(e) => setSpecialtyDraft(e.target.value)}
                    onBlur={() => saveProfileField('specialty')(specialtyDraft)}
                    placeholder="Nội tổng quát"
                  />
                </Row>

                <Row
                  label="Email liên hệ"
                  desc={profile?.email_verified
                    ? 'Đã xác nhận khi đăng ký.'
                    : 'Dùng để đăng nhập và khôi phục tài khoản.'}
                  stack
                >
                  <input
                    type="email"
                    className="st-input"
                    value={emailDraft}
                    onChange={(e) => setEmailDraft(e.target.value)}
                    onBlur={() => saveProfileField('email')(emailDraft)}
                    placeholder="bacsi@phongkham.vn"
                  />
                </Row>

                <Row
                  label="Xóa toàn bộ dữ liệu cục bộ"
                  desc="Xóa cài đặt và cuộc trò chuyện khỏi trình duyệt này. Tài liệu trên máy chủ không bị ảnh hưởng."
                >
                  <button type="button" className="st-btn st-btn-danger" onClick={actions.onResetLocalData}>
                    Xóa dữ liệu
                  </button>
                </Row>
              </>
            ))}

            {/* ---------------- Keyboard ---------------- */}
            {panel('keyboard', 'Phím tắt', (
              <div className="st-kbd-table">
                {SHORTCUTS.map((s) => (
                  <div className="st-kbd-row" key={s.label}>
                    <span>{s.label}</span>
                    <span className="st-kbd-keys">
                      {s.keys.map((k) => <kbd className="st-kbd" key={k}>{k}</kbd>)}
                    </span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </Dialog.Content>
      </Dialog.Portal>

      {/* nested "custom instructions" dialog, mirroring ChatGPT's sub-modal */}
      <Dialog.Root open={ciOpen} onOpenChange={setCiOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="st-overlay st-subdialog-overlay" />
          <Dialog.Content className="st-subdialog st-scope" aria-describedby={undefined}>
            <Dialog.Title asChild><h3>Hướng dẫn tùy chỉnh</h3></Dialog.Title>

            <div className="st-field">
              <label htmlFor="ci-nickname">Trợ lý nên gọi bạn là gì?</label>
              <input
                id="ci-nickname"
                className="st-input"
                value={ciDraft.nickname}
                onChange={(e) => setCiDraft({ ...ciDraft, nickname: e.target.value })}
                placeholder="BS. Hùng"
              />
            </div>

            <div className="st-field">
              <label htmlFor="ci-specialty">Bạn làm việc ở chuyên khoa nào?</label>
              <input
                id="ci-specialty"
                className="st-input"
                value={ciDraft.specialty}
                onChange={(e) => setCiDraft({ ...ciDraft, specialty: e.target.value })}
                placeholder="Nội tổng quát, Tim mạch..."
              />
            </div>

            <div className="st-field">
              <label htmlFor="ci-traits">Bạn muốn trợ lý trả lời theo phong cách nào?</label>
              <textarea
                id="ci-traits"
                className="st-textarea"
                value={ciDraft.traits}
                onChange={(e) => setCiDraft({ ...ciDraft, traits: e.target.value })}
                placeholder="Ưu tiên phác đồ Bộ Y tế, trích dẫn trang tài liệu, trình bày theo gạch đầu dòng..."
              />
            </div>

            <div className="st-field">
              <label htmlFor="ci-extra">Trợ lý cần biết thêm điều gì?</label>
              <textarea
                id="ci-extra"
                className="st-textarea"
                value={ciDraft.extra}
                onChange={(e) => setCiDraft({ ...ciDraft, extra: e.target.value })}
                placeholder="Đối tượng bệnh nhân thường gặp, thuốc sẵn có tại phòng khám..."
              />
            </div>

            <div className="st-subdialog-actions">
              <Dialog.Close asChild>
                <button type="button" className="st-btn">Hủy</button>
              </Dialog.Close>
              <button
                type="button"
                className="st-btn st-btn-primary"
                onClick={() => { settings.setCustomInstructions(ciDraft); setCiOpen(false); }}
              >
                Lưu
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </Dialog.Root>
  );
}
