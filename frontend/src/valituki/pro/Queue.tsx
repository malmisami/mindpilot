import { useMemo, useState } from 'react';
import { useValituki } from '../context';
import { fmtShort, fmtThousands, plural } from '../format';
import { AlertIcon, ChevronRightIcon, CrossIcon, InfoIcon, SortIcon } from '../icons';
import { Synthetic } from '../components/ui';
import type { QueueRow } from '../types';

type SortKey = 'review' | 'name' | 'waitingDays' | 'lastCheckIn' | 'trend' | 'matching';
const REVIEW_ORDER: Record<string, number> = { safety: 0, requested: 1, contact: 2, matching_review: 3, task: 4, reviewed: 5, none: 6 };
const TREND_ORDER: Record<string, number> = { declining: 0, insufficient: 1, stable: 2, improving: 3 };

const initials = (name: string) => name.split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase();
const share = (value: number, total: number) => `${Math.round((value / Math.max(1, total)) * 100)}% of the list`;

export default function Queue() {
  const { view, setProClientId } = useValituki();
  const pro = view.professional;
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'review', dir: 1 });
  // A card in the overview filters the list to its group; the first card (and a second click) shows everyone again.
  const [filter, setFilter] = useState<string | null>(null);

  const rows = useMemo(() => {
    const value = (row: QueueRow): string | number => {
      switch (sort.key) {
        case 'review': return REVIEW_ORDER[row.reviewKey] * 1000 - (row.waitingDays ?? 0);
        case 'name': return row.name;
        case 'waitingDays': return row.waitingDays ?? -1;
        case 'lastCheckIn': return row.lastCheckIn ?? '';
        case 'trend': return TREND_ORDER[row.trend] ?? 9;
        case 'matching': return row.matchingStatus;
      }
    };
    return pro.queue.filter((row) => !filter || row.bucket === filter).sort((a, b) => {
      const va = value(a);
      const vb = value(b);
      return (va < vb ? -1 : va > vb ? 1 : 0) * sort.dir;
    });
  }, [pro.queue, sort, filter]);

  function header(key: SortKey, label: string) {
    const active = sort.key === key;
    return (
      <th scope="col" aria-sort={active ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
        <button type="button" className={`th-sort ${active ? 'active' : ''}`} onClick={() => setSort({ key, dir: active ? (sort.dir === 1 ? -1 : 1) : 1 })}>
          {label} <SortIcon size={13} />
        </button>
      </th>
    );
  }

  const buckets = pro.overview.buckets;
  const activeBucket = buckets.find((b) => b.key === filter) ?? null;
  const samples = activeBucket ? pro.overview.samples.filter((sample) => sample.bucket === activeBucket.key) : [];
  return (
    <div className="queue-page">
      <section className="kpi-band" aria-label="Filter the client list">
        <button type="button" className="kpi kpi-hero" aria-pressed={filter === null} onClick={() => setFilter(null)}>
          <span className="kpi-label">Active clients</span>
          <span className="kpi-value">{fmtThousands(pro.overview.total)}</span>
          <span className="kpi-sub">on the therapy waiting list, using Mieliluotsi</span>
          {/* The whole queue as one bar: each group's share, in the group's colour. */}
          <span className="kpi-stack" aria-hidden="true">
            {buckets.map((b) => <i key={b.key} className={`kpi-seg kpi-${b.key}`} style={{ flexGrow: b.value }} />)}
          </span>
        </button>
        <div className="kpi-groups">
          {buckets.map((b) => (
            <button key={b.key} type="button" className={`kpi kpi-${b.key}`} aria-pressed={filter === b.key}
              onClick={() => setFilter(filter === b.key ? null : b.key)}>
              <span className="kpi-label"><span className="kpi-dot" aria-hidden="true" />{b.label}</span>
              <span className="kpi-value">{fmtThousands(b.value)}</span>
              <span className="kpi-share" aria-hidden="true"><i style={{ width: `${(b.value / Math.max(1, pro.overview.total)) * 100}%` }} /></span>
              <span className="kpi-sub">{share(b.value, pro.overview.total)}{b.live ? ` · ${b.live} in the demo` : ''}</span>
            </button>
          ))}
        </div>
      </section>
      <Synthetic>{pro.overview.syntheticNote} The figures describe the situation – they are not a clinical prioritisation. Mieliluotsi has not prioritised clients.</Synthetic>

      <section className="card queue-card">
        <div className="card-row">
          <h2 className="card-title-lg">Client list
            {activeBucket && (
              <button type="button" className="queue-filter" onClick={() => setFilter(null)} aria-label={`Remove filter: ${activeBucket.label}`}>
                {activeBucket.label} <CrossIcon size={13} />
              </button>
            )}
          </h2>
          <p className="muted small"><InfoIcon size={14} /> Work queue order: open review requests first, then waiting time. The urgency of care is
            always set by a professional.</p>
        </div>
        <div className="table-wrap">
          <table className="table queue-table">
            <thead>
              <tr>
                {header('name', 'Client')}
                {header('waitingDays', 'Waiting time')}
                {header('lastCheckIn', 'Latest check-in')}
                {header('trend', 'Direction')}
                <th scope="col">Latest observation</th>
                {header('review', 'Professional review')}
                {header('matching', 'Matching')}
                <th scope="col">Next action</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && samples.length === 0 && (
                <tr className="queue-empty"><td colSpan={8}>There are no demo clients in this group – the figure {fmtThousands(activeBucket?.value ?? 0)} is a synthetic figure for the background cohort.</td></tr>
              )}
              {rows.map((row) => (
                <tr key={row.clientId} className={`${row.demoPrimary ? 'row-primary' : ''} review-${row.reviewKey}`} onClick={() => setProClientId(row.clientId)}>
                  <td>
                    <button type="button" className="row-link" onClick={(e) => { e.stopPropagation(); setProClientId(row.clientId); }}>
                      <span className="row-avatar" aria-hidden="true">{initials(row.name)}</span>
                      <span className="row-who">
                        <span className="row-name">{row.name}</span>
                        <span className="row-sub">{row.stateLabel}</span>
                      </span>
                    </button>
                  </td>
                  <td className="num">{row.waitingDays !== null ? plural(row.waitingDays, 'day') : '–'}</td>
                  <td>{row.lastCheckIn ? fmtShort(row.lastCheckIn) : '–'}</td>
                  <td><span className={`trend trend-${row.trend}`} title={row.trendLabel}>{row.trendArrow}</span></td>
                  <td className="cell-obs">{row.latestObservation ?? '–'}</td>
                  <td><span className={`review-pill rp-${row.reviewKey}`}>{row.reviewKey === 'safety' && <AlertIcon size={13} />}{row.reviewLabel}</span></td>
                  <td className="small">{row.matchingStatus}</td>
                  <td className="cell-next">{row.nextAction} <ChevronRightIcon size={15} /></td>
                </tr>
              ))}
              {samples.length > 0 && (
                <tr className="queue-sample-head"><td colSpan={8}>{pro.overview.samplesNote}</td></tr>
              )}
              {samples.map((sample) => (
                <tr key={sample.name} className={`row-sample review-${sample.reviewKey}`}>
                  <td>
                    <span className="row-link">
                      <span className="row-avatar" aria-hidden="true">{initials(sample.name)}</span>
                      <span className="row-who">
                        <span className="row-name">{sample.name} <span className="sample-tag">Example</span></span>
                        <span className="row-sub">Age {sample.age} · background cohort</span>
                      </span>
                    </span>
                  </td>
                  <td className="num">{plural(sample.waitingDays, 'day')}</td>
                  <td>{fmtShort(sample.lastCheckIn)}</td>
                  <td><span className={`trend trend-${sample.trend}`} title={sample.trendLabel}>{sample.trendArrow}</span></td>
                  <td className="cell-obs">{sample.latestObservation ?? '–'}</td>
                  <td><span className={`review-pill rp-${sample.reviewKey}`}>{sample.reviewLabel}</span></td>
                  <td className="small">{sample.matchingStatus}</td>
                  <td className="cell-next muted">{sample.nextAction}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted small">Showing the demo's {plural(rows.length, 'fictional client')}{activeBucket ? ` in the group “${activeBucket.label}”` : ''}{samples.length ? ` and ${plural(samples.length, 'example profile')}` : ''}. The background cohort's {fmtThousands(pro.overview.total - pro.overview.liveClients)} clients
          are synthetic figures.</p>
      </section>

      {pro.notifications.length > 0 && (
        <section className="card">
          <h2 className="card-title">Notifications for the care team</h2>
          <ul className="pro-notes">
            {pro.notifications.slice(0, 6).map((n) => (
              <li key={n.id} className={`kind-${n.kind}`}>
                <button type="button" className="note-link" onClick={() => n.clientId && setProClientId(n.clientId)}>
                  <strong>{n.title}</strong> <span className="muted">{n.body}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
