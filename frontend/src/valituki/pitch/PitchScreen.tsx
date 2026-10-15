import { Fragment } from 'react';
import { useValituki } from '../context';
import { ArrowDownIcon, ArrowRightIcon, CheckIcon, ClockIcon, EyeIcon, HandHeartIcon, NodesIcon, PuzzleIcon, ShieldIcon, SparkleIcon, StethoscopeIcon, ThoughtIcon } from '../icons';

const BEFORE = ['Seeking help', 'Waiting list', 'Waiting', 'Waiting', 'Therapy'];
const AFTER_TOP = ['Seeking help', 'Getting started from records'];
const AFTER_BOX = ['Tracking mood and anxiety', 'Guided CBT practice in the chat', 'Detecting changes', 'Therapy Fit Profile'];
const AFTER_BOTTOM = ['The best-fitting available therapist', 'A ready handover, approved by the client', 'Therapy + between-session tasks in Mieliluotsi',
  'Follow-up after therapy'];
const CHAIN = ['Seeking help', 'Waiting', 'Proactive support', 'CBT practice', 'Human oversight', 'Therapist matching', 'Handover', 'Therapy',
  'Support between sessions', 'Follow-up'];

const PRINCIPLES = [
  { icon: <ClockIcon size={20} />, title: 'Support starts now', text: 'Useful support from the moment the client is added to the waiting list.' },
  { icon: <ThoughtIcon size={20} />, title: 'CBT one question at a time', text: 'Situation → thought → feeling 0–10 → thinking trap → alternative → exercise.' },
  { icon: <ArrowRightIcon size={20} />, title: 'Continuity', text: 'What is learned while waiting carries on in therapy – and in the follow-up after it.' },
  { icon: <PuzzleIcon size={20} />, title: 'Transparent matching', text: 'Explainable, explicit criteria – no black box.' },
  { icon: <EyeIcon size={20} />, title: 'The user decides', text: 'What is stored, shared and used in matching.' },
  { icon: <StethoscopeIcon size={20} />, title: 'A human decides', text: 'AI suggests and summarises – treatment and prioritisation belong to the professional.' },
];

const AGENTS = [
  { name: 'Support agent', text: 'Chat and guided CBT exercises' },
  { name: 'Check-in agent', text: 'Mood, anxiety, reminders' },
  { name: 'Observation agent', text: 'Change from own baseline' },
  { name: 'Matching agent', text: 'Deterministic matching' },
  { name: 'Service guidance agent', text: 'Next step and transitions' },
  { name: 'Safety agent', text: 'Can interrupt everything' },
];

export default function PitchScreen() {
  const { setRole, setClientId, setClientTab } = useValituki();
  return (
    <div className="pitch">
      <section className="pitch-hero">
        <p className="pitch-kicker">Mieliluotsi</p>
        <h1 className="pitch-title">From a passive waiting list to an active care pathway</h1>
        <p className="pitch-lead">Support starts now, even if therapy does not start yet. The waiting list stops being passive waiting and becomes an active part of the care pathway.</p>
      </section>

      <section className="pitch-compare" aria-label="Before and with Mieliluotsi">
        <div className="flow flow-before">
          <p className="flow-label">Before</p>
          {BEFORE.map((step, i) => (
            <Fragment key={`${step}-${i}`}>
              <div className={`flow-step ${step === 'Waiting' ? 'flow-wait' : ''}`}>{step}</div>
              {i < BEFORE.length - 1 && <span className="flow-arrow" aria-hidden="true"><ArrowDownIcon size={18} /></span>}
            </Fragment>
          ))}
        </div>
        <div className="flow flow-after">
          <p className="flow-label">With Mieliluotsi</p>
          {AFTER_TOP.map((step) => (
            <Fragment key={step}>
              <div className="flow-step">{step}</div>
              <span className="flow-arrow" aria-hidden="true"><ArrowDownIcon size={18} /></span>
            </Fragment>
          ))}
          <div className="flow-box">
            <p className="flow-box-title"><SparkleIcon size={18} /> Mieliluotsi</p>
            <ul>{AFTER_BOX.map((item) => <li key={item}><CheckIcon size={15} /> {item}</li>)}</ul>
          </div>
          {AFTER_BOTTOM.map((step) => (
            <Fragment key={step}>
              <span className="flow-arrow" aria-hidden="true"><ArrowDownIcon size={18} /></span>
              <div className={`flow-step ${step.startsWith('Follow-up') ? 'flow-final' : ''}`}>{step}</div>
            </Fragment>
          ))}
        </div>
      </section>

      <section className="pitch-orchestration">
        <h2>Conversation in front – rules, agents and professionals behind it</h2>
        <ol className="chain">
          {CHAIN.map((step, i) => <li key={step}><span className="chain-n">{i + 1}</span>{step}</li>)}
        </ol>
      </section>

      <section className="pitch-agents">
        <div className="agents-diagram">
          <div className="orchestrator"><NodesIcon size={22} /><strong>Orchestrator</strong><span>decides which agent acts</span></div>
          <ul className="agent-ring">{AGENTS.map((a) => <li key={a.name}><strong>{a.name}</strong><span>{a.text}</span></li>)}</ul>
        </div>
        <div className="pitch-rules">
          <p><ShieldIcon size={18} /><span><strong>Rules decide; the language model only phrases.</strong> The exercise steps, the safety level,
            matching and states are deterministic; every reply goes through a safety check.</span></p>
          <p><StethoscopeIcon size={18} /><span><strong>A human decides about care.</strong> Mieliluotsi raises changes for review – it does not change
            the urgency.</span></p>
          <p><EyeIcon size={18} /><span><strong>The client decides about their data.</strong> Interpretations are saved only once approved, and every item has
            its own permission.</span></p>
        </div>
      </section>

      <section className="pitch-principles">
        {PRINCIPLES.map((p) => (
          <div key={p.title} className="principle"><span className="principle-icon">{p.icon}</span><strong>{p.title}</strong><p>{p.text}</p></div>
        ))}
      </section>

      <section className="pitch-close">
        <HandHeartIcon size={30} />
        <p className="pitch-quote">Mieliluotsi does not replace the therapist.</p>
        <p className="pitch-quote-2">It makes the time before therapy, between sessions and after them a continuous part of the care pathway.</p>
        <button type="button" className="btn btn-primary btn-lg" onClick={() => { setClientId('cl-aino'); setClientTab('koti'); setRole('client'); }}>
          Start demo: Sami is on the waiting list for therapy <ArrowRightIcon size={18} />
        </button>
        <p className="muted small">All the people and health information in the demo are entirely fictional.</p>
      </section>
    </div>
  );
}
