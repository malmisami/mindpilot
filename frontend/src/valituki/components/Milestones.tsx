import type { ReactNode } from 'react';
import { fmtShort } from '../format';
import { CalendarIcon, FlagIcon, HandHeartIcon, LeafIcon, PulseIcon, SparkleIcon, StethoscopeIcon, UserSearchIcon } from '../icons';
import type { Milestone } from '../types';

const ICONS: Record<string, ReactNode> = {
  sought_help: <HandHeartIcon size={18} />, started: <FlagIcon size={18} />, first_insight: <SparkleIcon size={18} />,
  helpful: <LeafIcon size={18} />, change: <PulseIcon size={18} />, therapist_found: <UserSearchIcon size={18} />,
  first_session: <CalendarIcon size={18} />, therapy_mode: <StethoscopeIcon size={18} />,
};

/** "Matkani" – the client's journey as a visual timeline: what has happened and what comes next. `compact` shows the titles
    only (the rest on hover) – the therapist's side column. */
export function Milestones({ items, compact = false }: { items: Milestone[]; compact?: boolean }) {
  return (
    <ol className={`milestones ${compact ? 'is-compact' : ''}`}>
      {items.map((item, index) => (
        <li key={item.key} className={`ms ms-${item.tone} ms-${item.status}`} style={{ animationDelay: `${index * 60}ms` }}
          title={compact ? [item.text, item.note].filter(Boolean).join(' – ') : undefined}>
          <div className="ms-date">
            {item.date ? <><span className="ms-day">{fmtShort(item.date)}</span></> : <span className="ms-soon">Coming up</span>}
          </div>
          <div className="ms-rail" aria-hidden="true"><span className="ms-node">{ICONS[item.key]}</span></div>
          <div className="ms-card">
            <p className="ms-title">{item.title}</p>
            {!compact && item.quote && <blockquote className="ms-quote">“{item.quote}”</blockquote>}
            {!compact && <p className="ms-text">{item.text}</p>}
            {!compact && item.note && <p className="ms-note">{item.note}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}
