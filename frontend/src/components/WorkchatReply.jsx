import React from 'react';
import { BookOpen, ClipboardList, Copy } from 'lucide-react';

export function WorkchatActivity({ message }) {
  return <div className="fil-workchat-activity" role="status">
    <span className="fil-workchat-signal" aria-hidden="true"><img src="/fil-mark.svg" width="23" height="23" alt="" /></span>
    <span><strong>Fil</strong><span>{message}</span></span>
  </div>;
}

export function WorkchatReply({ reply, onOpenSource, onCopy }) {
  if (reply.kind === 'outline' && reply.outline) {
    const { title, sections } = reply.outline;
    return <section className="fil-workchat-outline" aria-label={title}>
      <div className="fil-workchat-outline-title"><ClipboardList size={21} aria-hidden="true" /><h3>{title}</h3></div>
      <ol>{sections.map(section => <li key={section}>{section}</li>)}</ol>
      <button type="button" onClick={() => onCopy([title, ...sections.map(section => '- ' + section + ':')].join('\n'))}>
        <Copy size={15} aria-hidden="true" /> Sao chép khung ghi chú
      </button>
    </section>;
  }
  if (reply.kind === 'answer') {
    return <div className="fil-workchat-paragraphs">
      {reply.paragraphs.map((paragraph, index) => <p key={index}>{paragraph.text}{' '}
        {paragraph.references.map(number => <button key={number} type="button" className="citation-badge"
          onClick={() => onOpenSource(number - 1)} aria-label={'Mở nguồn ' + number}>{number}</button>)}
      </p>)}
    </div>;
  }
  if (reply.kind === 'notice') {
    return <div className="fil-workchat-notice"><BookOpen size={18} aria-hidden="true" /><p>{reply.text}</p></div>;
  }
  return null;
}
