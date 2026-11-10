import React from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { BadgeCheck, KeyRound, Mail, Pencil, ShieldCheck, Stethoscope, UserRound, X } from 'lucide-react';
import { ProfileAvatar } from './AccountMenu';
import './AccountDialog.css';

export default function AccountDialog({ open, onOpenChange, user, onEditProfile, onChangePassword }) {
  const role = user.role_label || (user.role === 'admin' ? 'Quản trị viên' : 'Bác sĩ');
  return <Dialog.Root open={open} onOpenChange={onOpenChange}>
    <Dialog.Portal><Dialog.Overlay className="st-overlay" />
      <Dialog.Content className="st-scope fil-account-dialog" aria-describedby="fil-account-description">
        <div className="fil-account-hero">
          <Dialog.Title>Hồ sơ tài khoản</Dialog.Title>
          <Dialog.Description id="fil-account-description">Thông tin cá nhân và đăng nhập của bạn.</Dialog.Description>
          <Dialog.Close className="fil-account-close" aria-label="Đóng hồ sơ tài khoản"><X size={21} aria-hidden="true" /></Dialog.Close>
          <div className="fil-account-identity"><ProfileAvatar profile={user} /><div><h2>{user.display_name || user.username}</h2><span>@{user.username} <span aria-hidden="true">·</span> {role}</span></div></div>
        </div>
        <div className="fil-account-body">
          <div className="fil-account-section-title"><h3>Thông tin cá nhân</h3><button className="fil-account-edit" type="button" onClick={onEditProfile}><Pencil size={15} aria-hidden="true" /> Chỉnh sửa hồ sơ</button></div>
          <dl className="fil-account-fields">
            <div><dt><UserRound size={17} aria-hidden="true" />Tên đăng nhập</dt><dd>{user.username || 'Chưa cập nhật'}</dd></div>
            <div><dt><Stethoscope size={17} aria-hidden="true" />Chuyên khoa</dt><dd>{user.specialty || 'Chưa cập nhật'}</dd></div>
            <div className="fil-account-email"><dt><Mail size={17} aria-hidden="true" />Email</dt><dd>{user.email || 'Chưa cập nhật'}{user.email && user.email_verified && <span className="fil-account-verified"><BadgeCheck size={14} aria-hidden="true" /> Đã xác nhận</span>}</dd></div>
          </dl>
          <section className="fil-account-security" aria-labelledby="account-login-heading"><span className="fil-account-security-icon"><ShieldCheck size={23} aria-hidden="true" /></span><div><h3 id="account-login-heading">Mật khẩu & đăng nhập</h3><p>{user.has_password === false ? 'Đặt mật khẩu để đăng nhập bằng tên đăng nhập.' : 'Quản lý mật khẩu đăng nhập của tài khoản.'}</p></div><button type="button" className="fil-account-edit" onClick={onChangePassword}><KeyRound size={16} aria-hidden="true" />{user.has_password === false ? 'Đặt mật khẩu' : 'Đổi mật khẩu'}</button></section>
        </div>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}
