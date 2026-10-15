import { fmtTime, fmtWeekday } from '../format';
import { SparkleIcon } from '../icons';
import { AgentBadge } from './ui';

export interface TimelineItem {
  id: string; at: string; agent: string | null; title: string; detail?: string; ruleId?: string | null; aiSource?: string | null;
  kind?: 'agent' | 'client'; clientName?: string | null;
}

/** "Mitä Mieliluotsi teki?" – every autonomous step with its time, the agent that took it and the rule behind it. */
export function AgentTimeline({ items, fresh, showClient = false, compact = false, limit }: {
  items: TimelineItem[]; fresh?: Set<string>; showClient?: boolean; compact?: boolean; limit?: number;
}) {
  const shown = limit ? items.slice(0, limit) : items;
  const days: { day: string; rows: TimelineItem[] }[] = [];
  for (const item of shown) {
    const day = item.at.slice(0, 10);
    const bucket = days[days.length - 1];
    if (bucket && bucket.day === day) bucket.rows.push(item);
    else days.push({ day, rows: [item] });
  }
  if (!shown.length) return <p className="muted small">Ei vielä tapahtumia.</p>;
  return (
    <div className={`timeline ${compact ? 'timeline-compact' : ''}`}>
      {days.map((group) => (
        <section key={group.day} className="tl-day">
          <h4 className="tl-date">{fmtWeekday(group.day)}</h4>
          <ol className="tl-list">
            {group.rows.map((item) => (
              <li key={item.id} className={`tl-row ${item.kind === 'client' ? 'tl-client' : ''} ${fresh?.has(item.id) ? 'tl-fresh' : ''}`}>
                <span className="tl-time">{fmtTime(item.at)}</span>
                <span className={`tl-node ${item.agent ? `node-${item.agent}` : 'node-client'}`} aria-hidden="true" />
                <div className="tl-body">
                  <p className="tl-title">
                    {item.title}
                    {showClient && item.clientName && <span className="tl-client-name"> · {item.clientName}</span>}
                  </p>
                  {!compact && item.detail && <p className="tl-detail">{item.detail}</p>}
                  <p className="tl-meta">
                    <AgentBadge agent={item.agent} />
                    {item.ruleId && <span className="tl-rule">{item.ruleId}</span>}
                    {item.aiSource && (
                      <span className="tl-ai"><SparkleIcon size={11} /> {item.aiSource === 'live' ? 'Claude muotoili' : 'tekstipohja'}</span>
                    )}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      ))}
    </div>
  );
}
