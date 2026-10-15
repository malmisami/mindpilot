import { useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { api } from '../api';
import { useValituki } from '../context';
import { dayWord, fmtShort, plural } from '../format';
import {
  ArrowRightIcon, CalendarIcon, ChatIcon, CheckIcon, ChevronRightIcon, CrossIcon, FlaskIcon, LeafIcon, PhoneIcon, SendIcon,
  SparkleIcon, StairsIcon, StethoscopeIcon, ThoughtIcon,
} from '../icons';
import { LogoMark } from '../components/Logo';
import { Scale5 } from '../components/ui';
import type { PracticeTask } from '../types';
import { useClientUI } from './ClientApp';

// The words come from the backend's mood scale (view.meta.labels.moodScale); these are only the fallback.
const MOODS: { value: number; short: string }[] = [
  { value: 1, short: 'Very bad' }, { value: 2, short: 'Bad' }, { value: 3, short: 'Okay' },
  { value: 4, short: 'Good' }, { value: 5, short: 'Very good' },
];

/** Today's mood and anxiety right after the intake – the first point of the client's own baseline, not a comparison with others. */
function callClock(time: string | null): string {
  return time ?? '18:30';
}

/* Calls by phone (contactChannel 'phone'): when Mieliluotsi calls next, and a call at once on request. */
function CallCard({ dueNow, onCall }: { dueNow: boolean; onCall: () => void }) {
  const { client } = useClientUI();
  const check = client.checkIn;
  const when = dueNow ? `I'll call you today at ${callClock(check.callTime)}`
    : check.nextLabel ? `Next call ${check.nextLabel} at ${callClock(check.callTime)}` : 'I call on the agreed days';
  return (
    <section className="cx-call-card">
      <span className="cx-call-icon" aria-hidden="true"><PhoneIcon size={20} /></span>
      <div className="cx-call-text">
        <p className="cx-call-title">{check.needsBaseline ? 'First wellbeing call' : 'Wellbeing call'}</p>
        <p className="cx-fine">{when} · {check.frequencyText}</p>
      </div>
      <button type="button" className="cx-btn cx-btn-dark cx-btn-sm" onClick={onCall}><PhoneIcon size={14} /> Call now</button>
    </section>
  );
}

function BaselineCard() {
  const { view, run, busy } = useValituki();
  const { client } = useClientUI();
  const [mood, setMood] = useState<number | null>(null);
  const [anxiety, setAnxiety] = useState<number | null>(null);
  return (
    <section className="cx-baseline">
      <Scale5 name="How are you today?" value={mood} onChange={setMood} labels={view.meta.labels.moodScale} />
      <p className="cx-baseline-q">How much anxiety or nervousness have you felt today?</p>
      <Scale5 name="How much anxiety or nervousness?" value={anxiety} onChange={setAnxiety} labels={view.meta.labels.anxietyScale} />
      <button type="button" className="cx-btn cx-btn-dark cx-btn-block" disabled={busy || mood === null}
        onClick={() => mood !== null && run((s) => api.recordBaseline(s, client.id, { mood, anxiety }),
          () => 'Thank you! This becomes your own baseline – how you feel is compared with it, not with other people.')}>
        Save
      </button>
    </section>
  );
}

export default function HomeTab() {
  const { view, run, busy } = useValituki();
  const { client, openSheet, openTab, startTool, send, answerMood, doTask, phoneMode, startCall } = useClientUI();
  const [text, setText] = useState('');
  const today = view.meta.currentDate;
  const practice = client.practice;
  const guided = client.guided;
  const due = client.checkIn.due;
  const checkedInToday = client.progress.series.some((p) => p.date === today);
  const todayTasks = practice.tasks.filter((t) => t.dueDate && t.dueDate <= today);
  const nextTask = practice.tasks.find((t) => t.dueDate && t.dueDate > today);
  const activity = client.today;
  const pattern = client.memory.pending.find((i) => i.kind === 'pattern');
  const feedbackPending = client.matching.feedback.eligible && client.matching.feedback.given.length === 0;
  const featured = practice.tools.find((t) => t.id === 'thought_record' && t.allowed) ?? practice.tools.find((t) => t.allowed);
  // Right after the intake the first "How are you today?" sets the client's own baseline: mood and anxiety on one card.
  const needsBaseline = client.checkIn.needsBaseline;
  const askMood = needsBaseline || Boolean(due) || !checkedInToday;

  function submit(event: FormEvent) {
    event.preventDefault();
    const value = text.trim();
    if (!value) return;
    setText('');
    void send(value);
  }

  return (
    <div className="cx-screen cx-home">
      <h1 className="cx-greeting">Hi {client.firstName},<br />{askMood ? 'how are you today?' : "what's on your mind?"}</h1>

      {phoneMode ? <CallCard dueNow={askMood} onCall={startCall} /> : needsBaseline ? <BaselineCard /> : askMood && (
        <div className="cx-moods" role="group" aria-label="How are you today? Choose 1–5">
          {MOODS.map((m) => (
            <button key={m.value} type="button" className={`cx-mood cx-mood-${m.value}`} disabled={busy} onClick={() => answerMood(m.value)}>
              <span className="cx-mood-n">{m.value}</span>
              <span className="cx-mood-w">{view.meta.labels.moodScale[String(m.value)] ?? m.short}</span>
            </button>
          ))}
        </div>
      )}

      <form className="cx-ask" onSubmit={submit}>
        <label className="visually-hidden" htmlFor="home-ask">Write to Mieliluotsi</label>
        <textarea id="home-ask" rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="Write what's on your mind…"
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) submit(e); }} />
        <button type="submit" className="cx-send" aria-label="Send" disabled={busy || !text.trim()}><SendIcon size={18} /></button>
      </form>

      {/* A new observation waits for the client's decision: right below the writing box. */}
      {pattern && (
        <section className="cx-insight">
          <p className="cx-eyebrow"><SparkleIcon size={14} /> We noticed something</p>
          <p className="cx-insight-text">{pattern.text}</p>
          <p className="cx-fine">Based on: {(pattern.evidence.basis ?? []).filter(Boolean).join(' · ')}</p>
          <div className="cx-row">
            <button type="button" className="cx-btn cx-btn-dark cx-btn-sm" disabled={busy}
              onClick={() => run((s) => api.decideInsight(s, client.id, pattern.id, 'approve'), () => 'The observation was saved to your Therapy Fit Profile. You can change who may use it on the My data page.')}>
              <CheckIcon size={15} /> This feels right
            </button>
            <button type="button" className="cx-btn cx-btn-ghost cx-btn-sm" disabled={busy}
              onClick={() => run((s) => api.decideInsight(s, client.id, pattern.id, 'reject'), () => 'Thank you – the observation will not be used for anything.')}>
              <CrossIcon size={15} /> This doesn't describe my situation
            </button>
          </div>
        </section>
      )}

      {guided && (
        <button type="button" className="cx-continue" onClick={() => openTab('keskustelu')}>
          <span className="cx-bot-avatar" aria-hidden="true"><LogoMark /></span>
          <span className="cx-continue-text">
            <strong>Continue: {guided.title}</strong>
            <span>Question {guided.stepIndex}/{guided.stepCount} is waiting for your answer</span>
          </span>
          <ChevronRightIcon size={20} />
        </button>
      )}

      <section className="cx-section">
        <h2 className="cx-h2">Your day</h2>
        <ol className="cx-day">
          {due && (phoneMode ? (
            <DayItem icon={<PhoneIcon size={16} />} tag="Wellbeing call" title={`I'll call you at ${callClock(client.checkIn.callTime)}`}
              text="Mood, anxiety and a short thought exercise, by voice" action="Call now" busy={busy} onAction={startCall} />
          ) : (
            <DayItem icon={<ChatIcon size={16} />} tag={due.kind === 'extra' ? 'Extra check-in' : 'Check-in'} title="How are you today?"
              text="Mood and anxiety – under a minute" action={guided?.tool === 'checkin' ? 'Continue' : 'Start'} busy={busy}
              onAction={() => (guided?.tool === 'checkin' ? openTab('keskustelu') : startTool('checkin', {}, 'home'))} />
          ))}
          {todayTasks.map((task) => <TaskItem key={task.id} task={task} busy={busy} onAction={() => doTask(task.id)} />)}
          {activity && (
            <DayItem icon={<LeafIcon size={16} />} tag="Today's step" title={activity.title}
              text={activity.status === 'completed' ? 'Done – thank you!' : activity.status === 'skipped' ? 'Skipped' : `${activity.estimatedDuration} min · approved exercise`}
              action={activity.status === 'suggested' ? 'Open' : undefined} done={activity.status !== 'suggested'} busy={busy}
              onAction={() => openSheet({ type: 'activity', activityId: activity.id })} />
          )}
          {!due && todayTasks.length === 0 && !activity && (
            <li className="cx-day-empty">Nothing planned for today. {nextTask ? `Next: ${nextTask.title} (${dayWord(nextTask.dueLabel)}).` : 'You can start an exercise at any time.'}</li>
          )}
        </ol>
        {client.checkIn.nextLabel && !due && (
          <p className="cx-fine"><CalendarIcon size={13} /> {phoneMode
            ? `Next wellbeing call ${client.checkIn.nextLabel} at ${callClock(client.checkIn.callTime)}`
            : `Next check-in ${client.checkIn.nextLabel}`} · {client.checkIn.frequencyText}</p>
        )}
      </section>

      <ProgressTeaser />

      {feedbackPending && (
        <button type="button" className="cx-note cx-note-brand cx-note-btn" onClick={() => openTab('polku')}>
          <ChatIcon size={18} />
          <span><span className="cx-note-title">How does working with your therapist feel?</span>Short feedback – it does not change your therapist automatically.</span>
          <ChevronRightIcon size={18} />
        </button>
      )}

      <JourneyCard />

      {featured && !guided && (
        <button type="button" className={`cx-guided cx-tool-${featured.id}`} disabled={busy} onClick={() => startTool(featured.id, {}, 'home')}>
          <span className="cx-guided-icon" aria-hidden="true">{toolIcon(featured.id, 22)}</span>
          <span className="cx-guided-text">
            <span className="cx-guided-title">Start a guided exercise <span className="cx-guided-min">{featured.duration} min</span></span>
            <span className="cx-guided-sub">{featured.title}: {featured.description}</span>
          </span>
        </button>
      )}
    </div>
  );
}

function DayItem({ icon, tag, title, text, action, onAction, done = false, busy, secondary }: {
  icon: ReactNode; tag: string; title: string; text: string; action?: string; onAction?: () => void; done?: boolean; busy: boolean;
  secondary?: ReactNode;
}) {
  return (
    <li className={`cx-day-item ${done ? 'is-done' : ''}`}>
      <span className="cx-day-dot" aria-hidden="true">{done ? <CheckIcon size={13} /> : icon}</span>
      <div className="cx-day-card">
        <span className="cx-tag">{tag}</span>
        <p className="cx-day-title">{title}</p>
        <p className="cx-day-text">{text}</p>
        {(action || secondary) && (
          <div className="cx-row">
            {action && onAction && <button type="button" className="cx-btn cx-btn-dark cx-btn-sm" disabled={busy} onClick={onAction}>{action} <ArrowRightIcon size={14} /></button>}
            {secondary}
          </div>
        )}
      </div>
    </li>
  );
}

function TaskItem({ task, busy, onAction }: { task: PracticeTask; busy: boolean; onAction: () => void }) {
  const { run } = useValituki();
  const { client } = useClientUI();
  const icon = task.kind === 'exposure_step' ? <StairsIcon size={16} /> : task.kind === 'experiment' ? <FlaskIcon size={16} />
    : task.kind === 'homework' ? <StethoscopeIcon size={16} /> : <LeafIcon size={16} />;
  return (
    <DayItem icon={icon} tag={`${task.kindLabel}${task.overdue ? ' · overdue' : ''}`} title={task.title}
      text={task.kind === 'homework' ? `${task.assignedByLabel}: ${task.detail || 'between-session task'}` : task.detail || task.dueLabel}
      action={task.actionLabel} busy={busy} onAction={onAction}
      secondary={task.kind !== 'homework' ? (
        <button type="button" className="cx-btn cx-btn-ghost cx-btn-sm" disabled={busy}
          onClick={() => run((s) => api.clientTaskAction(s, client.id, task.id, 'later'), () => 'Moved to tomorrow.')}>Move to tomorrow</button>
      ) : undefined} />
  );
}

const PATH = [
  { key: 'wait', label: 'Waiting' },
  { key: 'therapist', label: 'Therapist' },
  { key: 'therapy', label: 'Therapy' },
  { key: 'after', label: 'Follow-up' },
];

export function pathIndex(phase: string): number {
  if (phase === 'AFTERCARE') return 3;
  if (phase === 'THERAPY_ACTIVE') return 2;
  if (['MATCH_PROPOSED', 'MATCH_ACCEPTED'].includes(phase)) return 1;
  return 0;
}

export function PathSteps({ phase }: { phase: string }) {
  const index = pathIndex(phase);
  return (
    <ol className="cx-path" aria-label="Care pathway">
      {PATH.map((step, i) => (
        <li key={step.key} className={i < index ? 'done' : i === index ? 'current' : ''} aria-current={i === index ? 'step' : undefined}>
          <span className="cx-path-dot" aria-hidden="true" />
          <span>{step.label}</span>
        </li>
      ))}
    </ol>
  );
}

function JourneyCard() {
  const { client, openTab } = useClientUI();
  const matching = client.matching;
  const shown = Math.min(matching.decision?.shownCount ?? 3, matching.candidates.length);
  const text = matching.stage === 'choose' ? `${plural(shown, 'suitable therapist is', 'suitable therapists are')} waiting for your choice`
    : matching.stage === 'booked' && matching.booking ? `First session ${matching.booking.startText} · ${matching.booking.therapist.name}`
      : matching.stage === 'therapy' && matching.booking ? `Therapy in progress · ${matching.booking.therapist.name}`
        : matching.stage === 'aftercare' ? 'Therapy has ended – follow-up continues with the maintenance plan'
          : matching.stage === 'on_hold' ? 'The search for a therapist continues after a professional review'
            : "We're looking for a therapist who suits your situation";
  return (
    <button type="button" className="cx-journey" onClick={() => openTab('polku')}>
      <span className="cx-journey-head">
        <span className="cx-eyebrow">Care pathway</span>
        {client.waiting.daysWaiting !== null && client.modeKey === 'waiting_support' && (
          <span className="cx-fine">{plural(client.waiting.daysWaiting, 'day', 'days')} since you sought help</span>
        )}
      </span>
      <PathSteps phase={client.phase} />
      <span className="cx-journey-text">{text} {matching.stage === 'choose' && <span className="cx-new">New</span>}</span>
    </button>
  );
}

function ProgressTeaser() {
  const { client, openTab } = useClientUI();
  const series = client.progress.series.filter((p) => p.mood !== null);
  const last = series[series.length - 1];
  const stats = client.practice.stats;
  return (
    <button type="button" className="cx-teaser" onClick={() => openTab('edistyminen')}>
      <span className="cx-teaser-head">
        <span className="cx-teaser-title">Your progress</span>
        <ChevronRightIcon size={18} />
      </span>
      <span className="cx-teaser-values">
        <span><i className="ma-swatch ma-mood" />Mood {last?.mood ?? '–'}/5</span>
        <span><i className="ma-swatch ma-anx" />Anxiety {last?.anxiety ?? '–'}/5</span>
      </span>
      <span className="cx-teaser-sub">
        {stats.thoughtRecords + stats.exposureAttempts + stats.experimentsDone > 0
          ? `${plural(stats.thoughtRecords, 'thought explored', 'thoughts explored')} · ${plural(stats.exposureAttempts, 'exposure step', 'exposure steps')} · ${plural(stats.experimentsDone, 'behavioural experiment', 'behavioural experiments')}`
          : last ? `Latest check-in ${fmtShort(last.date)}` : 'The chart fills in as you do check-ins'}
      </span>
    </button>
  );
}

export function toolIcon(tool: string, size = 18) {
  if (tool === 'exposure') return <StairsIcon size={size} />;
  if (tool === 'experiment') return <FlaskIcon size={size} />;
  if (tool === 'checkin') return <ChatIcon size={size} />;
  return <ThoughtIcon size={size} />;
}
