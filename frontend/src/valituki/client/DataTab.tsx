import { useState } from 'react';
import { api } from '../api';
import { useValituki } from '../context';
import { fmtDateTime, fmtShort } from '../format';
import { CheckIcon, CrossIcon, EditIcon, LayersIcon, SparkleIcon, TrashIcon } from '../icons';
import { Empty, Pill, SharingControl } from '../components/ui';
import type { ConsentScope, InsightRow } from '../types';
import { useClientUI } from './ClientApp';
import { plural } from '../format';

export default function DataTab() {
  const { view, run, busy } = useValituki();
  const { client } = useClientUI();
  const memory = client.memory;
  const consents = view.meta.labels.consents;
  return (
    <div className="screen data">
      <h1 className="display-sm">What Mieliluotsi remembers about me</h1>
      <p className="lead-sm">You decide what information is shared. For each item you can see where it came from and who may use it.</p>

      {memory.pending.length > 0 && (
        <section className="card pending-card">
          <h3 className="card-title"><SparkleIcon size={17} /> Waiting for your decision</h3>
          {memory.pending.map((item) => (
            <div key={item.id} className="pending-item">
              <p>{item.text}</p>
              <div className="row-gap">
                <button type="button" className="btn btn-violet btn-sm" disabled={busy} onClick={() => run((s) => api.decideInsight(s, client.id, item.id, 'approve'))}>
                  <CheckIcon size={15} /> This feels right</button>
                <button type="button" className="btn btn-quiet btn-sm" disabled={busy} onClick={() => run((s) => api.decideInsight(s, client.id, item.id, 'reject'))}>
                  <CrossIcon size={15} /> This doesn't describe my situation</button>
              </div>
            </div>
          ))}
        </section>
      )}

      {memory.groups.map((group) => (
        <section key={group.key} className="mem-group">
          <h2 className="mem-title">{group.label}</h2>
          {group.items.length === 0 ? <p className="muted small">Nothing saved.</p>
            : group.items.map((item) => <MemoryItem key={item.id} item={item} />)}
        </section>
      ))}

      <section className="card">
        <h3 className="card-title">Your consents for the service</h3>
        {(Object.keys(consents) as (keyof ConsentScope)[]).map((key) => (
          <label key={key} className="switch-row">
            <span><span className="switch-title">{consents[key].title}</span><span className="switch-desc">{consents[key].description}</span></span>
            <input type="checkbox" className="switch" checked={memory.consent[key]} disabled={busy}
              onChange={(e) => run((s) => api.setConsent(s, client.id, { [key]: e.target.checked }), () => 'Consent updated and recorded.')} />
          </label>
        ))}
      </section>

      {memory.fitProfile && (
        <section className="card">
          <div className="card-row"><h3 className="card-title"><LayersIcon size={17} /> Therapy Fit Profile</h3><Pill tone="brand">version {memory.fitProfile.version}</Pill></div>
          <ol className="changelog">
            {[...memory.fitProfile.changelog].reverse().map((c) => (
              <li key={c.version}><span className="muted small">v{c.version} · {fmtShort(c.at)}</span> {c.change}</li>
            ))}
          </ol>
        </section>
      )}

      {memory.permissionHistory.length > 0 && (
        <section className="card">
          <h3 className="card-title">Changes to permissions</h3>
          <ul className="perm-log">
            {memory.permissionHistory.map((p, i) => (
              <li key={i}><span className="muted small">{fmtDateTime(p.at)}</span> {p.title}: professional {p.professional ? 'yes' : 'no'},
                matching {p.matching ? 'yes' : 'no'}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="card">
        <h3 className="card-title">What is saved</h3>
        <p className="small">{plural(memory.stored.checkIns, 'check-in', 'check-ins')} · {plural(memory.stored.journal, 'diary entry', 'diary entries')} (only
          you can see them) · {plural(memory.stored.messages, 'message', 'messages')} · the chat history is not shared with anyone</p>
        {memory.handover && <p className="small">Summary for the therapist: {memory.handover.statusLabel}</p>}
      </section>
      {memory.pending.length === 0 && memory.groups.every((g) => g.items.length === 0) && (
        <Empty title="Mieliluotsi doesn't remember anything about you yet">Information is saved only once you approve it.</Empty>
      )}
    </div>
  );
}

function MemoryItem({ item }: { item: InsightRow }) {
  const { run, busy } = useValituki();
  const { client } = useClientUI();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(item.text);
  return (
    <article className="mem-item">
      <div className="mem-head">
        <p className="mem-kind">{item.title}</p>
        {item.editedByClient && <Pill tone="brand" icon={<EditIcon size={11} />}>Edited</Pill>}
      </div>
      {editing ? (
        <div className="stack-sm">
          <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} aria-label={`Edit: ${item.title}`} />
          <div className="row-gap">
            <button type="button" className="btn btn-primary btn-sm" disabled={busy || !text.trim()}
              onClick={async () => { await run((s) => api.editInsight(s, client.id, item.id, text), () => 'Information updated.'); setEditing(false); }}>Save</button>
            <button type="button" className="btn btn-quiet btn-sm" onClick={() => { setText(item.text); setEditing(false); }}>Cancel</button>
          </div>
        </div>
      ) : <p className="mem-text">{item.text}</p>}
      <p className="mem-meta">{item.sourceLabel} · {fmtShort(item.date)} · {item.originLabel}</p>
      <p className="mem-q">Who may use this information?</p>
      <SharingControl sharing={item.sharing} busy={busy}
        onChange={(next) => run((s) => api.setSharing(s, client.id, item.id, next), () =>
          `Permission updated: ${!next.professional && !next.matching ? 'only you' : [next.professional && 'professional', next.matching && 'matching'].filter(Boolean).join(' + ')}.`)} />
      <div className="mem-actions">
        {item.editable && !editing && <button type="button" className="btn btn-quiet btn-sm" disabled={busy} onClick={() => setEditing(true)}><EditIcon size={14} /> Edit</button>}
        <button type="button" className="btn btn-quiet btn-sm" disabled={busy}
          onClick={() => run((s) => api.removeInsight(s, client.id, item.id), () => 'Information deleted – it is no longer used or shared.')}>
          <TrashIcon size={14} /> Delete
        </button>
      </div>
    </article>
  );
}
