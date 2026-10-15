import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { ReactNode, RefObject } from 'react';
import { fmtNum } from '../format';
import {
  AlertIcon, CheckIcon, ChevronDownIcon, EyeIcon, EyeOffIcon, LayersIcon, LeafIcon, PuzzleIcon, PulseIcon, SlidersIcon, TargetIcon,
} from '../icons';
import { useDockSlot } from '../components/dockPlace';
import type { BackstageMatch, BackstageModality, ClientView, InsightRow } from '../types';
import { DataFlow } from './DataFlow';
import type { Flow } from './DataFlow';

interface ProfileRow { key: string; icon: ReactNode; label: string; hint: string; value: string | null; pro: boolean; match: boolean }

function sharing(items: InsightRow[]) {
  return { pro: items.some((i) => i.sharing.professional), match: items.some((i) => i.sharing.matching) };
}

/** What the future therapist's profile holds right now – one row per kind of information, with who may use it. */
function profileRows(client: ClientView): ProfileRow[] {
  const profile = client.fitProfile;
  const groups = Object.fromEntries(client.memory.groups.map((g) => [g.key, g.items]));
  const checkins = client.progress.series.filter((p) => p.mood !== null);
  const moods = checkins.slice(-7).map((p) => p.mood ?? 0);
  const name = client.firstName;
  return [
    { key: 'goals', icon: <TargetIcon size={14} />, label: 'Goals', hint: `What ${name} hopes therapy will change`, value: profile?.goals.primary[0]?.text ?? null, ...sharing(groups.goal ?? []) },
    { key: 'wellbeing', icon: <PulseIcon size={14} />, label: 'Wellbeing while waiting', hint: 'Mood and anxiety from check-ins while waiting',
      value: checkins.length ? `${checkins.length} ${checkins.length === 1 ? 'check-in' : 'check-ins'} · mood avg. ${fmtNum(moods.reduce((a, b) => a + b, 0) / moods.length)}/5` : null,
      pro: client.memory.consent.storeHistory, match: false },
    { key: 'helpful', icon: <LeafIcon size={14} />, label: 'What helps', hint: `Things ${name} has found helpful`,
      value: (groups.helpful ?? []).map((i) => i.text).join(' ') || null, ...sharing(groups.helpful ?? []) },
    { key: 'challenge', icon: <AlertIcon size={14} />, label: 'Difficult moments', hint: 'Situations when things feel hardest',
      value: (groups.challenge ?? []).map((i) => i.text).join(' ') || null, ...sharing(groups.challenge ?? []) },
  ];
}

function matchSignature(match: BackstageMatch): string {
  return `${match.ran}|${match.candidates.map((c) => `${c.name}:${c.total}:${c.status}`).join(',')}`;
}

function modalitySignature(modality: BackstageModality): string {
  return modality.rows.map((r) => `${r.id}:${r.total}`).join(',');
}

const MODALITY_CHANGES: [string, string][] = [['workingStyle', 'Working style wishes'], ['goals', 'Goals']];

/** What moved the therapy approach table: the working style first, then the goals. */
function modalityChange(before: BackstageModality, after: BackstageModality): string {
  const old = new Map(before.rows.flatMap((r) => r.components.map((c) => [`${r.id}.${c.key}`, c.score] as const)));
  const moved = MODALITY_CHANGES.find(([key]) => after.rows.some((r) => r.components.some((c) => c.key === key
    && old.get(`${r.id}.${key}`) !== c.score)));
  return moved ? moved[1] : 'Therapy approach fit';
}

/** At or below this window width the panel is under the phone (the same breakpoint as in styles/app.css). */
const STACKED = 640;
const PHONE = { width: 396, height: 836 };  // the phone at full size
const GAP = 64;  // between the phone and the panel (and the demo control's column): room for the data travelling
const DOCK = 320;  // the demo control's column beside the panel (.dock-slot in styles/app.css)

interface Seen {
  clientId: string; rowSig: string; matchSig: string; modSig: string; modality: BackstageModality; values: Record<string, string>;
  ran: boolean; chosen: string | null; shared: string | null; seq: number;
}

/** What the panel last showed for each client. It outlives the panel: when another view was on the screen meanwhile (the
    professional's review, the therapist's plan), what changed there travels to the panel when the client's view is back. */
const lastSeen = new Map<string, Seen>();

/** Next to the phone on wide screens, stacked in one compact column: the matching tables (therapist, therapy approach)
    and the profile for the therapist, all always visible. Framed apart from the app – behind the scenes, not what the
    client sees: computed by rules from their actions and approved entries. When the client's data changes, it visibly
    travels from the phone to the rows it updates. */
export default function Backstage({ client }: { client: ClientView }) {
  const asideRef = useRef<HTMLElement>(null);
  const dockSlot = useDockSlot();
  const rows = profileRows(client);
  const match = client.backstage.match;
  const values = Object.fromEntries(rows.map((r) => [r.key, r.value ?? '']));
  const rowSig = rows.map((r) => `${r.key}=${r.value ?? ''}`).join('|');
  const matchSig = matchSignature(match);
  const modality = client.backstage.modality;
  const modSig = modalitySignature(modality);
  const handover = client.matching.handover;
  const shared = handover?.status === 'approved' ? handover.therapistName : null;
  const now = { clientId: client.id, rowSig, matchSig, modSig, modality, values, ran: match.ran, chosen: match.chosen, shared };

  const [seen, setSeen] = useState<Seen>(() => lastSeen.get(client.id) ?? { ...now, seq: 0 });
  const [flows, setFlows] = useState<Flow[]>([]);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  if (seen.clientId !== client.id || seen.rowSig !== rowSig || seen.matchSig !== matchSig || seen.modSig !== modSig
    || seen.shared !== shared) {
    const seq = seen.seq + 1;
    if (seen.clientId === client.id) {
      // Only approved, stored information moves: each changed row flies to the profile, and to matching when allowed there.
      const changed = rows.filter((r) => r.value && r.value !== seen.values[r.key]);
      const next: Omit<Flow, 'id'>[] = [];
      for (const r of changed) {
        next.push({ label: r.label, target: 'profile', row: r.key });
        if (r.match) next.push({ label: r.label, target: 'match' });
      }
      if (seen.matchSig !== matchSig && !next.some((f) => f.target === 'match')) {
        next.push({ target: 'match', label: match.chosen && match.chosen !== seen.chosen ? `Choice: ${match.chosen}`
          : match.ran && !seen.ran ? "Therapist's free slot" : 'Scores updated' });
      }
      // The client approves the summary: the profile is shared with the therapist.
      if (shared && shared !== seen.shared) next.push({ label: 'Approved for sharing', target: 'profile' });
      if (seen.modSig !== modSig) next.push({ label: modalityChange(seen.modality, modality), target: 'modality' });
      // Every table that changed gets its chip even when many rows changed at once.
      const firsts = next.filter((f, i) => next.findIndex((g) => g.target === f.target) === i);
      const ordered = [...firsts, ...next.filter((f) => !firsts.includes(f))];
      setFlows(ordered.slice(0, 7).map((f, i) => ({ ...f, id: `${seq}-${i}` })));
      setFresh(new Set([...changed.map((r) => r.key), ...(seen.matchSig !== matchSig ? ['match'] : []),
        ...(seen.modSig !== modSig ? ['modality'] : []), ...(shared && shared !== seen.shared ? ['shared'] : [])]));
    } else {
      setFlows([]);
      setFresh(new Set());
    }
    setSeen({ ...now, seq });
  }
  useEffect(() => { lastSeen.set(seen.clientId, seen); }, [seen]);
  useEffect(() => {
    if (!fresh.size) return undefined;
    const timer = window.setTimeout(() => setFresh(new Set()), 3600);
    return () => window.clearTimeout(timer);
  }, [fresh]);

  // The phone and the panel side by side on one screen: both are scaled to the height under the demo dock, and when the
  // window is narrow they shrink together – the gap with them – until they fit its width. The panel may grow a little on
  // a large screen; an opened log scrolls inside it. When the presenter has moved the demo control beside the panel, it
  // takes a column of its own and the top bar's height is free.
  useLayoutEffect(() => {
    const aside = asideRef.current;
    const stage = aside?.parentElement;
    if (!aside || !stage) return undefined;
    const fit = () => {
      if (window.innerWidth <= STACKED) {
        aside.style.removeProperty('--bs-zoom');
        stage.style.removeProperty('--phone-zoom');
        stage.style.removeProperty('--stage-gap');
        return;
      }
      const zoom = Number.parseFloat(aside.style.getPropertyValue('--bs-zoom')) || 1;
      const parts = [aside.querySelector('.bs-bar'), ...aside.querySelectorAll('.bm-card'), aside.querySelector('.bp-doc')];
      const box = getComputedStyle(aside);
      const frame = ['paddingTop', 'paddingBottom', 'borderTopWidth', 'borderBottomWidth'] as const;
      const height = parts.reduce((sum, el) => sum + (el ? el.getBoundingClientRect().height / zoom : 0), 0)
        + (parts.length - 1) * (Number.parseFloat(box.rowGap) || 0) + frame.reduce((sum, k) => sum + (Number.parseFloat(box[k]) || 0), 0) + 4;
      const width = aside.getBoundingClientRect().width / zoom;
      // Measured here rather than read from --stage-top: when the demo control moves, this runs before that is updated. Sized
      // for the control's first row: its extra controls under the chevron are open only for a moment.
      const extra = document.querySelector('.dock:not(.is-side) .dock-actions')?.getBoundingClientRect().height ?? 0;
      const stageTop = (stage.closest('main')?.getBoundingClientRect().top ?? 110) + window.scrollY - extra;
      const room = Math.max(360, window.innerHeight - stageTop - 28);
      let phone = Math.min(1, room / PHONE.height);  // an iPhone's proportions, as tall as the room allows
      // The panel as tall as the phone, so that the phone, the panel and the demo control beside it line up.
      let panel = Math.min(1.15, Math.min(room, PHONE.height) / height);
      // The demo control beside the panel has the panel's scale, so their texts are the same size – but stays big enough to
      // use. Its room is set aside at the scale the panel would have without it.
      const MIN_DOCK = 0.6;
      const reserved = dockSlot ? DOCK * Math.max(MIN_DOCK, panel) : 0;
      const gaps = dockSlot ? 2 : 1;  // the same gap before the demo control's column
      const fits = (gap: number) => Math.min(1, (stage.clientWidth - gap * gaps - reserved) / (PHONE.width * phone + width * panel));
      let gap = GAP;
      if (fits(gap) < 1) {
        gap = Math.max(24, Math.round(GAP * fits(gap)));
        const factor = fits(gap);
        phone *= factor;
        panel *= factor;
      }
      panel = Math.max(0.45, panel);
      if (Math.abs(panel - zoom) > 0.005) aside.style.setProperty('--bs-zoom', panel.toFixed(3));
      if (Math.abs(phone - (Number.parseFloat(stage.style.getPropertyValue('--phone-zoom')) || 0)) > 0.005) {
        stage.style.setProperty('--phone-zoom', phone.toFixed(3));
      }
      stage.style.setProperty('--stage-gap', `${gap}px`);
      if (dockSlot) stage.style.setProperty('--dock-zoom', Math.max(MIN_DOCK, panel).toFixed(3));
      else stage.style.removeProperty('--dock-zoom');
      // Where the panel ends and the demo control begins: the other views put their page's right edge and the control in
      // the same places, so nothing moves when the demo switches views (.page-layout.has-dock in styles/app.css).
      window.requestAnimationFrame(() => {
        const slot = stage.querySelector('.dock-slot');
        const root = document.documentElement.style;
        if (!slot) return;
        root.setProperty('--compose-right', `${Math.round(aside.getBoundingClientRect().right)}px`);
        root.setProperty('--compose-dock', `${Math.round(slot.getBoundingClientRect().left)}px`);
      });
    };
    fit();
    const observer = new ResizeObserver(fit);
    aside.querySelectorAll('.bm-card, .bp-doc').forEach((el) => observer.observe(el));
    const phone = stage.querySelector('.phone');
    if (phone) observer.observe(phone);  // the phone is scaled to the screen height: the room beside it changes
    window.addEventListener('resize', fit);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', fit);
    };
  }, [dockSlot]);

  return (
    <aside className="backstage" ref={asideRef} aria-label="Mieliluotsi behind the scenes">
      <header className="bs-bar">
        <span className="bs-bar-icon" aria-hidden="true"><EyeOffIcon size={17} /></span>
        <span className="bs-bar-text">
          <strong>Behind the scenes – the user does not see this</strong>
        </span>
      </header>
      <MatchCard match={match} fresh={fresh.has('match')} />
      <ModalityCard modality={modality} fresh={fresh.has('modality')} />
      <ProfileCard client={client} rows={rows} fresh={fresh} />
      <DataFlow flows={flows} asideRef={asideRef} />
    </aside>
  );
}

/* ---------- Profile for the future therapist ---------- */

function ProfileCard({ client, rows, fresh }: { client: ClientView; rows: ProfileRow[]; fresh: Set<string> }) {
  const filled = rows.filter((r) => r.value).length;
  const handover = client.matching.handover;
  return (
    <section className={`bp-doc ${[...fresh].some((k) => k !== 'match' && k !== 'modality') ? 'is-fresh' : ''}`} aria-label="Profile for the therapist">
      <div className="bp-head">
        <p className="bs-title"><LayersIcon size={15} /> Profile for the therapist</p>
        <span className="bp-meter" title={`${filled}/${rows.length} sections`} aria-label={`${filled}/${rows.length} sections`}>
          {rows.map((r) => <i key={r.key} className={r.value ? 'on' : ''} />)}
        </span>
      </div>
      <ul className="bp-rows">
        {rows.map((r) => (
          <li key={r.key} data-row={r.key} className={`${r.value ? 'is-filled' : ''} ${fresh.has(r.key) ? 'is-fresh' : ''}`}>
            <span className="bp-icon" aria-hidden="true">{r.icon}</span>
            <span className="bp-text" title={r.value ?? undefined}>
              <span className="bp-label">{r.label}</span> <span className="bp-value">{r.value ?? r.hint}</span>
            </span>
            <span className="bp-flags">
              <span className={r.value && r.pro ? 'on' : ''} title={r.value && r.pro ? 'Visible to the therapist' : 'Not visible to the therapist'}><EyeIcon size={13} /></span>
              <span className={r.value && r.match ? 'on' : ''} title={r.value && r.match ? 'Used in matching' : 'Not used in matching'}><PuzzleIcon size={13} /></span>
            </span>
          </li>
        ))}
      </ul>
      <p className="bp-legend">
        <span><EyeIcon size={12} /> visible to the therapist</span><span><PuzzleIcon size={12} /> used in matching</span>
        {handover?.status === 'approved' && (
          <span className="bp-shared"><CheckIcon size={12} /> summary shared: {handover.therapistName}</span>
        )}
      </p>
    </section>
  );
}

/* ---------- Matching: the approved data against the therapist pool ---------- */

// The columns a person reads at a glance: what fits the client. Language, place and time are hard criteria (they
// exclude) or practicalities, so they stay in the total but get no column of their own.
const COLUMNS: { key: string; label: string }[] = [
  { key: 'goalCompetence', label: 'Expertise' }, { key: 'workingStyle', label: 'Working style' }, { key: 'userPreferences', label: 'Wishes' },
];

function Dots({ score, label }: { score: number; label: string }) {
  const filled = Math.round(score * 4);
  return (
    <span className="bm-dots" title={`${label}: ${Math.round(score * 100)}%`} aria-label={`${label} ${filled}/4`}>
      {[0, 1, 2, 3].map((i) => <i key={i} className={i < filled ? 'on' : ''} />)}
    </span>
  );
}

/** Rows glide to their new place when the ranking changes (FLIP; no re-render needed). */
function useRowFlip(gridRef: RefObject<HTMLDivElement | null>, order: string) {
  const tops = useRef(new Map<string, number>());
  useLayoutEffect(() => {
    const grid = gridRef.current;
    if (!grid) return;
    grid.querySelectorAll<HTMLElement>('[data-name]').forEach((el) => {
      const name = el.dataset.name ?? '';
      const before = tops.current.get(name);
      if (before !== undefined && before !== el.offsetTop) {
        el.animate([{ transform: `translateY(${before - el.offsetTop}px)` }, { transform: 'none' }],
          { duration: 700, easing: 'cubic-bezier(0.2, 0.7, 0.2, 1)' });
      }
      tops.current.set(name, el.offsetTop);
    });
  }, [gridRef, order]);
}

function MatchCard({ match, fresh }: { match: BackstageMatch; fresh: boolean }) {
  const gridRef = useRef<HTMLDivElement>(null);
  useRowFlip(gridRef, match.candidates.map((c) => c.name).join('|'));
  // One row highlighted, as in the therapy approach table: the therapist the client chose, until then the best fit.
  const chosen = match.candidates.find((c) => c.status === 'selected');
  const highlighted = chosen ?? match.candidates[0];

  return (
    <section className={`bm-card ${fresh ? 'is-fresh' : ''}`} aria-label="Best-fitting therapist">
      <div className="bp-head">
        <p className="bs-title"><PuzzleIcon size={15} /> Best-fitting therapist</p>
        <span className={`bm-state ${match.ran ? 'is-run' : ''}`}>{match.ran ? 'matching run' : 'preview'}</span>
      </div>
      <div className="bm-grid" ref={gridRef} role="table" aria-label="Scores by area">
        <div className="bm-row bm-row-head" role="row">
          <span role="columnheader">Therapist</span>
          {COLUMNS.map((c) => <span key={c.key} role="columnheader">{c.label}</span>)}
          <span role="columnheader">Fit</span>
        </div>
        {match.candidates.map((cand) => (
          <div key={cand.name} data-name={cand.name} role="row" className={`bm-row ${cand === highlighted ? 'is-top' : ''}`}>
            <span role="cell" className="bm-name">{cand.name}{cand.status === 'selected' && <em>chosen</em>}</span>
            {COLUMNS.map((col) => {
              const c = cand.components.find((x) => x.key === col.key);
              return <span key={col.key} role="cell" className="bm-cell">{c ? <Dots score={c.score} label={c.label} /> : '–'}</span>;
            })}
            <span role="cell" className="bm-total">
              <span className="bm-bar"><i style={{ width: `${Math.min(100, cand.total)}%` }} /></span>{Math.round(cand.total)}
            </span>
          </div>
        ))}
      </div>
      <div className="bm-foot">
        <p className="bm-scale">
          <span className="bm-legend-dots"><Dots score={1} label="Strong match" /> strong match ·</span>
          fit 0–100 by rules, not by AI
        </p>
        {match.excluded.length > 0 && (
          <details className="bm-out">
            <summary title="Excluded by hard criteria"><ChevronDownIcon size={12} /> Excluded: {match.excluded.length}</summary>
            <ul>
              {match.excluded.map((e) => <li key={e.name}><b>{e.name}</b> {e.reason}</li>)}
            </ul>
          </details>
        )}
      </div>
    </section>
  );
}

/* ---------- Therapy approach: which way of working fits the client ---------- */

/** What a fit is made of, for the tooltip: "Goals 94% · Working style 94%". */
function fitBreakdown(row: BackstageModality['rows'][number]): string {
  return row.components.map((c) => (c.known ? `${c.label} ${Math.round(c.score * 100)}%` : `${c.label}: no information yet`))
    .join(' · ');
}

/** The same kind of table as the therapist matching, for the therapy approaches – only the fit, computed from the
    client's goals and the way of working they wish for (the breakdown is in the tooltip). A suggestion – the
    professional decides. */
function ModalityCard({ modality, fresh }: { modality: BackstageModality; fresh: boolean }) {
  const gridRef = useRef<HTMLDivElement>(null);
  useRowFlip(gridRef, modality.rows.map((r) => r.id).join('|'));
  return (
    <section className={`bm-card bm-modality ${fresh ? 'is-fresh' : ''}`} aria-label="Best-fitting therapy approach and working style">
      <div className="bp-head">
        <p className="bs-title"><SlidersIcon size={15} /> Best-fitting therapy approach and working style</p>
        <span className="bm-state">suggestion</span>
      </div>
      <div className="bm-grid" ref={gridRef} role="table" aria-label="Fit of therapy approaches">
        <div className="bm-row bm-row-head" role="row">
          <span role="columnheader">Therapy approach</span>
          <span role="columnheader">Fit</span>
        </div>
        {modality.rows.map((row, i) => (
          <div key={row.id} data-name={row.id} role="row" className={`bm-row ${i === 0 ? 'is-top' : ''}`}
            title={row.therapists ? `Offered by ${row.therapists} ${row.therapists === 1 ? 'therapist' : 'therapists'}` : 'Not available now'}>
            <span role="cell" className="bm-name">{row.label}</span>
            <span role="cell" className="bm-total" title={fitBreakdown(row)}
              aria-label={`${Math.round(row.total)}: ${fitBreakdown(row)}`}>
              <span className="bm-bar"><i style={{ width: `${Math.min(100, row.total)}%` }} /></span>{Math.round(row.total)}
            </span>
          </div>
        ))}
      </div>
      <p className="bm-scale">best fit at the top · fit 0–100 by rules, from goals and working style wishes</p>
    </section>
  );
}
