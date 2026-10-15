import { useState } from 'react';
import { CheckIcon, MinusIcon, PlusIcon, SparkleIcon, TrashIcon } from '../icons';
import type { ChatWidget, LadderStepInput, SummaryData } from '../types';

/* The structured answers of a guided exercise. Each answer is one tap (a scale, a choice) or an explicit "Done"; every
   skippable question can be skipped. Proposals (thinking traps, example thoughts, ladder steps) are never pre-selected –
   the client decides. */

interface WidgetProps {
  widget: ChatWidget; busy: boolean; onAnswer: (value: unknown) => void; onSkip: () => void;
  /** A multiple choice is sent with the composer's send button: the chat holds what is picked. */
  selected?: string[]; onSelect?: (values: string[]) => void;
}

export function WidgetPanel(props: WidgetProps) {
  switch (props.widget.type) {
    case 'scale':
      return <ScaleWidget {...props} />;
    case 'scale5':
      return <Scale5Widget {...props} />;
    case 'choices':
      return <ChoiceWidget {...props} />;
    case 'multi':
      return <MultiWidget {...props} />;
    case 'traps':
      return <TrapWidget {...props} />;
    case 'ladder':
      return <LadderWidget {...props} />;
    default:
      return null;
  }
}

function Skip({ widget, busy, onSkip }: { widget: ChatWidget; busy: boolean; onSkip: () => void }) {
  if (!widget.skippable) return null;
  return <button type="button" className="cw-skip" disabled={busy} onClick={onSkip}>{widget.skipLabel || 'Skip question'}</button>;
}

function ScaleWidget({ widget, busy, onAnswer }: WidgetProps) {
  const values = Array.from({ length: widget.max - widget.min + 1 }, (_, i) => widget.min + i);
  return (
    <div className="cw cw-scale">
      <div className="cw-scale-row" role="group" aria-label={`Choose ${widget.min}–${widget.max}`}>
        {values.map((n) => (
          <button key={n} type="button" className={`cw-num cw-num-${Math.round(((n - widget.min) / (widget.max - widget.min)) * 4)}`} disabled={busy}
            aria-label={`${n}${n === widget.min && widget.minLabel ? ` – ${widget.minLabel}` : ''}${n === widget.max && widget.maxLabel ? ` – ${widget.maxLabel}` : ''}`}
            onClick={() => onAnswer(n)}>{n}</button>
        ))}
      </div>
      <div className="cw-scale-labels" aria-hidden="true"><span>{widget.minLabel}</span><span>{widget.maxLabel}</span></div>
    </div>
  );
}

function Scale5Widget({ widget, busy, onAnswer }: WidgetProps) {
  return (
    <div className="cw cw-scale5" role="group" aria-label="Choose 1–5">
      {widget.options.map((o) => (
        <button key={o.value} type="button" className={`cw-five cw-five-${o.value}`} disabled={busy} onClick={() => onAnswer(Number(o.value))}>
          <span className="cw-five-n">{o.value}</span>
          <span className="cw-five-w">{o.label}</span>
        </button>
      ))}
    </div>
  );
}

function ChoiceWidget({ widget, busy, onAnswer, onSkip }: WidgetProps) {
  return (
    <div className="cw cw-choices">
      {widget.options.map((o) => (
        <button key={o.value} type="button" className="cw-choice" disabled={busy} onClick={() => onAnswer(o.value)}>{o.label}</button>
      ))}
      <Skip widget={widget} busy={busy} onSkip={onSkip} />
    </div>
  );
}

function MultiWidget({ widget, busy, onSkip, selected = [], onSelect }: WidgetProps) {
  const toggle = (value: string) => onSelect?.(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);
  return (
    <div className="cw cw-multi">
      <div className="cw-chips">
        {widget.options.map((o) => (
          <button key={o.value} type="button" className="cw-chip" aria-pressed={selected.includes(o.value)} disabled={busy}
            onClick={() => toggle(o.value)}>{selected.includes(o.value) && <CheckIcon size={13} />}{o.label}</button>
        ))}
      </div>
      {widget.skippable && <div className="cw-actions"><Skip widget={widget} busy={busy} onSkip={onSkip} /></div>}
    </div>
  );
}

/** Thinking traps as quick replies, like a chat: one tap answers. Mieliluotsi's proposals (explained in the chat just
    before the question, see TrapHint) come first; the rest of the list opens with "Something else…". */
function TrapWidget({ widget, busy, onAnswer, onSkip }: WidgetProps) {
  const [others, setOthers] = useState(false);
  const suggested = widget.options.filter((o) => widget.suggested.includes(o.value));
  const rest = suggested.length ? widget.options.filter((o) => !widget.suggested.includes(o.value)) : widget.options;
  return (
    <div className="cw cw-quick" role="group" aria-label="Answer options">
      {suggested.map((o) => (
        <button key={o.value} type="button" className="cw-reply" disabled={busy} onClick={() => onAnswer([o.value])}>{o.label}</button>
      ))}
      {suggested.length > 1 && (
        <button type="button" className="cw-reply" disabled={busy} onClick={() => onAnswer(suggested.map((o) => o.value))}>
          {suggested.length === 2 ? 'Both' : 'All of these'}
        </button>
      )}
      {(others || !suggested.length) ? rest.map((o) => (
        <button key={o.value} type="button" className="cw-reply cw-reply-soft" title={o.hint ?? undefined} disabled={busy}
          onClick={() => onAnswer([o.value])}>{o.label}</button>
      )) : (
        <button type="button" className="cw-reply cw-reply-soft" disabled={busy} onClick={() => setOthers(true)}>Something else…</button>
      )}
      {widget.skippable && (
        <button type="button" className="cw-reply cw-reply-soft" disabled={busy} onClick={onSkip}>{widget.skipLabel || "I don't recognise any"}</button>
      )}
    </div>
  );
}

/** Mieliluotsi's proposal as its own chat bubble just before the question: which traps and what they mean. */
export function TrapHint({ widget, cont = false }: { widget: ChatWidget; cont?: boolean }) {
  const suggested = widget.options.filter((o) => widget.suggested.includes(o.value));
  if (!suggested.length) return null;
  return (
    <div className={`cx-bubble cx-trap-hint${cont ? ' is-cont' : ''}`}>
      <p>{suggested.length === 1 ? 'A thought like this often shows this trap:' : 'A thought like this often shows these traps:'}</p>
      <ul>
        {suggested.map((o) => <li key={o.value}><strong>{o.label}</strong> – {o.hint?.replace(/^\p{Lu}(?=\p{Ll})/u, (c) => c.toLowerCase())}</li>)}
      </ul>
    </div>
  );
}

function LadderWidget({ widget, busy, onAnswer }: WidgetProps) {
  const [steps, setSteps] = useState<LadderStepInput[]>(() => widget.steps.map((s) => ({ ...s })));
  const update = (i: number, change: Partial<LadderStepInput>) => setSteps((all) => all.map((s, j) => (j === i ? { ...s, ...change } : s)));
  const valid = steps.filter((s) => s.text.trim());
  return (
    <div className="cw cw-ladder">
      {widget.suggestedSource === 'live' && <p className="cw-proposal"><SparkleIcon size={13} /> Ladder suggested by AI – edit it freely.</p>}
      <ol className="cw-ladder-list">
        {steps.map((step, i) => (
          <li key={i} className="cw-ladder-row">
            <input className="cw-ladder-text" value={step.text} aria-label={`Step ${i + 1}`} onChange={(e) => update(i, { text: e.target.value })}
              placeholder="Write a step…" />
            <span className="cw-stepper" role="group" aria-label={`Expected nervousness, step ${i + 1}`}>
              <button type="button" aria-label="Less" disabled={busy || step.expected <= 0} onClick={() => update(i, { expected: step.expected - 1 })}><MinusIcon size={12} /></button>
              <span className="cw-stepper-value">{step.expected}</span>
              <button type="button" aria-label="More" disabled={busy || step.expected >= 10} onClick={() => update(i, { expected: step.expected + 1 })}><PlusIcon size={12} /></button>
            </span>
            <button type="button" className="cw-icon" aria-label={`Delete step ${i + 1}`} disabled={busy || steps.length <= 2}
              onClick={() => setSteps((all) => all.filter((_, j) => j !== i))}><TrashIcon size={14} /></button>
          </li>
        ))}
      </ol>
      <p className="cw-fine">Number = expected nervousness 0–10. The ladder is sorted from easiest to hardest.</p>
      <div className="cw-actions">
        <button type="button" className="cx-btn cx-btn-ghost cx-btn-sm" disabled={busy || steps.length >= 8}
          onClick={() => setSteps((all) => [...all, { text: '', expected: Math.min(10, (all[all.length - 1]?.expected ?? 4) + 1) }])}>
          <PlusIcon size={14} /> Add step
        </button>
        <button type="button" className="cx-btn cx-btn-dark cx-btn-sm" disabled={busy || valid.length < 2}
          onClick={() => onAnswer([...valid].map((s) => ({ text: s.text.trim(), expected: s.expected })).sort((a, b) => a.expected - b.expected))}>
          Save ladder
        </button>
      </div>
    </div>
  );
}

export function Examples({ widget, busy, onUse }: { widget: ChatWidget; busy: boolean; onUse: (text: string) => void }) {
  if (widget.examples.length === 0) return null;
  return (
    <div className="cw cw-examples">
      <p className="cw-proposal"><SparkleIcon size={13} /> {widget.examplesSource === 'live' ? 'AI suggestions' : 'Examples'} – tap one and make it your own:</p>
      {widget.examples.map((example) => (
        <button key={example} type="button" className="cw-example" disabled={busy} onClick={() => onUse(example)}>{example}</button>
      ))}
    </div>
  );
}

/** The saved result of an exercise, shown in the chat as a card. */
export function SummaryCard({ data }: { data: SummaryData }) {
  const change = data.change;
  return (
    <article className={`cx-summary cx-summary-${data.kind}`}>
      <p className="cx-summary-kicker">Saved</p>
      <h3 className="cx-summary-title">{data.title}</h3>
      <dl className="cx-summary-rows">
        {data.rows.map((row) => (
          <div key={row.label}>
            <dt>{row.label}</dt>
            <dd>{Array.isArray(row.value) ? <ol>{row.value.map((v) => <li key={v}>{v}</li>)}</ol> : row.value}</dd>
          </div>
        ))}
      </dl>
      {change && change.before !== null && change.after !== null && <ChangeBars change={change} />}
    </article>
  );
}

export function ChangeBars({ change }: { change: NonNullable<SummaryData['change']> }) {
  const rows = [
    { key: 'before', label: 'Before', value: change.before },
    ...(change.peak !== undefined && change.peak !== null ? [{ key: 'peak', label: 'Peak', value: change.peak }] : []),
    { key: 'after', label: 'Now', value: change.after },
  ];
  return (
    <div className="cx-change" aria-label={`${change.label}: ${rows.map((r) => `${r.label.toLowerCase()} ${r.value}/${change.max}`).join(', ')}`}>
      <p className="cx-change-label">{change.label} (0–{change.max})</p>
      {rows.map((row) => (
        <div key={row.key} className={`cx-change-row cx-change-${row.key}`}>
          <span className="cx-change-name">{row.label}</span>
          <span className="cx-change-track" aria-hidden="true"><span style={{ width: `${((row.value ?? 0) / change.max) * 100}%` }} /></span>
          <span className="cx-change-value">{row.value}</span>
        </div>
      ))}
    </div>
  );
}

/** A readable form of a demo answer for the presenter's shortcut chip. */
export function describeValue(value: unknown, widget: ChatWidget | null): string {
  if (value === null || value === undefined) return '';
  const label = (v: string) => widget?.options.find((o) => o.value === v)?.label ?? v;
  if (Array.isArray(value)) {
    if (value.length && typeof value[0] === 'object') return `Ladder with ${value.length} ${value.length === 1 ? 'step' : 'steps'}`;
    return value.map((v) => label(String(v))).join(', ');
  }
  if (typeof value === 'number') return widget?.type === 'scale' ? `${value}/${widget.max}` : widget?.type === 'scale5' ? `${value}/5 · ${label(String(value))}` : String(value);
  return label(String(value));
}
