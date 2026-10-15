import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useValituki } from '../context';
import { fmtShort } from '../format';
import { ArrowRightIcon, ChatIcon, CheckIcon, ClockIcon, EditIcon, InfoIcon, PhoneIcon, QuoteIcon, SendIcon, SparkleIcon } from '../icons';
import { LogoMark } from '../components/Logo';
import { Pill, Segmented } from '../components/ui';
import type { ConsentScope, IntakeProposal, ValitukiView } from '../types';
import { useClientUI } from './ClientApp';


export default function Intake() {
  const { client } = useClientUI();
  switch (client.intake.status) {
    case 'not_started':
    case 'consent':
      return <Welcome />;
    case 'conversation':
      return <Conversation />;
    case 'review':
      return <Review />;
    case 'rhythm':
      return <Rhythm />;
    default:
      return null;
  }
}

function Welcome() {
  const { view, run, busy } = useValituki();
  const { client } = useClientUI();
  const [consent, setConsent] = useState<ConsentScope>(client.intake.consentDefaults);
  const labels = view.meta.labels.consents;
  return (
    <div className="screen intake-welcome iw">
      <h1 className="display iw-hello">Hi {client.firstName}</h1>
      <p className="lead">You are on the therapy waiting list. Normally this is where the wait would begin – now support can start straight away.</p>
      <div className="card wait-card wait-hero">
        <p className="wait-hero-label"><ClockIcon size={16} /> Estimated wait for therapy</p>
        <p className="wait-hero-value">{client.waiting.estimatedWait}</p>
        <p className="wait-hero-meta">You sought help on {fmtShort(client.waiting.soughtHelpAt)} · {client.waiting.service}</p>
      </div>
      <p className="iw-text">You already described your situation in your referral and at your assessment visit, so you won't be asked the same
        things again. With your permission, Mieliluotsi uses this information. You can check and edit it on the My data page.</p>
      <div className="card consent-card iw-consent">
        <h3 className="card-title">How your information is used</h3>
        {(Object.keys(labels) as (keyof ConsentScope)[]).map((key) => (
          <label key={key} className="switch-row" title={labels[key].description}>
            <span className="switch-title">{labels[key].title}</span>
            <input type="checkbox" className="switch" checked={consent[key]} onChange={(e) => setConsent({ ...consent, [key]: e.target.checked })} />
          </label>
        ))}
        <details className="iw-more">
          <summary>What do these mean?</summary>
          <dl>{(Object.keys(labels) as (keyof ConsentScope)[]).map((key) => (
            <div key={key}><dt>{labels[key].title}</dt><dd>{labels[key].description}</dd></div>
          ))}</dl>
          <p>You can change these at any time on the My data page.</p>
        </details>
      </div>
      <p className="iw-notice"><InfoIcon size={14} /> Not a therapist or an emergency service – in an emergency, call 112.</p>
      <button type="button" className="btn btn-primary btn-lg btn-block" disabled={busy}
        onClick={() => run((s) => api.intakeStart(s, client.id, consent))}>
        Continue <ArrowRightIcon size={18} />
      </button>
    </div>
  );
}

function Conversation() {
  const { view, run, busy } = useValituki();
  const { client } = useClientUI();
  const intake = client.intake;
  const [text, setText] = useState('');
  const endRef = useRef<HTMLDivElement>(null);
  const pending = intake.pendingQuestion;

  // Demo mode (not Claude): each question's scripted answer is already typed in the field – press send or edit it first.
  const demoMode = view.meta.ai.configuredMode === 'DEMO_AI_MODE';
  const draftKey = `${pending?.key ?? ''}|${demoMode}`;
  const [draftFor, setDraftFor] = useState<string | null>(null);
  if (draftFor !== draftKey) {
    setDraftFor(draftKey);
    setText(demoMode ? pending?.demoAnswer ?? '' : '');
  }

  // Scroll the phone to the very bottom: scrollIntoView would leave the newest message under the sticky composer.
  useEffect(() => {
    const scroller = endRef.current?.closest('.phone-scroll');
    scroller?.scrollTo({ top: scroller.scrollHeight, behavior: 'smooth' });
  }, [intake.messages.length, busy, pending?.key]);

  async function send(answer: string): Promise<ValitukiView | null> {
    let latest: ValitukiView | null = null;
    await run(async (s) => {
      const response = await api.intakeAnswer(s, client.id, answer);
      latest = response.view;
      return response;
    });
    return latest;
  }

  async function submit() {
    const answer = text.trim();
    if (!answer) return;
    setText('');
    await send(answer);
  }


  const total = intake.plan.length;
  const step = Math.min(total, intake.answeredCount + 1);
  return (
    <div className="chat-screen">
      <div className="chat-progress" aria-label={`Question ${step}/${total}`}>
        {intake.plan.map((q, i) => <span key={q.key} className={i < intake.answeredCount ? 'done' : i === intake.answeredCount ? 'current' : ''} />)}
      </div>
      <div className="chat-log" aria-live="polite">
        {intake.messages.map((m) => (
          <div key={m.id} className={`bubble-row ${m.role === 'client' ? 'me' : 'bot'}`}>
            {m.role === 'assistant' && <span className="bot-mark" aria-hidden="true"><LogoMark size={26} /></span>}
            <div className={`bubble ${m.role === 'client' ? 'bubble-me' : m.questionKey ? 'bubble-q' : 'bubble-bot'}`}>{m.text}</div>
          </div>
        ))}
        {busy && <div className="bubble-row bot"><span className="bot-mark" aria-hidden="true"><LogoMark size={26} /></span><div className="bubble bubble-bot typing"><i /><i /><i /></div></div>}
        <div ref={endRef} />
      </div>
      <div className="composer">
        <div className="composer-row">
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={Math.min(5, Math.max(2, Math.ceil(text.length / 36)))}
            placeholder="Write in your own words…" aria-label="Your answer"
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void submit(); } }} disabled={busy} />
          <button type="button" className="send-btn" aria-label="Send" disabled={busy || !text.trim()} onClick={submit}><SendIcon size={18} /></button>
        </div>
        <div className="composer-actions">
          {pending && pending.key !== 'reason' && (
            <button type="button" className="link-btn" disabled={busy} onClick={() => run((s) => api.intakeSkip(s, client.id))}>Skip question</button>
          )}
          {intake.canFinish && (
            <button type="button" className="link-btn" disabled={busy} onClick={() => run((s) => api.intakeFinish(s, client.id))}>Go to the summary</button>
          )}
        </div>
      </div>
    </div>
  );
}

function ProposalChips({ proposal }: { proposal: IntakeProposal }) {
  const { view } = useValituki();
  const labels = view.meta.labels;
  const s = proposal.structured as Record<string, unknown>;
  if (proposal.category === 'practical') {
    const langs = (s.languages as string[] | undefined) ?? [];
    const times = (s.times as string[] | undefined) ?? [];
    const days = (s.days as number[] | undefined) ?? [];
    return (
      <div className="chips">
        <span className="chip-static">{labels.formats[String(s.format ?? 'either')]}</span>
        {langs.map((l) => <span key={l} className="chip-static">{labels.languages[l]}</span>)}
        {times.map((t) => <span key={t} className="chip-static">{labels.times[t]}</span>)}
        {days.map((d) => <span key={d} className="chip-static">{labels.weekdays[d]}</span>)}
      </div>
    );
  }
  return null;
}

function Review() {
  const { run, busy } = useValituki();
  const { client } = useClientUI();
  const intake = client.intake;
  const [editing, setEditing] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  // Practical wishes (format, language, times) are saved with the rest but not shown here – the card stays about Sami.
  const main = intake.proposals.filter((p) => ['goal', 'working_style'].includes(p.category));
  const more = intake.proposals.filter((p) => !['goal', 'working_style', 'practical'].includes(p.category));

  async function saveEdits() {
    for (const proposal of intake.proposals) {
      const draft = drafts[proposal.id];
      if (draft !== undefined && draft.trim() && draft.trim() !== proposal.text) {
        await run((s) => api.updateProposal(s, client.id, proposal.id, { text: draft.trim() }));
      }
    }
    setDrafts({});
    setEditing(false);
  }

  function card(proposal: IntakeProposal) {
    return (
      <article key={proposal.id} className={`proposal prop-${proposal.category} ${proposal.included ? '' : 'prop-excluded'}`}>
        <header className="prop-head">
          <span className="prop-title">{proposal.title}</span>
          {proposal.editedByClient ? <Pill tone="brand" icon={<EditIcon size={12} />}>You edited</Pill>
            : <Pill tone="violet" icon={<SparkleIcon size={12} />}>Interpretation</Pill>}
        </header>
        {editing ? (
          <textarea className="prop-edit" rows={3} value={drafts[proposal.id] ?? proposal.text} aria-label={`Edit: ${proposal.title}`}
            onChange={(e) => setDrafts({ ...drafts, [proposal.id]: e.target.value })} />
        ) : (
          <p className="prop-text">{proposal.text}</p>
        )}
        {!editing && <ProposalChips proposal={proposal} />}
        {proposal.userWords.length > 0 && (
          <div className="prop-quote">
            <p className="prop-quote-label"><QuoteIcon size={13} /> You said in the conversation</p>
            {proposal.userWords.map((w) => <p key={w} className="prop-quote-text">“{w}”</p>)}
          </div>
        )}
      </article>
    );
  }

  return (
    <div className="screen review-screen">
      <p className="eyebrow">Summary of the first conversation</p>
      <h1 className="display-sm">Did I understand your situation correctly?</h1>
      <p className="muted">These are only suggestions. Nothing is saved or used until you approve them.</p>
      <div className="proposals">{[...main, ...more].map(card)}</div>
      <div className="stack-sm sticky-actions">
        {editing ? (
          <>
            <button type="button" className="btn btn-primary btn-lg btn-block" disabled={busy} onClick={saveEdits}>Save changes</button>
            <button type="button" className="btn btn-quiet btn-block" onClick={() => { setDrafts({}); setEditing(false); }}>Cancel</button>
          </>
        ) : (
          <>
            <button type="button" className="btn btn-primary btn-lg btn-block" disabled={busy}
              onClick={() => run((s) => api.intakeConfirm(s, client.id), () => 'You approved the interpretations. Your Therapy Fit Profile was created only from the information you approved.')}>
              <CheckIcon size={18} /> Yes, this describes my situation
            </button>
            <button type="button" className="btn btn-secondary btn-block" disabled={busy} onClick={() => setEditing(true)}>
              <EditIcon size={17} /> I want to edit
            </button>
          </>
        )}
      </div>
    </div>
  );
}

/* When Mieliluotsi may call (contactChannel 'phone') – the same times as CALL_TIMES in backend/app/valituki/intake.py. */
const CALL_TIMES = [{ value: '09:00', label: 'at 09:00' }, { value: '15:00', label: 'at 15:00' }, { value: '18:30', label: 'at 18:30' }];

function Rhythm() {
  const { view, run, busy } = useValituki();
  const { client } = useClientUI();
  const options = view.meta.checkInFrequencyOptions;
  const demo = client.intake.demoRhythm;
  const [perWeek, setPerWeek] = useState<number>(demo ? demo.checkInDays.length : 3);
  // In the app in writing, or by phone: Mieliluotsi calls on the check-in days, asks how the client is and does a short
  // thought exercise by speech.
  const [channel, setChannel] = useState<'app' | 'phone'>('app');
  const [callTime, setCallTime] = useState('18:30');
  const days = options.find((o) => o.perWeek === perWeek)?.days ?? [0, 2, 5];
  const phone = channel === 'phone';
  return (
    <div className="screen rhythm-screen">
      <p className="eyebrow">Last step</p>
      <h1 className="display-sm">How will Mieliluotsi support you?</h1>
      <section className="card">
        <h3 className="card-title">How would you like us to keep in touch?</h3>
        <div className="radio-cards">
          <button type="button" className="radio-card" aria-pressed={!phone} onClick={() => setChannel('app')}>
            <strong><ChatIcon size={16} /> In the app, in writing</strong>
            <span className="muted small">You answer wellbeing check-ins and do exercises in writing, whenever it suits you.</span>
          </button>
          <button type="button" className="radio-card" aria-pressed={phone} onClick={() => setChannel('phone')}>
            <strong><PhoneIcon size={16} /> By phone – Mieliluotsi calls you</strong>
            <span className="muted small">On the agreed days Mieliluotsi calls you, asks how you are and does a short thought exercise with you
              by voice.</span>
          </button>
        </div>
        {phone && (
          <div className="rhythm-call-time">
            <p className="field-label">What time may I call?</p>
            <Segmented label="Call time" value={callTime} onChange={setCallTime} options={CALL_TIMES} />
          </div>
        )}
      </section>
      <section className="card">
        <h3 className="card-title">{phone ? 'How often may I call?' : 'How often may I check in on you?'}</h3>
        <div className="radio-cards">
          {[...options].sort((a, b) => b.perWeek - a.perWeek).map((option) => (
            <button key={option.perWeek} type="button" className="radio-card" aria-pressed={perWeek === option.perWeek} onClick={() => setPerWeek(option.perWeek)}>
              <strong>{option.label}</strong>
              {option.perWeek === 3 && <span className="muted small">Recommended while you wait – changes are noticed in time</span>}
            </button>
          ))}
        </div>
      </section>
      <button type="button" className="btn btn-primary btn-lg btn-block" disabled={busy}
        onClick={() => run((s) => api.intakeComplete(s, client.id, { checkInDays: days, communicationStyle: demo?.communicationStyle ?? 'brief',
          contactChannel: channel, callTime: phone ? callTime : undefined }),
        () => (phone ? 'Mieliluotsi is now on. Your first wellbeing call is coming soon – you can also ask for it right away.'
          : 'Mieliluotsi is now on. The agents created a support plan and chose the first step for today.'))}>
        Start Mieliluotsi <ArrowRightIcon size={18} />
      </button>
    </div>
  );
}
