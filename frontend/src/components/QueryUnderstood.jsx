import React from 'react';

/**
 * "Đã hiểu: Paracetamol (Efferalgan) · Liều dùng · trẻ em · ĐTĐ = đái tháo đường"
 *
 * Nói lại cho bác sĩ máy đã nhận ra thuốc nào, mục nào trong chuyên luận, điều
 * kiện bệnh nhân nào và chữ viết tắt nào (backend: drug_alias.py,
 * query_intent.py). Hiểu sai thì bác sĩ thấy ngay và hỏi lại — không bị giấu.
 */
export default function QueryUnderstood({ understood }) {
  if (!understood) return null;
  const parts = [];

  for (const d of understood.drugs || []) {
    const names = (d.names || []).filter(Boolean);
    if (!names.length) continue;
    const typed = d.text || '';
    const sameAsTyped = names.some(n => n.toLowerCase() === typed.toLowerCase());
    parts.push({
      key: `d-${typed}`,
      strong: names.join(' / '),
      note: sameAsTyped || !typed ? null : typed,
    });
  }
  for (const label of understood.labels || []) {
    parts.push({ key: `l-${label}`, text: label });
  }
  for (const a of understood.abbreviations || []) {
    parts.push({ key: `a-${a.abbr}`, text: `${a.abbr} = ${a.expansion}` });
  }
  if (!parts.length) return null;

  return (
    <p className="bubble-understood">
      Đã hiểu:{' '}
      {parts.map((p, i) => (
        <React.Fragment key={p.key}>
          {i > 0 && <span className="bubble-understood-sep" aria-hidden="true"> · </span>}
          {p.strong ? (
            <>
              <strong>{p.strong}</strong>
              {p.note && <span className="bubble-understood-note"> ({p.note})</span>}
            </>
          ) : (
            <span>{p.text}</span>
          )}
        </React.Fragment>
      ))}
    </p>
  );
}
