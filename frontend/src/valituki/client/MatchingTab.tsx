import { useState } from 'react';
import { api } from '../api';
import { useValituki } from '../context';
import { fmtDateTime } from '../format';
import { CalendarIcon, CheckIcon, ChevronDownIcon, CrossIcon, EyeIcon, InfoIcon, PuzzleIcon, SparkleIcon, UsersIcon, VideoIcon } from '../icons';
import { HandoverDoc } from '../components/HandoverDoc';
import { Pill, Scale5, Segmented, SharingSummary, TypeTag } from '../components/ui';
import type { Candidate, FitProfile } from '../types';
import { useClientUI } from './ClientApp';

/** Finding the right therapist – from the Therapy Fit Profile to the choice, the first session and the handover. Shown in
    "Care pathway"; `embedded` drops the screen padding. */
export default function MatchingTab({ embedded = false }: { embedded?: boolean }) {
  const { client } = useClientUI();
  const matching = client.matching;
  return (
    <div className={embedded ? 'matching matching-embedded' : 'screen matching'}>
      {matching.stage === 'choose' && <Choose />}
      {['booked', 'therapy', 'aftercare'].includes(matching.stage) && <Booked />}
      {['no_profile', 'building', 'searching', 'on_hold'].includes(matching.stage) && <Searching />}
    </div>
  );
}

function Searching() {
  const { client } = useClientUI();
  const matching = client.matching;
  return (
    <>
      <h1 className="display-sm">We're looking for a therapist who suits your situation</h1>
      <p className="muted">{matching.stage === 'on_hold'
        ? 'The search for a therapist continues once a professional has reviewed your situation.'
        : 'When a suitable therapist has a free slot, Mieliluotsi finds the options straight away and tells you why each one is suggested.'}</p>
      {client.fitProfile && <FitProfileCard profile={client.fitProfile} />}
      {matching.readiness && (
        <section className="card">
          <h3 className="card-title">What the search needs</h3>
          <ul className="criteria">
            {matching.readiness.map((c) => (
              <li key={c.key} className={c.passed ? 'ok' : 'todo'}>{c.passed ? <CheckIcon size={15} /> : <span className="dot-todo" />} {c.label}
                {c.detail && <span className="muted small"> · {c.detail}</span>}</li>
            ))}
          </ul>
        </section>
      )}
      <p className="notice"><InfoIcon size={16} /> Matching is deterministic: first the hard criteria (language, remote sessions, capacity, expertise), then
        a transparent weighted fit. AI does not choose the therapist.</p>
    </>
  );
}

export function FitProfileCard({ profile }: { profile: FitProfile }) {
  return (
    <section className="card fit-card">
      <div className="card-row">
        <h3 className="card-title">Therapy Fit Profile</h3>
        <Pill tone="brand">version {profile.version}</Pill>
      </div>
      <p className="muted small">Built while you wait, only from information you have approved.</p>
      <dl className="fit-dl">
        {profile.goals.primary.map((g) => (
          <div key={g.insightId}><dt>Goal</dt><dd>{g.text} <SharingSummary sharing={g} /></dd></div>
        ))}
        {profile.goals.secondary.map((g) => (
          <div key={g.insightId}><dt>Also</dt><dd>{g.text}</dd></div>
        ))}
        {profile.preferredWorkingStyle.text && (
          <div><dt>Working style</dt><dd>{String(profile.preferredWorkingStyle.text)} <SharingSummary sharing={{
            professional: Boolean(profile.preferredWorkingStyle.professional), matching: Boolean(profile.preferredWorkingStyle.matching) }} /></dd></div>
        )}
        {profile.practicalRows.map((row) => <div key={row.label}><dt>{row.label}</dt><dd>{row.value}</dd></div>)}
        {profile.selfCareResponses.filter((r) => r.helpful).map((r) => (
          <div key={r.activityId}><dt>What helps</dt><dd>{r.title} ({r.latestRating}/5)</dd></div>
        ))}
      </dl>
    </section>
  );
}

function CandidateCard({ candidate, onSelect, busy }: { candidate: Candidate; onSelect: () => void; busy: boolean }) {
  const [open, setOpen] = useState(false);
  const [allReasons, setAllReasons] = useState(false);
  const t = candidate.therapist;
  const reasons = allReasons ? candidate.reasons : candidate.reasons.slice(0, 5);
  return (
    <article className={`cand cand-${candidate.label}`}>
      <header className="cand-head">
        <span className="avatar" aria-hidden="true">{t.name.split(' ').map((p) => p[0]).join('')}</span>
        <div>
          <h3 className="cand-name">{t.name}</h3>
          <p className="cand-role">{t.role}</p>
        </div>
      </header>
      <p className={`fit-label fit-${candidate.label}`}>{candidate.labelText.toUpperCase()}</p>
      <p className="cand-why-title">Why {t.firstName}?</p>
      <ul className="reasons">{reasons.map((r) => <li key={r}><CheckIcon size={15} /> {r}</li>)}</ul>
      {candidate.reasons.length > 5 && (
        <button type="button" className="link-btn" onClick={() => setAllReasons(!allReasons)}>
          {allReasons ? 'Show less' : `+ ${candidate.reasons.length - 5} more ${candidate.reasons.length - 5 === 1 ? 'reason' : 'reasons'}`}
        </button>
      )}
      <div className="slot-box">
        <span className="eyebrow">First available time</span>
        <strong><CalendarIcon size={16} /> {candidate.firstSlotText}</strong>
      </div>
      <details className="unmet">
        <summary>Which wishes could not be met? <span className="unmet-count">{candidate.unmet.length || 'none'}</span></summary>
        {candidate.unmet.length ? <ul>{candidate.unmet.map((u) => <li key={u}><CrossIcon size={13} /> {u}</li>)}</ul>
          : <p className="muted small">All the wishes you told us about are met.</p>}
      </details>
      {open && (
        <div className="cand-more">
          <p>{t.bio}</p>
          <dl className="mini-dl">
            <div><dt>Approach</dt><dd>{t.approaches.join(', ')}</dd></div>
            <div><dt>Working style</dt><dd>{t.workingStyle}</dd></div>
            <div><dt>Languages</dt><dd>{t.languages.join(', ')}</dd></div>
            <div><dt>Sessions</dt><dd>{t.formats.join(' · ')}</dd></div>
            <div><dt>Times</dt><dd>{t.availableTimes.join(', ')}</dd></div>
          </dl>
          <p className="muted small">{candidate.explanation}</p>
          <p className="synthetic-tag">{t.syntheticLabel}</p>
        </div>
      )}
      <div className="cand-actions">
        <button type="button" className="btn btn-secondary" onClick={() => setOpen(!open)}>
          {open ? 'Close' : `Get to know ${t.firstName}`} <ChevronDownIcon size={15} />
        </button>
        <button type="button" className="btn btn-primary" disabled={busy} onClick={onSelect}>Choose</button>
      </div>
    </article>
  );
}

function Choose() {
  const { run, busy } = useValituki();
  const { client } = useClientUI();
  const matching = client.matching;
  const count = matching.candidates.length;
  const words: Record<number, string> = { 1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six' };
  const first = matching.candidates[0];
  return (
    <>
      <p className="eyebrow eyebrow-ok"><SparkleIcon size={14} /> Finding a therapist</p>
      <h1 className="display-sm">{count === 1 ? 'We found one therapist who suits your situation.' : `We found ${words[count] ?? count} therapists who suit your situation.`}</h1>
      <p className="muted">The order is based on the information you approved and on transparent criteria – not on probability. {first ? `Why do we recommend ${first.therapist.firstName}? See the reasons.` : ''}</p>
      <div className="cands">
        {matching.candidates.map((candidate) => (
          <CandidateCard key={candidate.id} candidate={candidate} busy={busy}
            onSelect={() => run((s) => api.selectCandidate(s, client.id, candidate.id),
              () => `You chose ${candidate.therapist.name}. Your first session was booked – please check the summary.`)} />
        ))}
      </div>
      <div className="stack-sm">
        {matching.decision?.canShowMore && (
          <button type="button" className="btn btn-secondary btn-block" disabled={busy}
            onClick={() => run((s) => api.moreCandidates(s, client.id), (r) => (r.added ? `${r.added} more ${r.added === 1 ? 'option' : 'options'}.` : 'There are no other options right now.'))}>
            Show other options
          </button>
        )}
        <button type="button" className="btn btn-quiet btn-block" disabled={busy || matching.decision?.helpRequested}
          onClick={() => run((s) => api.matchingHelp(s, client.id, ''), () => 'Your request was passed to the care team.')}>
          <UsersIcon size={17} /> {matching.decision?.helpRequested ? 'A professional will help you choose – request sent' : 'I want a professional to help me choose'}
        </button>
      </div>
      {first && (
        <details className="data-used card">
          <summary>What information was used in matching?</summary>
          <p className="section-label"><PuzzleIcon size={14} /> Used</p>
          <ul>{first.dataUsed.map((d) => <li key={d}>{d}</li>)}</ul>
          <p className="section-label"><EyeIcon size={14} /> Not used</p>
          <ul>{first.dataNotUsed.map((d) => <li key={d}>{d}</li>)}</ul>
        </details>
      )}
    </>
  );
}

// Summary items shown only in the therapist's view.
const CLIENT_HIDDEN = new Set(['sources', 'ai_summary']);

function Booked() {
  const { view, run, busy } = useValituki();
  const { client } = useClientUI();
  const matching = client.matching;
  const booking = matching.booking;
  const handover = matching.handover;
  if (!booking) return null;
  const therapy = matching.stage === 'therapy' || matching.stage === 'aftercare';
  return (
    <>
      <section className="booking-card">
        <p className="eyebrow">{matching.stage === 'aftercare' ? 'Therapy ended – follow-up continues' : therapy ? 'Your therapist' : 'First session'}</p>
        {matching.stage === 'aftercare' ? (
          <p className="booking-when"><UsersIcon size={20} /> {booking.therapist.name}</p>
        ) : (
          <p className="booking-when"><CalendarIcon size={20} /> {booking.startText}</p>
        )}
        <p className="booking-who">{matching.stage === 'aftercare' ? `Therapy started on ${booking.startText}` : booking.therapist.name} · <VideoIcon size={15} /> {booking.format}</p>
        <p className="synthetic-tag">{booking.therapist.syntheticLabel}</p>
      </section>

      {matching.stage === 'therapy' && <MatchFeedback />}

      {handover && (
        <section className="card handover-card">
          <div className="card-row">
            <h2 className="card-title-lg">Summary for the first session</h2>
          </div>
          {handover.status === 'approved' ? (
            <p className="banner banner-ok"><CheckIcon size={17} /> You approved the summary on {fmtDateTime(handover.approvedAt)}. {handover.therapistName} sees only the items below.</p>
          ) : (
            <p className="muted">This is a draft. Nothing is shared until you approve it. You can edit or remove items – your chat history is not shared.</p>
          )}
          <div className="type-legend" aria-label="Information types">
            {(['user_said', 'measured', 'ai_summary', 'professional_note'] as const).map((t) => <TypeTag key={t} type={t} />)}
          </div>
          {/* The sources list and the AI summary are for the therapist's view – the client sees the items themselves. */}
          <HandoverDoc sections={handover.sections.filter((x) => !CLIENT_HIDDEN.has(x.key))} editable busy={busy}
            onRemove={(section) => run((s) => api.updateHandover(s, client.id, { action: 'remove', section }), () => 'Item removed from the summary.')}
            onRestore={(section) => run((s) => api.updateHandover(s, client.id, { action: 'restore', section }))}
            onEditText={(section, text) => run((s) => api.updateHandover(s, client.id, { action: 'edit', section, text }), () => 'Edit saved.')}
            onEditQuestions={(questions) => run((s) => api.updateHandover(s, client.id, { action: 'edit', section: 'questions', questions }))} />
          <div className="stack-sm">
            {handover.status !== 'approved' ? (
              <button type="button" className="btn btn-primary btn-lg btn-block" disabled={busy}
                onClick={() => run((s) => api.approveHandover(s, client.id), () => `Summary shared: ${handover.therapistName} sees only the items you approved.`)}>
                <CheckIcon size={18} /> Approve for sharing
              </button>
            ) : (
              <button type="button" className="btn btn-quiet btn-block" disabled={busy}
                onClick={() => run((s) => api.withdrawHandover(s, client.id), () => 'Sharing withdrawn.')}>Withdraw sharing</button>
            )}
            <p className="muted small">{view.meta.syntheticNotice}</p>
          </div>
        </section>
      )}

    </>
  );
}

function MatchFeedback() {
  const { view, run, busy } = useValituki();
  const { client } = useClientUI();
  const given = client.matching.feedback.given;
  const [heard, setHeard] = useState<number | null>(null);
  const [goals, setGoals] = useState<number | null>(null);
  const [style, setStyle] = useState<number | null>(null);
  const [cont, setCont] = useState<'yes' | 'unsure' | 'no'>('yes');
  const [discuss, setDiscuss] = useState(false);
  const labels = { '1': 'Not at all', '2': 'A little', '3': 'Somewhat', '4': 'A lot', '5': 'Completely' };
  if (given.length) {
    const last = given[given.length - 1];
    return (
      <section className={`banner ${last.negative ? 'banner-warn' : 'banner-ok'}`}>
        <CheckIcon size={17} />
        <p>{last.negative ? 'Thank you for your feedback. Your therapist is not changed automatically – the care team will contact you and go through the situation with you.'
          : 'Thank you for your feedback! It helps us assess how well matching works.'}</p>
      </section>
    );
  }
  return (
    <section className="card feedback-card">
      <h3 className="card-title">How does working with your therapist feel?</h3>
      <p className="muted small">Your answers do not change your therapist automatically. Negative feedback opens a conversation with a professional.</p>
      <p className="q">Did I feel heard?</p>
      <Scale5 name="Did I feel heard?" value={heard} onChange={setHeard} labels={labels} />
      <p className="q">Did the therapist understand my goals?</p>
      <Scale5 name="Did the therapist understand my goals?" value={goals} onChange={setGoals} labels={labels} />
      <p className="q">Did the way of working feel right?</p>
      <Scale5 name="Did the way of working feel right?" value={style} onChange={setStyle} labels={labels} />
      <p className="q">Do I want to continue with this therapist?</p>
      <Segmented label="Do I want to continue?" value={cont} onChange={setCont}
        options={[{ value: 'yes', label: 'Yes' }, { value: 'unsure', label: 'Not sure' }, { value: 'no', label: 'No' }]} />
      <label className="check-row"><input type="checkbox" checked={discuss} onChange={(e) => setDiscuss(e.target.checked)} /> I want to discuss another option</label>
      <button type="button" className="btn btn-primary btn-block" disabled={busy || !heard || !goals || !style}
        onClick={() => run((s) => api.matchFeedback(s, client.id, { heard: heard ?? 3, goalsUnderstood: goals ?? 3, styleFit: style ?? 3,
          wantContinue: cont, wantDiscussAlternative: discuss, note: '' }), (negative) => (negative
          ? 'Feedback sent: the care team gets a review request (Matching review requested).' : 'Thank you for your feedback!'))}>
        Send feedback
      </button>
      <p className="muted small">{view.meta.syntheticNotice}</p>
    </section>
  );
}

