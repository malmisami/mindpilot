import { useState } from 'react';
import { api } from '../api';
import { useValituki } from '../context';
import { dayWord, fmtDate, fmtDateTime, fmtNum, fmtShort, fmtTime, plural } from '../format';
import { CalendarIcon, CheckIcon, ChevronDownIcon, FlagIcon, LockIcon, PlayIcon, PulseIcon, QuoteIcon, SparkleIcon, StethoscopeIcon,
  VideoIcon } from '../icons';
import { MoodAnxietyChart, Sparkline } from '../components/charts';
import { HandoverDoc } from '../components/HandoverDoc';
import { Logo } from '../components/Logo';
import { Milestones } from '../components/Milestones';
import { Empty, Pill, Segmented, TypeTag } from '../components/ui';
import type { AftercareInput, PlanInput, PracticeStats, TherapistClientRow } from '../types';

export default function TherapistApp() {
  const { view } = useValituki();
  const therapist = view.therapist.selected;
  const clients = therapist?.clients ?? [];
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const current = clients.find((c) => c.clientId === selectedId) ?? clients.find((c) => c.clientId === 'cl-aino') ?? clients[0];
  return (
    <div className="therapist">
      <header className="pro-head th-head">
        <div className="pro-brand"><Logo size={32} /></div>
        <p className="pro-kicker"><span className="pro-kicker-dot" aria-hidden="true" />Therapist's view{therapist ? ` · ${therapist.name}` : ''}</p>
        <h1 className="pro-title">Therapist's desk</h1>
        <p className="pro-lede">The summary the client approved and Mieliluotsi's support between sessions – the therapist decides the limits the AI works within.</p>
      </header>
      <aside className="th-side">
        {current && current.milestones.length > 0 && (
          <section className="th-milestones">
            <p className="section-label">Milestones – {current.firstName}</p>
            <Milestones items={current.milestones} compact />
          </section>
        )}
      </aside>
      <main className="th-main">
        {current ? <ClientSummary row={current} clients={clients} onSelect={setSelectedId} /> : <Empty title="No client selected">Choose a therapist who has clients who came through Mieliluotsi.</Empty>}
      </main>
    </div>
  );
}

function ClientSummary({ row, clients, onSelect }: { row: TherapistClientRow; clients: TherapistClientRow[]; onSelect: (id: string) => void }) {
  const { run, busy, scope } = useValituki();
  const therapistId = scope.therapistId ?? 'th-anna';
  const status = row.therapy.episodeStatus;
  const active = status === 'active';
  const ended = status === 'ended';
  // The direction of wellbeing from the summary the client approved – nothing is shown before the approval.
  const wellbeing = (row.sections ?? []).find((x) => x.key === 'wellbeing' && x.available && !x.removed)?.content as WellbeingFacts | undefined;
  return (
    <div className="th-summary">
      <section className="session-banner review-head">
        <div className="review-who">
          <span className="review-avatar" aria-hidden="true">{initials(row.clientName)}</span>
          <div>
            <p className="session-kicker"><CalendarIcon size={14} /> {ended ? 'Therapy ended – follow-up' : active ? 'Therapy in progress' : 'First session coming up'}</p>
            <h2 className="review-name">{row.clientName}</h2>
            <p className="review-meta"><VideoIcon size={15} /> {row.format === 'remote' ? 'Remote session' : 'In-person session'} · age {row.age}</p>
            {clients.length > 1 && (
              <div className="th-switch" role="group" aria-label="Clients">
                {clients.map((c) => (
                  <button key={c.clientId} type="button" aria-pressed={c.clientId === row.clientId} onClick={() => onSelect(c.clientId)}>{c.clientName}</button>
                ))}
              </div>
            )}
            {row.therapy.canHoldFirstSession && (
              <button type="button" className="btn btn-secondary btn-sm session-action" disabled={busy}
                onClick={() => run((s) => api.holdFirstSession(s, therapistId, row.clientId), (r) =>
                  `The first session was held (demo: ${plural(r.days, 'day')} forward). Mieliluotsi moved to support between therapy sessions.`)}>
                <PlayIcon size={14} /> Mark the first session as held (demo)
              </button>
            )}
          </div>
        </div>
        <dl className="review-stats">
          <div>
            <dt>{ended ? 'Therapy ended' : active ? 'Therapy started' : 'First session'}</dt>
            <dd><span className="review-stat review-stat-word">{fmtShort(ended ? row.therapy.endedAt : row.firstSession)}</span>
              {!ended && <span className="review-stat-sub">at {fmtTime(row.firstSession)}</span>}</dd>
          </div>
          <div>
            <dt>Sessions</dt>
            <dd><span className="review-stat">{row.therapy.sessionsHeld}</span></dd>
          </div>
          {wellbeing && wellbeing.recent !== null && (
            <div className={`trend-${wellbeing.direction}`}>
              <dt>Wellbeing during the wait</dt>
              <dd><span className="review-stat">{fmtNum(wellbeing.recent)}</span> / 5
                {wellbeing.baseline !== null && <span className="review-stat-sub">own baseline {fmtNum(wellbeing.baseline)}</span>}</dd>
            </div>
          )}
        </dl>
      </section>

      <HandoverCard row={row} />

      {(active || ended) && <PracticePanel row={row} />}

      {!ended && <TherapyPlan key={`${row.clientId}-${status}-${row.therapy.config?.version ?? 0}`} row={row} therapistId={therapistId} />}
      {active && row.therapy.config && <EndTherapy key={`end-${row.clientId}`} row={row} therapistId={therapistId} />}
      {ended && <AftercareSummary row={row} />}
    </div>
  );
}

const initials = (name: string) => name.split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase();

const LEGEND = ['user_said', 'measured', 'ai_summary', 'professional_note'] as const;
const DIRECTION_ARROWS: Record<string, string> = { improving: '↑', stable: '→', declining: '↓', insufficient: '·' };

type GoalRow = { id: string; text: string; priority: 'primary' | 'secondary' };
type WellbeingFacts = { baseline: number | null; recent: number | null; direction: string; directionLabel: string; checkIns: number;
  points: { date: string; mood: number | null }[] };
type PracticeFacts = { stats: PracticeStats; ladders: { goal: string; done: number; total: number }[] };
type HelpedFacts = { activities: { title: string; rating: number | null }[]; ownWords: string | null };

/** The first-session summary at a glance – goals, the direction of wellbeing and practice while waiting, the three things the
    first session builds on. The whole summary the client approved opens below. */
function HandoverCard({ row }: { row: TherapistClientRow }) {
  const [full, setFull] = useState(false);
  const shared = (row.sections ?? []).filter((s) => s.available && !s.removed);
  const facts = <T,>(key: string) => shared.find((s) => s.key === key)?.content as T | undefined;
  const goals = facts<GoalRow[]>('goals') ?? [];
  const primary = goals.find((g) => g.priority === 'primary') ?? goals[0];
  const wellbeing = facts<WellbeingFacts>('wellbeing');
  const practiced = facts<PracticeFacts>('practice');
  const helped = facts<HelpedFacts>('helped');
  const practice = [
    practiced && practiced.stats.thoughtRecords > 0
      ? `Exploring a thought ${practiced.stats.thoughtRecords}×${practiced.stats.avgDrop ? ` – the feeling dropped by ${fmtNum(practiced.stats.avgDrop)}` : ''}` : null,
    ...(practiced?.ladders ?? []).slice(0, 1).map((l) => `Exposure ladder ${l.done}/${l.total} steps`),
    ...(helped?.activities ?? []).slice(0, 1).map((a) => `Helped: ${a.title}${a.rating ? ` (${a.rating}/5)` : ''}`),
  ].filter((line): line is string => Boolean(line));
  const count = shared.filter((s) => s.infoType !== 'system').length;

  return (
    <section className="card doc-card">
      <div className="card-row">
        <h2 className="card-title-lg">Summary for the first session</h2>
        {row.handoverStatus === 'approved' ? <Pill tone="ok" icon={<CheckIcon size={13} />}>Approved {fmtDateTime(row.approvedAt)}</Pill>
          : <Pill tone="neutral">{row.handoverStatus === 'withdrawn' ? 'Sharing withdrawn' : 'Draft – waiting for the client\'s approval'}</Pill>}
      </div>
      {row.sections ? (
        <>
          <div className="glance">
            {primary && (
              <div className="glance-tile type-user_said">
                <p className="glance-label"><QuoteIcon size={13} /> Goals</p>
                <p className="glance-main">{primary.text}</p>
                {goals.filter((g) => g !== primary).map((g) => <p key={g.id} className="glance-sub">{g.text}</p>)}
              </div>
            )}
            {wellbeing && (
              <div className="glance-tile type-measured">
                <p className="glance-label"><PulseIcon size={13} /> Wellbeing during the wait</p>
                <p className={`glance-main glance-dir is-${wellbeing.direction}`}>{DIRECTION_ARROWS[wellbeing.direction]} {wellbeing.directionLabel}</p>
                <p className="glance-sub">Recent days {fmtNum(wellbeing.recent)} / 5 · own level {fmtNum(wellbeing.baseline)}</p>
                <Sparkline values={wellbeing.points.map((p) => p.mood)} baseline={wellbeing.baseline}
                  label={`Wellbeing 1–5, ${plural(wellbeing.points.length, 'check-in')}: ${wellbeing.directionLabel.toLowerCase()}`} />
              </div>
            )}
            {practice.length > 0 && (
              <div className="glance-tile type-measured">
                <p className="glance-label"><PulseIcon size={13} /> Practice during the wait</p>
                <ul className="glance-list">{practice.map((line) => <li key={line}>{line}</li>)}</ul>
              </div>
            )}
          </div>
          <button type="button" className="glance-more" aria-expanded={full} onClick={() => setFull(!full)}>
            {full ? 'Hide the full summary' : `Full summary · ${plural(count, 'item')}`} <ChevronDownIcon size={15} />
          </button>
          {full && (
            <div className="glance-full">
              <div className="ho-legend">
                {LEGEND.map((type) => <TypeTag key={type} type={type} short />)}
                <span className="ho-legend-note">An AI summary is not a clinical assessment.</span>
              </div>
              <HandoverDoc sections={row.sections} layout="grid" />
            </div>
          )}
        </>
      ) : (
        <Empty icon={<LockIcon size={22} />} title="The summary is not available yet">
          {row.firstName} decides what is shared. You will see the summary as soon as it is approved.
        </Empty>
      )}
    </section>
  );
}

/** Between-session practice: the figures in one line with the client's permission, the details a click away; journal entries
    only when the client shared them. */
function PracticePanel({ row }: { row: TherapistClientRow }) {
  const practice = row.therapy.practice;
  const stats = practice.stats;
  const since = row.therapy.sinceStart;
  const figures = stats ? [
    stats.thoughtRecords > 0 ? `${stats.thoughtRecords}× exploring a thought${stats.avgDrop !== null ? ` (the feeling dropped by ${fmtNum(stats.avgDrop)})` : ''}` : null,
    stats.exposureAttempts > 0 ? plural(stats.exposureAttempts, 'exposure step') : null,
    stats.experiments > 0 ? `behavioural experiments ${stats.experimentsDone}/${stats.experiments}` : null,
  ].filter((f): f is string => Boolean(f)) : [];
  const records = practice.sharedRecords;
  return (
    <section className="card th-practice">
      <div className="card-row">
        <h2 className="card-title-lg"><SparkleIcon size={19} /> Practice between sessions</h2>
        {practice.allowed ? <Pill tone="ok">With the client's permission</Pill> : <Pill tone="neutral" icon={<LockIcon size={12} />}>No permission for a summary</Pill>}
      </div>
      {since.length > 1 && <MoodAnxietyChart points={since.map((p) => ({ date: p.date, at: null, mood: p.mood, anxiety: p.anxiety }))}
        title="Mood and anxiety since therapy started" height={140} />}
      {!stats ? <p className="muted">{row.firstName} has not allowed a summary of the practice. You see only the entries the client shares.</p>
        : <p className="th-figures">{figures.length ? figures.join(' · ') : 'No exercises yet since therapy started.'}</p>}
      {stats && stats.traps.length > 0 && (
        <p className="muted small">Thinking traps recognised: {stats.traps.map((t) => `${t.label} (${t.count})`).join(', ')}</p>
      )}
      {practice.homework.map((h) => (
        <p key={h.id} className="th-line"><span className="th-line-label">Between-session task</span> {h.title} <span className="muted">· {h.status === 'done'
          ? `done ${fmtShort(h.completedAt)}` : h.status === 'skipped' ? 'skipped' : `open, ${dayWord(h.dueLabel)}`}</span></p>
      ))}
      {practice.ladders.map((ladder) => (
        <details key={ladder.id} className="th-more">
          <summary>
            <span className="th-line-label">Exposure ladder</span> <span className="th-more-title">{ladder.goal}</span>
            <span className="th-progress" aria-hidden="true"><i style={{ width: `${(ladder.progress.done / Math.max(1, ladder.progress.total)) * 100}%` }} /></span>
            <span className="muted">{ladder.progress.done}/{ladder.progress.total}</span>
          </summary>
          <ol className="th-ladder-steps">
            {ladder.steps.map((s) => {
              const last = s.attempts[s.attempts.length - 1];
              return <li key={s.id} className={`is-${s.status}`}>{s.text} <span className="muted small">({s.expected}/10{last ? ` · last time ${last.peak}→${last.after}` : ''})</span></li>;
            })}
          </ol>
        </details>
      ))}
      {records.length === 0 ? <p className="muted small">No shared thought diary entries – by default they belong to the client only.</p> : (
        <details className="th-more">
          <summary><span className="th-line-label">Shared entries</span> <span className="th-more-title">Thought diary ({records.length})</span></summary>
          <div className="th-shared">
            {records.map((r) => (
              <article key={r.id} className="th-record">
                <p className="muted small">{fmtShort(r.date)} · {r.emotions.join(', ')} {r.intensityBefore ?? '–'} → {r.intensityAfter ?? '–'} / 10</p>
                <p><strong>Situation:</strong> {r.situation}</p>
                <p><strong>Thought:</strong> “{r.thought}”</p>
                {r.traps.length > 0 && <p><strong>Thinking traps:</strong> {r.traps.map((t) => t.label).join(', ')}</p>}
                {r.alternative && <p><strong>Alternative thought:</strong> “{r.alternative}”</p>}
              </article>
            ))}
          </div>
        </details>
      )}
    </section>
  );
}

/** The between-session support the therapist sets once therapy has started: a suggestion built from what the client approved,
    shown as a summary to take into use as is – the form only when the therapist wants to change it. */
function TherapyPlan({ row, therapistId }: { row: TherapistClientRow; therapistId: string }) {
  const { view, run, busy } = useValituki();
  const therapy = row.therapy;
  const config = therapy.config;
  const empty: PlanInput = { primaryGoal: '', allowedActivityIds: [], allowedTools: [], homeworkTool: null, homeworkNote: '', checkInsPerWeek: 2,
    track: '', doNotAddress: '' };
  const initial: PlanInput = config ? { primaryGoal: config.primaryGoal, allowedActivityIds: config.allowedActivityIds, allowedTools: config.allowedTools,
    homeworkTool: config.homeworkTool, homeworkNote: config.homeworkNote, checkInsPerWeek: config.checkInsPerWeek, track: config.track,
    doNotAddress: config.doNotAddress } : therapy.suggestedPlan ?? empty;
  const [plan, setPlan] = useState<PlanInput>(initial);
  const [editing, setEditing] = useState(!config && !therapy.suggestedPlan);
  const library = view.therapist.library;
  const tools = view.therapist.tools;

  if (therapy.episodeStatus !== 'active') {
    return (
      <section className="card plan-card plan-locked">
        <h2 className="card-title-lg"><StethoscopeIcon size={20} /> Mieliluotsi between sessions</h2>
        <p className="muted">When therapy starts, you set here how Mieliluotsi supports the client between sessions.</p>
      </section>
    );
  }

  function toggle(key: 'allowedActivityIds' | 'allowedTools', id: string) {
    setPlan((p) => ({ ...p, [key]: p[key].includes(id) ? p[key].filter((a) => a !== id) : [...p[key], id] }));
  }

  async function save() {
    const result = await run((s) => api.savePlan(s, therapistId, row.clientId, plan),
      () => 'Mieliluotsi now works only within the limits you set. The client was notified.');
    if (result) setEditing(false);
  }

  const toolTitle = (id: string | null) => tools.find((t) => t.id === id)?.title ?? '–';
  const shown = config ?? plan;
  const canSave = !busy && Boolean(plan.primaryGoal.trim()) && plan.allowedActivityIds.length > 0;
  return (
    <section className="card plan-card">
      <div className="card-row">
        <h2 className="card-title-lg"><StethoscopeIcon size={20} /> Mieliluotsi between sessions</h2>
        {!editing && (config ? <Pill tone="violet">In effect · v{config.version}</Pill> : <Pill tone="neutral">Suggestion</Pill>)}
      </div>
      <p className="muted">{config ? 'The AI works only within these limits.' : 'The suggestion is built from the information the client approved. The AI works only within these limits.'}</p>
      {editing ? (
        <div className="plan-form">
          <label className="field"><span className="field-label">Main goal</span>
            <input value={plan.primaryGoal} onChange={(e) => setPlan({ ...plan, primaryGoal: e.target.value })} /></label>
          <div className="field"><span className="field-label">Guided CBT exercises in the chat</span>
            <div className="chips">{tools.map((t) => (
              <button key={t.id} type="button" className="chip" aria-pressed={plan.allowedTools.includes(t.id)} onClick={() => toggle('allowedTools', t.id)}>{t.title}</button>
            ))}</div>
          </div>
          <div className="field"><span className="field-label">Between-session task (weekly)</span>
            <Segmented label="Between-session task" value={plan.homeworkTool ?? 'none'} onChange={(v) => setPlan({ ...plan, homeworkTool: v === 'none' ? null : v })}
              options={[{ value: 'none', label: 'No between-session task' }, ...tools.map((t) => ({ value: t.id, label: t.title }))]} />
            {plan.homeworkTool && (
              <textarea rows={2} value={plan.homeworkNote} aria-label="Instructions for the between-session task" onChange={(e) => setPlan({ ...plan, homeworkNote: e.target.value })}
                placeholder="E.g. write down one meeting situation before the next session" />
            )}
          </div>
          <div className="field"><span className="field-label">Allowed self-care exercises</span>
            <div className="chips">{library.map((a) => (
              <button key={a.id} type="button" className="chip" aria-pressed={plan.allowedActivityIds.includes(a.id)} onClick={() => toggle('allowedActivityIds', a.id)}>{a.title}</button>
            ))}</div>
          </div>
          <div className="field"><span className="field-label">Check-in frequency (mood and anxiety)</span>
            <Segmented label="Check-in frequency" value={plan.checkInsPerWeek} onChange={(v) => setPlan({ ...plan, checkInsPerWeek: v })}
              options={[{ value: 1, label: '1× / wk' }, { value: 2, label: '2× / wk' }, { value: 3, label: '3× / wk' }]} />
          </div>
          <label className="field"><span className="field-label">To track</span>
            <input value={plan.track} onChange={(e) => setPlan({ ...plan, track: e.target.value })} /></label>
          <label className="field"><span className="field-label">Do not address (free text)</span>
            <textarea rows={2} value={plan.doNotAddress} onChange={(e) => setPlan({ ...plan, doNotAddress: e.target.value })}
              placeholder="E.g. conflicts with colleagues are dealt with in sessions" /></label>
          <div className="row-gap">
            <button type="button" className="btn btn-primary" disabled={!canSave} onClick={save}><CheckIcon size={16} /> Save and activate</button>
            {(config || therapy.suggestedPlan) && (
              <button type="button" className="btn btn-quiet" onClick={() => { setPlan(initial); setEditing(false); }}>Cancel</button>
            )}
          </div>
        </div>
      ) : (
        <>
          <dl className="plan-dl plan-dl-grid">
            <div className="plan-dl-wide"><dt>Main goal</dt><dd>{shown.primaryGoal}</dd></div>
            <div><dt>Between-session task</dt><dd>{shown.homeworkTool ? `${toolTitle(shown.homeworkTool)}${shown.homeworkNote ? ` – ${shown.homeworkNote}` : ''}` : 'No between-session task'}</dd></div>
            <div><dt>Check-in</dt><dd>{shown.checkInsPerWeek}× / week{shown.track ? ` · tracking: ${shown.track}` : ''}</dd></div>
            <div className="plan-dl-wide"><dt>Allowed exercises</dt><dd className="chips">
              {shown.allowedTools.map((t) => <span key={t} className="chip-static chip-tool">{toolTitle(t)}</span>)}
              {library.filter((a) => shown.allowedActivityIds.includes(a.id)).map((a) => <span key={a.id} className="chip-static">{a.title}</span>)}
            </dd></div>
            {shown.doNotAddress && <div className="plan-dl-wide"><dt>Do not address</dt><dd>{shown.doNotAddress}</dd></div>}
          </dl>
          {config && <p className="statement"><CheckIcon size={16} /> The client sees: “{therapy.mode.statement}”</p>}
          <div className="row-gap">
            {!config && <button type="button" className="btn btn-primary" disabled={!canSave} onClick={save}><CheckIcon size={16} /> Activate</button>}
            <button type="button" className={`btn ${config ? 'btn-secondary btn-sm' : 'btn-quiet'}`} onClick={() => setEditing(true)}>
              {config ? 'Edit the settings' : 'Edit the suggestion'}
            </button>
          </div>
        </>
      )}
    </section>
  );
}

/** Ending therapy starts the follow-up: mood and anxiety weekly, a maintenance plan, and a change goes back to the care team. */
function EndTherapy({ row, therapistId }: { row: TherapistClientRow; therapistId: string }) {
  const { view, run, busy } = useValituki();
  const suggested = row.therapy.suggestedAftercare ?? { checkInsPerWeek: 1, allowedTools: [], maintenance: '', warningSigns: '' };
  const [plan, setPlan] = useState<AftercareInput>(suggested);
  const [open, setOpen] = useState(false);
  const tools = view.therapist.tools;
  return (
    <section className="card plan-card th-end">
      <div className="card-row">
        <h2 className="card-title-lg"><FlagIcon size={19} /> Ending therapy and follow-up</h2>
        {!open && <button type="button" className="btn btn-secondary btn-sm" onClick={() => setOpen(true)}>Draw up a maintenance plan</button>}
      </div>
      <p className="muted">After therapy, Mieliluotsi follows the client's wellbeing at the agreed pace. If wellbeing drops, the care team gets a review request.</p>
      {open && (
        <div className="plan-form">
          <label className="field"><span className="field-label">Maintenance plan – what to continue</span>
            <textarea rows={3} value={plan.maintenance} onChange={(e) => setPlan({ ...plan, maintenance: e.target.value })} /></label>
          <label className="field"><span className="field-label">Signs to act on</span>
            <textarea rows={2} value={plan.warningSigns} onChange={(e) => setPlan({ ...plan, warningSigns: e.target.value })} /></label>
          <div className="field"><span className="field-label">Exercises during follow-up</span>
            <div className="chips">{tools.map((t) => (
              <button key={t.id} type="button" className="chip" aria-pressed={plan.allowedTools.includes(t.id)}
                onClick={() => setPlan({ ...plan, allowedTools: plan.allowedTools.includes(t.id) ? plan.allowedTools.filter((x) => x !== t.id) : [...plan.allowedTools, t.id] })}>{t.title}</button>
            ))}</div>
          </div>
          <div className="field"><span className="field-label">Check-in during follow-up</span>
            <Segmented label="Check-in during follow-up" value={plan.checkInsPerWeek} onChange={(v) => setPlan({ ...plan, checkInsPerWeek: v })}
              options={[{ value: 1, label: '1× / wk' }, { value: 2, label: '2× / wk' }]} />
          </div>
          <div className="row-gap">
            <button type="button" className="btn btn-primary" disabled={busy || !plan.maintenance.trim()}
              onClick={() => run((s) => api.endTherapy(s, therapistId, row.clientId, plan), () => 'Therapy ended. Follow-up after therapy began, and the client was notified.')}>
              <CheckIcon size={16} /> End therapy and move to follow-up
            </button>
            <button type="button" className="btn btn-quiet" onClick={() => setOpen(false)}>Cancel</button>
          </div>
          <p className="muted small">The suggestion is built from the client's practice and the exercises they rated helpful. Edit it freely.</p>
        </div>
      )}
    </section>
  );
}

function AftercareSummary({ row }: { row: TherapistClientRow }) {
  const plan = row.therapy.aftercare;
  if (!plan) return null;
  return (
    <section className="card plan-card">
      <div className="card-row">
        <h2 className="card-title-lg"><FlagIcon size={19} /> Follow-up after therapy</h2>
        <Pill tone="brand">Started {fmtDate(plan.createdAt)}</Pill>
      </div>
      <dl className="plan-dl">
        <div><dt>Maintenance plan</dt><dd>{plan.maintenance}</dd></div>
        {plan.warningSigns && <div><dt>Signs to act on</dt><dd>{plan.warningSigns}</dd></div>}
        <div><dt>Check-in</dt><dd>{plan.checkInsPerWeek}× / week – mood and anxiety</dd></div>
      </dl>
      <p className="muted small">If wellbeing drops, the care team gets a review request. The client can always ask to be contacted.</p>
    </section>
  );
}
