import { useCallback, useEffect, useMemo, useState } from 'react';

/**
 * Owns every persisted user preference behind the settings dialog.
 *
 * App.jsx already stored a handful of these ad-hoc (theme, med_library_view,
 * notify_enabled, ...); this hook keeps those exact localStorage keys so
 * existing installs keep their settings, and adds the rest under a `set_` prefix.
 */

const readBool = (key, fallback) => {
  const raw = localStorage.getItem(key);
  if (raw === null) return fallback;
  return raw !== 'false';
};

const readString = (key, fallback) => localStorage.getItem(key) || fallback;

const readJSON = (key, fallback) => {
  try {
    const raw = localStorage.getItem(key);
    return raw ? { ...fallback, ...JSON.parse(raw) } : fallback;
  } catch {
    return fallback;
  }
};

export const ACCENT_COLORS = [
  { value: 'default', label: 'Mặc định', color: '#3a83f7' },
  { value: 'blue', label: 'Xanh dương', color: '#2563eb' },
  { value: 'teal', label: 'Xanh ngọc', color: '#0d9488' },
  { value: 'green', label: 'Xanh lá', color: '#16a34a' },
  { value: 'violet', label: 'Tím', color: '#7c3aed' },
  { value: 'orange', label: 'Cam', color: '#ea580c' },
  { value: 'rose', label: 'Hồng', color: '#e11d48' },
];

const DEFAULT_CUSTOM_INSTRUCTIONS = {
  nickname: '',
  specialty: '',
  traits: '',
  extra: '',
};

/** Rough byte count of everything this app has put in localStorage. */
export const measureStorage = () => {
  let bytes = 0;
  const perKey = [];
  for (let i = 0; i < localStorage.length; i += 1) {
    const key = localStorage.key(i);
    const size = ((localStorage.getItem(key) || '').length + key.length) * 2;
    bytes += size;
    perKey.push({ key, size });
  }
  perKey.sort((a, b) => b.size - a.size);
  return { bytes, perKey };
};

export const formatBytes = (bytes) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
};

export default function useSettings() {
  // --- General ---
  // Khoá mới (_v2) để mọi máy về giao diện SÁNG một lần: nền trắng–xanh bệnh
  // viện là mặc định, chế độ tối chỉ còn là lựa chọn tự bật.
  const [appearance, setAppearanceState] = useState(() => readString('set_appearance_v2', 'light'));
  const [accentColor, setAccentColorState] = useState(() => readString('set_accent', 'default'));
  const [language, setLanguageState] = useState(() => readString('set_language', 'vi'));
  const [followUpSuggestions, setFollowUpSuggestionsState] = useState(() => readBool('followup_suggestions', true));

  // --- Notifications ---
  const [notifyEnabled, setNotifyEnabledState] = useState(() => readBool('notify_enabled', true));
  const [notifyRecheck, setNotifyRecheckState] = useState(() => readBool('set_notify_recheck', true));
  const [notifyInteraction, setNotifyInteractionState] = useState(() => readBool('set_notify_interaction', true));

  // --- Personalization ---
  const [memoryEnabled, setMemoryEnabledState] = useState(() => readBool('personalization_memory', true));
  const [referenceHistory, setReferenceHistoryState] = useState(() => readBool('set_reference_history', true));
  const [answerDetail, setAnswerDetailState] = useState(() => readString('set_answer_detail', 'balanced'));
  const [customInstructions, setCustomInstructionsState] = useState(() =>
    readJSON('set_custom_instructions', DEFAULT_CUSTOM_INSTRUCTIONS));

  // --- Voice ---
  const [voiceInputEnabled, setVoiceInputEnabledState] = useState(() => readBool('set_voice_input', true));
  const [voiceLang, setVoiceLangState] = useState(() => readString('set_voice_lang', 'vi-VN'));
  const [voiceAutoSend, setVoiceAutoSendState] = useState(() => readBool('set_voice_autosend', false));

  // --- Data controls ---
  const [improveModel, setImproveModelState] = useState(() => readBool('set_improve_model', false));

  // --- Safety (clinical guard-rails) ---
  const [showDisclaimer, setShowDisclaimerState] = useState(() => readBool('set_show_disclaimer', true));
  const [doseWarning, setDoseWarningState] = useState(() => readBool('set_dose_warning', true));
  const [confirmPrescription, setConfirmPrescriptionState] = useState(() => readBool('set_confirm_prescription', true));

  // --- Security ---
  const [appLock, setAppLockState] = useState(() => readBool('set_app_lock', false));
  const [autoLogout, setAutoLogoutState] = useState(() => readString('set_auto_logout', 'never'));

  // Account identity (name/username/avatar) lives in useProfiles(), backed by the API.

  // Persisting setter factory — keeps every setter a one-liner below.
  const persist = useCallback((key, setter, serialize = String) => (value) => {
    setter(value);
    localStorage.setItem(key, serialize(value));
  }, []);

  const setAppearance = useMemo(() => persist('set_appearance_v2', setAppearanceState), [persist]);
  const setAccentColor = useMemo(() => persist('set_accent', setAccentColorState), [persist]);
  const setLanguage = useMemo(() => persist('set_language', setLanguageState), [persist]);
  const setFollowUpSuggestions = useMemo(() => persist('followup_suggestions', setFollowUpSuggestionsState), [persist]);
  const setNotifyEnabled = useMemo(() => persist('notify_enabled', setNotifyEnabledState), [persist]);
  const setNotifyRecheck = useMemo(() => persist('set_notify_recheck', setNotifyRecheckState), [persist]);
  const setNotifyInteraction = useMemo(() => persist('set_notify_interaction', setNotifyInteractionState), [persist]);
  const setMemoryEnabled = useMemo(() => persist('personalization_memory', setMemoryEnabledState), [persist]);
  const setReferenceHistory = useMemo(() => persist('set_reference_history', setReferenceHistoryState), [persist]);
  const setAnswerDetail = useMemo(() => persist('set_answer_detail', setAnswerDetailState), [persist]);
  const setVoiceInputEnabled = useMemo(() => persist('set_voice_input', setVoiceInputEnabledState), [persist]);
  const setVoiceLang = useMemo(() => persist('set_voice_lang', setVoiceLangState), [persist]);
  const setVoiceAutoSend = useMemo(() => persist('set_voice_autosend', setVoiceAutoSendState), [persist]);
  const setImproveModel = useMemo(() => persist('set_improve_model', setImproveModelState), [persist]);
  const setShowDisclaimer = useMemo(() => persist('set_show_disclaimer', setShowDisclaimerState), [persist]);
  const setDoseWarning = useMemo(() => persist('set_dose_warning', setDoseWarningState), [persist]);
  const setConfirmPrescription = useMemo(() => persist('set_confirm_prescription', setConfirmPrescriptionState), [persist]);
  const setAppLock = useMemo(() => persist('set_app_lock', setAppLockState), [persist]);
  const setAutoLogout = useMemo(() => persist('set_auto_logout', setAutoLogoutState), [persist]);

  const setCustomInstructions = useCallback((value) => {
    setCustomInstructionsState(value);
    localStorage.setItem('set_custom_instructions', JSON.stringify(value));
  }, []);

  // Appearance: 'system' follows the OS, otherwise it is pinned.
  const [systemDark, setSystemDark] = useState(() =>
    window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false);
  const isDarkMode = appearance === 'system' ? systemDark : appearance === 'dark';

  // Re-render on OS theme change while "system" is selected.
  useEffect(() => {
    if (appearance !== 'system' || !window.matchMedia) return undefined;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => setSystemDark(mq.matches);
    onChange();
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, [appearance]);

  useEffect(() => {
    const syncAppearance = (event) => {
      if (event.key === 'set_appearance_v2') {
        setAppearanceState(['light', 'dark', 'system'].includes(event.newValue) ? event.newValue : 'light');
      }
    };
    window.addEventListener('storage', syncAppearance);
    return () => window.removeEventListener('storage', syncAppearance);
  }, []);

  // Apply theme + accent to the document so plain CSS can react to both.
  useEffect(() => {
    document.documentElement.classList.toggle('dark', isDarkMode);
    localStorage.setItem('theme', isDarkMode ? 'dark' : 'light');
  }, [isDarkMode]);

  useEffect(() => {
    const entry = ACCENT_COLORS.find((a) => a.value === accentColor) || ACCENT_COLORS[0];
    document.documentElement.setAttribute('data-accent', accentColor);
    document.documentElement.style.setProperty('--accent-color', entry.color);
  }, [accentColor]);

  return {
    appearance, setAppearance, isDarkMode,
    accentColor, setAccentColor,
    language, setLanguage,
    followUpSuggestions, setFollowUpSuggestions,
    notifyEnabled, setNotifyEnabled,
    notifyRecheck, setNotifyRecheck,
    notifyInteraction, setNotifyInteraction,
    memoryEnabled, setMemoryEnabled,
    referenceHistory, setReferenceHistory,
    answerDetail, setAnswerDetail,
    customInstructions, setCustomInstructions,
    voiceInputEnabled, setVoiceInputEnabled,
    voiceLang, setVoiceLang,
    voiceAutoSend, setVoiceAutoSend,
    improveModel, setImproveModel,
    showDisclaimer, setShowDisclaimer,
    doseWarning, setDoseWarning,
    confirmPrescription, setConfirmPrescription,
    appLock, setAppLock,
    autoLogout, setAutoLogout,
  };
}
