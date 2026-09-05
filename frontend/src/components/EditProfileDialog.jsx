import React, { useEffect, useRef, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { Camera, Loader2, Trash2 } from 'lucide-react';
import { initialsOf, avatarColorOf } from './useProfiles';
import AuthedImage from './AuthedImage';
import './SettingsDialog.css';

/**
 * "Chỉnh sửa hồ sơ" — a standalone dialog opened from the account menu,
 * deliberately kept out of Settings (this mirrors how ChatGPT separates
 * "Profile" from "Settings").
 *
 * Layout matches the reference: a large ringed avatar with a camera badge,
 * then boxed label-over-value fields, then Cancel / Save at bottom right.
 */

const MAX_AVATAR_BYTES = 5 * 1024 * 1024;
const ACCEPTED = 'image/png,image/jpeg,image/webp,image/gif';

export default function EditProfileDialog({ open, onOpenChange, profile, profileActions, onSaved }) {
  const [displayName, setDisplayName] = useState('');
  const [username, setUsername] = useState('');
  const [preview, setPreview] = useState(null);   // object URL for a not-yet-uploaded pick
  const [pendingFile, setPendingFile] = useState(null);
  const [removeExisting, setRemoveExisting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const fileRef = useRef(null);

  // Reset the form to the stored profile every time the dialog opens.
  useEffect(() => {
    if (!open) return;
    setDisplayName(profile?.display_name || '');
    setUsername(profile?.username || '');
    setPendingFile(null);
    setRemoveExisting(false);
    setError('');
    setSaving(false);
    setPreview((old) => { if (old) URL.revokeObjectURL(old); return null; });
  }, [open, profile]);

  // Never leak the object URL created for the local preview.
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  const handlePickFile = (e) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // let the same file be re-picked after a cancel
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      setError('Ảnh đại diện phải là tệp PNG, JPG, WEBP hoặc GIF.');
      return;
    }
    if (file.size > MAX_AVATAR_BYTES) {
      setError('Ảnh đại diện không được vượt quá 5 MB.');
      return;
    }
    setError('');
    setPendingFile(file);
    setRemoveExisting(false);
    setPreview((old) => { if (old) URL.revokeObjectURL(old); return URL.createObjectURL(file); });
  };

  const handleRemoveAvatar = () => {
    setPendingFile(null);
    setRemoveExisting(true);
    setPreview((old) => { if (old) URL.revokeObjectURL(old); return null; });
  };

  const handleSave = async () => {
    if (!profile?.id) {
      setError('Không kết nối được máy chủ nên chưa thể lưu hồ sơ.');
      return;
    }
    if (!displayName.trim() || !username.trim()) {
      setError('Tên hiển thị và tên đăng nhập không được để trống.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      // Avatar first, so a rejected image doesn't leave the text half-saved.
      if (pendingFile) await profileActions.uploadAvatar(profile.id, pendingFile);
      else if (removeExisting && profile.avatar_url) await profileActions.removeAvatar(profile.id);

      const updated = await profileActions.updateProfile(profile.id, {
        display_name: displayName.trim(),
        username: username.trim(),
      });
      onSaved?.(updated);
      onOpenChange(false);
    } catch (err) {
      setError(err.message || 'Không thể lưu hồ sơ.');
    } finally {
      setSaving(false);
    }
  };

  const shownAvatar = preview || (removeExisting ? null : profile?.avatar_url);
  const tint = avatarColorOf(profile?.display_name || displayName);

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="st-overlay st-subdialog-overlay" />
        <Dialog.Content className="st-subdialog st-profile-dialog st-scope" aria-describedby={undefined}>
          <Dialog.Title asChild><h3>Chỉnh sửa hồ sơ</h3></Dialog.Title>

          <div className="st-profile-avatar-wrap">
            <button
              type="button"
              className="st-profile-avatar"
              style={shownAvatar ? undefined : { backgroundColor: tint }}
              onClick={() => fileRef.current?.click()}
              aria-label="Đổi ảnh đại diện"
            >
              {shownAvatar
                ? (
                  // shownAvatar là blob: của bản xem trước khi vừa chọn tệp, hoặc
                  // /api/profiles/.../avatar cần token. AuthedImage nhận cả hai.
                  <AuthedImage
                    url={shownAvatar}
                    alt=""
                    fallback={<span>{initialsOf(profile?.display_name || displayName)}</span>}
                  />
                )
                : <span>{initialsOf(profile?.display_name || displayName)}</span>}
              <span className="st-profile-avatar-badge" aria-hidden="true">
                <Camera size={17} />
              </span>
            </button>
            <input
              ref={fileRef}
              type="file"
              accept={ACCEPTED}
              onChange={handlePickFile}
              hidden
            />
            {shownAvatar && (
              <button type="button" className="st-profile-avatar-remove" onClick={handleRemoveAvatar}>
                <Trash2 size={13} /> Xóa ảnh
              </button>
            )}
          </div>

          <div className="st-boxed-field">
            <label htmlFor="ep-display-name">Tên hiển thị</label>
            <input
              id="ep-display-name"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="BS. Hà Thanh Hùng"
              maxLength={80}
            />
          </div>

          <div className="st-boxed-field">
            <label htmlFor="ep-username">Tên đăng nhập</label>
            <input
              id="ep-username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="ha.thanhhung"
              maxLength={60}
            />
          </div>

          {error && <div className="st-profile-error">{error}</div>}

          <div className="st-subdialog-actions">
            <Dialog.Close asChild>
              <button type="button" className="st-btn" disabled={saving}>Hủy</button>
            </Dialog.Close>
            <button
              type="button"
              className="st-btn st-btn-primary"
              onClick={handleSave}
              disabled={saving}
            >
              {saving && <Loader2 size={15} className="st-spin" />}
              {saving ? 'Đang lưu' : 'Lưu'}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
