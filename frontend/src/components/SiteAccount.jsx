import React, { useEffect, useState } from 'react';
import AccountMenu from './AccountMenu';
import ClinicAdminDialog, { ChangePasswordDialog } from './ClinicAdmin';
import EditProfileDialog from './EditProfileDialog';
import SettingsDialog from './SettingsDialog';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { Moon, Settings, Sun } from 'lucide-react';

export default function SiteAccount({ auth, settings, profiles, clinical, showHeaderSettings = false }) {
  const [section, setSection] = useState('general');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [adminOpen, setAdminOpen] = useState(false);
  const [notice, setNotice] = useState('');
  const { user } = auth;
  const { conversations, setConversations, documents, apiKey, config, saveApiKey } = clinical;

  function openSettings(next = 'general') {
    setSection(next);
    setSettingsOpen(true);
  }

  useEffect(() => {
    const onKey = (event) => {
      if (!(event.ctrlKey || event.metaKey) || ![',', '/'].includes(event.key)) return;
      event.preventDefault();
      openSettings(event.key === '/' ? 'keyboard' : 'general');
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    if (!notice) return undefined;
    const timer = setTimeout(() => setNotice(''), 4000);
    return () => clearTimeout(timer);
  }, [notice]);

  async function logout() {
    if (!window.confirm('Đăng xuất khỏi thiết bị này?')) return;
    await auth.logout();
  }

  function exportData() {
    const payload = {
      exported_at: new Date().toISOString(),
      doctor: {
        name: user.display_name, username: user.username,
        specialty: user.specialty, email: user.email,
      },
      custom_instructions: settings.customInstructions,
      conversations,
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `tro-ly-y-khoa-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice('Đã xuất dữ liệu ra tệp JSON.');
  }

  return (
    <>
      {showHeaderSettings && <DropdownMenu.Root onOpenChange={open => { if (open) clinical.markNotificationsRead(); }}>
        <DropdownMenu.Trigger className="fil-header-icon" aria-label="Cài đặt" title="Cài đặt">
          <Settings size={20} aria-hidden="true" />
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content align="end" sideOffset={8} className="dropdown-menu-content fil-header-settings">
            <DropdownMenu.Item className="dropdown-menu-item" onSelect={() => openSettings()}><Settings size={17} /> Cài đặt tài khoản</DropdownMenu.Item>
            <DropdownMenu.Item className="dropdown-menu-item" onSelect={() => settings.setAppearance(settings.isDarkMode ? 'light' : 'dark')}>
              {settings.isDarkMode ? <Sun size={17} /> : <Moon size={17} />} {settings.isDarkMode ? 'Chuyển sang nền sáng' : 'Chuyển sang nền tối'}
            </DropdownMenu.Item>
            <DropdownMenu.Separator className="dropdown-menu-separator" />
            <DropdownMenu.Label className="fil-notification-label">Thông báo</DropdownMenu.Label>
            <div className="fil-header-notifications">
              {clinical.notifications.length === 0 ? <p>Chưa có thông báo mới.</p>
                : clinical.notifications.map((item, index) => <div className="fil-notification" key={index}>
                  <span>{item.message}</span><time>{item.time.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })}</time>
                </div>)}
            </div>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>}
      <AccountMenu
        currentUser={user}
        onOpenSettings={() => openSettings()}
        onOpenSection={openSettings}
        onEditProfile={() => setEditOpen(true)}
        onLogout={logout}
        onOpenClinicAdmin={() => setAdminOpen(true)}
      />
      <ClinicAdminDialog open={adminOpen} onOpenChange={setAdminOpen} currentUser={user} />
      <ChangePasswordDialog open={passwordOpen} onOpenChange={setPasswordOpen}
        onChangePassword={auth.changePassword} elevated hasPassword={user.has_password !== false} />
      <EditProfileDialog open={editOpen} onOpenChange={setEditOpen}
        profile={user} profileActions={profiles}
        onSaved={(updated) => { auth.absorbProfile(updated); setNotice('Đã cập nhật hồ sơ bác sĩ.'); }} />
      <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen}
        section={section} onSectionChange={setSection} settings={settings}
        profile={user} profileActions={{
          ...profiles,
          updateProfile: async (...args) => {
            const updated = await profiles.updateProfile(...args);
            auth.absorbProfile(updated);
            return updated;
          },
        }}
        actions={{
          onEditProfile: () => setEditOpen(true),
          apiKey,
          backendHasKey: Boolean(config?.has_api_key),
          onSaveApiKey: (value) => { saveApiKey(value); setNotice('Đã lưu khóa API.'); },
          micSupported: 'SpeechRecognition' in window || 'webkitSpeechRecognition' in window,
          conversationCount: conversations.length,
          documentCount: documents.length,
          onDeleteAllConversations: () => {
            if (!window.confirm('Xóa toàn bộ lịch sử trò chuyện? Hành động này không thể hoàn tác.')) return;
            setConversations([]);
            setNotice('Đã xóa toàn bộ cuộc trò chuyện.');
          },
          onExportData: exportData,
          onArchiveAll: () => {
            setConversations(prev => prev.map(item => ({ ...item, archived: true })));
            setNotice('Đã lưu trữ toàn bộ cuộc trò chuyện.');
          },
          onResetLocalData: () => {
            if (!window.confirm('Xóa toàn bộ cài đặt và cuộc trò chuyện trên trình duyệt này?')) return;
            localStorage.clear();
            window.location.reload();
          },
          onLogout: logout,
          onChangePassword: () => setPasswordOpen(true),
          hasPassword: user.has_password !== false,
        }}
      />
      <div className={notice ? 'fil-account-notice' : 'sr-only'} role="status">{notice}</div>
    </>
  );
}
