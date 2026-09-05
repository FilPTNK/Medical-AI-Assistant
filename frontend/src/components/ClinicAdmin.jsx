import React, { useCallback, useEffect, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import {
  X, UserPlus, Loader2, AlertCircle, KeyRound, Lock, Unlock, Trash2, Check,
  Building2, Users, ShieldCheck, Eye, EyeOff, Save,
} from 'lucide-react';
import { apiJson, apiSend } from '../lib/apiClient';
import './ClinicAdmin.css';

/**
 * Quản trị phòng khám: tài khoản bác sĩ (tạo, đổi vai trò, khóa, đặt lại mật
 * khẩu) và thông tin cơ sở in trên đầu giấy tờ xuất PDF.
 *
 * Vai trò quyết định phạm vi nhìn thấy hồ sơ bệnh nhân:
 *   admin     — toàn phòng khám, quản lý được tài khoản
 *   doctor    — chỉ bệnh nhân do mình phụ trách
 *   assistant — xem được toàn phòng khám, không sửa được gì
 */

const ROLE_HINTS = {
  admin: 'Xem toàn bộ hồ sơ và quản lý tài khoản.',
  doctor: 'Chỉ xem hồ sơ bệnh nhân do mình phụ trách.',
  assistant: 'Xem được mọi hồ sơ nhưng không chỉnh sửa.',
};

const EMPTY_DRAFT = {
  display_name: '', username: '', password: '', role: 'doctor', specialty: '', email: '',
};

function PasswordInput({ id, value, onChange, placeholder, autoComplete }) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="ca-password">
      <input
        id={id}
        type={visible ? 'text' : 'password'}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        autoComplete={autoComplete}
      />
      <button
        type="button"
        className="ca-eye"
        onClick={() => setVisible((v) => !v)}
        title={visible ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
      >
        {visible ? <EyeOff size={15} /> : <Eye size={15} />}
      </button>
    </div>
  );
}

/** Đổi mật khẩu của chính mình — mở được từ menu tài khoản, không cần quyền admin. */
/**
 * Đổi mật khẩu của chính mình. Mở từ Cài đặt → Tài khoản.
 *
 * `elevated` nâng z-index để hộp này nằm trên hộp Cài đặt đã mở sẵn.
 * `hasPassword` = false với tài khoản tạo qua Google: chưa từng có mật khẩu nên
 * không hỏi mật khẩu hiện tại, và đổi nhãn thành "Đặt mật khẩu".
 */
export function ChangePasswordDialog({
  open, onOpenChange, onChangePassword, elevated = false, hasPassword = true,
}) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setCurrent(''); setNext(''); setConfirm(''); setError(''); setDone(false);
    }
  }, [open]);

  const submit = async () => {
    if (hasPassword && !current) { setError('Vui lòng nhập mật khẩu hiện tại.'); return; }
    if (next.length < 6) { setError('Mật khẩu mới phải có ít nhất 6 ký tự.'); return; }
    if (next !== confirm) { setError('Hai lần nhập mật khẩu mới không khớp.'); return; }
    setBusy(true);
    setError('');
    try {
      await onChangePassword(current, next);
      setDone(true);
      setCurrent(''); setNext(''); setConfirm('');
    } catch (err) {
      setError(err.message || 'Không đổi được mật khẩu.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className={`ca-overlay${elevated ? ' ca-overlay-top' : ''}`} />
        <Dialog.Content
          className={`ca-dialog ca-dialog-sm${elevated ? ' ca-dialog-top' : ''}`}
          aria-describedby={undefined}
        >
          <Dialog.Title asChild>
            <h3><KeyRound size={17} /> {hasPassword ? 'Đổi mật khẩu' : 'Đặt mật khẩu'}</h3>
          </Dialog.Title>

          {!hasPassword && (
            <p className="ca-dialog-note">
              Tài khoản của bạn đang đăng nhập bằng Google. Đặt thêm mật khẩu để vào
              được bằng tên đăng nhập khi không dùng Google.
            </p>
          )}

          {hasPassword && (
            <div className="ca-field">
              <label htmlFor="cp-current">Mật khẩu hiện tại</label>
              <PasswordInput
                id="cp-current" value={current} autoComplete="current-password"
                onChange={(e) => setCurrent(e.target.value)} placeholder="Mật khẩu đang dùng"
              />
            </div>
          )}

          <div className="ca-field">
            <label htmlFor="cp-new">Mật khẩu mới</label>
            <PasswordInput
              id="cp-new" value={next} autoComplete="new-password"
              onChange={(e) => setNext(e.target.value)} placeholder="Ít nhất 6 ký tự"
            />
          </div>

          <div className="ca-field">
            <label htmlFor="cp-confirm">Nhập lại mật khẩu mới</label>
            <PasswordInput
              id="cp-confirm" value={confirm} autoComplete="new-password"
              onChange={(e) => setConfirm(e.target.value)} placeholder="Nhập lại"
            />
          </div>

          {error && <div className="ca-error"><AlertCircle size={14} /> {error}</div>}
          {done && (
            <div className="ca-success">
              <Check size={14} /> {hasPassword ? 'Đã đổi mật khẩu thành công.' : 'Đã đặt mật khẩu thành công.'}
            </div>
          )}

          <div className="ca-dialog-actions">
            <Dialog.Close asChild>
              <button type="button" className="ca-btn" disabled={busy}>Đóng</button>
            </Dialog.Close>
            <button type="button" className="ca-btn ca-btn-primary" onClick={submit} disabled={busy}>
              {busy
                ? <><Loader2 size={14} className="ca-spin" /> Đang lưu</>
                : (hasPassword ? 'Đổi mật khẩu' : 'Đặt mật khẩu')}
            </button>
          </div>

          <Dialog.Close asChild>
            <button type="button" className="ca-close" aria-label="Đóng"><X size={16} /></button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function UserRow({ user, currentUserId, onUpdate, onReset, onDelete, busy }) {
  const [resetting, setResetting] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const isSelf = user.id === currentUserId;

  return (
    <li className={`ca-user ${user.is_disabled ? 'is-disabled' : ''}`}>
      <div className="ca-user-main">
        <div className="ca-user-id">
          <strong>{user.display_name}</strong>
          {isSelf && <span className="ca-tag">bạn</span>}
          {user.is_disabled && <span className="ca-tag ca-tag-off">đã khóa</span>}
        </div>
        <div className="ca-user-meta">
          <span>@{user.username}</span>
          {user.specialty && <span>· {user.specialty}</span>}
          {!user.has_password && <span className="ca-warn">· chưa đặt mật khẩu</span>}
          {user.must_change_password && <span className="ca-warn">· cần đổi mật khẩu</span>}
        </div>
      </div>

      <div className="ca-user-controls">
        <select
          className="ca-role-select"
          value={user.role}
          disabled={busy}
          onChange={(e) => onUpdate(user, { role: e.target.value })}
          title={ROLE_HINTS[user.role]}
          aria-label={`Vai trò của ${user.display_name}`}
        >
          <option value="admin">Quản trị</option>
          <option value="doctor">Bác sĩ</option>
          <option value="assistant">Điều dưỡng</option>
        </select>

        <button
          type="button" className="ca-icon-btn" disabled={busy}
          onClick={() => setResetting((v) => !v)}
          title="Đặt lại mật khẩu"
        ><KeyRound size={15} /></button>

        {!isSelf && (
          <>
            <button
              type="button" className="ca-icon-btn" disabled={busy}
              onClick={() => onUpdate(user, { is_disabled: !user.is_disabled })}
              title={user.is_disabled ? 'Mở khóa tài khoản' : 'Khóa tài khoản'}
            >
              {user.is_disabled ? <Unlock size={15} /> : <Lock size={15} />}
            </button>
            <button
              type="button" className="ca-icon-btn ca-icon-danger" disabled={busy}
              onClick={() => onDelete(user)}
              title="Xóa tài khoản"
            ><Trash2 size={15} /></button>
          </>
        )}
      </div>

      {resetting && (
        <div className="ca-reset">
          <PasswordInput
            id={`reset-${user.id}`} value={newPassword} autoComplete="new-password"
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="Mật khẩu mới, ít nhất 6 ký tự"
          />
          <button
            type="button" className="ca-btn ca-btn-primary" disabled={busy}
            onClick={async () => {
              await onReset(user, newPassword);
              setNewPassword('');
              setResetting(false);
            }}
          >Đặt lại</button>
          <button type="button" className="ca-btn" onClick={() => { setResetting(false); setNewPassword(''); }}>
            Hủy
          </button>
        </div>
      )}
    </li>
  );
}

export default function ClinicAdminDialog({ open, onOpenChange, currentUser }) {
  const [tab, setTab] = useState('users');
  const [users, setUsers] = useState([]);
  const [clinic, setClinic] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState(EMPTY_DRAFT);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [userList, clinicInfo] = await Promise.all([
        apiJson('/api/users'),
        apiJson('/api/clinic'),
      ]);
      setUsers(userList);
      setClinic(clinicInfo);
    } catch (err) {
      setError(err.message || 'Không tải được dữ liệu quản trị.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      setTab('users');
      setAdding(false);
      setDraft(EMPTY_DRAFT);
      setNotice('');
      load();
    }
  }, [open, load]);

  /** Bọc mọi thao tác ghi: bật cờ bận, hiện lỗi/ghi chú, rồi tải lại danh sách. */
  const run = useCallback(async (action, successNote) => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await action();
      if (successNote) setNotice(successNote);
      await load();
      return true;
    } catch (err) {
      setError(err.message || 'Thao tác không thành công.');
      return false;
    } finally {
      setBusy(false);
    }
  }, [load]);

  const createUser = () => {
    if (!draft.display_name.trim() || !draft.username.trim()) {
      setError('Tên hiển thị và tên đăng nhập không được để trống.');
      return;
    }
    if (draft.password.length < 6) {
      setError('Mật khẩu phải có ít nhất 6 ký tự.');
      return;
    }
    run(
      () => apiSend('/api/users', 'POST', draft),
      `Đã tạo tài khoản cho ${draft.display_name.trim()}.`,
    ).then((ok) => {
      if (ok) { setDraft(EMPTY_DRAFT); setAdding(false); }
    });
  };

  const updateUser = (user, fields) =>
    run(() => apiSend(`/api/users/${user.id}`, 'PUT', fields));

  const resetPassword = (user, password) => {
    if (password.length < 6) {
      setError('Mật khẩu phải có ít nhất 6 ký tự.');
      return Promise.resolve(false);
    }
    return run(
      () => apiSend(`/api/users/${user.id}/reset-password`, 'POST', {
        new_password: password, must_change: true,
      }),
      `Đã đặt lại mật khẩu cho ${user.display_name}. Người dùng nên đổi lại sau khi đăng nhập.`,
    );
  };

  const deleteUser = (user) => {
    // Xóa tài khoản không xóa bệnh nhân họ phụ trách; nhắc rõ để quản trị bàn giao trước.
    const confirmed = window.confirm(
      `Xóa tài khoản "${user.display_name}"?\n\n`
      + 'Hồ sơ bệnh nhân do người này phụ trách sẽ không bị xóa, nhưng sẽ không còn ai '
      + 'phụ trách cho tới khi bạn bàn giao lại.',
    );
    if (!confirmed) return;
    run(() => apiJson(`/api/users/${user.id}`, { method: 'DELETE' }),
      `Đã xóa tài khoản ${user.display_name}.`);
  };

  const saveClinic = () =>
    run(() => apiSend('/api/clinic', 'PUT', clinic), 'Đã lưu thông tin phòng khám.');

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="ca-overlay" />
        <Dialog.Content className="ca-dialog" aria-describedby={undefined}>
          <Dialog.Title asChild><h3><ShieldCheck size={17} /> Quản trị phòng khám</h3></Dialog.Title>

          <div className="ca-tabs" role="tablist">
            <button
              type="button" role="tab" aria-selected={tab === 'users'}
              className={tab === 'users' ? 'active' : ''} onClick={() => setTab('users')}
            ><Users size={15} /> Tài khoản</button>
            <button
              type="button" role="tab" aria-selected={tab === 'clinic'}
              className={tab === 'clinic' ? 'active' : ''} onClick={() => setTab('clinic')}
            ><Building2 size={15} /> Thông tin phòng khám</button>
          </div>

          {error && <div className="ca-error"><AlertCircle size={14} /> {error}</div>}
          {notice && <div className="ca-success"><Check size={14} /> {notice}</div>}

          {loading ? (
            <div className="ca-state"><Loader2 size={18} className="ca-spin" /> Đang tải…</div>
          ) : tab === 'users' ? (
            <>
              <p className="ca-hint">
                Bác sĩ chỉ nhìn thấy hồ sơ bệnh nhân do mình phụ trách. Quản trị và điều dưỡng
                thấy toàn bộ hồ sơ; điều dưỡng không chỉnh sửa được.
              </p>

              <ul className="ca-users">
                {users.map((user) => (
                  <UserRow
                    key={user.id}
                    user={user}
                    currentUserId={currentUser?.id}
                    busy={busy}
                    onUpdate={updateUser}
                    onReset={resetPassword}
                    onDelete={deleteUser}
                  />
                ))}
              </ul>

              {adding ? (
                <div className="ca-add">
                  <h4>Tài khoản mới</h4>
                  <div className="ca-field-row">
                    <div className="ca-field">
                      <label htmlFor="ca-name">Tên hiển thị</label>
                      <input
                        id="ca-name" type="text" value={draft.display_name}
                        onChange={(e) => setDraft((d) => ({ ...d, display_name: e.target.value }))}
                        placeholder="BS. Lê Thị Hoa"
                      />
                    </div>
                    <div className="ca-field">
                      <label htmlFor="ca-username">Tên đăng nhập</label>
                      <input
                        id="ca-username" type="text" value={draft.username}
                        onChange={(e) => setDraft((d) => ({ ...d, username: e.target.value }))}
                        placeholder="le.thihoa"
                      />
                    </div>
                  </div>

                  <div className="ca-field-row">
                    <div className="ca-field">
                      <label htmlFor="ca-role">Vai trò</label>
                      <select
                        id="ca-role" value={draft.role}
                        onChange={(e) => setDraft((d) => ({ ...d, role: e.target.value }))}
                      >
                        <option value="doctor">Bác sĩ</option>
                        <option value="assistant">Điều dưỡng / Trợ lý</option>
                        <option value="admin">Quản trị phòng khám</option>
                      </select>
                      <span className="ca-field-hint">{ROLE_HINTS[draft.role]}</span>
                    </div>
                    <div className="ca-field">
                      <label htmlFor="ca-specialty">Chuyên khoa</label>
                      <input
                        id="ca-specialty" type="text" value={draft.specialty}
                        onChange={(e) => setDraft((d) => ({ ...d, specialty: e.target.value }))}
                        placeholder="Nội tổng quát"
                      />
                    </div>
                  </div>

                  <div className="ca-field">
                    <label htmlFor="ca-pass">Mật khẩu ban đầu</label>
                    <PasswordInput
                      id="ca-pass" value={draft.password} autoComplete="new-password"
                      onChange={(e) => setDraft((d) => ({ ...d, password: e.target.value }))}
                      placeholder="Ít nhất 6 ký tự"
                    />
                    <span className="ca-field-hint">
                      Người dùng sẽ được nhắc đổi mật khẩu sau lần đăng nhập đầu tiên.
                    </span>
                  </div>

                  <div className="ca-add-actions">
                    <button type="button" className="ca-btn" onClick={() => { setAdding(false); setDraft(EMPTY_DRAFT); }}>
                      Hủy
                    </button>
                    <button type="button" className="ca-btn ca-btn-primary" onClick={createUser} disabled={busy}>
                      {busy ? <><Loader2 size={14} className="ca-spin" /> Đang tạo</> : 'Tạo tài khoản'}
                    </button>
                  </div>
                </div>
              ) : (
                <button type="button" className="ca-btn ca-btn-add" onClick={() => setAdding(true)}>
                  <UserPlus size={15} /> Thêm tài khoản
                </button>
              )}
            </>
          ) : (
            <>
              <p className="ca-hint">
                Những thông tin này in ở đầu bệnh án, phiếu khám và giấy chuyển tuyến xuất ra PDF.
              </p>

              <div className="ca-field-row">
                <div className="ca-field">
                  <label htmlFor="cl-parent">Cơ quan chủ quản</label>
                  <input
                    id="cl-parent" type="text" value={clinic?.parent_org || ''}
                    onChange={(e) => setClinic((c) => ({ ...c, parent_org: e.target.value }))}
                    placeholder="SỞ Y TẾ TỈNH…"
                  />
                </div>
                <div className="ca-field">
                  <label htmlFor="cl-name">Tên cơ sở khám chữa bệnh</label>
                  <input
                    id="cl-name" type="text" value={clinic?.name || ''}
                    onChange={(e) => setClinic((c) => ({ ...c, name: e.target.value }))}
                    placeholder="PHÒNG KHÁM ĐA KHOA…"
                  />
                </div>
              </div>

              <div className="ca-field">
                <label htmlFor="cl-dept">Khoa / phòng</label>
                <input
                  id="cl-dept" type="text" value={clinic?.department || ''}
                  onChange={(e) => setClinic((c) => ({ ...c, department: e.target.value }))}
                  placeholder="Khoa Nội"
                />
              </div>

              <div className="ca-field">
                <label htmlFor="cl-address">Địa chỉ</label>
                <input
                  id="cl-address" type="text" value={clinic?.address || ''}
                  onChange={(e) => setClinic((c) => ({ ...c, address: e.target.value }))}
                  placeholder="Số nhà, đường, phường/xã, tỉnh/thành"
                />
              </div>

              <div className="ca-field-row">
                <div className="ca-field">
                  <label htmlFor="cl-phone">Điện thoại</label>
                  <input
                    id="cl-phone" type="text" value={clinic?.phone || ''}
                    onChange={(e) => setClinic((c) => ({ ...c, phone: e.target.value }))}
                    placeholder="028 1234 5678"
                  />
                </div>
                <div className="ca-field">
                  <label htmlFor="cl-email">Email</label>
                  <input
                    id="cl-email" type="text" value={clinic?.email || ''}
                    onChange={(e) => setClinic((c) => ({ ...c, email: e.target.value }))}
                    placeholder="Không bắt buộc"
                  />
                </div>
              </div>

              <div className="ca-add-actions">
                <button type="button" className="ca-btn ca-btn-primary" onClick={saveClinic} disabled={busy}>
                  {busy ? <><Loader2 size={14} className="ca-spin" /> Đang lưu</> : <><Save size={14} /> Lưu thông tin</>}
                </button>
              </div>
            </>
          )}

          <Dialog.Close asChild>
            <button type="button" className="ca-close" aria-label="Đóng"><X size={16} /></button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
