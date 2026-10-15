import { useState } from 'react';
import { api } from '../api';
import { useValituki } from '../context';
import { fmtShort } from '../format';
import { CopyIcon, EyeIcon, LockIcon, QuoteIcon, TrashIcon } from '../icons';
import { MoodAnxietyChart } from '../components/charts';
import type { ThoughtRecordRow } from '../types';
import { ChangeBars } from './ChatWidgets';
import { useClientUI } from './ClientApp';
import { LadderCard } from './ToolsTab';

/* "Progress": mood and anxiety over time (Limbic's "Your progress"), a weekly review built only from the client's own
   answers (Wysa's "Your week in review") and the private thought journal. */

export default function ProgressTab() {
  const { client } = useClientUI();
  const practice = client.practice;
  const stats = practice.stats;
  return (
    <div className="cx-screen cx-progress">
      <h1 className="cx-title">Progress</h1>
      <MoodAnxietyChart points={client.progress.series} title="Your mood and anxiety" />
      <WordsCard />

      {practice.thoughtRecords.length > 0 && (
        <section className="cx-section">
          <h2 className="cx-h2">Thought diary</h2>
          <p className="cx-fine"><LockIcon size={12} /> Only you can see your entries. You can share a single entry with your therapist.</p>
          {practice.thoughtRecords.map((record) => <RecordCard key={record.id} record={record} />)}
        </section>
      )}

      <div className="cx-stats" aria-label="Practice in total">
        <span><strong>{stats.thoughtRecords}</strong> {stats.thoughtRecords === 1 ? 'thought explored' : 'thoughts explored'}</span>
        <span><strong>{stats.exposureAttempts}</strong> {stats.exposureAttempts === 1 ? 'exposure step' : 'exposure steps'}</span>
        <span><strong>{stats.experimentsDone}</strong> {stats.experimentsDone === 1 ? 'behavioural experiment' : 'behavioural experiments'}</span>
      </div>
      {stats.avgDrop !== null && (
        <p className="cx-fine">After exploring a thought, the feeling has dropped by <strong>{String(stats.avgDrop)}</strong>
          {stats.avgDrop === 1 ? ' point' : ' points'} on average on a scale of 0–10.{stats.traps.length > 0
          && ` The thinking trap you spot most often: ${stats.traps[0].label}.`}</p>
      )}

      <WeekCard />

      {practice.experiments.length > 0 && (
        <section className="cx-section">
          <h2 className="cx-h2">Behavioural experiments</h2>
          {practice.experiments.map((e) => (
            <article key={e.id} className="cx-card">
              <div className="cx-done-top"><span className="cx-tag">{e.status === 'done' ? 'Done' : 'Planned'}</span>
                <span className="cx-fine">{e.plannedFor ? fmtShort(e.plannedFor) : ''}</span></div>
              <p className="cx-card-label">Prediction</p><p>{e.prediction}</p>
              <p className="cx-card-label">Experiment</p><p>{e.plan}</p>
              {e.status === 'done' && (
                <>
                  <p className="cx-card-label">What happened</p><p>{e.outcome}</p>
                  {e.learned && <><p className="cx-card-label">What I learned</p><p>{e.learned}</p></>}
                  {e.beliefBefore !== null && e.beliefAfter !== null && (
                    <ChangeBars change={{ label: 'Belief in the prediction', before: e.beliefBefore, after: e.beliefAfter, max: 10 }} />
                  )}
                </>
              )}
            </article>
          ))}
        </section>
      )}

      {practice.ladders.length > 0 && (
        <section className="cx-section">
          <h2 className="cx-h2">Exposure ladders</h2>
          {practice.ladders.map((ladder) => <LadderCard key={ladder.id} ladder={ladder} />)}
        </section>
      )}
    </div>
  );
}

/** The week's own words, lifted from the client's answers – shown right under the chart. */
function WordsCard() {
  const { client } = useClientUI();
  const words = client.progress.week.words;
  const [copied, setCopied] = useState(false);
  if (!words) return null;
  return (
    <div className="cx-words">
      <p className="cx-words-kicker"><QuoteIcon size={14} /> Words to remember – in your own words</p>
      <p className="cx-words-text">{words}</p>
      <button type="button" className="cx-icon-btn cx-words-copy" aria-label="Copy"
        onClick={() => { void navigator.clipboard?.writeText(words).then(() => setCopied(true)).catch(() => undefined); }}>
        <CopyIcon size={17} />
      </button>
      {copied && <span className="cx-fine" role="status">Copied</span>}
    </div>
  );
}

function WeekCard() {
  const { view } = useValituki();
  const { client } = useClientUI();
  const week = client.progress.week;
  const moodWords = view.meta.labels.moodScale;
  return (
    <section className="cx-week" aria-label="Your week">
      <p className="cx-week-range">This week · {fmtShort(week.start)}–{fmtShort(week.end)}</p>
      <p className="cx-week-big"><strong>{week.sessions}</strong> {week.sessions === 1 ? 'exercise' : 'exercises'} this week</p>
      <div className="cx-week-days" role="list" aria-label="Mood by day">
        {week.days.map((d) => (
          <span key={d.date} role="listitem" className={`cx-week-day ${d.future ? 'is-future' : ''}`}
            aria-label={`${d.weekday}: ${d.mood ? `mood ${d.mood}/5 (${moodWords[String(d.mood)]})` : 'no check-in'}`}>
            <span className="cx-week-wd">{d.weekday}</span>
            <span className={`cx-week-dot ${d.mood ? `mood-${d.mood}` : ''}`}>{d.mood ?? ''}</span>
          </span>
        ))}
      </div>
      <p className="cx-fine cx-week-legend">Number = mood 1–5 (1 {(moodWords['1'] ?? 'very bad').toLowerCase()} … 5 {(moodWords['5'] ?? 'very good').toLowerCase()})</p>
      {week.cameUp.length > 0 && (
        <>
          <h3 className="cx-h3">What came up this week</h3>
          <ul className="cx-bullets">{week.cameUp.map((t) => <li key={t}>{t}</li>)}</ul>
        </>
      )}
      {week.steps.length > 0 && (
        <>
          <h3 className="cx-h3">Small steps forward</h3>
          <ul className="cx-bullets">{week.steps.map((t) => <li key={t}>{t}</li>)}</ul>
        </>
      )}
      <p className="cx-fine">Put together only from your own answers – not a diagnosis.</p>
    </section>
  );
}

function RecordCard({ record }: { record: ThoughtRecordRow }) {
  const { run, busy } = useValituki();
  const { client } = useClientUI();
  const [open, setOpen] = useState(false);
  const therapist = client.mode.therapistFirstName;
  return (
    <article className="cx-record">
      <button type="button" className="cx-record-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="cx-fine">{fmtShort(record.date)}{record.shared ? ' · shared with your therapist' : ''}</span>
        <span className="cx-record-situation">{record.situation}</span>
        <span className="cx-record-thoughts">
          <span className="cx-record-old">“{record.thought}”</span>
          {record.alternative && <span className="cx-record-new">→ “{record.alternative}”</span>}
        </span>
      </button>
      {open && (
        <div className="cx-record-body">
          {record.emotions.length > 0 && <p><span className="cx-card-label">Feelings</span> {record.emotions.join(', ')}</p>}
          {record.behaviour && <p><span className="cx-card-label">What I did</span> {record.behaviour}</p>}
          {record.traps.length > 0 && <p className="cx-chips-inline">{record.traps.map((t) => <span key={t.id} className="cx-tag">{t.label}</span>)}</p>}
          {record.evidenceFor && <p><span className="cx-card-label">What supports the thought</span> {record.evidenceFor}</p>}
          {record.evidenceAgainst && <p><span className="cx-card-label">What I would say to a friend</span> {record.evidenceAgainst}</p>}
          {record.intensityBefore !== null && record.intensityAfter !== null && (
            <ChangeBars change={{ label: 'Strength of the feeling', before: record.intensityBefore, after: record.intensityAfter, max: 10 }} />
          )}
          <div className="cx-row">
            <button type="button" className="cx-btn cx-btn-ghost cx-btn-sm" disabled={busy} aria-pressed={record.shared}
              onClick={() => run((s) => api.setPracticeSharing(s, client.id, 'thought_record', record.id, !record.shared),
                () => (record.shared ? 'Only you can see the entry again.' : `Entry shared${therapist ? ` with your therapist ${therapist}` : ' with your therapist once therapy starts'}.`))}>
              {record.shared ? <><LockIcon size={14} /> Stop sharing</> : <><EyeIcon size={14} /> Share with therapist</>}
            </button>
            <button type="button" className="cx-btn cx-btn-ghost cx-btn-sm" disabled={busy}
              onClick={() => run((s) => api.removePracticeItem(s, client.id, 'thought_record', record.id), () => 'Entry deleted.')}>
              <TrashIcon size={14} /> Delete
            </button>
          </div>
        </div>
      )}
    </article>
  );
}
