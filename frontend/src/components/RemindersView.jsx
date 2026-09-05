import React, { useCallback, useEffect, useMemo, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import {
  BellRing, CalendarClock, CalendarCheck, Check, Clock, Loader2, Plus, RefreshCw,
  Repeat, Trash2, X, AlertCircle, UserRound, ChevronRight, Ban, RotateCcw,
} from 'lucide-react';
import { apiJson, apiSend } from '../lib/apiClient';
import './RemindersView.css';

/**
 * Nhắc lịch tái khám & theo dõi bệnh nhân mãn tính.
 *
 * Lời nhắc tái khám sinh tự động từ ngày hẹn trong phiếu khám; bác sĩ tạo thêm
 * lời nhắc thủ công có chu kỳ lặp cho bệnh nhân mãn tính (ví dụ đo HbA1c mỗi
 * 90 ngày). Danh sách chia theo mức khẩn để việc quá hạn không lẫn vào lịch của
 * tuần sau.
 */

const KIND_OPTIONS = [
  { value: 'followup', label: 'Tái khám' },
  { value: 'chronic', label: 'Theo dõi mãn tính' },
  { value: 'lab', label: 'Xét nghiệm / cận lâm sàng' },
  { value: 'medication', label: 'Nhắc thuốc' },
  { value: 'custom', label: 'Khác' },
];

const REPEAT_OPTIONS = [
  { value: '', label: 'Không lặp lại' },
  { value: '7', label: 'Mỗi tuần' },
  { value: '14', label: 'Mỗi 2 tuần' },
  { value: '30', label: 'Mỗi tháng' },
  { value: '90', label: 'Mỗi 3 tháng' },
  { value: '180', label: 'Mỗi 6 tháng' },
  { value: '365', label: 'Mỗi năm' },
];

const STATUS_TABS = [
  { value: 'pending', label: 'Đang chờ' },
  { value: 'done', label: 'Đã thực hiện' },
  { value: 'dismissed', label: 'Đã bỏ qua' },
];

const formatDate = (iso) => {
  if (!iso) return '--';
  const d = new Date(`${String(iso).slice(0, 10)}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' });
};

const todayIso = () => new Date().toISOString().slice(0, 10);

/** "Quá hạn 3 ngày" / "Hôm nay" / "Còn 5 ngày" — đọc nhanh hơn ngày tuyệt đối. */
const dueLabel = (days) => {
  if (days === null || days === undefined) return '';
  if (days < 0) return `Quá hạn ${Math.abs(days)} ngày`;
  if (days === 0) return 'Đến hạn hôm nay';
  if (days === 1) return 'Ngày mai';
  return `Còn ${days} ngày`;
};

const repeatLabel = (days) =>
  REPEAT_OPTIONS.find((o) => o.value === String(days))?.label
  || (days ? `Mỗi ${days} ngày` : null);

function ReminderCard({ reminder, onComplete, onSnooze, onDismiss, onReopen, onDelete, onOpenPatient, busy, readOnly }) {
  const tone = reminder.status !== 'pending' ? 'done'
    : reminder.overdue ? 'overdue'
    : reminder.days_diff === 0 ? 'today' : 'upcoming';

  return (
    <li className={`rm-card rm-card-${tone}`}>
      <div className="rm-card-main">
        <div className="rm-card-top">
          <button type="button" className="rm-patient" onClick={() => onOpenPatient(reminder.patient_id)}>
            <span className="rm-patient-avatar"><UserRound size={14} /></span>
            <span className="rm-patient-name">{reminder.patient_name}</span>
            <span className="rm-patient-code">{reminder.patient_code}</span>
            <ChevronRight size={14} className="rm-patient-chevron" />
          </button>
          <span className={`rm-kind rm-kind-${reminder.kind}`}>{reminder.kind_label}</span>
        </div>

        <div className="rm-card-body">
          <strong className="rm-card-title">{reminder.title || reminder.kind_label}</strong>
          {reminder.note && <p className="rm-card-note">{reminder.note}</p>}
        </div>

        <div className="rm-card-meta">
          <span className="rm-meta-item">
            <CalendarClock size={13} /> {formatDate(reminder.effective_date)}
          </span>
          {reminder.status === 'pending' && (
            <span className={`rm-due rm-due-${tone}`}>{dueLabel(reminder.days_diff)}</span>
          )}
          {reminder.snoozed && reminder.status === 'pending' && (
            <span className="rm-meta-item rm-meta-muted"><Clock size={13} /> đã hoãn</span>
          )}
          {reminder.repeat_interval_days ? (
            <span className="rm-meta-item rm-meta-muted">
              <Repeat size={13} /> {repeatLabel(reminder.repeat_interval_days)}
            </span>
          ) : null}
          {reminder.source === 'visit' && (
            <span className="rm-meta-item rm-meta-muted">từ phiếu khám</span>
          )}
          {reminder.status === 'done' && reminder.completed_at && (
            <span className="rm-meta-item rm-meta-muted">
              <CalendarCheck size={13} /> xong {formatDate(reminder.completed_at)}
            </span>
          )}
        </div>
      </div>

      {!readOnly && (
        <div className="rm-card-actions">
          {reminder.status === 'pending' ? (
            <>
              <button
                type="button" className="rm-act rm-act-primary" disabled={busy}
                onClick={() => onComplete(reminder)} title="Đánh dấu đã thực hiện"
              >
                <Check size={14} /> Đã khám
              </button>
              <div className="rm-snooze">
                <Clock size={13} />
                {[1, 3, 7].map((d) => (
                  <button
                    key={d} type="button" className="rm-act-mini" disabled={busy}
                    onClick={() => onSnooze(reminder, d)} title={`Hoãn ${d} ngày`}
                  >+{d}n</button>
                ))}
              </div>
              <button
                type="button" className="rm-act" disabled={busy}
                onClick={() => onDismiss(reminder)} title="Bỏ qua lời nhắc này"
              >
                <Ban size={14} />
              </button>
            </>
          ) : (
            <button
              type="button" className="rm-act" disabled={busy}
              onClick={() => onReopen(reminder)} title="Mở lại lời nhắc"
            >
              <RotateCcw size={14} /> Mở lại
            </button>
          )}
          {reminder.source !== 'visit' && (
            <button
              type="button" className="rm-act rm-act-danger" disabled={busy}
              onClick={() => onDelete(reminder)} title="Xóa lời nhắc"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      )}
    </li>
  );
}

function CreateReminderDialog({ open, onOpenChange, patients, defaultPatientId, onCreated }) {
  const [form, setForm] = useState({
    patient_id: '', kind: 'followup', title: '', note: '',
    due_date: todayIso(), repeat_interval_days: '',
  });
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setForm({
        patient_id: defaultPatientId || '',
        kind: 'followup', title: '', note: '',
        due_date: todayIso(), repeat_interval_days: '',
      });
      setError('');
    }
  }, [open, defaultPatientId]);

  const submit = async () => {
    if (!form.patient_id) {
      setError('Hãy chọn bệnh nhân cần nhắc lịch.');
      return;
    }
    if (!form.due_date) {
      setError('Hãy chọn ngày hẹn.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const created = await apiSend('/api/reminders', 'POST', {
        patient_id: form.patient_id,
        kind: form.kind,
        title: form.title.trim() || null,
        note: form.note.trim() || null,
        due_date: form.due_date,
        repeat_interval_days: form.repeat_interval_days ? Number(form.repeat_interval_days) : null,
      });
      onCreated(created);
      onOpenChange(false);
    } catch (err) {
      setError(err.message || 'Không tạo được lời nhắc.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="rm-overlay" />
        <Dialog.Content className="rm-dialog" aria-describedby={undefined}>
          <Dialog.Title asChild><h3>Tạo lời nhắc</h3></Dialog.Title>
          <p className="rm-dialog-sub">
            Dùng cho lịch theo dõi bệnh nhân mãn tính, hẹn xét nghiệm hoặc nhắc thuốc.
            Lịch tái khám ghi trong phiếu khám đã được nhắc tự động.
          </p>

          <div className="rm-field">
            <label htmlFor="rm-patient">Bệnh nhân</label>
            <select
              id="rm-patient"
              value={form.patient_id}
              onChange={(e) => setForm((f) => ({ ...f, patient_id: e.target.value }))}
            >
              <option value="">— Chọn bệnh nhân —</option>
              {patients.map((p) => (
                <option key={p.id} value={p.id}>{p.name} · {p.code}</option>
              ))}
            </select>
          </div>

          <div className="rm-field-row">
            <div className="rm-field">
              <label htmlFor="rm-kind">Loại nhắc</label>
              <select
                id="rm-kind"
                value={form.kind}
                onChange={(e) => setForm((f) => ({ ...f, kind: e.target.value }))}
              >
                {KIND_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
            <div className="rm-field">
              <label htmlFor="rm-due">Ngày hẹn</label>
              <input
                id="rm-due" type="date" value={form.due_date}
                onChange={(e) => setForm((f) => ({ ...f, due_date: e.target.value }))}
              />
            </div>
          </div>

          <div className="rm-field">
            <label htmlFor="rm-title">Tiêu đề</label>
            <input
              id="rm-title" type="text" value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              placeholder="Ví dụ: Đo HbA1c định kỳ"
            />
          </div>

          <div className="rm-field">
            <label htmlFor="rm-note">Nội dung / lý do</label>
            <textarea
              id="rm-note" rows={2} value={form.note}
              onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
              placeholder="Đái tháo đường type 2 — theo dõi đường huyết"
            />
          </div>

          <div className="rm-field">
            <label htmlFor="rm-repeat">Lặp lại</label>
            <select
              id="rm-repeat" value={form.repeat_interval_days}
              onChange={(e) => setForm((f) => ({ ...f, repeat_interval_days: e.target.value }))}
            >
              {REPEAT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <span className="rm-field-hint">
              Khi đánh dấu đã thực hiện, hệ thống tự tạo lời nhắc kế tiếp theo chu kỳ này.
            </span>
          </div>

          {error && <div className="rm-error"><AlertCircle size={14} /> {error}</div>}

          <div className="rm-dialog-actions">
            <Dialog.Close asChild>
              <button type="button" className="rm-btn" disabled={saving}>Hủy</button>
            </Dialog.Close>
            <button type="button" className="rm-btn rm-btn-primary" onClick={submit} disabled={saving}>
              {saving ? <><Loader2 size={14} className="rm-spin" /> Đang lưu</> : 'Tạo lời nhắc'}
            </button>
          </div>

          <Dialog.Close asChild>
            <button type="button" className="rm-dialog-close" aria-label="Đóng"><X size={16} /></button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export default function RemindersView({ permissions, patients, onOpenPatient, onChanged }) {
  const [status, setStatus] = useState('pending');
  const [kind, setKind] = useState('');
  const [scope, setScope] = useState(permissions.seesAllPatients ? 'clinic' : 'mine');
  const [reminders, setReminders] = useState([]);
  const [summary, setSummary] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    const params = new URLSearchParams({ status });
    if (kind) params.set('kind', kind);
    if (scope === 'mine') params.set('scope', 'mine');
    try {
      const [list, sum] = await Promise.all([
        apiJson(`/api/reminders?${params.toString()}`),
        apiJson(`/api/reminders/summary${scope === 'mine' ? '?scope=mine' : ''}`),
      ]);
      setReminders(Array.isArray(list) ? list : []);
      setSummary(sum || {});
    } catch (err) {
      setError(err.message || 'Không tải được danh sách nhắc lịch.');
    } finally {
      setLoading(false);
    }
  }, [status, kind, scope]);

  useEffect(() => { load(); }, [load]);

  const act = useCallback(async (reminder, request) => {
    setBusyId(reminder.id);
    try {
      await request();
      await load();
      onChanged?.();
    } catch (err) {
      setError(err.message || 'Thao tác không thành công.');
    } finally {
      setBusyId(null);
    }
  }, [load, onChanged]);

  const handlers = useMemo(() => ({
    onComplete: (r) => act(r, () => apiSend(`/api/reminders/${r.id}/complete`, 'POST')),
    onSnooze: (r, days) => act(r, () => apiSend(`/api/reminders/${r.id}/snooze`, 'POST', { days })),
    onDismiss: (r) => act(r, () => apiSend(`/api/reminders/${r.id}/dismiss`, 'POST')),
    onReopen: (r) => act(r, () => apiSend(`/api/reminders/${r.id}/reopen`, 'POST')),
    onDelete: (r) => act(r, () => apiJson(`/api/reminders/${r.id}`, { method: 'DELETE' })),
  }), [act]);

  // Chỉ nhóm theo mức khẩn ở tab "đang chờ" — tab đã xong không còn khái niệm quá hạn.
  const groups = useMemo(() => {
    if (status !== 'pending') return [{ key: 'all', label: null, items: reminders }];
    const overdue = reminders.filter((r) => r.days_diff < 0);
    const today = reminders.filter((r) => r.days_diff === 0);
    const week = reminders.filter((r) => r.days_diff > 0 && r.days_diff <= 7);
    const later = reminders.filter((r) => r.days_diff > 7);
    return [
      { key: 'overdue', label: 'Quá hạn', items: overdue },
      { key: 'today', label: 'Hôm nay', items: today },
      { key: 'week', label: '7 ngày tới', items: week },
      { key: 'later', label: 'Sau đó', items: later },
    ].filter((g) => g.items.length > 0);
  }, [reminders, status]);

  return (
    <div className="rm-view animate-fade-in">
      <div className="rm-topbar">
        <div>
          <h1 className="rm-title">Nhắc lịch & theo dõi</h1>
          <p className="rm-subtitle">
            {scope === 'mine' ? 'Bệnh nhân bạn phụ trách' : 'Toàn phòng khám'} ·
            {' '}lịch tái khám và theo dõi bệnh mãn tính
          </p>
        </div>

        <div className="rm-actions">
          {permissions.seesAllPatients && (
            <div className="rm-segmented" role="group" aria-label="Phạm vi">
              <button type="button" className={scope === 'clinic' ? 'active' : ''} onClick={() => setScope('clinic')}>Phòng khám</button>
              <button type="button" className={scope === 'mine' ? 'active' : ''} onClick={() => setScope('mine')}>Của tôi</button>
            </div>
          )}
          <button type="button" className="rm-btn rm-btn-ghost" onClick={load} title="Tải lại">
            <RefreshCw size={15} className={loading ? 'rm-spin' : ''} />
          </button>
          {!permissions.isReadOnly && (
            <button type="button" className="rm-btn rm-btn-primary" onClick={() => setCreateOpen(true)}>
              <Plus size={15} /> Tạo lời nhắc
            </button>
          )}
        </div>
      </div>

      <div className="rm-summary">
        <div className={`rm-sum rm-sum-overdue ${summary.overdue ? 'is-alert' : ''}`}>
          <span className="rm-sum-label"><AlertCircle size={14} /> Quá hạn</span>
          <strong>{summary.overdue ?? 0}</strong>
        </div>
        <div className="rm-sum rm-sum-today">
          <span className="rm-sum-label"><BellRing size={14} /> Hôm nay</span>
          <strong>{summary.today ?? 0}</strong>
        </div>
        <div className="rm-sum">
          <span className="rm-sum-label"><CalendarClock size={14} /> 7 ngày tới</span>
          <strong>{summary.next_7_days ?? 0}</strong>
        </div>
        <div className="rm-sum">
          <span className="rm-sum-label"><CalendarCheck size={14} /> Đang chờ</span>
          <strong>{summary.pending_total ?? 0}</strong>
        </div>
      </div>

      <div className="rm-filters">
        <div className="rm-segmented" role="group" aria-label="Trạng thái">
          {STATUS_TABS.map((t) => (
            <button
              key={t.value} type="button"
              className={status === t.value ? 'active' : ''}
              onClick={() => setStatus(t.value)}
            >{t.label}</button>
          ))}
        </div>

        <select className="rm-select" value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Loại nhắc">
          <option value="">Tất cả loại</option>
          {KIND_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>

      {error && <div className="rm-error rm-error-block"><AlertCircle size={14} /> {error}</div>}

      {loading && reminders.length === 0 ? (
        <div className="rm-state"><Loader2 size={20} className="rm-spin" /> Đang tải nhắc lịch…</div>
      ) : reminders.length === 0 ? (
        <div className="rm-state rm-state-empty">
          <div className="rm-empty-icon"><CalendarCheck size={26} /></div>
          <h3>{status === 'pending' ? 'Không có lịch nào cần nhắc' : 'Danh sách trống'}</h3>
          <p>
            {status === 'pending'
              ? 'Ghi ngày hẹn tái khám trong phiếu khám, hoặc tạo lời nhắc theo dõi cho bệnh nhân mãn tính.'
              : 'Chưa có lời nhắc nào ở trạng thái này.'}
          </p>
        </div>
      ) : (
        groups.map((group) => (
          <section className="rm-group" key={group.key}>
            {group.label && (
              <h2 className={`rm-group-title rm-group-${group.key}`}>
                {group.label} <span>{group.items.length}</span>
              </h2>
            )}
            <ul className="rm-list">
              {group.items.map((reminder) => (
                <ReminderCard
                  key={reminder.id}
                  reminder={reminder}
                  busy={busyId === reminder.id}
                  readOnly={permissions.isReadOnly}
                  onOpenPatient={onOpenPatient}
                  {...handlers}
                />
              ))}
            </ul>
          </section>
        ))
      )}

      <CreateReminderDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        patients={patients}
        onCreated={() => { load(); onChanged?.(); }}
      />
    </div>
  );
}
