import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { api } from '../api';
import type { ViewScope } from '../api';
import { useValituki } from '../context';
import { daysBetween } from '../format';
import { LogoMark } from '../components/Logo';
import { MicIcon, MicOffIcon, PhoneIcon, SendIcon, SpeakerIcon, SpeakerOffIcon } from '../icons';
import type { ChatMessage, ClientView, FeelingProposal, GuidedView, Mutation, ValitukiView } from '../types';
import { useClientUI } from './ClientApp';

/* WELLBEING CALL – when the client chose calls (contactChannel 'phone'), Mieliluotsi calls on the check-in days: it asks
   how they are and does a short thought exercise by speech. Mood and anxiety are a conversation, not a form: the client
   describes them in their own words, Mieliluotsi proposes where that falls on the 1–5 scale and asks whether it matches,
   and the number the client settles on is what is saved. The call runs the same guided tools as the chat (check-in,
   "Exploring a thought") through the same API, so the answers, the safety rules and the AI reflections are the same – only
   the medium is the voice. The browser speaks (speechSynthesis, the most natural English voice it has) and listens
   (SpeechRecognition, en-GB) where it can; the answer buttons and the text field work everywhere. */

type Phase = 'ringing' | 'live' | 'ended';
type Scale = 'mood' | 'anxiety';
type Line = { id: number; who: 'luotsi' | 'me'; text: string };
type Ask =
  | { kind: 'yesno' }
  | { kind: 'scale'; min: number; max: number; labels: string[] }
  | { kind: 'text'; skippable: boolean; placeholder: string }
  // How they feel in their own words – or a number straight away.
  | { kind: 'describe'; labels: string[] }
  // Mieliluotsi's proposal: yes keeps it, a number corrects it.
  | { kind: 'confirm'; value: number; labels: string[] }
  | { kind: 'choices'; options: { value: string; label: string }[]; skippable: boolean };
type Answer = { yes: boolean } | { value: number | string } | { skip: true } | { hangup: true };

// Kept short by speech: the steps a call skips (they are skippable in the chat too).
const CALL_SKIPS: Record<string, string[]> = {
  checkin: ['changes', 'note'],
  thought_record: ['emotions', 'behaviour', 'traps', 'evidenceFor'],
};
// The scale words come from the backend (view.meta.labels.moodScale / anxietyScale); these are only the fallback.
const MOOD_LABELS = ['Very bad', 'Bad', 'Okay', 'Good', 'Very good'];
const ANXIETY_LABELS = ['Not at all', 'A little', 'Somewhat', 'A lot', 'Very much'];
// Spoken numbers in English and in Finnish (the client may answer in either).
const NUMBER_WORDS: Record<string, number> = {
  zero: 0, nought: 0, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10,
  nolla: 0, yksi: 1, yks: 1, ykkönen: 1, kaksi: 2, kaks: 2, kakkonen: 2, kolme: 3, kolmonen: 3, neljä: 4, nelonen: 4, viisi: 5,
  viis: 5, vitonen: 5, kuusi: 6, kuus: 6, seitsemän: 7, seittemän: 7, kahdeksan: 8, kaheksan: 8, yhdeksän: 9, yheksän: 9,
  kymmenen: 10, kymppi: 10,
};
// What speech recognition often writes for a lone English number word – trusted only when it is the whole answer.
const NUMBER_SOUNDALIKES: Record<string, number> = { won: 1, to: 2, too: 2, for: 4, fore: 4, sex: 6, ate: 8 };

function parseNumber(text: string, min: number, max: number): number | null {
  const digits = text.match(/\d+/);
  const words = text.toLowerCase().split(/[^a-zåäö]+/).filter(Boolean);
  const candidates = digits ? [Number(digits[0])]
    : words.length === 1 && NUMBER_SOUNDALIKES[words[0]] !== undefined ? [NUMBER_SOUNDALIKES[words[0]]]
      : words.map((w) => NUMBER_WORDS[w]).filter((n) => n !== undefined);
  return candidates.find((n) => n >= min && n <= max) ?? null;
}

/** One of `alternatives` as a whole word or phrase – also when it ends in ä or ö, which \b would not see as a letter. */
function wordRe(alternatives: string, atStart = false): RegExp {
  return new RegExp(`${atStart ? '^' : '(?<!\\p{L})'}(${alternatives})(?!\\p{L})`, 'u');
}
const NO_FI = [wordRe('ei|en|nyt ei|myöhemmin', true), wordRe('ei nyt|myöhemmin|en halua')];
const YES_FI = wordRe('kyllä|joo|juu|jep|okei|ok|sopii|voidaan|tehdään|mennään|hyvä|selvä|toki');
const YES_FI_PLAIN = wordRe('kyllä|joo|juu|okei|sopii|selvä|toki');  // "no joo", "no kyllä" is a Finnish yes
const YES_EN_PHRASE = wordRe('no problem|no worries|not busy');
const NO_EN = [wordRe('no|nope|nah|not now|not really|later', true),
  wordRe("not now|not right now|not today|not a good time|not good|bad time|later|don't want|do not want|can't|cannot|busy|no thanks")];
const YES_EN = wordRe("yes|yeah|yep|yup|sure|okay|ok|fine|alright|all right|go ahead|let's|lets|of course|certainly|good|great|why not");

/** A spoken or typed yes or no, in English or in Finnish; a "not now" or "later" is a no. */
function parseYesNo(text: string): boolean | null {
  const t = text.toLowerCase().trim();
  if (NO_FI.some((re) => re.test(t))) return false;
  if (YES_EN_PHRASE.test(t) || YES_FI_PLAIN.test(t)) return true;
  if (NO_EN.some((re) => re.test(t))) return false;
  if (YES_FI.test(t) || YES_EN.test(t)) return true;
  return null;
}

/** The option the client named: the whole label, or a word that starts like the label's first real word ("stop" for
    "I'll stop here"; short words such as "I", "a" or "the" are passed over). */
function matchOption<T extends { label: string }>(text: string, options: T[]): T | undefined {
  const said = text.toLowerCase();
  const words = said.split(/[^\p{L}\p{N}'-]+/u).filter(Boolean);
  return options.find((o) => {
    const label = o.label.toLowerCase();
    if (said.includes(label) || said.includes(label.replace(/-/g, ' '))) return true;
    const parts = label.split(/[ ,–]/).filter(Boolean);
    const key = parts.find((w) => w.replace(/[^\p{L}]/gu, '').length >= 4) ?? parts[0];
    return Boolean(key) && words.some((w) => w.startsWith(key));
  });
}

function hhmm(time: string | null): string {
  return time ?? '18:30';
}

/* The browser's speech recognition, where it has one (Chrome, Edge, Safari). */
interface RecognitionEvent { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }
interface Recognition {
  lang: string; interimResults: boolean; continuous: boolean; maxAlternatives: number;
  start(): void; abort(): void;
  onresult: ((event: RecognitionEvent) => void) | null; onend: (() => void) | null; onerror: (() => void) | null;
}
type RecognitionCtor = new () => Recognition;
const isNatural = (v: SpeechSynthesisVoice | null) => Boolean(v && /natural|neural|online|premium|enhanced|siri/i.test(v.name));

/** The most natural-sounding English voice the browser has, British English first: a neural one (Edge: Microsoft
    Sonia/Libby/Ryan Online (Natural)), then a downloaded premium or enhanced voice (macOS: Serena, Daniel, Kate), then
    Google's (Chrome: Google UK English), then any other English voice (en-US, en-IE, en-AU…) – the macOS Eloquence and
    novelty voices last. */
function bestEnglishVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  const lang = (v: SpeechSynthesisVoice) => v.lang.toLowerCase().replace('_', '-');
  const english = voices.filter((v) => lang(v).startsWith('en'));
  const score = (v: SpeechSynthesisVoice) => (/natural|neural/i.test(v.name) ? 40 : 0) + (/online/i.test(v.name) ? 10 : 0)
    + (/premium/i.test(v.name) ? 30 : 0) + (/enhanced|siri/i.test(v.name) ? 20 : 0) + (/google/i.test(v.name) ? 15 : 0)
    + (lang(v) === 'en-gb' ? 25 : 0)
    + (/sonia|libby|ryan|maisie|thomas|serena|daniel|kate|arthur|martha|google uk/i.test(v.name) ? 5 : 0)
    // macOS's Eloquence voices (Eddy, Flo, Grandma…) come first in the list but sound the most synthetic; its novelty
    // voices (Albert, Bubbles, Zarvox…) are not meant for talking at all.
    - (/eddy|flo|grandma|grandpa|reed|rocko|sandy|shelley/i.test(v.name) ? 20 : 0)
    - (/albert|bad news|bahh|bells|boing|bubbles|cellos|good news|jester|organ|superstar|trinoids|whisper|wobble|zarvox|junior|ralph|fred|kathy/i
      .test(v.name) ? 60 : 0);
  return [...english].sort((a, b) => score(b) - score(a))[0] ?? null;
}

const speechWindow = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
const RecognitionImpl: RecognitionCtor | undefined = speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;

export default function PhoneCall({ onClose }: { onClose: () => void }) {
  const { view, run } = useValituki();
  const { client } = useClientUI();
  const [phase, setPhase] = useState<Phase>('ringing');
  const [lines, setLines] = useState<Line[]>([]);
  const [asking, setAsking] = useState<Ask | null>(null);
  const [speaking, setSpeaking] = useState(false);
  const [listening, setListening] = useState(false);
  const [heard, setHeard] = useState('');
  const [hint, setHint] = useState('');
  const [typed, setTyped] = useState('');
  const [speakerOn, setSpeakerOn] = useState(true);
  const [micOn, setMicOn] = useState(Boolean(RecognitionImpl));
  const [hasVoice, setHasVoice] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [outcome, setOutcome] = useState('');

  const latest = useRef<ValitukiView>(view);
  latest.current = view;
  const ended = useRef(false);
  const resolver = useRef<((answer: Answer) => void) | null>(null);
  const askingRef = useRef<Ask | null>(null);
  const seen = useRef(new Set<string>());
  const voice = useRef<SpeechSynthesisVoice | null>(null);
  const recognition = useRef<Recognition | null>(null);
  const speakerRef = useRef(speakerOn);
  speakerRef.current = speakerOn;
  const micRef = useRef(micOn);
  micRef.current = micOn;
  const lineId = useRef(0);
  // An answer given while Mieliluotsi still speaks cuts the speech short.
  const interrupted = useRef(false);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const id = client.id;

  // An English voice, when the browser has one – without it the call is shown as text only.
  useEffect(() => {
    if (!('speechSynthesis' in window)) return undefined;
    const pick = () => {
      const voices = window.speechSynthesis.getVoices();
      voice.current = bestEnglishVoice(voices);
      setHasVoice(Boolean(voice.current));
    };
    pick();
    window.speechSynthesis.addEventListener('voiceschanged', pick);
    return () => window.speechSynthesis.removeEventListener('voiceschanged', pick);
  }, []);

  // The call's clock, and everything stops when the screen closes.
  useEffect(() => {
    if (phase !== 'live') return undefined;
    const timer = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(timer);
  }, [phase]);
  // (React's development mode mounts twice: the first cleanup must not end the call for good.)
  useEffect(() => {
    ended.current = false;
    return () => hangUpQuietly();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight, behavior: 'smooth' }); }, [lines, asking, heard]);

  function addLine(who: Line['who'], text: string) {
    lineId.current += 1;
    const next = { id: lineId.current, who, text };
    setLines((all) => [...all, next]);
  }

  function pause(ms: number) {
    return new Promise<void>((resolve) => window.setTimeout(resolve, ms));
  }

  function speak(text: string): Promise<void> {
    if (!speakerRef.current || !voice.current || !('speechSynthesis' in window)) return pause(Math.min(1400, 300 + text.length * 12));
    return new Promise((resolve) => {
      // Sentence by sentence: a basic voice reads a long line in one breath, a short breath between sentences sounds
      // more like talking.
      const sentences = text.match(/[^.!?…]+[.!?…]*["”]?\s*/g)?.map((t) => t.trim()).filter(Boolean) ?? [text];
      let left = sentences.length;
      const done = () => resolve();
      sentences.forEach((sentence) => {
        const utterance = new SpeechSynthesisUtterance(sentence);
        utterance.voice = voice.current;
        utterance.lang = voice.current?.lang ?? 'en-GB';
        // Natural (neural) voices sound best at their own pace; a basic voice is calmer a little slower.
        utterance.rate = isNatural(voice.current) ? 1 : 0.94;
        utterance.pitch = 1;
        const next = () => { left -= 1; if (left <= 0) done(); };
        utterance.onend = next;
        utterance.onerror = done;
        window.speechSynthesis.speak(utterance);
      });
      window.setTimeout(done, 25000);
    });
  }

  /* The lines go to the transcript at once – the question is on the screen before the answer – and are then spoken in
     turn, unless an answer cuts the speech short. */
  async function say(text: string | string[]) {
    interrupted.current = false;
    const all = (Array.isArray(text) ? text : [text]).map((l) => l.trim()).filter(Boolean);
    if (ended.current) return;
    all.forEach((line) => addLine('luotsi', line));
    for (const line of all) {
      if (ended.current || interrupted.current) break;
      setSpeaking(true);
      await speak(line);
      setSpeaking(false);
    }
  }

  function stopListening() {
    recognition.current?.abort();
    recognition.current = null;
    setListening(false);
  }

  function listen() {
    if (!RecognitionImpl || !micRef.current || ended.current || !askingRef.current) return;
    stopListening();
    const rec = new RecognitionImpl();
    rec.lang = 'en-GB';
    rec.interimResults = true;
    rec.continuous = false;
    rec.maxAlternatives = 1;
    rec.onresult = (event) => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        if (result.isFinal) {
          setHeard('');
          onSpeech(result[0].transcript.trim());
          return;
        }
        interim += result[0].transcript;
      }
      setHeard(interim);
    };
    rec.onend = () => { if (recognition.current === rec) { recognition.current = null; setListening(false); } };
    rec.onerror = () => { if (recognition.current === rec) { recognition.current = null; setListening(false); } };
    recognition.current = rec;
    setListening(true);
    try {
      rec.start();
    } catch {
      setListening(false);
    }
  }

  function ask(spec: Ask, listenNow = true): Promise<Answer> {
    askingRef.current = spec;
    setAsking(spec);
    setHint('');
    if (listenNow) listen();
    return new Promise((resolve) => { resolver.current = resolve; });
  }

  /* Say the lines and ask: the answers are on the screen at once, the microphone opens when the speech ends. */
  async function question(text: string | string[], spec: Ask): Promise<Answer> {
    const answer = ask(spec, false);
    await say(text);
    if (askingRef.current === spec) listen();
    return answer;
  }

  function give(answer: Answer, display: string | null) {
    if (!resolver.current) return;
    interrupted.current = true;
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    setSpeaking(false);
    stopListening();
    askingRef.current = null;
    setAsking(null);
    setTyped('');
    if (display) addLine('me', display);
    const resolve = resolver.current;
    resolver.current = null;
    resolve(answer);
  }

  // What the client said, for the question on the screen.
  function onSpeech(text: string) {
    const spec = askingRef.current;
    if (!spec || !text) return;
    if (spec.kind === 'yesno') {
      const yes = parseYesNo(text);
      if (yes !== null) return give({ yes }, text);
    } else if (spec.kind === 'scale') {
      const n = parseNumber(text, spec.min, spec.max);
      if (n !== null) return give({ value: n }, text);
    } else if (spec.kind === 'describe' && text.split(/\s+/).length <= 3 && parseNumber(text, 1, 5) !== null) {
      // Just a number ("three", "a four") is an answer already – no need to propose one.
      return give({ value: parseNumber(text, 1, 5) as number }, text);
    } else if (spec.kind === 'confirm') {
      // "No, more like a two" corrects; "yes, that's right" keeps the proposal; a bare "no" asks for their own number.
      const n = parseNumber(text, 1, 5);
      if (n !== null) return give({ value: n }, text);
      const yes = parseYesNo(text);
      if (yes !== null) return give(yes ? { value: spec.value } : { yes: false }, text);
    } else if (spec.kind === 'choices') {
      const option = matchOption(text, spec.options);
      if (option) return give({ value: option.value }, option.label);
    } else {
      return give({ value: text }, text);
    }
    setHint(`I heard: “${text}”. Say it again or choose below.`);
    window.setTimeout(listen, 400);
  }

  async function mutate(call: (s: ViewScope) => Promise<Mutation<unknown>>): Promise<ValitukiView | null> {
    let fresh: ValitukiView | null = null;
    await run(async (s) => {
      const response = await call(s);
      fresh = response.view;
      return response;
    });
    return fresh;
  }

  async function mutateWith<T>(call: (s: ViewScope) => Promise<Mutation<T>>): Promise<Mutation<T> | null> {
    let fresh: Mutation<T> | null = null;
    await run(async (s) => {
      fresh = await call(s);
      return fresh;
    });
    return fresh;
  }

  const scaleRange = (labels: string[]) => `where one is ${labels[0].toLowerCase()} and five is ${labels[4].toLowerCase()}`;

  async function ownNumber(lines: string[], labels: string[]): Promise<number | null> {
    const picked = await question(lines, { kind: 'scale', min: 1, max: 5, labels });
    return !ended.current && 'value' in picked ? Number(picked.value) : null;
  }

  /* Mood or anxiety as a conversation: the client says how it is, Mieliluotsi reflects it, proposes a level on the 1–5
     scale and asks whether it matches. Their own words are checked by the safety rules and are not stored. */
  async function feeling(scale: Scale, open: string[], labels: string[]): Promise<number | null> {
    const described = await question(open, { kind: 'describe', labels });
    if (ended.current || !('value' in described)) return null;
    if (typeof described.value === 'number') return described.value;
    const out = await mutateWith<FeelingProposal>((s) => api.callFeeling(s, id, scale, String(described.value)));
    if (ended.current) return null;
    if (!out) return ownNumber([`Where would you put it on a scale from one to five, ${scaleRange(labels)}?`], labels);
    if (out.result.safety.level >= 3) {
      await say(out.view.client ? spoken(unseen(out.view.client), null) : []);
      finish('The call was stopped for safety reasons. In an emergency, call 112.');
      return null;
    }
    const reflection = out.result.reflection ?? '';
    const value = out.result.value;
    if (!value) return ownNumber([reflection, `Where would you put it on a scale from one to five, ${scaleRange(labels)}?`], labels);
    const proposal = await question([reflection, `On a scale from one to five, ${scaleRange(labels)}, I'd put that at about `
      + `${value} – ${labels[value - 1].toLowerCase()}. Does that match how you see it?`], { kind: 'confirm', value, labels });
    if (ended.current) return null;
    if ('value' in proposal) return Number(proposal.value);
    if ('yes' in proposal && !proposal.yes) return ownNumber(['What number would you give it yourself, from one to five?'], labels);
    return null;
  }

  // Mieliluotsi's new messages in the chat since the call started – what it says now.
  function unseen(c: ClientView): ChatMessage[] {
    const fresh = c.chat.filter((m) => !seen.current.has(m.id));
    fresh.forEach((m) => seen.current.add(m.id));
    return fresh;
  }

  function spoken(messages: ChatMessage[], skipQuestionOf: string | null): string[] {
    return messages.filter((m) => m.role === 'assistant' && ['text', 'question', 'notice'].includes(m.kind) && m.text
      && !(m.kind === 'question' && m.stepKey === skipQuestionOf)).map((m) => m.text);
  }

  function askFor(g: GuidedView): Ask | null {
    const widget = g.widget;
    if (!widget) return null;
    if (widget.type === 'scale5') return { kind: 'scale', min: 1, max: 5, labels: widget.options.map((o) => o.label) };
    if (widget.type === 'scale') return { kind: 'scale', min: widget.min, max: widget.max, labels: [] };
    if (widget.type === 'text') return { kind: 'text', skippable: widget.skippable, placeholder: widget.placeholder };
    if (widget.type === 'choices' || widget.type === 'multi' || widget.type === 'traps') {
      return { kind: 'choices', options: widget.options.map((o) => ({ value: o.value, label: o.label })), skippable: widget.skippable };
    }
    return null;
  }

  /* One guided tool by speech: say what Mieliluotsi says, ask the step, answer it through the same API as the chat. */
  async function guided(tool: string): Promise<'done' | 'stop'> {
    let current = await mutate((s) => api.startPractice(s, id, tool, {}, 'call'));
    if (!current) return 'done';
    while (current && !ended.current) {
      const c: ClientView | null = current.client;
      if (!c) return 'stop';
      const fresh = unseen(c);
      if (c.safety.lockActive || fresh.some((m) => m.safetyLevel >= 3)) {
        await say(spoken(fresh, null));
        finish('The call was stopped for safety reasons. In an emergency, call 112.');
        return 'stop';
      }
      const g = c.guided;
      if (g && g.tool !== tool) {
        // The exercise led on to another (e.g. a behavioural experiment): it is continued in the app, not on this call.
        await say([...spoken(fresh, g.stepKey).filter((line) => line !== g.questionText),
          `You can continue the exercise “${g.title}” in the app's Chat whenever it suits you.`]);
        return 'done';
      }
      if (!g || !g.stepKey) {
        await say(spoken(fresh, null));
        return 'done';
      }
      const skip = Boolean(CALL_SKIPS[tool]?.includes(g.stepKey) && g.widget?.skippable);
      const toSay = spoken(fresh, skip ? g.stepKey : null);
      if (!skip && !fresh.some((m) => m.kind === 'question' && m.stepKey === g.stepKey) && g.questionText) toSay.push(g.questionText);
      let answer: Answer = { skip: true };
      if (skip) {
        await say(toSay);
      } else if (tool === 'checkin' && (g.stepKey === 'mood' || g.stepKey === 'anxiety') && g.widget?.type === 'scale5') {
        const value = await feeling(g.stepKey, toSay, g.widget.options.map((o) => o.label));
        if (value === null) return 'stop';
        answer = { value };
      } else {
        const spec = askFor(g);
        if (!spec) return 'done';
        answer = await question(toSay, spec);
      }
      if (ended.current || 'hangup' in answer) return 'stop';
      const body = 'skip' in answer ? { sessionId: g.id, stepKey: g.stepKey, skip: true }
        : { sessionId: g.id, stepKey: g.stepKey, value: 'value' in answer ? answer.value : null };
      const next = await mutate((s) => api.answerPractice(s, id, body));
      if (next) current = next;
      else await say("Sorry, I didn't catch that. Could you say it again?");
    }
    return 'stop';
  }

  async function script() {
    const ready = await question(`Hi ${client.firstName}, this is Mieliluotsi. Is now a good time to talk for a couple of minutes?`,
      { kind: 'yesno' });
    if (ended.current || 'hangup' in ready) return;
    if ('yes' in ready && !ready.yes) {
      await say('All right, no problem. You can ask for a call in the app whenever it suits you. Bye for now!');
      return finish('The call was moved to later.');
    }
    let did = "how you're feeling";
    if (latest.current.client?.checkIn.needsBaseline) {
      const scale = latest.current.meta.labels;
      const moodLabels = MOOD_LABELS.map((word, i) => scale.moodScale[String(i + 1)] ?? word);
      const anxietyLabels = ANXIETY_LABELS.map((word, i) => scale.anxietyScale[String(i + 1)] ?? word);
      const mood = await feeling('mood', ["Let's start with how you're feeling. How are you today?"], moodLabels);
      if (ended.current || mood === null) return;
      const anxiety = await feeling('anxiety', ['And how about anxiety or nervousness – how much of it have you felt today?'],
        anxietyLabels);
      if (ended.current || anxiety === null) return;
      const saved = await mutate((s) => api.recordBaseline(s, id, { mood, anxiety }));
      if (!saved) return finish("How you're feeling could not be saved.");
      unseen(saved.client as ClientView);
      await say('Thank you. This becomes your own baseline – from now on, how you feel is compared with it, not with other people.');
    } else if (await guided('checkin') === 'stop') {
      return;
    }
    const exercise = await question('Shall we also do a short thought exercise? It takes a couple of minutes.', { kind: 'yesno' });
    if (ended.current || 'hangup' in exercise) return;
    if ('yes' in exercise && exercise.yes) {
      if (await guided('thought_record') === 'stop') return;
      did = "how you're feeling and the thought exercise";
    }
    const after = latest.current.client?.checkIn;
    // "tomorrow at 18:30", but "on Wed 21 Oct at 18:30"
    const onDay = after?.nextDate && daysBetween(latest.current.meta.currentDate, after.nextDate) > 1 ? 'on ' : '';
    const next = after?.nextLabel ? `${onDay}${after.nextLabel} at ${hhmm(after.callTime)}` : 'on the agreed day';
    await say(`Thank you, ${client.firstName}. I've saved ${did} in the app. I'll call you again ${next}. Bye for now!`);
    finish(`Saved: ${did}.`);
  }

  function finish(text: string) {
    if (ended.current) return;
    ended.current = true;
    stopListening();
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    setOutcome(text);
    setAsking(null);
    setPhase('ended');
  }

  function hangUpQuietly() {
    ended.current = true;
    stopListening();
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    const resolve = resolver.current;
    resolver.current = null;
    resolve?.({ hangup: true });
  }

  function hangUp() {
    const resolve = resolver.current;
    resolver.current = null;
    finish('Call ended. You can continue where you left off in Chat.');
    resolve?.({ hangup: true });
  }

  function answerCall() {
    // Everything already in the chat is history: the call speaks only what is new.
    client.chat.forEach((m) => seen.current.add(m.id));
    setPhase('live');
    void script();
  }

  function submitTyped(event: FormEvent) {
    event.preventDefault();
    const value = typed.trim();
    if (value) onSpeech(value);
  }

  function toggleMic() {
    const next = !micOn;
    setMicOn(next);
    micRef.current = next;
    if (next) listen();
    else stopListening();
  }

  function toggleSpeaker() {
    const next = !speakerOn;
    setSpeakerOn(next);
    speakerRef.current = next;
    if (!next && 'speechSynthesis' in window) window.speechSynthesis.cancel();
  }

  const clock = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
  const status = phase === 'ringing' ? 'calling…' : speaking ? 'Mieliluotsi is speaking' : listening ? 'Listening…' : asking ? 'Answer by speaking or choose' : clock;

  return (
    <section className={`call call-${phase}`} role="dialog" aria-modal="true" aria-label="Wellbeing call from Mieliluotsi">
      <header className="call-head">
        <span className={`call-avatar ${speaking ? 'is-speaking' : ''}`} aria-hidden="true"><LogoMark size={phase === 'ringing' ? 64 : 34} /></span>
        <div className="call-who">
          <p className="call-name">Mieliluotsi</p>
          <p className="call-status" aria-live="polite">{phase === 'ringing' ? 'Wellbeing call · calling…' : phase === 'ended' ? `Call ended · ${clock}` : status}</p>
        </div>
        {phase === 'live' && <span className="call-clock">{clock}</span>}
      </header>

      {phase === 'ringing' && (
        <div className="call-incoming">
          <p className="call-lead">Mieliluotsi is calling as agreed: to ask how you are and do a short thought exercise with you.</p>
          <div className="call-answer-row">
            <button type="button" className="call-round call-decline" onClick={() => { hangUpQuietly(); onClose(); }} aria-label="Later">
              <PhoneIcon size={26} />
            </button>
            <button type="button" className="call-round call-accept" onClick={answerCall} aria-label="Answer">
              <PhoneIcon size={26} />
            </button>
          </div>
          <div className="call-answer-labels"><span>Later</span><span>Answer</span></div>
        </div>
      )}

      {phase !== 'ringing' && (
        <>
          <div className="call-transcript" ref={transcriptRef}>
            {lines.map((line) => <p key={line.id} className={`call-line is-${line.who}`}>{line.text}</p>)}
            {heard && <p className="call-line is-me is-interim">{heard}…</p>}
          </div>

          {phase === 'live' && asking && (
            <div className="call-answers">
              {hint && <p className="call-hint">{hint}</p>}
              {asking.kind === 'yesno' && (
                <div className="call-chips">
                  <button type="button" onClick={() => give({ yes: true }, 'Yes')}>Yes</button>
                  <button type="button" onClick={() => give({ yes: false }, 'Not now')}>Not now</button>
                </div>
              )}
              {asking.kind === 'scale' && (
                <div className={`call-scale ${asking.max - asking.min > 4 ? 'is-wide' : ''}`}>
                  {Array.from({ length: asking.max - asking.min + 1 }, (_, i) => asking.min + i).map((n) => (
                    <button key={n} type="button" title={asking.labels[n - asking.min]}
                      onClick={() => give({ value: n }, asking.labels[n - asking.min] ? `${n} – ${asking.labels[n - asking.min]}` : String(n))}>{n}</button>
                  ))}
                </div>
              )}
              {asking.kind === 'confirm' && (
                <>
                  <div className="call-chips">
                    <button type="button" onClick={() => give({ value: asking.value }, "Yes, that's right")}>Yes, that's right</button>
                  </div>
                  <p className="call-or">Or choose your own number:</p>
                  <div className="call-scale">
                    {asking.labels.map((label, i) => (
                      <button key={label} type="button" title={label} className={i + 1 === asking.value ? 'is-proposed' : undefined}
                        onClick={() => give({ value: i + 1 }, `${i + 1} – ${label}`)}>{i + 1}</button>
                    ))}
                  </div>
                </>
              )}
              {asking.kind === 'choices' && (
                <div className="call-chips">
                  {asking.options.map((o) => <button key={o.value} type="button" onClick={() => give({ value: o.value }, o.label)}>{o.label}</button>)}
                  {asking.skippable && <button type="button" onClick={() => give({ skip: true }, "Let's skip this")}>Skip</button>}
                </div>
              )}
              {(asking.kind === 'text' || asking.kind === 'describe') && (
                <form className="call-type" onSubmit={submitTyped}>
                  <input value={typed} onChange={(e) => setTyped(e.target.value)} aria-label="Write your answer"
                    placeholder={asking.kind === 'describe' ? (RecognitionImpl && micOn ? 'Say or write it in your own words…'
                      : 'Write it in your own words…') : RecognitionImpl && micOn ? 'Say or write your answer…' : 'Write your answer…'} />
                  <button type="submit" aria-label="Send" disabled={!typed.trim()}><SendIcon size={16} /></button>
                  {asking.kind === 'text' && asking.skippable
                    && <button type="button" className="call-skip" onClick={() => give({ skip: true }, "Let's skip this")}>Skip</button>}
                </form>
              )}
              {asking.kind === 'describe' && (
                <>
                  <p className="call-or">Or choose a number from 1 to 5:</p>
                  <div className="call-scale">
                    {asking.labels.map((label, i) => (
                      <button key={label} type="button" title={label} onClick={() => give({ value: i + 1 }, `${i + 1} – ${label}`)}>{i + 1}</button>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

          {phase === 'live' && (
            <div className="call-controls">
              <button type="button" className={`call-ctrl ${micOn ? 'is-on' : ''}`} onClick={toggleMic} disabled={!RecognitionImpl}
                aria-pressed={micOn} title={RecognitionImpl ? 'Microphone' : 'Speech recognition is not available in this browser'}>
                {micOn ? <MicIcon size={20} /> : <MicOffIcon size={20} />}<span>{micOn ? 'Mic' : 'Muted'}</span>
              </button>
              <button type="button" className="call-round call-decline call-end" onClick={hangUp} aria-label="End call">
                <PhoneIcon size={24} />
              </button>
              <button type="button" className={`call-ctrl ${speakerOn ? 'is-on' : ''}`} onClick={toggleSpeaker} disabled={!hasVoice}
                aria-pressed={speakerOn} title={hasVoice ? 'Speaker' : 'No English voice was found in this browser'}>
                {speakerOn && hasVoice ? <SpeakerIcon size={20} /> : <SpeakerOffIcon size={20} />}<span>Speaker</span>
              </button>
            </div>
          )}

          {phase === 'ended' && (
            <div className="call-ended">
              <p>{outcome}</p>
              <button type="button" className="cx-btn cx-btn-dark" onClick={onClose}>Close</button>
            </div>
          )}
          <p className="call-fine">Not an emergency call – in an emergency, call 112.</p>
        </>
      )}
    </section>
  );
}
