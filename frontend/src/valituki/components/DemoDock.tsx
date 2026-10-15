import { useEffect, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { api } from '../api';
import { useValituki } from '../context';
import { fmtNum } from '../format';
import {
  ArrowLeftIcon, ArrowRightIcon, CheckIcon, ChevronDownIcon, ForwardIcon, PersonIcon, PresentIcon, StethoscopeIcon, UsersIcon,
} from '../icons';
import { useDemoActions } from './demoActions';
import { useDockRoomy, useDockSide, useDockSlot } from './dockPlace';
import { BEATS, DEMO_INTRO, STAGES, stageEnd, stageStart, useDemoPilot } from './demoPilot';
import type { AICheck, AIStatus } from '../types';

const seconds = (ms: number | null) => (ms === null ? '' : `${fmtNum(ms / 1000)} s`);

/** The toast after switching the AI mode or testing the connection. */
function describeAI(result: AIStatus & { check: AICheck | null }): string {
  if (result.configuredMode === 'DEMO_AI_MODE') return 'Tekoäly: demotila – ennalta hyväksytyt tekstit, ei tekoälykutsuja.';
  const check = result.check;
  const label = result.providerLabel;
  if (check?.ok) return `${label} vastasi (${seconds(check.ms)}): "${check.reply ?? ''}" Keskustelu käyttää nyt tätä mallia.`;
  if (!result.keyPresent) {
    const line = result.provider === 'openai' ? 'VALITUKI_OPENAI_BASE_URL=' : 'ANTHROPIC_API_KEY=';
    return `${result.missing}: lisää se projektin .env-tiedoston riville ${line} ja valitse ${label} uudelleen. Siihen asti käytetään demotekstejä.`;
  }
  return `${label} ei vastannut (${check?.failure ?? 'tuntematon virhe'}). Käytetään demotekstejä.`;
}

/** Demo ↔ the live model (Claude, or vLLM on an AMD GPU), always in view in the demo control. The model only phrases: rules, safety levels and matching stay
    deterministic in both modes. */
export function AISwitch() {
  const { view, run, busy } = useValituki();
  const ai = view.meta.ai;
  const label = ai.providerLabel;
  const wantsLive = ai.configuredMode === 'LIVE_AI_MODE';
  const live = ai.effectiveMode === 'LIVE_AI_MODE';
  const failed = live && ai.lastCall.ok === false;
  const tone = !wantsLive ? 'is-off' : live && !failed ? 'is-live' : 'is-warn';
  // Whether AI writes the replies right now – said in words beside the switch, not only by its colour.
  const legend = !wantsLive ? 'Tekoäly pois · valmiit tekstit'
    : live && !failed ? `Tekoäly päällä · ${label} vastaa`
      : `${label} ei vastaa · valmiit tekstit`;
  // On a phone, where the switch shares its row with the view switch.
  const short = !wantsLive ? 'AI pois' : live && !failed ? 'AI päällä' : 'AI ei vastaa';
  // The details on hover: the model and its reply time, or why the model is not answering.
  const status = !wantsLive ? ai.note : !ai.keyPresent ? ai.missing
    : failed ? (ai.lastCall.failure ?? 'virhe')
      : [ai.lastCall.model ?? ai.model, ai.lastCall.ok ? seconds(ai.lastCall.ms) : ''].filter(Boolean).join(' · ');

  function setMode(mode: AIStatus['configuredMode']) {
    if (mode === ai.configuredMode && mode === 'DEMO_AI_MODE') return;
    void run((s) => api.aiMode(s, mode), describeAI);
  }

  // A note under the switch while Claude is on: the replies are real and take a moment – Demo is the quick way through the
  // interface. It comes up when the demo reaches stage 2 (the rhythm screen) and again on "Aloita Mieliluotsi", where the
  // AI starts to answer – and whenever Claude is switched on.
  const intakeStatus = view.client?.intake.status ?? null;
  const [noteFor, setNoteFor] = useState(intakeStatus);
  const [noteClosed, setNoteClosed] = useState(intakeStatus !== 'rhythm');
  if (noteFor !== intakeStatus) {
    setNoteFor(intakeStatus);
    if (intakeStatus === 'rhythm' || (intakeStatus === 'completed' && noteFor === 'rhythm')) setNoteClosed(false);
  }
  const closeNote = () => setNoteClosed(true);
  const showNote = wantsLive && !noteClosed;

  return (
    <div className={`dock-ai ${tone}`} role="group" aria-label={legend}>
      {/* The state in one sentence first, then the switch. */}
      <span className="dock-ai-status" title={status} aria-live="polite">
        <i className="dock-ai-dot" aria-hidden="true" /><span className="dock-ai-legend">{legend}</span>
        <span className="dock-ai-short" aria-hidden="true">{short}</span>
      </span>
      <span className="dock-seg">
        <button type="button" aria-pressed={!wantsLive} disabled={busy} onClick={() => setMode('DEMO_AI_MODE')}>Demo</button>
        <button type="button" aria-pressed={wantsLive} disabled={busy}
          onClick={() => { setNoteClosed(false); setMode('LIVE_AI_MODE'); }}>{label}</button>
      </span>
      {showNote && (
        <div className="dock-ai-note" role="note">
          <p><strong>{label} on päällä.</strong> Vastaukset tulevat oikealta tekoälyltä ja voivat viedä muutaman sekunnin.
            Jos haluat demota käyttöliittymää nopeasti, vaihda Demoon.</p>
          <div className="dock-ai-note-actions">
            <button type="button" className="dock-ai-note-demo" disabled={busy}
              onClick={() => { closeNote(); setMode('DEMO_AI_MODE'); }}>Vaihda Demoon</button>
            <button type="button" className="dock-ai-note-close" onClick={closeNote}>Selvä</button>
          </div>
        </div>
      )}
    </div>
  );
}

/** Whose view is on the screen – client, care coordinator or therapist; always in view in the demo control. */
function ViewSwitch() {
  const { view, role, setRole, scope } = useValituki();
  const clientName = view.demo.clients.find((c) => c.id === scope.clientId)?.firstName;
  const therapistName = view.demo.therapists.find((t) => t.id === scope.therapistId)?.name.split(' ')[0];
  const views = [
    { key: 'client' as const, icon: <PersonIcon size={14} />, label: 'Asiakas', who: clientName },
    { key: 'professional' as const, icon: <StethoscopeIcon size={14} />, label: 'Ammattilainen', who: undefined },
    { key: 'therapist' as const, icon: <UsersIcon size={14} />, label: 'Terapeutti', who: therapistName },
  ];
  return (
    <nav className="dock-views" aria-label="Demo: näkymä">
      {views.map((v) => (
        <button key={v.key} type="button" aria-pressed={role === v.key} title={v.who ? `${v.label} – ${v.who}` : v.label}
          aria-label={v.label} onClick={() => setRole(v.key)}>
          {v.icon}<span className="dock-view-t">{v.label}</span>
        </button>
      ))}
    </nav>
  );
}

type Stage = (typeof STAGES)[number];

/** DEMO-OHJAUS – presenter controls, visually separate from the product. One row: back, Seuraava and "Vaihe loppuun",
    the concept's stages (click one to jump there) and the step number; everything else (time, scenarios, other clients)
    opens from the chevron. → / PageDown = Seuraava, ← / PageUp = back, Shift+→ = the rest of the stage. It can sit in a
    column on the right instead (dockPlace.ts), with the stage's narration for the pitch video. */
export default function DemoDock() {
  const { view, run, busy } = useValituki();
  const [more, setMore] = useState(false);
  // A column beside the content – the backstage panel in the client's view, the page in the others – when the presenter
  // has chosen so and the window has room for it. Only the markup moves (a portal): the demo's state stays in this
  // component, so moving never interrupts a step.
  const side = useDockSide();
  const canSide = useDockRoomy();
  const slot = useDockSlot();
  const place = side && canSide ? slot : null;
  const { weeks } = useDemoActions();
  const pilot = useDemoPilot();
  const current = pilot.pointer > 0 ? BEATS[pilot.pointer - 1] : null;
  const upcoming = BEATS[pilot.pointer] ?? null;
  const upcomingStage = upcoming ? STAGES.findIndex((s) => s.key === upcoming.stage) : -1;
  const stageKey = current?.stage ?? 'intro';
  // The narration beside the panel: the stage, its presses (done ones filled), the part to read now and the next stage.
  const currentStage = STAGES.findIndex((s) => s.key === stageKey);
  const tellStage = STAGES[currentStage] ?? null;
  const nextStage = STAGES[currentStage + 1] ?? null;
  const stagePresses = tellStage ? BEATS.flatMap((b, i) => (b.stage === tellStage.key ? [i] : [])) : [];
  // The part of the stage's narration that belongs to the step on the screen (steps are 1-based, like the pointer).
  const tellPart = tellStage ? [...tellStage.tell].reverse().find((t) => t.from <= pilot.pointer) ?? tellStage.tell[0] : null;
  // Keep the current stage in view when the row is too narrow for all of them.
  const railRef = useRef<HTMLOListElement>(null);
  useEffect(() => {
    railRef.current?.querySelector('.current')?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }, [stageKey]);

  // The rail: the concept's stages, the four inside the "Mieliluotsi" box grouped together.
  const rail: (Stage | Stage[])[] = [];
  STAGES.forEach((stage) => {
    const last = rail[rail.length - 1];
    if (stage.group && Array.isArray(last)) last.push(stage);
    else rail.push(stage.group ? [stage] : stage);
  });
  const pill = (stage: Stage) => {
    const n = STAGES.indexOf(stage) + 1;
    const isCurrent = stage.key === stageKey;
    const done = !isCurrent && stageEnd(stage.key) < pilot.pointer;
    return (
      <li key={stage.key} className={isCurrent ? 'current' : done ? 'done' : ''}>
        <button type="button" disabled={pilot.running} aria-current={isCurrent ? 'step' : undefined} aria-label={`${n}. ${stage.label}`}
          title={`${n}. ${stage.label}${isCurrent ? '' : ' – siirry tähän vaiheeseen'}`}
          onClick={() => (isCurrent ? undefined : pilot.enter(stageStart(stage.key)))}>
          <span className="dock-step-n">{done ? <CheckIcon size={12} /> : n}</span>
          {isCurrent && <span className="dock-step-t">{stage.label}</span>}
        </button>
      </li>
    );
  };

  const dock = (
    <section className={`dock ${place ? 'is-side' : ''} ${more ? 'is-open' : ''}`} aria-label="Demo-ohjaus (ei osa palvelua)">
      <div className="dock-row">
        {/* On a phone the bar is one row: "Demo" and where the demo is – a press opens the stages and the other controls –
            then back and Seuraava. Elsewhere hidden (styles/app.css). */}
        <button type="button" className="dock-now" aria-expanded={more} onClick={() => setMore(!more)}
          aria-label={`Demo: ${tellStage ? `vaihe ${currentStage + 1}/${STAGES.length}, ${tellStage.label}` : 'ei vielä aloitettu'}. Avaa vaiheet ja muut ohjaimet.`}>
          <span className="dock-now-text">
            <span className={`dock-now-kicker ${pilot.failed ? 'is-warn' : ''}`}>
              {pilot.failed ? 'Ei onnistunut – paina uudelleen' : `Demo${tellStage ? ` · vaihe ${currentStage + 1}/${STAGES.length}` : ''}`}
            </span>
            <span className="dock-now-stage">{tellStage?.label ?? 'Alkutilassa'}</span>
          </span>
          <ChevronDownIcon size={16} />
        </button>
        {/* Demo-ohjaus: back, Seuraava and "Vaihe loppuun" in one control at the start of the bar. */}
        <div className="dock-pilot" role="group" aria-label="Demo-ohjaus – ei osa palvelua">
          <span className="dock-pilot-label" title="Demon ohjaus – ei osa palvelua. Seuraava tai → vie demon eteenpäin.">
            <PresentIcon size={16} /> <span className="dock-pilot-text">Demo-ohjaus</span>
          </span>
          <button type="button" className="dock-btn pilot-prev" disabled={pilot.running || pilot.pointer <= 1} onClick={() => void pilot.prev()}
            aria-label="Edellinen (←)" title="Edellinen (←)"><ArrowLeftIcon size={17} /></button>
          {/* While a step plays (a conversation), the same button – or → – finishes it at once. */}
          <button type="button" className="dock-btn dock-next pilot-next" disabled={!pilot.running && !upcoming} onClick={() => void pilot.next()}
            title={pilot.running ? 'Kelaa käynnissä oleva vaihe loppuun (→)' : upcoming ? `Seuraavaksi: ${upcoming.title} (→)` : 'Demo on valmis'}>
            {pilot.running ? 'Kelaa' : pilot.pointer === 0 ? 'Aloita demo' : 'Seuraava'} <ArrowRightIcon size={17} />
          </button>
          {/* The stage the next press belongs to, simulated to its end at once – no presses or pauses in between. */}
          {upcomingStage >= 0 && (
            <button type="button" className="dock-btn pilot-stage" disabled={pilot.running} onClick={() => void pilot.finishStage()}
              aria-label={`Vaihe ${upcomingStage + 1} loppuun`}
              title={`Simuloi vaihe ${upcomingStage + 1} (${STAGES[upcomingStage].label}) loppuun ilman välipainalluksia (Shift+→)`}>
              <ForwardIcon size={15} /> <span className="pilot-stage-text">Vaihe {upcomingStage + 1} loppuun</span>
            </button>
          )}
        </div>
        {/* Beside the panel, the narration: where the demo is and what the solution does – the presenter reads it aloud
            and the audience sees it in the video. */}
        <div className="pilot-tell" aria-live="polite">
          <p className="pilot-tell-stage">
            <span>{tellStage ? `Vaihe ${currentStage + 1}/${STAGES.length}` : 'Ennen demoa'}</span>
            {tellStage && (
              <span className="pilot-tell-steps" role="img"
                aria-label={`${stagePresses.filter((i) => i < pilot.pointer).length}/${stagePresses.length} painallusta tehty`}>
                {stagePresses.map((i) => <i key={i} className={i < pilot.pointer ? 'on' : ''} />)}
              </span>
            )}
          </p>
          <p className="pilot-tell-title">{tellStage?.label ?? 'Mieliluotsi'}</p>
          {tellPart?.heading && <p className="pilot-tell-part">{tellPart.heading}</p>}
          <p className="pilot-tell-say">{tellPart?.text ?? DEMO_INTRO}</p>
          {nextStage && <p className="pilot-tell-next">Seuraavaksi: {currentStage + 2}. {nextStage.label}</p>}
        </div>
        <ol className="dock-steps pilot-rail" ref={railRef} aria-label="Demon runko – siirry vaiheeseen">
          {rail.map((item) => (Array.isArray(item) ? (
            <li key="valituki" className="pilot-group" title="Mieliluotsi">
              <span className="pilot-group-label">Mieliluotsi</span>
              <ol>{item.map(pill)}</ol>
            </li>
          ) : pill(item)))}
        </ol>
        <div className="pilot-buttons">
          {pilot.failed && <span className="pilot-warn" role="alert">Ei onnistunut – paina uudelleen</span>}
          {/* The step count, its pill filled as far as the demo has come. */}
          <span className="pilot-count" aria-live="polite" style={{ '--p': `${(pilot.pointer / BEATS.length) * 100}%` } as CSSProperties}
            title={current ? `Nyt: ${current.title} – ${current.say}` : 'Paina Aloita demo tai →'}>
            <span className="pilot-count-k">Askel</span> {pilot.pointer}/{BEATS.length}
          </span>
        </div>
        <button type="button" className="dock-toggle" aria-expanded={more} aria-label="Lisää demo-ohjaimia" title="Lisää demo-ohjaimia"
          onClick={() => setMore(!more)}>
          <ChevronDownIcon size={16} />
        </button>
      </div>
      {/* The settings that stay as they are while the demo runs – whose view is on the screen and whether AI writes the
          replies – always in view: a row of their own under the flow, at the bottom of the column beside the panel. */}
      <div className="dock-context">
        <div className="dock-views-row"><span className="dock-ctx-label">Näkymä</span><ViewSwitch /></div>
        <div className="dock-ai-row"><AISwitch /></div>
      </div>
      {more && (
        <div className="dock-row dock-actions">
          {/* On a phone "Vaihe loppuun" is here: the bar keeps room for back and Seuraava. */}
          {upcomingStage >= 0 && (
            <button type="button" className="dock-btn dock-phone-only" disabled={pilot.running} onClick={() => void pilot.finishStage()}>
              <ForwardIcon size={14} /> Vaihe {upcomingStage + 1} loppuun
            </button>
          )}
          <div className="dock-group" role="group" aria-label="Aika">
            <button type="button" className="dock-btn" disabled={busy} onClick={() => run((s) => api.advance(s, 1), (r) => `+1 päivä – ${r.agentActions} agenttitoimintoa.`)}>+1 pv</button>
            <button type="button" className="dock-btn" disabled={busy} onClick={() => run((s) => api.advance(s, 7), (r) => `+7 päivää – ${r.agentActions} agenttitoimintoa.`)}>+7 pv</button>
            <button type="button" className="dock-btn" disabled={busy} onClick={weeks}>+14 pv</button>
          </div>
          <div className="dock-group" role="group" aria-label="Keskustelu">
            <button type="button" className="dock-btn" disabled={pilot.running || !(view.client?.intake.status === 'conversation' || view.client?.guided)}
              title="Toistaa auki olevan harjoituksen loppuun demovastauksilla" onClick={() => void pilot.replay()}>
              <ForwardIcon size={14} /> Toista demokeskustelu
            </button>
          </div>
        </div>
      )}
    </section>
  );
  return place ? createPortal(dock, place) : dock;
}
