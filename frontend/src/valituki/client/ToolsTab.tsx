import { useState } from 'react';
import { api } from '../api';
import { useValituki } from '../context';
import { ClockIcon, LockIcon, SearchIcon, StethoscopeIcon } from '../icons';
import { normalizeText } from '../format';
import type { LadderRow, PracticeTask } from '../types';
import { useClientUI } from './ClientApp';
import { toolIcon } from './HomeTab';

/* "Exercises": the agreed tasks first, then the guided CBT tools and the approved self-care library. */

const TOPICS: { key: string; label: string; tools: string[]; activities: string[] }[] = [
  { key: 'all', label: 'All', tools: [], activities: [] },
  { key: 'thoughts', label: 'Thoughts', tools: ['thought_record', 'experiment'], activities: ['act-values'] },
  { key: 'exposure', label: 'Nervousness', tools: ['exposure', 'experiment'], activities: ['act-grounding', 'act-paced-breathing'] },
  { key: 'calm', label: 'Calming down', tools: [], activities: ['act-grounding', 'act-paced-breathing'] },
  { key: 'worry', label: 'Worries', tools: ['thought_record'], activities: ['act-worry-time', 'act-small-next-step'] },
  { key: 'sleep', label: 'Sleep', tools: [], activities: ['act-sleep-reflection', 'act-paced-breathing'] },
  { key: 'mood', label: 'Mood', tools: ['thought_record'], activities: ['act-activity-planning', 'act-values', 'act-support-network'] },
];

export default function ToolsTab() {
  const { view } = useValituki();
  const { client, openSheet, startTool } = useClientUI();
  const [query, setQuery] = useState('');
  const [topic, setTopic] = useState('all');
  const practice = client.practice;
  const selected = TOPICS.find((t) => t.key === topic) ?? TOPICS[0];
  const matches = (text: string) => !query.trim() || normalizeText(text).includes(normalizeText(query));
  const tools = practice.tools.filter((t) => (topic === 'all' || selected.tools.includes(t.id)) && matches(`${t.title} ${t.kind} ${t.description}`));
  const library = client.plan.library.filter((a) => (topic === 'all' || selected.activities.includes(a.id)) && matches(`${a.title} ${a.description}`));
  const mode = client.mode;

  return (
    <div className="cx-screen cx-tools">
      <h1 className="cx-title">Exercises</h1>
      <label className="cx-search">
        <SearchIcon size={18} />
        <span className="visually-hidden">Search exercises</span>
        <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search exercises…" />
      </label>
      <div className="cx-chips-scroll" role="group" aria-label="Topic">
        {TOPICS.map((t) => (
          <button key={t.key} type="button" className="cx-filter" aria-pressed={topic === t.key} onClick={() => setTopic(t.key)}>{t.label}</button>
        ))}
      </div>

      {practice.tasks.length > 0 && topic === 'all' && !query && (
        <section className="cx-section">
          <h2 className="cx-h2">Your tasks</h2>
          <div className="cx-stack">{practice.tasks.map((task) => <TaskCard key={task.id} task={task} />)}</div>
        </section>
      )}

      {mode.mode === 'therapy_support' && mode.homework && (
        <p className="cx-note cx-note-brand"><StethoscopeIcon size={17} />
          <span><span className="cx-note-title">Between-session task from your therapist: {mode.homework.title}</span>{mode.homework.note}</span></p>
      )}

      {tools.length > 0 && (
        <section className="cx-section">
          <h2 className="cx-h2">Guided exercises</h2>
          <p className="cx-fine">Tools from cognitive behavioural therapy (CBT). Mieliluotsi asks one question at a time – you can skip a question or stop at any time.</p>
          <div className="cx-tool-grid">
            {tools.map((tool) => (
              <button key={tool.id} type="button" className={`cx-tile cx-tool-${tool.id}`} disabled={!tool.allowed}
                onClick={() => startTool(tool.id, {}, 'library')}>
                <span className="cx-tile-top"><span className="cx-tag cx-tag-light">{tool.kind}</span><span className="cx-tile-min"><ClockIcon size={13} /> {tool.duration} min</span></span>
                <span className="cx-tile-icon" aria-hidden="true">{toolIcon(tool.id, 26)}</span>
                <span className="cx-tile-title">{tool.title}</span>
                <span className="cx-tile-text">{tool.allowed ? tool.description : <><LockIcon size={13} /> {tool.lockedReason}</>}</span>
                {tool.count > 0 && <span className="cx-tile-count">{tool.count === 1 ? 'Done once' : `Done ${tool.count} times`}</span>}
              </button>
            ))}
          </div>
        </section>
      )}

      {practice.ladders.length > 0 && (topic === 'all' || topic === 'exposure') && !query && (
        <section className="cx-section">
          <h2 className="cx-h2">Your exposure ladders</h2>
          {practice.ladders.map((ladder) => <LadderCard key={ladder.id} ladder={ladder} />)}
        </section>
      )}

      {library.length > 0 && (
        <section className="cx-section">
          <h2 className="cx-h2">Self-care exercises</h2>
          <ul className="cx-lib">
            {library.map((a) => (
              <li key={a.id}>
                <button type="button" className="cx-lib-item" disabled={!a.allowed} onClick={() => openSheet({ type: 'activity', activityId: a.id })}>
                  <span className="cx-lib-title">{a.title}</span>
                  <span className="cx-lib-text">{a.description}</span>
                  <span className="cx-lib-meta"><ClockIcon size={13} /> {a.estimatedDuration} min
                    {a.response?.latestRating ? ` · your rating ${a.response.latestRating}/5` : ''}{a.response?.helpful ? ' · helps you' : ''}
                    {!a.allowed && <> · <LockIcon size={12} /> {mode.mode === 'therapy_support' ? 'not enabled by your therapist' : 'not right now'}</>}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      {tools.length === 0 && library.length === 0 && <p className="cx-day-empty">No exercises match your search.</p>}
      <p className="cx-fine">{view.meta.cbt.approvalNote}</p>
    </div>
  );
}

export function TaskCard({ task }: { task: PracticeTask }) {
  const { view, run, busy } = useValituki();
  const { client, doTask } = useClientUI();
  return (
    <article className={`cx-task ${task.overdue ? 'is-overdue' : ''}`}>
      <div className="cx-task-top">
        <span className="cx-tag">{task.kindLabel}</span>
        <span className={`cx-due ${task.dueDate === view.meta.currentDate ? 'is-today' : ''}`}>{task.dueLabel}</span>
      </div>
      <p className="cx-task-title">{task.title}</p>
      {task.detail && <p className="cx-task-text">{task.detail}</p>}
      {task.assignedBy !== 'client' && <p className="cx-fine">From: {task.assignedByLabel}</p>}
      <div className="cx-row">
        <button type="button" className="cx-btn cx-btn-dark cx-btn-sm" disabled={busy} onClick={() => doTask(task.id)}>{task.actionLabel}</button>
        {task.kind !== 'homework' && (
          <>
            <button type="button" className="cx-btn cx-btn-ghost cx-btn-sm" disabled={busy}
              onClick={() => run((s) => api.clientTaskAction(s, client.id, task.id, 'later'), () => 'Moved to tomorrow.')}>Later</button>
            <button type="button" className="cx-btn cx-btn-ghost cx-btn-sm" disabled={busy}
              onClick={() => run((s) => api.clientTaskAction(s, client.id, task.id, 'skip'), () => 'Task skipped – that is always fine.')}>Skip</button>
          </>
        )}
      </div>
    </article>
  );
}

export function LadderCard({ ladder }: { ladder: LadderRow }) {
  const pct = ladder.progress.total ? Math.round((ladder.progress.done / ladder.progress.total) * 100) : 0;
  return (
    <article className="cx-ladder">
      <div className="cx-ladder-head">
        <p className="cx-ladder-goal">{ladder.goal}</p>
        <span className="cx-fine">{ladder.progress.done}/{ladder.progress.total} steps{ladder.status === 'completed' ? ' · complete' : ''}</span>
      </div>
      <span className="cx-progressbar" role="progressbar" aria-valuemin={0} aria-valuemax={ladder.progress.total} aria-valuenow={ladder.progress.done}
        aria-label="Ladder progress"><span style={{ width: `${pct}%` }} /></span>
      <ol className="cx-steps">
        {[...ladder.steps].reverse().map((step) => {
          const last = step.attempts[step.attempts.length - 1];
          return (
            <li key={step.id} className={`cx-step is-${step.status}`}>
              <span className="cx-step-mark" aria-hidden="true">{step.expected}</span>
              <span className="cx-step-text">{step.text}
                <span className="cx-step-meta">{step.status === 'done' ? 'Done' : step.status === 'doing' ? 'In progress' : 'Coming up'}
                  {last ? ` · anxiety ${last.peak ?? '–'} → ${last.after ?? '–'}` : ` · expected ${step.expected}/10`}</span>
              </span>
            </li>
          );
        })}
      </ol>
    </article>
  );
}
