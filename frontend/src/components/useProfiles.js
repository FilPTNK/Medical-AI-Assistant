import { useCallback, useEffect, useMemo, useState } from 'react';

/**
 * Doctor profiles, backed by the API (backend/profile_db.py → data/profiles.db).
 *
 * This is the single source of truth for the doctor's display name, username,
 * specialty, email and avatar — shared by the sidebar account menu, the
 * "Chỉnh sửa hồ sơ" dialog and Settings → Tài khoản.
 *
 * If the backend is unreachable the hook degrades to a read-only placeholder
 * so the sidebar still renders a name instead of collapsing.
 */

const FALLBACK_PROFILE = {
  id: null,
  display_name: 'BS. Hà Thanh Hùng',
  username: 'ha.thanhhung',
  specialty: 'Nội tổng quát',
  email: '',
  avatar_url: null,
  is_active: true,
};

export const initialsOf = (name) => {
  const parts = String(name || '').replace(/^BS\.?\s*/i, '').trim().split(/\s+/);
  return ((parts[0]?.[0] || '') + (parts[parts.length - 1]?.[0] || '')).toUpperCase() || 'BS';
};

/** Deterministic avatar tint, so each doctor keeps a stable colour. */
const AVATAR_COLORS = ['#c2410c', '#0d9488', '#7c3aed', '#b91c1c', '#1d4ed8', '#a16207', '#be185d'];
export const avatarColorOf = (name) => {
  let hash = 0;
  const s = String(name || '');
  for (let i = 0; i < s.length; i += 1) hash = (hash * 31 + s.charCodeAt(i)) >>> 0;
  return AVATAR_COLORS[hash % AVATAR_COLORS.length];
};

/** Turns a failed fetch into a thrown Error carrying the API's Vietnamese detail. */
const unwrap = async (res) => {
  if (res.ok) return res.json();
  let detail = 'Không thể kết nối máy chủ.';
  try {
    const body = await res.json();
    if (body?.detail) detail = body.detail;
  } catch {
    /* non-JSON error body — keep the generic message */
  }
  throw new Error(detail);
};

export default function useProfiles() {
  const [profiles, setProfiles] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [offline, setOffline] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const list = await unwrap(await fetch('/api/profiles'));
      setProfiles(Array.isArray(list) ? list : []);
      setOffline(false);
    } catch {
      setProfiles([]);
      setOffline(true);
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const activeProfile = useMemo(() => {
    if (!profiles.length) return FALLBACK_PROFILE;
    return profiles.find((p) => p.is_active) || profiles[0];
  }, [profiles]);

  /** Replaces one profile in local state with the row the API just returned. */
  const absorb = useCallback((updated) => {
    setProfiles((prev) => {
      const next = prev.some((p) => p.id === updated.id)
        ? prev.map((p) => (p.id === updated.id ? updated : p))
        : [...prev, updated];
      // Only one row may be active at a time.
      return updated.is_active
        ? next.map((p) => (p.id === updated.id ? p : { ...p, is_active: false }))
        : next;
    });
    return updated;
  }, []);

  const updateProfile = useCallback(async (profileId, fields) => {
    const updated = await unwrap(await fetch(`/api/profiles/${profileId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(fields),
    }));
    return absorb(updated);
  }, [absorb]);

  const uploadAvatar = useCallback(async (profileId, file) => {
    const form = new FormData();
    form.append('file', file);
    const updated = await unwrap(await fetch(`/api/profiles/${profileId}/avatar`, {
      method: 'POST',
      body: form,
    }));
    return absorb(updated);
  }, [absorb]);

  const removeAvatar = useCallback(async (profileId) => {
    const updated = await unwrap(await fetch(`/api/profiles/${profileId}/avatar`, {
      method: 'DELETE',
    }));
    return absorb(updated);
  }, [absorb]);

  const createProfile = useCallback(async (fields) => {
    const created = await unwrap(await fetch('/api/profiles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(fields),
    }));
    await refresh();
    return created;
  }, [refresh]);

  const activateProfile = useCallback(async (profileId) => {
    const updated = await unwrap(await fetch(`/api/profiles/${profileId}/activate`, {
      method: 'POST',
    }));
    return absorb(updated);
  }, [absorb]);

  const deleteProfile = useCallback(async (profileId) => {
    await unwrap(await fetch(`/api/profiles/${profileId}`, { method: 'DELETE' }));
    await refresh();
  }, [refresh]);

  return {
    profiles, activeProfile, loaded, offline, refresh,
    updateProfile, uploadAvatar, removeAvatar,
    createProfile, activateProfile, deleteProfile,
  };
}
