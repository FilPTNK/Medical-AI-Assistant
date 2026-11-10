import React from 'react';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import {
  UserRound, KeyRound, LogOut, ChevronRight, BookOpen, ShieldCheck,
} from 'lucide-react';
import { initialsOf, avatarColorOf } from './useProfiles';
import AuthedImage from './AuthedImage';
import './SettingsDialog.css';

/**
 * Account menu in the shared website header.
 *
 * Trước đây menu này có bộ chuyển hồ sơ bác sĩ không mật khẩu. Từ khi phòng khám
 * dùng đăng nhập thật, đổi người dùng nghĩa là đăng xuất rồi đăng nhập lại —
 * nếu không thì quy tắc "bác sĩ chỉ xem bệnh nhân của mình" bỏ qua được chỉ bằng
 * một cú bấm. Việc tạo tài khoản mới chuyển vào mục Quản trị phòng khám.
 *
 * Hồ sơ và mật khẩu thuộc tài khoản; tùy chọn website mở bằng bánh răng riêng.
 */

/** Avatar that shows the uploaded image when there is one, else initials. */
export function ProfileAvatar({ profile, className = '' }) {
  const name = profile?.display_name || '';
  return (
    <div
      className={`st-avatar ${className}`}
      // Đặt màu nền cả khi có ảnh: ảnh phủ kín nên không thấy, nhưng nếu tải ảnh
      // thất bại thì chữ viết tắt rơi về đúng vòng tròn có màu như bình thường.
      style={{ backgroundColor: avatarColorOf(name) }}
    >
      {profile?.avatar_url
        ? <AuthedImage url={profile.avatar_url} alt="" fallback={<>{initialsOf(name)}</>} />
        : initialsOf(name)}
    </div>
  );
}

export default function AccountMenu({
  currentUser: account, onOpenAccount, onChangePassword, onLogout, onOpenClinicAdmin,
}) {
  const isAdmin = account?.role === 'admin';

  return (
    <>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger className="st-pill st-scope fil-account-trigger" aria-label={`Tài khoản: ${account?.display_name || 'Bác sĩ'}`} title="Tài khoản">
          <ProfileAvatar profile={account} className="st-avatar-md" />
          <div className="st-pill-meta">
            <span className="st-pill-name">{account?.display_name}</span>
            <span className="st-pill-plan">
              {account?.role_label || account?.specialty || 'Bác sĩ'}
            </span>
          </div>
          <ChevronRight size={15} className="st-pill-chevron" aria-hidden="true" />
        </DropdownMenu.Trigger>

        <DropdownMenu.Portal>
          <DropdownMenu.Content
            className="st-menu st-scope fil-account-menu"
            side="bottom"
            align="end"
            sideOffset={8}
          >
            <div className="st-menu-account st-menu-account-static">
              <ProfileAvatar profile={account} className="st-avatar-sm" />
              <div className="st-menu-account-meta">
                <strong>{account?.display_name}</strong>
                <span>
                  {account?.username ? `@${account.username}` : ''}
                  {account?.role_label ? ` · ${account.role_label}` : ''}
                </span>
              </div>
            </div>

            <DropdownMenu.Separator className="st-menu-separator" />

            <DropdownMenu.Item className="st-menu-item" onSelect={onOpenAccount}>
              <UserRound size={20} />
              <span>Hồ sơ tài khoản</span>
            </DropdownMenu.Item>
            <DropdownMenu.Item className="st-menu-item" onSelect={onChangePassword}>
              <KeyRound size={20} /><span>{account?.has_password === false ? 'Đặt mật khẩu' : 'Đổi mật khẩu'}</span>
            </DropdownMenu.Item>

            {isAdmin && (
              <>
                <DropdownMenu.Item className="st-menu-item" asChild><a href="/quan-tri"><BookOpen size={20} /> Quản trị dữ liệu thuốc</a></DropdownMenu.Item>
                <DropdownMenu.Item className="st-menu-item" onSelect={onOpenClinicAdmin}>
                  <ShieldCheck size={20} />
                  <span>Quản trị phòng khám</span>
                </DropdownMenu.Item>
              </>
            )}

            <DropdownMenu.Separator className="st-menu-separator" />

            <DropdownMenu.Item className="st-menu-item" onSelect={onLogout}>
              <LogOut size={20} />
              <span>Đăng xuất</span>
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>

    </>
  );
}
