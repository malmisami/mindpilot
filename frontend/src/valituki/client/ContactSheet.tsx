import { useState } from 'react';
import { api } from '../api';
import { useValituki } from '../context';
import { Sheet } from '../components/ui';
import { useClientUI } from './ClientApp';

export default function ContactSheet({ initialReason, onClose }: { initialReason?: string; onClose: () => void }) {
  const { view, run, busy } = useValituki();
  const { client } = useClientUI();
  const [reason, setReason] = useState(initialReason ?? 'wellbeing');
  const [message, setMessage] = useState('');
  const reasons = view.meta.labels.contactReasons;

  async function send() {
    const result = await run((s) => api.requestHuman(s, client.id, reason, message),
      () => 'Your request went to the care team straight away. Demo: they will contact you within two working days.');
    if (result) onClose();
  }

  return (
    <Sheet title="I want to talk to a professional" onClose={onClose}
      footer={<button type="button" className="btn btn-primary btn-block" disabled={busy} onClick={send}>Send request</button>}>
      <p className="muted">Your request goes to the care team straight away. It is not an emergency service – if you need help right now, use “Help now”.</p>
      <div className="radio-list" role="radiogroup" aria-label="Topic">
        {Object.entries(reasons).map(([key, label]) => (
          <label key={key} className="radio-row">
            <input type="radio" name="contact-reason" checked={reason === key} onChange={() => setReason(key)} /> {label}
          </label>
        ))}
      </div>
      <label className="q" htmlFor="contact-msg">Message (optional)</label>
      <textarea id="contact-msg" rows={3} value={message} onChange={(e) => setMessage(e.target.value)} />
    </Sheet>
  );
}
