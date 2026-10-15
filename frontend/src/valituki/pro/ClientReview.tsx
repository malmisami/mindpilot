import { useState } from 'react';
import { api } from '../api';
import { useValituki } from '../context';
import { fmtDate, fmtDateTime, fmtNum, fmtShort, genitive, plural } from '../format';
import { AlertIcon, ArrowLeftIcon, CheckIcon, ChatIcon, CrossIcon, EyeIcon, LockIcon, PuzzleIcon, ShieldIcon, SparkleIcon } from '../icons';
import { Meter, WellbeingChart } from '../components/charts';
import { AgentTimeline } from '../components/Timeline';
import { AgentBadge, Pill, TypeTag } from '../components/ui';
import { FitProfileCard } from '../client/MatchingTab';
import type { ObservationRow, ProfessionalClient } from '../types';

export default function ClientReview({ client }: { client: ProfessionalClient }) {
  const { view, run, busy, setProClientId } = useValituki();
  const review = client.openReview;
  const lastReviewed = client.observations.find((o) => o.status !== 'open' && o.reviewedAt && o.kind !== 'trend_improvement');
  const openTasks = client.tasks.filter((t) => ['open', 'contact_requested'].includes(t.status) && (!review || t.observationId !== review.id));
  const events = client.observations.filter((o) => o.kind === 'trend_decline').map((o) => ({ date: o.createdAt.slice(0, 10), label: 'Review request' }));
  return (
    <div className="review-page">
      <button type="button" className="back-link" onClick={() => setProClientId(null)}><ArrowLeftIcon size={16} /> Waiting list</button>
      <header className="review-head">
        <div className="review-who">
          <span className="review-avatar" aria-hidden="true">{client.firstName[0]}{client.displayName.split(' ').slice(-1)[0]?.[0]}</span>
          <div>
            <h1 className="review-name">{client.displayName}</h1>
            <p className="review-meta">Age {client.age} · {client.municipality} · {client.referral?.serviceLabel} · sought help on {fmtDate(client.referral?.soughtHelpAt)}</p>
            <div className="review-chips">
              <span className="review-chip">{client.stateLabel}</span>
              {client.mode === 'therapy_support' && <span className="review-chip">Support between therapy sessions</span>}
              {client.safetyLockActive && <span className="review-chip is-alert"><AlertIcon size={13} /> Safety instructions shown</span>}
            </div>
          </div>
        </div>
        <dl className="review-stats">
          <div>
            <dt>Waited</dt>
            <dd><span className="review-stat">{client.waitingDays ?? '–'}</span> {client.waitingDays === 1 ? 'day' : 'days'}</dd>
          </div>
          {client.monitoring && client.trend.recent !== null && (
            <div className={`trend-${client.trend.direction}`}>
              <dt>Wellbeing now</dt>
              <dd><span className="review-stat">{fmtNum(client.trend.recent)}</span> / 5
                {client.trend.baseline !== null && <span className="review-stat-sub">own baseline {fmtNum(client.trend.baseline)}</span>}</dd>
            </div>
          )}
          {client.urgency && (
            <div className={`urgency-${client.urgency.value}`}>
              <dt>Urgency</dt>
              <dd><span className="review-stat review-stat-word">{client.urgency.label}</span>
                <span className="review-stat-sub">professional's decision</span></dd>
            </div>
          )}
        </dl>
      </header>

      <div className="review-grid">
        <div className="review-main">
          {review ? <WhyCard client={client} observation={review} /> : lastReviewed ? (
            <section className="card reviewed-card">
              <span className="reviewed-mark" aria-hidden="true"><CheckIcon size={20} /></span>
              <div>
                <p className="reviewed-when">Reviewed {fmtDateTime(lastReviewed.reviewedAt)}</p>
                <p className="reviewed-what"><strong>{lastReviewed.title}</strong> → {lastReviewed.reviewOutcome}</p>
                <p className="muted small">{lastReviewed.reviewedBy}{lastReviewed.reviewNote ? ` – ${lastReviewed.reviewNote}` : ''}</p>
              </div>
            </section>
          ) : (
            <section className="card calm-card">
              <p className="eyebrow">No open review requests</p>
              <p>Mieliluotsi continues its support. Nothing has been raised for review.</p>
            </section>
          )}

          <section className="card">
            {client.monitoring ? (
              <>
                <WellbeingChart title={`${genitive(client.firstName)} wellbeing compared with own baseline`} points={client.trend.series} height={230}
                  baseline={client.trend.baseline} events={events} note="self-reported 1–5 · not a diagnosis" />
                <p className="small">{client.trend.text}</p>
                <CheckInTable client={client} />
              </>
            ) : <p className="muted"><LockIcon size={15} /> The client has not allowed the care team to follow their wellbeing.</p>}
          </section>

          <MatchingPanel client={client} />

          <ClientTimeline client={client} />
        </div>

        <aside className="review-side">
          {client.urgency && <UrgencyBox client={client} />}
          <NoteForm client={client} />
          {openTasks.length > 0 && (
            <section className="card">
              <h2 className="card-title">Open tasks</h2>
              {openTasks.map((task) => (
                <div key={task.id} className="task">
                  <p className="task-title">{task.title} <AgentBadge agent={task.agent} /></p>
                  <p className="small">{task.reason}</p>
                  {typeof task.underlyingData.clientMessage === 'string' && <p className="task-quote">“{task.underlyingData.clientMessage}”</p>}
                  <p className="muted small">{task.suggestedAction}</p>
                  <div className="row-gap">
                    {task.status === 'open' && <button type="button" className="btn btn-secondary btn-sm" disabled={busy}
                      onClick={() => run((s) => api.taskAction(s, task.id, 'contact'), () => 'Contact arranged – the client was notified.')}><ChatIcon size={14} /> Contact</button>}
                    <button type="button" className="btn btn-quiet btn-sm" disabled={busy}
                      onClick={() => run((s) => api.taskAction(s, task.id, 'complete'), () => 'The task was marked as handled.')}><CheckIcon size={14} /> Handled</button>
                  </div>
                </div>
              ))}
            </section>
          )}

          <section className="card">
            <h2 className="card-title">Information shared by the client</h2>
            <p className="muted small">Only the information the client has given the permission “May be shown to a professional”.</p>
            <ul className="shared-list">
              {client.insights.visible.map((i) => (
                <li key={i.id}>
                  <span className="shared-kind">{i.title}</span> {i.text}
                  <span className="shared-meta">{i.sourceLabel}{i.matching ? <> · <PuzzleIcon size={12} /> matching</> : ''}</span>
                </li>
              ))}
            </ul>
            {client.insights.hiddenCount > 0 && <p className="muted small"><LockIcon size={13} /> {plural(client.insights.hiddenCount, 'item')} visible only to the client</p>}
          </section>

          {client.fitProfile && <FitProfileCard profile={client.fitProfile} />}

          {client.booking && (
            <section className="card">
              <h2 className="card-title">Therapy</h2>
              <p><strong>{client.booking.therapistName}</strong> · {client.booking.startText}</p>
              <p className="small">Summary: {client.handover?.statusLabel ?? 'not yet'}</p>
              <p className="small">Status: {client.therapy.mode.title}{client.therapy.configured ? ' – set by the therapist' : ''}</p>
              {client.matchFeedback.map((f) => (
                <p key={f.id} className={`small ${f.negative ? 'text-warn' : ''}`}>Working relationship feedback: felt heard {f.heard}/5 · goals {f.goalsUnderstood}/5 · way of working {f.styleFit}/5
                  {f.note ? ` – “${f.note}”` : ''}</p>
              ))}
            </section>
          )}

          <p className="muted small">{view.meta.syntheticNotice}</p>
        </aside>
      </div>
    </div>
  );
}

function ClientTimeline({ client }: { client: ProfessionalClient }) {
  const [all, setAll] = useState(false);
  const total = client.timeline.length;
  return (
    <section className="card">
      <div className="card-row">
        <h2 className="card-title">What did Mieliluotsi do? – {client.firstName}</h2>
        {total > 10 && <button type="button" className="link-btn" aria-expanded={all} onClick={() => setAll(!all)}>
          {all ? 'Show the latest' : `Show all (${total})`}</button>}
      </div>
      <AgentTimeline items={client.timeline.map((e) => ({ id: e.id, at: e.at, agent: e.agent, title: e.title, detail: e.detail,
        ruleId: e.ruleId, aiSource: e.aiSource, kind: e.kind }))} limit={all ? total : 10} />
    </section>
  );
}

function UrgencyBox({ client }: { client: ProfessionalClient }) {
  const { run, busy } = useValituki();
  const urgency = client.urgency;
  if (!urgency) return null;
  return (
    <section className={`card urgency-box urgency-${urgency.value}`}>
      <p className="eyebrow"><ShieldIcon size={14} /> Urgency of care</p>
      <p className="urgency-value">{urgency.label}</p>
      <p className="small muted">Set by: {urgency.setBy} · {fmtDate(urgency.setAt)}</p>
      <p className="urgency-note">Mieliluotsi has not changed the urgency of care. Only a professional can change it.</p>
      <label className="small">
        <span className="visually-hidden">Change the urgency (professional)</span>
        <select value={urgency.value} disabled={busy}
          onChange={(e) => run((s) => api.setUrgency(s, client.id, e.target.value as 'non_urgent' | 'urgent', 'Professional\'s assessment'),
            () => 'A professional changed the urgency of care – the change was recorded in the audit log.')}>
          <option value="non_urgent">Non-urgent</option>
          <option value="urgent">Urgent</option>
        </select>
      </label>
    </section>
  );
}

function WhyCard({ client, observation }: { client: ProfessionalClient; observation: ObservationRow }) {
  const { run, busy } = useValituki();
  const [showFrequency, setShowFrequency] = useState(false);
  const safety = observation.category === 'safety';
  const describe = (r: { outcome: string }) => `${client.firstName}: ${r.outcome}. Mieliluotsi continues its support – the urgency of care is unchanged.`;
  return (
    <section className={`card why-card ${safety ? 'why-safety' : ''}`}>
      <p className="why-eyebrow"><span className="why-pulse" aria-hidden="true" />{safety ? 'Safety observation' : 'Review request'} · {fmtDateTime(observation.createdAt)}</p>
      <h2 className="why-title">Why did {client.firstName} come up for review?</h2>
      <ul className="why-list">
        {observation.explanation.map((row, i) => (
          <li key={row.text}><span className="why-num" aria-hidden="true">{String(i + 1).padStart(2, '0')}</span>{row.text}</li>
        ))}
      </ul>
      <p className="why-basis">
        <AgentBadge agent={observation.agent} /> Rule <code>{observation.ruleId}</code> · deterministic · self-reported data · not a diagnosis
      </p>
      {observation.aiSummary && (
        <div className="ai-box">
          <TypeTag type="ai_summary" />
          <p>{observation.aiSummary}</p>
        </div>
      )}
      <div className="action-box">
        <p className="eyebrow">Mieliluotsi's action</p>
        <p className="action-text"><SparkleIcon size={16} /> {observation.suggestedAction || 'Suggestion: a professional review.'}</p>
        <div className="why-actions">
          <button type="button" className="btn btn-primary" disabled={busy}
            onClick={() => run((s) => api.reviewObservation(s, observation.id, 'mark_reviewed'), describe)}><CheckIcon size={16} /> Mark as reviewed</button>
          <button type="button" className="btn btn-secondary" disabled={busy}
            onClick={() => run((s) => api.reviewObservation(s, observation.id, 'contact'), describe)}><ChatIcon size={16} /> Contact</button>
          <button type="button" className="btn btn-secondary" disabled={busy}
            onClick={() => run((s) => api.reviewObservation(s, observation.id, 'no_action'), describe)}><CrossIcon size={16} /> No action</button>
          {!safety && (
            <button type="button" className="btn btn-secondary" disabled={busy} aria-expanded={showFrequency} onClick={() => setShowFrequency(!showFrequency)}>
              Change check-in frequency
            </button>
          )}
        </div>
        {showFrequency && (
          <div className="row-gap freq-row">
            {[3, 2, 1].map((n) => (
              <button key={n} type="button" className="btn btn-quiet btn-sm" disabled={busy}
                onClick={() => run((s) => api.reviewObservation(s, observation.id, 'frequency', '', n), describe)}>{n}× a week</button>
            ))}
          </div>
        )}
      </div>
      <p className="why-statement"><ShieldIcon size={16} /> The AI did not change the urgency – it raised the situation for review. Mieliluotsi has not changed the urgency
        of care. This observation is waiting for a professional review.</p>
    </section>
  );
}

function CheckInTable({ client }: { client: ProfessionalClient }) {
  const { view } = useValituki();
  const domains = view.meta.labels.domains;
  return (
    <details className="checkin-table">
      <summary>Check-ins ({client.checkIns.length})</summary>
      <table className="table">
        <thead><tr><th scope="col">Date</th><th scope="col">Status</th><th scope="col">Wellbeing</th><th scope="col">Anxiety</th><th scope="col">Changed</th><th scope="col">Note</th></tr></thead>
        <tbody>
          {client.checkIns.map((c) => (
            <tr key={c.id}>
              <td>{fmtShort(c.dueDate)}</td>
              <td>{c.status === 'completed' ? (c.kind === 'client_initiated' ? 'done (on own initiative)' : 'done') : c.status === 'missed' ? 'missed' : 'waiting'}</td>
              <td className="num">{c.mood ?? '–'}</td>
              <td className="num">{c.anxiety ?? '–'}</td>
              <td className="small">{Object.entries(c.changes).map(([k, v]) => `${domains[k]} ${v === 'worse' ? '↓' : '↑'}`).join(', ') || '–'}</td>
              <td className="small muted">{c.hasNote ? 'client only' : '–'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

function MatchingPanel({ client }: { client: ProfessionalClient }) {
  const matching = client.matching;
  if (!matching.decision) {
    return (
      <section className="card">
        <h2 className="card-title">Matching</h2>
        <ul className="criteria">
          {matching.readiness.map((c) => <li key={c.key} className={c.passed ? 'ok' : 'todo'}>{c.passed ? <CheckIcon size={15} /> : <span className="dot-todo" />} {c.label}</li>)}
        </ul>
        <p className="muted small">Matching runs automatically when a therapist has a client place free.</p>
      </section>
    );
  }
  return (
    <section className="card">
      <div className="card-row">
        <h2 className="card-title">Matching {matching.run ? `· ${fmtDateTime(matching.run.createdAt)}` : ''}</h2>
        <Pill tone="neutral">{matching.decision.status === 'held_for_review' ? 'Waiting for review' : matching.decision.status === 'client_selected' ? 'Client chose' : 'With the client'}</Pill>
      </div>
      <p className="muted small">Deterministic: hard requirements → weighted fit. The points are a transparent aid for ordering, not a probability – the client
        sees only the fit in words.</p>
      <div className="pro-cands">
        {matching.candidates.slice(0, 4).map((c) => (
          <details key={c.id} className="pro-cand" open={c.rank === 1}>
            <summary><span className="rank">{c.rank}</span> {c.therapist.name} <span className={`fit-label fit-${c.label}`}>{c.labelText}</span>
              {c.status === 'selected' && <Pill tone="ok">Chosen</Pill>}</summary>
            <div className="meters">
              {(c.components ?? []).map((m) => <Meter key={m.key} label={m.label} value={m.points} max={m.weight} detail={m.explanation} />)}
            </div>
          </details>
        ))}
      </div>
      {matching.excluded.length > 0 && (
        <details className="excluded">
          <summary>Ruled out by hard requirements ({matching.excluded.length})</summary>
          <ul>{matching.excluded.map((x) => <li key={x.therapistId}><strong>{x.name}</strong>: {x.failed.map((f) => f.reason).join(' · ')}</li>)}</ul>
        </details>
      )}
      {matching.candidates[0] && (
        <details className="excluded">
          <summary><EyeIcon size={14} /> Information used</summary>
          <ul>{matching.candidates[0].dataUsed.map((d) => <li key={d}>{d}</li>)}</ul>
          <p className="section-label">Not used</p>
          <ul>{matching.candidates[0].dataNotUsed.map((d) => <li key={d}>{d}</li>)}</ul>
        </details>
      )}
    </section>
  );
}

function NoteForm({ client }: { client: ProfessionalClient }) {
  const { run, busy } = useValituki();
  const [text, setText] = useState('');
  const [include, setInclude] = useState(true);
  return (
    <section className="card">
      <h2 className="card-title">Professional's note</h2>
      {client.notes.map((n) => <p key={n.id} className="small"><TypeTag type="professional_note" short /> {n.text}</p>)}
      <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="E.g. called, agreed next steps…" aria-label="Note" />
      <label className="check-row"><input type="checkbox" checked={include} onChange={(e) => setInclude(e.target.checked)} /> May be added to the therapist's summary (the client approves)</label>
      <button type="button" className="btn btn-secondary btn-sm" disabled={busy || !text.trim()}
        onClick={async () => { await run((s) => api.addNote(s, client.id, text, include), () => 'The note was saved.'); setText(''); }}>Save note</button>
    </section>
  );
}
