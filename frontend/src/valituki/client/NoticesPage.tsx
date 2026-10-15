import { fmtDateTime } from '../format';
import { BellIcon, ChatIcon } from '../icons';
import { AgentBadge } from '../components/ui';
import { useClientUI } from './ClientApp';

/** "Messages from Mieliluotsi": notifications (reminders, service steps) and the client's own requests to the care team. */
export default function NoticesPage() {
  const { client, openSheet } = useClientUI();
  return (
    <div className="cx-screen">
      <ul className="notice-list">
        {client.notifications.map((n) => (
          <li key={n.id} className={`notice-item kind-${n.kind} ${n.read ? '' : 'unread'}`}>
            <span className="notice-icon"><BellIcon size={16} /></span>
            <div>
              <p className="notice-title">{n.title}</p>
              <p className="notice-body">{n.body}</p>
              <p className="notice-meta">{fmtDateTime(n.createdAt)} {n.agent && <AgentBadge agent={n.agent} />}</p>
            </div>
          </li>
        ))}
      </ul>
      {client.requests.length > 0 && (
        <section className="cx-section">
          <h2 className="cx-h2">Your requests to the care team</h2>
          <ul className="request-list">
            {client.requests.map((r) => (
              <li key={r.id}>
                <strong>{r.title}</strong>
                <span className="muted small">{fmtDateTime(r.createdAt)} · {r.status === 'open' ? 'Waiting to be contacted' : r.status === 'contact_requested' ? 'Contact arranged' : 'Handled'}</span>
                {r.outcome && <span className="small">{r.outcome}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
      <button type="button" className="cx-btn cx-btn-ghost cx-btn-block" onClick={() => openSheet({ type: 'contact' })}>
        <ChatIcon size={18} /> I want to talk to a professional
      </button>
    </div>
  );
}
