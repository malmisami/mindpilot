import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import type { FormEvent } from 'react';
import { api } from '../api';
import { useValituki } from '../context';
import { LogoMark } from '../components/Logo';
import { fmtWeekday } from '../format';
import { InfoIcon, LifebuoyIcon, SendIcon, SparkleIcon } from '../icons';
import type { ChatMessage, ChatWidget, GuidedView, SummaryData, ValitukiView } from '../types';
import { Examples, SummaryCard, TrapHint, WidgetPanel, describeValue } from './ChatWidgets';
import { chatHurried, setChatRevealing, splitBubbles, subscribeChatHurry, typingTime } from './chatPace';
import { useClientUI } from './ClientApp';
import { toolIcon } from './HomeTab';

const TOOL_LABELS: Record<string, string> = { checkin: 'Do a check-in', thought_record: 'Exploring a thought', exposure: 'Exposure ladder',
  experiment: 'Behavioural experiment' };

/** One row of the conversation. Mieliluotsi's messages are split into short bubbles, a sentence each; the client's
    messages, the dates and the saved cards are shown whole. */
type Row =
  | { key: string; type: 'day'; label: string }
  | { key: string; type: 'bot'; text: string; message: ChatMessage | null; last: boolean }
  | { key: string; type: 'hint'; message: ChatMessage }
  | { key: string; type: 'other'; message: ChatMessage };

function buildRows(chat: ChatMessage[], greeting: string, today: string): Row[] {
  const rows: Row[] = [];
  const greet = () => splitBubbles(greeting).forEach((text, i, all) =>
    rows.push({ key: `greet-${i}`, type: 'bot', text, message: null, last: i === all.length - 1 }));
  if (chat.length === 0) {
    rows.push({ key: `day-${today}`, type: 'day', label: fmtWeekday(today) });
    greet();
  }
  chat.forEach((m, i) => {
    const day = m.createdAt.slice(0, 10);
    if (i === 0 || chat[i - 1].createdAt.slice(0, 10) !== day) rows.push({ key: `day-${day}`, type: 'day', label: fmtWeekday(day) });
    if (i === 0 && m.role === 'client') greet();  // a conversation the client started: the greeting stays above it
    if (m.role === 'client' || m.safetyLevel >= 3 || m.kind === 'summary' || m.kind === 'notice') {
      rows.push({ key: m.id, type: 'other', message: m });
      return;
    }
    const bubbles = splitBubbles(m.text);
    if (bubbles.length === 0) bubbles.push(m.text);
    // Thinking traps: Mieliluotsi's proposal comes just before the actual question, the message's last sentence.
    const hint = m.kind === 'question' && m.widget?.type === 'traps' && m.widget.suggested.length > 0;
    bubbles.forEach((text, j) => {
      const last = j === bubbles.length - 1;
      if (hint && last) rows.push({ key: `${m.id}-hint`, type: 'hint', message: m });
      rows.push({ key: `${m.id}-${j}`, type: 'bot', text, message: m, last });
    });
  });
  return rows;
}

const byBot = (row: Row | undefined) => row?.type === 'bot' || row?.type === 'hint';
/** Mieliluotsi's rows appear after the typing dots; the client's own message, a date and a safety message at once. */
const paced = (row: Row) => byBot(row) || (row.type === 'other' && row.message.role === 'assistant' && row.message.safetyLevel < 3);
const delayOf = (row: Row) => (row.type === 'bot' ? typingTime(row.text) : row.type === 'hint' ? 1000 : 700);

/** The conversation, like a chat with a person: Mieliluotsi answers in short bubbles, one at a time, and the client in
    their own words. A guided exercise shows its current question's answer controls above the composer once the question
    is on the screen; free text always works too (it answers a text question). */
export default function ChatTab() {
  const { view, run, busy } = useValituki();
  const { client, openSheet, send, pending, withPending } = useClientUI();
  const guided = client.guided;
  const widget = guided?.widget ?? null;
  const [text, setText] = useState('');
  const logRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const questionId = guided?.questionId ?? null;

  // What was already there appears at once; a new reply bubble by bubble. Another conversation (a demo reset, another
  // client), a burst of messages or a hurried demo is shown at once.
  const greeting = `Hi ${client.firstName}! What's on your mind today?`;
  const rows = useMemo(() => buildRows(client.chat, greeting, view.meta.currentDate), [client.chat, greeting, view.meta.currentDate]);
  const hurried = useSyncExternalStore(subscribeChatHurry, chatHurried);
  const [shown, setShown] = useState(rows.length);
  const [base, setBase] = useState(rows[0]?.key);
  if (base !== rows[0]?.key || shown > rows.length || (shown < rows.length && (hurried || rows.length - shown > 12))) {
    setBase(rows[0]?.key);
    setShown(rows.length);
  }
  let visible = Math.min(shown, rows.length);
  while (visible < rows.length && !paced(rows[visible])) visible += 1;
  const settled = visible >= rows.length;
  const delay = settled ? 0 : delayOf(rows[visible]);
  useEffect(() => {
    if (settled) return undefined;
    const timer = window.setTimeout(() => setShown(visible + 1), delay);
    return () => window.clearTimeout(timer);
  }, [settled, visible, delay]);
  useEffect(() => { setChatRevealing(!settled); }, [settled]);
  useEffect(() => () => setChatRevealing(false), []);

  const scrolled = useRef(false);
  useEffect(() => {
    const log = logRef.current;
    if (!log) return;
    log.scrollTo({ top: log.scrollHeight, behavior: scrolled.current ? 'smooth' : 'auto' });  // the history opens at its end
    scrolled.current = true;
  }, [visible, busy, pending, settled]);

  // Each new question empties the composer at once – in demo mode (not Claude) a text question's scripted answer is typed
  // in it once the question is on the screen: press send or edit it first.
  const demoMode = view.meta.ai.configuredMode === 'DEMO_AI_MODE';
  const demoText = demoMode && widget?.type === 'text' && typeof guided?.demoAnswer === 'string' ? guided.demoAnswer : '';
  // A multiple choice (what changed, emotions) is answered with the send button: the picked options are kept per question.
  const [picked, setPicked] = useState<{ question: string | null; values: string[] }>({ question: null, values: [] });
  const picking = widget?.type === 'multi';
  const multi = picking && picked.question === questionId ? picked.values : [];
  const draftKey = `${questionId ?? ''}|${demoMode}`;
  const [draft, setDraft] = useState<{ key: string | null; filled: boolean }>({ key: null, filled: false });
  if (draft.key !== draftKey) {
    setDraft({ key: draftKey, filled: false });
    setText('');
  } else if (settled && !draft.filled) {
    setDraft({ key: draftKey, filled: true });
    if (demoText && !text) setText(demoText);
  }

  async function answerWith(current: GuidedView, value: unknown, skip = false): Promise<ValitukiView | null> {
    let latest: ValitukiView | null = null;
    await withPending(skip ? '' : describeValue(value, current.widget), () => run(async (s) => {
      const response = await api.answerPractice(s, client.id, { sessionId: current.id, stepKey: current.stepKey, value, skip });
      latest = response.view;
      return response;
    }));
    return latest;
  }

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    const value = text.trim();
    if (busy || !settled) return;
    if (!value && guided && picking && multi.length > 0) {
      await answerWith(guided, multi);
      return;
    }
    if (!value) return;
    setText('');
    if (!(await send(value))) setText(value);  // not sent: keep what was written
  }

  const progress = guided ? Math.round(((guided.stepIndex - 1) / Math.max(1, guided.stepCount)) * 100) : 0;
  const tools = client.practice.allowedTools.filter((t) => TOOL_LABELS[t]);
  const asking = settled && guided ? widget : null;  // the answer controls wait until the question is on the screen

  return (
    <div className="cx-chat">
      <div className="cx-chat-head">
        <span className="cx-bot-avatar" aria-hidden="true"><LogoMark size={34} /></span>
        <div className="cx-chat-who">
          <p className="cx-chat-name">Mieliluotsi</p>
          <p className="cx-chat-sub">{guided ? `${guided.title} · you can stop at any time` : 'AI-assisted support – not a therapist or an emergency service'}</p>
        </div>
        {guided && (
          <button type="button" className="cx-stop" disabled={busy}
            onClick={() => run((s) => api.stopPractice(s, client.id, guided.id))}>Stop</button>
        )}
        {guided && <span className="cx-chat-progress" aria-hidden="true"><span style={{ width: `${progress}%` }} /></span>}
      </div>

      <div className="cx-chat-log" ref={logRef} aria-live="polite">
        <p className="cx-chat-disclaimer"><InfoIcon size={14} /> Mieliluotsi is not a therapist, and the chat is not monitored all the time. In an emergency, call 112.</p>
        {rows.slice(0, visible).map((row, i) => (
          <ChatRow key={row.key} row={row} cont={byBot(row) && byBot(rows[i - 1])} busy={busy}
            onChoose={(message, option) => run((s) => api.chooseOffer(s, client.id, message.id, option))}
            onHelp={() => openSheet({ type: 'help' })} />
        ))}
        {pending && <div className="cx-msg-me is-pending"><p>{pending}</p></div>}
        {(busy || !settled) && (
          <div className={`cx-typing${!pending && byBot(rows[visible - 1]) ? ' is-cont' : ''}`} aria-label="Mieliluotsi is typing">
            <i /><i /><i />
          </div>
        )}
      </div>

      <div className="cx-dock">
        <div className="cx-dock-top">
          {guided && asking && asking.type !== 'text' && (
            <WidgetPanel key={questionId ?? 'none'} widget={asking} busy={busy} selected={multi}
              onSelect={(values) => setPicked({ question: questionId, values })}
              onAnswer={(value) => answerWith(guided, value)} onSkip={() => answerWith(guided, null, true)} />
          )}
          {asking?.type === 'text' && (
            <Examples widget={asking} busy={busy} onUse={(example) => { setText(example); inputRef.current?.focus(); }} />
          )}
          {!guided && (
            <div className="cx-quick" role="group" aria-label="Start a guided exercise">
              {tools.map((tool) => (
                <button key={tool} type="button" className="cx-quick-chip" disabled={busy}
                  onClick={() => run((s) => api.startPractice(s, client.id, tool, {}, 'chat'))}>
                  {toolIcon(tool, 15)} {TOOL_LABELS[tool]}
                </button>
              ))}
            </div>
          )}
        </div>
        <form className="cx-composer" onSubmit={submit}>
          <label className="visually-hidden" htmlFor="chat-input">{guided?.questionText ?? 'Message to Mieliluotsi'}</label>
          <textarea id="chat-input" ref={inputRef} rows={Math.min(4, Math.max(1, Math.ceil(text.length / 34)))} value={text} onChange={(e) => setText(e.target.value)}
            placeholder={placeholder(asking, guided !== null, multi.length)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void submit(); } }}  />
          <button type="submit" className="cx-send" aria-label="Send" disabled={busy || !settled || (!text.trim() && multi.length === 0)}><SendIcon size={18} /></button>
        </form>
        {guided && asking?.type === 'text' && asking.skippable && (
          <button type="button" className="cw-skip cw-skip-center" disabled={busy} onClick={() => answerWith(guided, null, true)}>
            {asking.skipLabel || 'Skip question'}
          </button>
        )}
      </div>
    </div>
  );
}

function placeholder(widget: ChatWidget | null, guided: boolean, picked: number): string {
  if (widget?.type === 'text') return widget.placeholder || 'Write your answer…';
  if (widget?.type === 'multi') return picked ? `${picked} selected – send` : 'Choose one or more and send…';
  return guided ? 'Answer by choosing – or write…' : 'Write a message…';
}

function ChatRow({ row, cont, busy, onChoose, onHelp }: {
  row: Row; cont: boolean; busy: boolean; onChoose: (message: ChatMessage, option: string) => void; onHelp: () => void;
}) {
  if (row.type === 'day') return <p className="cx-day-sep"><span>{row.label}</span></p>;
  if (row.type === 'hint') return row.message.widget ? <TrapHint widget={row.message.widget} cont={cont} /> : null;
  if (row.type === 'other') return <Message message={row.message} onHelp={onHelp} />;
  const m = row.message;
  const offer = row.last && m && m.kind === 'offer' && m.actionable && m.widget ? { message: m, options: m.widget.options } : null;
  return (
    <>
      <div className={`cx-bubble${cont ? ' is-cont' : ''}`}><p>{row.text}</p></div>
      {offer && (
        <div className="cx-offer" role="group" aria-label="Options">
          {offer.options.map((o, i) => (
            <button key={o.value} type="button" className={`cx-btn cx-btn-sm ${i === 0 ? 'cx-btn-dark' : 'cx-btn-ghost'}`} disabled={busy}
              onClick={() => onChoose(offer.message, o.value)}>{o.label}</button>
          ))}
        </div>
      )}
      {row.last && m?.textSource === 'live' && <span className="cx-source"><SparkleIcon size={11} /> Worded by AI</span>}
      {row.last && m?.textSource === 'fallback' && <span className="cx-source">Ready-made text – the AI reply was not used</span>}
    </>
  );
}

/** The client's own message, a safety message, a saved exercise card or a notice – each shown whole. */
function Message({ message: m, onHelp }: { message: ChatMessage; onHelp: () => void }) {
  if (m.role === 'client') {
    return (
      <div className={`cx-msg-me ${m.kind === 'skip' ? 'is-skip' : ''}`}>
        <p>{m.text}</p>
      </div>
    );
  }
  if (m.safetyLevel >= 3) {
    return (
      <div className="cx-msg-safety" role="alert">
        <LifebuoyIcon size={18} />
        <div>
          <p>{m.text}</p>
          <button type="button" className="cx-btn cx-btn-rose cx-btn-sm" onClick={onHelp}>Help now</button>
        </div>
      </div>
    );
  }
  if (m.kind === 'summary' && m.widget) return <SummaryCard data={m.widget.data as unknown as SummaryData} />;
  return <p className="cx-msg-notice">{m.text}</p>;
}
