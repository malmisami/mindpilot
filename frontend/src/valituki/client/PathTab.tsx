import { fmtDate } from '../format';
import { ArrowRightIcon, CheckIcon, GridIcon, StethoscopeIcon } from '../icons';
import { Pill } from '../components/ui';
import { useClientUI } from './ClientApp';
import { plural } from '../format';
import { PathSteps } from './HomeTab';
import MatchingTab from './MatchingTab';

/* "Care pathway": the original pathway stays at the centre – waiting with support, finding the right therapist, therapy with
   therapist-guided support between sessions, and follow-up after therapy. */

export default function PathTab() {
  const { client } = useClientUI();
  return (
    <div className="cx-screen cx-path-screen">
      <h1 className="cx-title">Care pathway</h1>
      <PathSteps phase={client.phase} />
      <p className="cx-fine">{client.stateLabel}{client.waiting.daysWaiting !== null ? ` · ${plural(client.waiting.daysWaiting, 'day', 'days')} since you sought help` : ''}</p>

      <ModeCard />

      <section className="cx-section">
        <h2 className="cx-h2">Therapist</h2>
        <MatchingTab embedded />
      </section>
    </div>
  );
}

function ModeCard() {
  const { client, openTab } = useClientUI();
  const mode = client.mode;
  const therapy = mode.mode === 'therapy_support';
  const aftercare = mode.mode === 'aftercare_support';
  // While waiting there is nothing for Sami to act on here; the card appears once the therapist sets the support.
  if (!therapy && !aftercare) return null;
  return (
    <section className={`cx-modecard ${therapy ? 'is-therapy' : 'is-aftercare'}`}>
      <p className="cx-eyebrow">{therapy ? <StethoscopeIcon size={14} /> : <CheckIcon size={14} />} Now</p>
      <p className="cx-modecard-title">{mode.title}</p>
      <p className="cx-fine">Guided by: {mode.controlledBy}</p>
      {mode.statement && <p className="cx-modecard-statement">{mode.statement}</p>}
      {therapy && mode.configured && (
        <dl className="cx-dl">
          <div><dt>Main goal</dt><dd>{mode.primaryGoal}</dd></div>
          {mode.homework && <div><dt>Between-session task</dt><dd>{mode.homework.title}{mode.homework.note ? ` – ${mode.homework.note}` : ''}</dd></div>}
          {mode.allowedTools && mode.allowedTools.length > 0 && (
            <div><dt>Guided exercises</dt><dd className="cx-chips-inline">{mode.allowedTools.map((t) => <span key={t.id} className="cx-tag">{t.title}</span>)}</dd></div>
          )}
          <div><dt>Self-care</dt><dd className="cx-chips-inline">{mode.allowedActivities?.map((a) => <span key={a.id} className="cx-tag">{a.title}</span>)}</dd></div>
          <div><dt>Check-in</dt><dd>{mode.checkIns} · tracking: {mode.track}</dd></div>
          {mode.doNotAddress && <div><dt>Discussed in sessions</dt><dd>{mode.doNotAddress}</dd></div>}
        </dl>
      )}
      {aftercare && (
        <dl className="cx-dl">
          {mode.maintenance && <div><dt>Maintenance plan</dt><dd>{mode.maintenance}</dd></div>}
          {mode.warningSigns && <div><dt>Warning signs to act on</dt><dd>{mode.warningSigns}</dd></div>}
          <div><dt>Follow-up</dt><dd>Mood and anxiety, {mode.checkIns}</dd></div>
          {mode.allowedTools && mode.allowedTools.length > 0 && (
            <div><dt>Exercises</dt><dd className="cx-chips-inline">{mode.allowedTools.map((t) => <span key={t.id} className="cx-tag">{t.title}</span>)}</dd></div>
          )}
        </dl>
      )}
      {aftercare && (
        <button type="button" className="cx-btn cx-btn-dark cx-btn-block" onClick={() => openTab('harjoitukset')}>
          <GridIcon size={17} /> Go to exercises <ArrowRightIcon size={16} />
        </button>
      )}
      {therapy && mode.configured && <Pill tone="violet">Set by your therapist · v{mode.version} · {fmtDate(mode.configuredAt)}</Pill>}
    </section>
  );
}
