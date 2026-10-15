import { useEffect, useId, useRef } from 'react';
import type { ReactNode } from 'react';
import { CrossIcon, DocumentIcon, EyeIcon, LockIcon, PuzzleIcon, SparkleIcon, StethoscopeIcon, PulseIcon, QuoteIcon } from '../icons';
import { SOURCE_TEXT } from '../format';
import type { InfoType, TextSource } from '../types';

type Tone = 'brand' | 'ok' | 'warn' | 'rose' | 'violet' | 'neutral' | 'blue' | 'dark';

export function Pill({ tone = 'neutral', icon, children, title }: { tone?: Tone; icon?: ReactNode; children: ReactNode; title?: string }) {
  return <span className={`pill pill-${tone}`} title={title}>{icon}{children}</span>;
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="eyebrow">{children}</p>;
}

const TYPE_META: Record<InfoType, { label: string; icon: ReactNode }> = {
  user_said: { label: 'In the client\'s words / approved', icon: <QuoteIcon size={14} /> },
  measured: { label: 'Measured / self-reported', icon: <PulseIcon size={14} /> },
  ai_summary: { label: 'AI summary', icon: <SparkleIcon size={14} /> },
  professional_note: { label: 'Professional\'s note', icon: <StethoscopeIcon size={14} /> },
  system: { label: 'System information', icon: <DocumentIcon size={14} /> },
};

/** The information type of a piece of content – shown wherever user words, measurements, AI text and professional notes meet. */
export function TypeTag({ type, short = false, iconOnly = false }: { type: InfoType; short?: boolean; iconOnly?: boolean }) {
  const meta = TYPE_META[type];
  return (
    <span className={`type-tag type-${type} ${iconOnly ? 'is-icon' : ''}`} title={meta.label} aria-label={iconOnly ? meta.label : undefined}>
      {meta.icon}
      {!iconOnly && <span>{short ? meta.label.split(' / ')[0] : meta.label}</span>}
    </span>
  );
}

const AGENT_SHORT: Record<string, string> = {
  SupportAgent: 'Support', CheckInAgent: 'Check-in', ObservationAgent: 'Observations', MatchingAgent: 'Matching',
  NavigationAgent: 'Service guidance', SafetyAgent: 'Safety', Orchestrator: 'Orchestrator',
};

export function AgentBadge({ agent, full = false }: { agent: string | null; full?: boolean }) {
  if (!agent) return <span className="agent-badge agent-client">Client</span>;
  return <span className={`agent-badge agent-${agent}`} title={agent}>{full ? agent : AGENT_SHORT[agent] ?? agent}</span>;
}

export function SourceNote({ source }: { source: TextSource | null | undefined }) {
  if (!source || source === 'client') return null;
  return (
    <span className={`source-note source-${source}`}>
      {source === 'live' ? <SparkleIcon size={12} /> : null}
      {SOURCE_TEXT[source] ?? source}
    </span>
  );
}

/** "Kuka saa käyttää tätä tietoa?" – three explicit choices per stored item. */
export function SharingControl({ sharing, onChange, busy, compact = false }: {
  sharing: { professional: boolean; matching: boolean };
  onChange: (next: { professional: boolean; matching: boolean }) => void;
  busy?: boolean;
  compact?: boolean;
}) {
  const privateOnly = !sharing.professional && !sharing.matching;
  return (
    <div className={`sharing ${compact ? 'sharing-compact' : ''}`} role="group" aria-label="Who may use this information?">
      <button type="button" className="share-opt" aria-pressed={privateOnly} disabled={busy}
        onClick={() => onChange({ professional: false, matching: false })}>
        <LockIcon size={15} /> <span>Only me</span>
      </button>
      <button type="button" className="share-opt" aria-pressed={sharing.professional} disabled={busy}
        onClick={() => onChange({ professional: !sharing.professional, matching: sharing.matching })}>
        <EyeIcon size={15} /> <span>{compact ? 'Professional' : 'May be shown to a professional'}</span>
      </button>
      <button type="button" className="share-opt" aria-pressed={sharing.matching} disabled={busy}
        onClick={() => onChange({ professional: sharing.professional, matching: !sharing.matching })}>
        <PuzzleIcon size={15} /> <span>{compact ? 'Matching' : 'May be used in therapist matching'}</span>
      </button>
    </div>
  );
}

export function SharingSummary({ sharing }: { sharing: { professional: boolean; matching: boolean } }) {
  if (!sharing.professional && !sharing.matching) return <span className="share-sum"><LockIcon size={13} /> Only you</span>;
  return (
    <span className="share-sum">
      {sharing.professional && <><EyeIcon size={13} /> Professional</>}
      {sharing.professional && sharing.matching && <span aria-hidden="true">·</span>}
      {sharing.matching && <><PuzzleIcon size={13} /> Matching</>}
    </span>
  );
}

export function Sheet({ title, onClose, children, footer, wide = false, labelledBy }: {
  title: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean; labelledBy?: string;
}) {
  const id = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
  }, []);
  return (
    <div className="sheet-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
      onKeyDown={(e) => e.key === 'Escape' && onClose()}>
      <div className={`sheet ${wide ? 'sheet-wide' : ''}`} role="dialog" aria-modal="true" aria-labelledby={labelledBy ?? id}>
        <div className="sheet-head">
          <h3 id={labelledBy ?? id}>{title}</h3>
          <button type="button" ref={closeRef} className="icon-btn" aria-label="Close" onClick={onClose}><CrossIcon size={18} /></button>
        </div>
        <div className="sheet-body">{children}</div>
        {footer && <div className="sheet-foot">{footer}</div>}
      </div>
    </div>
  );
}

export function Segmented<T extends string | number>({ label, options, value, onChange, disabled }: {
  label: string; options: { value: T; label: ReactNode }[]; value: T; onChange: (value: T) => void; disabled?: boolean;
}) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <button key={String(option.value)} type="button" role="radio" aria-checked={value === option.value} disabled={disabled}
          onClick={() => onChange(option.value)}>{option.label}</button>
      ))}
    </div>
  );
}

/** 1–5 answer scale with words (no emoji faces – calm and adult). */
export function Scale5({ value, onChange, labels, name }: {
  value: number | null; onChange: (value: number) => void; labels: Record<string, string>; name: string;
}) {
  return (
    <div className="scale5" role="radiogroup" aria-label={name}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button key={n} type="button" role="radio" aria-checked={value === n} className={`scale-opt scale-${n}`} onClick={() => onChange(n)}>
          <span className="scale-num">{n}</span>
          <span className="scale-word">{labels[String(n)]}</span>
        </button>
      ))}
    </div>
  );
}

export function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      {icon && <span className="empty-icon">{icon}</span>}
      <p className="empty-title">{title}</p>
      {children && <div className="empty-text">{children}</div>}
    </div>
  );
}

export function Synthetic({ children = 'Synthetic example figures for the demo.' }: { children?: ReactNode }) {
  return <p className="synthetic-note"><InfoDot /> {children}</p>;
}

function InfoDot() {
  return <span className="info-dot" aria-hidden="true">i</span>;
}
