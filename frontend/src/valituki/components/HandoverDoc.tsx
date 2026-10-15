import { useState } from 'react';
import { fmtDate, fmtNum, plural } from '../format';
import { EditIcon, TrashIcon, UndoIcon } from '../icons';
import type { HandoverSection } from '../types';
import { WellbeingChart } from './charts';
import { TypeTag } from './ui';

type Row = Record<string, unknown>;

function asRows(value: unknown): Row[] {
  return Array.isArray(value) ? (value as Row[]) : [];
}

function str(value: unknown): string {
  return value === null || value === undefined ? '' : String(value);
}

function SectionContent({ section }: { section: HandoverSection }) {
  const content = section.content as Row | Row[] | null;
  switch (section.key) {
    case 'hopes':
    case 'working_style':
    case 'practical':
      return <p className={section.key === 'hopes' ? 'ho-quote' : ''}>{section.text}</p>;
    case 'ai_summary':
      return <p className="ho-ai">{section.text}</p>;
    case 'goals':
      return (
        <ul className="ho-list">
          {asRows(content).map((goal) => (
            <li key={str(goal.id)}><span className="ho-sub">{goal.priority === 'primary' ? 'Main goal' : 'Goal'}</span> {str(goal.text)}</li>
          ))}
        </ul>
      );
    case 'wellbeing': {
      const data = content as Row;
      const points = asRows(data.points).map((p) => ({ date: str(p.date), mood: p.mood as number | null, belowBaseline: Boolean(p.belowBaseline) }));
      return (
        <div>
          <p>{str(data.summary)}</p>
          <WellbeingChart title="Wellbeing 1–5 during the wait" points={points} baseline={data.baseline as number | null} height={150}
            events={asRows(data.events).map((e) => ({ date: str(e.date), label: 'Reviewed' }))} note="self-reported" />
        </div>
      );
    }
    case 'practice': {
      const data = content as Row;
      const stats = (data.stats ?? {}) as Row;
      const traps = asRows(stats.traps);
      return (
        <ul className="ho-list">
          {Number(stats.thoughtRecords) > 0 && (
            <li>Exploring a thought {str(stats.thoughtRecords)}×{stats.avgDrop !== null && stats.avgDrop !== undefined
              && <span className="muted"> – the feeling dropped by {fmtNum(Number(stats.avgDrop))} points on average (0–10)</span>}</li>
          )}
          {traps.length > 0 && <li>Thinking traps recognised: {traps.map((t) => `${str(t.label)} (${str(t.count)})`).join(', ')}</li>}
          {Number(stats.experiments) > 0 && <li>Behavioural experiments: {str(stats.experimentsDone)}/{str(stats.experiments)} done</li>}
          {asRows(data.ladders).map((ladder, i) => (
            <li key={i}>Exposure ladder: {str(ladder.goal)} <span className="muted">– {str(ladder.done)}/{str(ladder.total)} steps done</span></li>
          ))}
        </ul>
      );
    }
    case 'tried':
      return (
        <ul className="ho-list">
          {asRows(content).map((row) => (
            <li key={str(row.title)}>{str(row.title)} <span className="muted">– done {str(row.tried)}×{row.latestRating ? `, latest rating ${str(row.latestRating)}/5` : ''}</span></li>
          ))}
        </ul>
      );
    case 'helped': {
      const data = content as Row;
      return (
        <div>
          <ul className="ho-list">
            {asRows(data.activities).map((row) => <li key={str(row.title)}>{str(row.title)} <span className="muted">({str(row.rating)}/5)</span></li>)}
          </ul>
          {Boolean(data.ownWords) && <p className="ho-quote">{str(data.ownWords)}</p>}
        </div>
      );
    }
    case 'not_helped':
      return (
        <ul className="ho-list">
          {asRows(content).map((row) => (
            <li key={str(row.title)}>{str(row.title)} <span className="muted">{row.rating ? `(${str(row.rating)}/5)` : ''}{Number(row.skipped) ? ` · skipped ${str(row.skipped)}×` : ''}</span></li>
          ))}
        </ul>
      );
    case 'observations':
      return (
        <ul className="ho-list">
          {asRows(content).map((row) => (
            <li key={str(row.id)}>{str(row.text)}{Array.isArray(row.basis) && (
              <span className="ho-basis">Based on: {(row.basis as (string | null)[]).filter(Boolean).join(' · ')}</span>)}</li>
          ))}
        </ul>
      );
    case 'questions': {
      const data = content as Row;
      return <ol className="ho-list ho-numbered">{asRows(data.items).map((q, i) => <li key={i}>{str(q)}</li>)}</ol>;
    }
    case 'professional':
      return (
        <ul className="ho-list">
          {asRows(content).map((row, i) => (
            <li key={i}><span className="ho-sub">{fmtDate(str(row.date))}</span> {str(row.title)}{row.outcome ? ` → ${str(row.outcome)}` : ''}
              {Boolean(row.note) && <span className="ho-basis">{str(row.note)}</span>}{Boolean(row.by) && <span className="ho-basis">{str(row.by)}</span>}</li>
          ))}
        </ul>
      );
    case 'sources':
      return (
        <ul className="ho-sources">
          {asRows(content).map((row, i) => <li key={i}><span>{str(row.section)}</span> <span className="muted">{str(row.label)}{row.at ? ` · ${fmtDate(str(row.at))}` : ''}</span></li>)}
        </ul>
      );
    case 'sharing': {
      const data = content as Row;
      return (
        <div className="ho-sharing">
          <p>{str(data.statement)}</p>
          <p className="muted small">Items to share: {(data.included as string[]).length} · Removed: {(data.removed as string[]).length}
            {Number(data.privateItems) ? ` · ${plural(Number(data.privateItems), 'item')} only you have` : ''} · Chat history: {data.chatHistoryIncluded ? 'included' : 'not included'}</p>
        </div>
      );
    }
    default:
      return <p className="muted">{typeof content === 'string' ? content : ''}</p>;
  }
}

/* The therapist's read-only layout: the client's hopes first, short sections side by side, where the data comes from last. */
const GRID_ORDER = ['hopes', 'goals', 'questions', 'working_style', 'practical', 'wellbeing', 'practice', 'tried', 'helped', 'not_helped',
  'professional', 'observations', 'ai_summary'];
const GRID_WIDE = new Set(['hopes', 'wellbeing', 'observations', 'ai_summary']);
const GRID_META = new Set(['sources', 'sharing']);

export function HandoverDoc({ sections, layout = 'list', editable = false, busy = false, onRemove, onRestore, onEditText, onEditQuestions }: {
  sections: HandoverSection[]; layout?: 'list' | 'grid'; editable?: boolean; busy?: boolean;
  onRemove?: (key: string) => void; onRestore?: (key: string) => void; onEditText?: (key: string, text: string) => void;
  onEditQuestions?: (items: string[]) => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const visible = editable ? sections : sections.filter((s) => s.available && !s.removed);

  function startEdit(section: HandoverSection) {
    setEditing(section.key);
    if (section.key === 'questions') {
      setDraft(asRows((section.content as Row).items).map(str).join('\n'));
    } else {
      setDraft(section.text ?? '');
    }
  }

  function save(section: HandoverSection) {
    if (section.key === 'questions') onEditQuestions?.(draft.split('\n').map((q) => q.trim()).filter(Boolean));
    else onEditText?.(section.key, draft);
    setEditing(null);
  }

  function render(section: HandoverSection, extra = '') {
    const muted = !section.available || section.removed;
    return (
      <section key={section.key} className={`ho-section ho-${section.infoType} ho-k-${section.key} ${muted ? 'ho-muted' : ''} ${extra}`}>
        <header className="ho-head">
          <h4>{section.title}</h4>
          <TypeTag type={section.infoType} short iconOnly={layout === 'grid'} />
        </header>
        {section.removed ? (
          <p className="muted small">Removed – this item is not shared.</p>
        ) : !section.available ? (
          <p className="muted small">{section.unavailableReason}</p>
        ) : editing === section.key ? (
          <div className="ho-edit">
            <textarea value={draft} rows={section.key === 'questions' ? 4 : 3} onChange={(e) => setDraft(e.target.value)}
              aria-label={`Edit: ${section.title}`} />
            {section.key === 'questions' && <p className="muted small">One question per line.</p>}
            <div className="row-gap">
              <button type="button" className="btn btn-primary btn-sm" disabled={busy || !draft.trim()} onClick={() => save(section)}>Save</button>
              <button type="button" className="btn btn-quiet btn-sm" onClick={() => setEditing(null)}>Cancel</button>
            </div>
          </div>
        ) : (
          <SectionContent section={section} />
        )}
        {section.note && !muted && <p className="ho-note">{section.note}</p>}
        {editable && section.removable && section.available && editing !== section.key && (
          <div className="ho-actions">
            {section.editable && !section.removed && (
              <button type="button" className="btn btn-quiet btn-sm" disabled={busy} onClick={() => startEdit(section)}><EditIcon size={15} /> Edit</button>
            )}
            {section.removed ? (
              <button type="button" className="btn btn-quiet btn-sm" disabled={busy} onClick={() => onRestore?.(section.key)}><UndoIcon size={15} /> Restore</button>
            ) : (
              <button type="button" className="btn btn-quiet btn-sm" disabled={busy} onClick={() => onRemove?.(section.key)}><TrashIcon size={15} /> Remove item</button>
            )}
          </div>
        )}
      </section>
    );
  }

  if (layout === 'grid' && !editable) {
    const rank = (key: string) => (GRID_ORDER.includes(key) ? GRID_ORDER.indexOf(key) : GRID_ORDER.length);
    const main = visible.filter((s) => !GRID_META.has(s.key)).sort((a, b) => rank(a.key) - rank(b.key));
    const meta = visible.filter((s) => GRID_META.has(s.key));
    return (
      <div className="handover is-grid">
        {main.map((section) => render(section, GRID_WIDE.has(section.key) ? 'ho-wide' : ''))}
        {meta.length > 0 && (
          <details className="ho-meta ho-wide">
            <summary>Data sources and sharing permissions</summary>
            <div className="ho-meta-body">{meta.map((section) => render(section))}</div>
          </details>
        )}
      </div>
    );
  }

  return <div className="handover">{visible.map((section) => render(section))}</div>;
}

export function fmtScore(value: number | null | undefined): string {
  return value === null || value === undefined ? '–' : fmtNum(value);
}
