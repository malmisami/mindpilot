import { useEffect, useId, useState } from 'react';
import type { PointerEvent } from 'react';
import { fmtDate, fmtNum, fmtShort } from '../format';

/* Chart conventions (dataviz method): one series per chart – the title names it, so no legend box; 2px line with a 10% wash;
   >=8px markers with a 2px surface ring; solid hairline grid; a crosshair tooltip that snaps to the nearest point; and a table
   twin so no value is reachable only by hovering. Values on the 1–5 self-report scale are indicative, never a diagnosis. */

export interface WellbeingPoint { date: string; mood: number | null; belowBaseline?: boolean; changes?: Record<string, string> }
export interface ChartEvent { date: string; label: string }

const MOOD_WORDS: Record<number, string> = { 1: 'Very bad', 2: 'Bad', 3: 'Okay', 4: 'Good', 5: 'Very good' };
const DOMAIN_WORDS: Record<string, string> = { sleep: 'Sleep', anxiety: 'Anxiety', energy: 'Energy', work: 'Ability to work', social: 'Social life' };

/** The rendered width of an element, so an SVG can be drawn 1:1 (10px text stays 10px on a wide screen). */
function useElementWidth(fallback: number): [(node: HTMLElement | null) => void, number] {
  const [node, setNode] = useState<HTMLElement | null>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    if (!node) return undefined;
    const observer = new ResizeObserver(([entry]) => {
      const next = Math.round(entry.contentRect.width);
      if (next > 0) setWidth(next);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [node]);
  return [setNode, width];
}

export function WellbeingChart({ title, points, baseline, events = [], height = 190, compact = false, note }: {
  title: string; points: WellbeingPoint[]; baseline: number | null; events?: ChartEvent[]; height?: number; compact?: boolean; note?: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const [showTable, setShowTable] = useState(false);
  const [plotRef, plotWidth] = useElementWidth(360);
  const tableId = useId();
  const fadeId = useId();
  const data = points.filter((p): p is WellbeingPoint & { mood: number } => p.mood !== null);
  if (data.length < 2) {
    return (
      <figure className="viz viz-empty">
        <figcaption className="viz-title">{title}</figcaption>
        <p className="muted small">The chart appears once there are at least two check-ins.</p>
      </figure>
    );
  }
  const W = Math.max(260, plotWidth);
  const H = height;
  const padX = { right: 26, left: compact ? 10 : 24 };
  const t0 = Date.parse(data[0].date);
  const t1 = Date.parse(data[data.length - 1].date);
  const span = Math.max(86_400_000, t1 - t0);
  const x = (iso: string) => padX.left + ((Date.parse(iso) - t0) / span) * (W - padX.left - padX.right);
  const marks = placeEventLabels(events, x, W - padX.right);
  const rows = marks.reduce((n, m) => Math.max(n, m.row + 1), 0);
  const pad = { ...padX, top: 16 + (compact ? 0 : Math.max(0, rows - 1) * 11), bottom: 22 };
  const y = (v: number) => pad.top + (1 - (v - 1) / 4) * (H - pad.top - pad.bottom);
  const path = data.map((p, i) => `${i ? 'L' : 'M'}${x(p.date).toFixed(1)},${y(p.mood).toFixed(1)}`).join(' ');
  const area = `${path} L${x(data[data.length - 1].date).toFixed(1)},${y(1)} L${x(data[0].date).toFixed(1)},${y(1)} Z`;
  const last = data[data.length - 1];
  const active = hover !== null ? data[hover] : null;
  const belowLimit = baseline !== null ? baseline - 1 : null;
  const summary = `${title}: ${data.length} self-reported check-ins ${fmtDate(data[0].date)}–${fmtDate(last.date)}, latest ${last.mood}/5`
    + (baseline !== null ? `, own baseline ${fmtNum(baseline)}.` : '.');

  function onMove(event: PointerEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const px = ((event.clientX - rect.left) / rect.width) * W;
    let best = 0;
    data.forEach((p, i) => { if (Math.abs(x(p.date) - px) < Math.abs(x(data[best].date) - px)) best = i; });
    setHover(best);
  }

  return (
    <figure className={`viz ${compact ? 'viz-compact' : ''}`}>
      <figcaption className="viz-title">{title}{note && <span className="viz-note"> · {note}</span>}</figcaption>
      <div className="viz-plot" ref={plotRef}>
        <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={summary} onPointerMove={onMove} onPointerLeave={() => setHover(null)}
          tabIndex={0} onFocus={() => setHover(data.length - 1)} onBlur={() => setHover(null)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowLeft') setHover((h) => Math.max(0, (h ?? data.length - 1) - 1));
            if (e.key === 'ArrowRight') setHover((h) => Math.min(data.length - 1, (h ?? 0) + 1));
          }}>
          {belowLimit !== null && belowLimit > 1 && (
            <rect className="viz-zone" x={pad.left} width={W - pad.left - pad.right} y={y(belowLimit)} height={y(1) - y(belowLimit)} />
          )}
          {[1, 2, 3, 4, 5].map((tick) => (
            <g key={tick}>
              <line className="viz-grid" x1={pad.left} x2={W - pad.right} y1={y(tick)} y2={y(tick)} />
              {!compact && <text className="viz-tick" x={pad.left - 7} y={y(tick) + 3.5} textAnchor="end">{tick}</text>}
            </g>
          ))}
          {marks.map((mark) => (
            <g key={`${mark.date}-${mark.label}`}>
              <line className="viz-event" x1={mark.x} x2={mark.x} y1={compact ? pad.top - 4 : 12 + mark.row * 11} y2={H - pad.bottom} />
              {!compact && <text className="viz-event-label" x={mark.anchor === 'end' ? mark.x - 4 : mark.x + 4} y={22 + mark.row * 11}
                textAnchor={mark.anchor}>{mark.label}</text>}
            </g>
          ))}
          {/* The area fades out downwards: the line carries the reading, the fill only its weight. */}
          <defs>
            <linearGradient id={fadeId} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" className="viz-fade-top" />
              <stop offset="100%" className="viz-fade-bottom" />
            </linearGradient>
          </defs>
          <path className="viz-area" d={area} style={{ fill: `url(#${CSS.escape(fadeId)})` }} />
          {baseline !== null && (
            <g>
              <line className="viz-baseline" x1={pad.left} x2={W - pad.right} y1={y(baseline)} y2={y(baseline)} />
              {!compact && <text className="viz-baseline-label" x={pad.left + 4} y={y(baseline) - 5}>Own baseline {fmtNum(baseline)}</text>}
            </g>
          )}
          <path className="viz-line" d={path} />
          {data.map((p, i) => (
            <circle key={`${p.date}-${i}`} className={p.belowBaseline ? 'viz-dot viz-dot-below' : 'viz-dot'}
              cx={x(p.date)} cy={y(p.mood)} r={p.belowBaseline ? 4.5 : 3.5} />
          ))}
          {!compact && (
            <text className="viz-end-label" x={Math.min(x(last.date) + 8, W - 4)} y={y(last.mood) + 4} textAnchor="start">{last.mood}</text>
          )}
          {!compact && <text className="viz-tick" x={pad.left} y={H - 5}>{fmtShort(data[0].date)}</text>}
          {!compact && <text className="viz-tick" x={W - pad.right} y={H - 5} textAnchor="end">{fmtShort(last.date)}</text>}
          {active && (
            <g>
              <line className="viz-crosshair" x1={x(active.date)} x2={x(active.date)} y1={pad.top} y2={H - pad.bottom} />
              <circle className={active.belowBaseline ? 'viz-dot viz-dot-below' : 'viz-dot'} cx={x(active.date)} cy={y(active.mood)} r={5.5} />
            </g>
          )}
        </svg>
        {active && (
          <div className="viz-tooltip" role="status" style={{ left: `clamp(84px, ${(x(active.date) / W) * 100}%, calc(100% - 84px))` }}>
            <strong>{active.mood}/5 · {MOOD_WORDS[active.mood]}</strong>
            <span>{fmtDate(active.date)}</span>
            {active.changes && Object.keys(active.changes).length > 0 && (
              <span>{Object.entries(active.changes).map(([k, v]) => `${DOMAIN_WORDS[k] ?? k} ${v === 'worse' ? 'worse' : 'better'}`).join(' · ')}</span>
            )}
            {active.belowBaseline && <span className="viz-tip-flag">Below own baseline</span>}
          </div>
        )}
      </div>
      {!compact && (
        <>
          <button type="button" className="link-btn viz-table-toggle" aria-expanded={showTable} aria-controls={tableId}
            onClick={() => setShowTable(!showTable)}>{showTable ? 'Hide table' : 'Show as a table'}</button>
          <table id={tableId} className={showTable ? 'viz-table' : 'visually-hidden'}>
            <caption className="visually-hidden">{title}</caption>
            <thead><tr><th scope="col">Date</th><th scope="col">Wellbeing (1–5)</th><th scope="col">Changed</th></tr></thead>
            <tbody>
              {data.map((p, i) => (
                <tr key={`${p.date}-${i}`}>
                  <td>{fmtDate(p.date)}</td>
                  <td>{p.mood}{p.belowBaseline ? ' (below own baseline)' : ''}</td>
                  <td>{Object.entries(p.changes ?? {}).map(([k, v]) => `${DOMAIN_WORDS[k] ?? k} ${v === 'worse' ? '↓' : '↑'}`).join(', ') || '–'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </figure>
  );
}

/** Event markers: same-day events share one label; labels that would collide move to another row (never overlap). */
function placeEventLabels(events: ChartEvent[], x: (iso: string) => number, right: number) {
  const byDay = new Map<string, { date: string; labels: string[] }>();
  for (const event of events) {
    const day = event.date.slice(0, 10);
    const entry = byDay.get(day) ?? { date: event.date, labels: [] };
    if (!entry.labels.includes(event.label)) entry.labels.push(event.label);
    byDay.set(day, entry);
  }
  const placed: { x0: number; x1: number; row: number }[] = [];
  return [...byDay.values()]
    .map(({ date, labels }) => ({ date, label: labels.join(' · '), x: x(date) }))
    .sort((a, b) => a.x - b.x)
    .map((mark) => {
      const width = mark.label.length * 5.4 + 4;
      const anchor: 'start' | 'end' = mark.x + width > right ? 'end' : 'start';
      const x0 = anchor === 'end' ? mark.x - width : mark.x;
      const x1 = anchor === 'end' ? mark.x : mark.x + width;
      let row = 0;
      while (placed.some((p) => p.row === row && x0 < p.x1 + 6 && x1 > p.x0 - 6)) row += 1;
      placed.push({ x0, x1, row });
      return { ...mark, anchor, row };
    });
}

/** A word-free trend line for a summary tile: the 1–5 self-reports in order, the own baseline dashed, the latest value dotted.
    The tile's text states the values, so the line only shows the shape. */
export function Sparkline({ values, baseline, label }: { values: (number | null)[]; baseline: number | null; label: string }) {
  const data = values.filter((v): v is number => v !== null);
  if (data.length < 2) return null;
  const W = 220;
  const H = 46;
  const pad = 5;
  const x = (i: number) => pad + (i / (data.length - 1)) * (W - pad * 2);
  const y = (v: number) => pad + (1 - (v - 1) / 4) * (H - pad * 2);
  const path = data.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const last = data[data.length - 1];
  return (
    <svg className="sparkline" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      {baseline !== null && <line className="sparkline-base" x1={pad} x2={W - pad} y1={y(baseline)} y2={y(baseline)} />}
      <path className="sparkline-line" d={path} />
      <circle className={`sparkline-dot ${baseline !== null && last < baseline ? 'is-below' : ''}`} cx={x(data.length - 1)} cy={y(last)} r="3.5" />
    </svg>
  );
}

/** A bullet-style meter: filled share of a component's weight (transparent matching, never a probability). */
export function Meter({ label, value, max, detail }: { label: string; value: number; max: number; detail?: string }) {
  const share = max > 0 ? Math.max(0, Math.min(1, value / max)) : 0;
  return (
    <div className="meter">
      <div className="meter-head"><span>{label}</span><span className="meter-value">{fmtNum(value, 0)} / {fmtNum(max, 0)}</span></div>
      <div className="meter-track" aria-hidden="true"><div className="meter-fill" style={{ width: `${share * 100}%` }} /></div>
      {detail && <p className="meter-detail">{detail}</p>}
    </div>
  );
}

export interface MoodAnxietyPoint { date: string; at: string | null; mood: number | null; anxiety: number | null }

const ANXIETY_WORDS: Record<number, string> = { 1: 'not at all', 2: 'a little', 3: 'somewhat', 4: 'a lot', 5: 'very much' };
const SERIES = [
  { key: 'mood' as const, label: 'Mood', className: 'ma-mood' },
  { key: 'anxiety' as const, label: 'Anxiety', className: 'ma-anx' },
];

/** Mood and anxiety on the same 1–5 self-report scale (one axis): two lines, a legend, end labels, a crosshair tooltip and a
    table twin. Colours come from the validated categorical pair (blue = mood, orange = anxiety) – never colour alone. */
export function MoodAnxietyChart({ points, height = 176, title = 'Mood and anxiety' }: {
  points: MoodAnxietyPoint[]; height?: number; title?: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const [showTable, setShowTable] = useState(false);
  const [plotRef, plotWidth] = useElementWidth(320);
  const tableId = useId();
  const data = points.filter((p) => p.mood !== null || p.anxiety !== null);
  if (data.length < 2) {
    return (
      <figure className="ma-chart ma-empty">
        <figcaption className="ma-head"><span className="ma-title">{title}</span></figcaption>
        <p className="ma-empty-text">The chart appears once there are at least two check-ins.</p>
      </figure>
    );
  }
  const W = Math.max(240, plotWidth);
  const H = height;
  const pad = { left: 14, right: 74, top: 14, bottom: 26 };
  const stamp = (p: MoodAnxietyPoint) => Date.parse(p.at ?? `${p.date}T20:00`);
  const t0 = stamp(data[0]);
  const t1 = stamp(data[data.length - 1]);
  const span = Math.max(3_600_000, t1 - t0);
  const x = (p: MoodAnxietyPoint) => pad.left + ((stamp(p) - t0) / span) * (W - pad.left - pad.right);
  const y = (v: number) => pad.top + (1 - (v - 1) / 4) * (H - pad.top - pad.bottom);
  const days = [...new Set(data.map((p) => p.date))];
  const step = Math.max(1, Math.ceil(days.length / 5));
  const ticks = days.filter((_, i) => i % step === 0 || i === days.length - 1)
    .map((d) => ({ date: d, x: x(data.find((p) => p.date === d) as MoodAnxietyPoint) }))
    .filter((t, i, all) => i === 0 || t.x - all[i - 1].x > 30);
  const paths = SERIES.map((s) => {
    const pts = data.filter((p) => p[s.key] !== null);
    return { ...s, pts, d: pts.map((p, i) => `${i ? 'L' : 'M'}${x(p).toFixed(1)},${y(p[s.key] as number).toFixed(1)}`).join(' ') };
  });
  const ends = paths.filter((s) => s.pts.length).map((s) => {
    const last = s.pts[s.pts.length - 1];
    return { ...s, value: last[s.key] as number, y: y(last[s.key] as number) };
  });
  if (ends.length === 2 && Math.abs(ends[0].y - ends[1].y) < 13) {
    const mid = (ends[0].y + ends[1].y) / 2;
    const [upper, lower] = ends[0].value >= ends[1].value ? [0, 1] : [1, 0];
    ends[upper].y = mid - 7;
    ends[lower].y = mid + 7;
  }
  const active = hover !== null ? data[hover] : null;
  const last = data[data.length - 1];
  const summary = `${title}: ${data.length} check-ins ${fmtDate(data[0].date)}–${fmtDate(last.date)}. Latest mood `
    + `${last.mood ?? '–'}/5 and anxiety ${last.anxiety ?? '–'}/5 (self-rated, 1–5).`;

  function onMove(event: PointerEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const px = ((event.clientX - rect.left) / rect.width) * W;
    let best = 0;
    data.forEach((p, i) => { if (Math.abs(x(p) - px) < Math.abs(x(data[best]) - px)) best = i; });
    setHover(best);
  }

  return (
    <figure className="ma-chart">
      <figcaption className="ma-head">
        <span className="ma-title">{title}</span>
        <span className="ma-legend" aria-hidden="true">
          {SERIES.map((s) => <span key={s.key} className={`ma-key ${s.className}`}><i />{s.label}</span>)}
        </span>
      </figcaption>
      <div className="ma-plot" ref={plotRef}>
        <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={summary} tabIndex={0}
          onPointerMove={onMove} onPointerLeave={() => setHover(null)} onFocus={() => setHover(data.length - 1)} onBlur={() => setHover(null)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowLeft') setHover((h) => Math.max(0, (h ?? data.length - 1) - 1));
            if (e.key === 'ArrowRight') setHover((h) => Math.min(data.length - 1, (h ?? 0) + 1));
          }}>
          {ticks.map((t) => (
            <g key={t.date}>
              <line className="ma-grid" x1={t.x} x2={t.x} y1={pad.top - 6} y2={H - pad.bottom} />
              <text className="ma-tick" x={t.x} y={H - 8} textAnchor="middle">{fmtShort(t.date)}</text>
            </g>
          ))}
          {paths.map((s) => <path key={s.key} className={`ma-line ${s.className}`} d={s.d} />)}
          {paths.map((s) => s.pts.map((p, i) => (
            <circle key={`${s.key}-${i}`} className={`ma-dot ${s.className}`} cx={x(p)} cy={y(p[s.key] as number)} r={4} />
          )))}
          {ends.map((s) => (
            <text key={s.key} className={`ma-end ${s.className}`} x={W - pad.right + 10} y={s.y + 4}>{s.label} {s.value}</text>
          ))}
          {active && (
            <g>
              <line className="ma-crosshair" x1={x(active)} x2={x(active)} y1={pad.top - 6} y2={H - pad.bottom} />
              {SERIES.filter((s) => active[s.key] !== null).map((s) => (
                <circle key={s.key} className={`ma-dot ma-dot-active ${s.className}`} cx={x(active)} cy={y(active[s.key] as number)} r={5.5} />
              ))}
            </g>
          )}
        </svg>
        {active && (
          <div className="ma-tooltip" role="status" style={{ left: `clamp(78px, ${(x(active) / W) * 100}%, calc(100% - 78px))` }}>
            <strong>{fmtDate(active.date)}</strong>
            {active.mood !== null && <span><i className="ma-swatch ma-mood" />Mood {active.mood}/5 · {MOOD_WORDS[active.mood].toLowerCase()}</span>}
            {active.anxiety !== null && <span><i className="ma-swatch ma-anx" />Anxiety {active.anxiety}/5 · {ANXIETY_WORDS[active.anxiety]}</span>}
          </div>
        )}
      </div>
      <div className="ma-foot">
        <span>Self-rated 1–5 · not a diagnosis</span>
        <button type="button" className="ma-table-toggle" aria-expanded={showTable} aria-controls={tableId}
          onClick={() => setShowTable(!showTable)}>{showTable ? 'Hide table' : 'Show as a table'}</button>
      </div>
      <table id={tableId} className={showTable ? 'ma-table' : 'visually-hidden'}>
        <caption className="visually-hidden">{title}</caption>
        <thead><tr><th scope="col">Date</th><th scope="col">Mood (1–5)</th><th scope="col">Anxiety (1–5)</th></tr></thead>
        <tbody>
          {data.map((p, i) => (
            <tr key={`${p.date}-${i}`}><td>{fmtDate(p.date)}</td><td>{p.mood ?? '–'}</td><td>{p.anxiety ?? '–'}</td></tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
