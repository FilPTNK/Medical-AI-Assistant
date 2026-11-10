import React, { useEffect, useState } from 'react';
import AccountMenu from './AccountMenu';
import AccountDialog from './AccountDialog';
import ClinicAdminDialog, { ChangePasswordDialog } from './ClinicAdmin';
import EditProfileDialog from './EditProfileDialog';
import SettingsDialog from './SettingsDialog';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { Bell, Settings } from 'lucide-react';

export default function SiteAccount({ auth, settings, profiles, clinical, showHeaderSettings = false }) {
  const [section, setSection] = useState('general');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
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
      if (event.target instanceof Element && event.target.closest('[role="dialog"]')) return;
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
      {showHeaderSettings && <><button type="button" className="fil-header-icon" aria-label="Cài đặt" title="Cài đặt" onClick={() => openSettings()}>
          <Settings size={20} aria-hidden="true" />
        </button><DropdownMenu.Root onOpenChange={open => { if (open) clinical.markNotificationsRead(); }}>
        <DropdownMenu.Trigger className="fil-header-icon fil-header-notification" aria-label="Thông báo" title="Thông báo" data-unread={clinical.notifications.some(item => item.unread)}><Bell size={19} aria-hidden="true" /></DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content align="end" sideOffset={8} className="dropdown-menu-content fil-header-settings">
            <DropdownMenu.Label className="fil-notification-label">Thông báo</DropdownMenu.Label>
            <div className="fil-header-notifications">
              {clinical.notifications.length === 0 ? <p>Chưa có thông báo mới.</p>
                : clinical.notifications.map((item, index) => <div className="fil-notification" key={index}>
                  <span>{item.message}</span><time>{item.time.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })}</time>
                </div>)}
            </div>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root></>}
      <AccountMenu
        currentUser={user}
        onOpenAccount={() => setAccountOpen(true)}
        onChangePassword={() => setPasswordOpen(true)}
        onLogout={logout}
        onOpenClinicAdmin={() => setAdminOpen(true)}
      />
      <AccountDialog open={accountOpen} onOpenChange={setAccountOpen} user={user}
        onEditProfile={() => { setAccountOpen(false); setEditOpen(true); }}
        onChangePassword={() => { setAccountOpen(false); setPasswordOpen(true); }} />
      <ClinicAdminDialog open={adminOpen} onOpenChange={setAdminOpen} currentUser={user} />
      <ChangePasswordDialog open={passwordOpen} onOpenChange={setPasswordOpen}
        onChangePassword={auth.changePassword} elevated hasPassword={user.has_password !== false} />
      <EditProfileDialog open={editOpen} onOpenChange={setEditOpen}
        profile={user} profileActions={profiles}
        onSaved={(updated) => { auth.absorbProfile(updated); setNotice('Đã cập nhật hồ sơ bác sĩ.'); }} />
      <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen}
        section={section} onSectionChange={setSection} settings={settings}
        actions={{
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
        }}
      />
      <div className={notice ? 'fil-account-notice' : 'sr-only'} role="status">{notice}</div>
    </>
  );
}
