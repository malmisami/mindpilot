import { useEffect, useRef } from 'react';
import { ChatIcon, LifebuoyIcon, PhoneIcon } from '../icons';
import type { Meta, SafetyContact } from '../types';
import { Sheet } from './ui';

function ContactList({ contacts }: { contacts: SafetyContact[] }) {
  return (
    <ul className="safety-contacts">
      {contacts.map((contact) => (
        <li key={contact.id}>
          <a className={`safety-call call-${contact.id}`} href={`tel:${contact.tel}`}>
            <span className="call-icon"><PhoneIcon size={20} /></span>
            <span className="call-text">
              <span className="call-label">{contact.label}: <strong>{contact.action}</strong></span>
              <span className="call-when">{contact.when}</span>
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}

/** Level 3: interrupts normal interaction until the client explicitly acknowledges it. Fixed text – no AI. */
export function SafetyScreen({ safety, busy, onDismiss }: { safety: Meta['safety']; busy: boolean; onDismiss: () => void }) {
  const titleRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => { titleRef.current?.focus(); }, []);
  const screen = safety.screen;
  return (
    <div className="safety-overlay">
      <div className="safety-screen" role="alertdialog" aria-modal="true" aria-labelledby="safety-title" aria-describedby="safety-desc">
        <span className="safety-icon" aria-hidden="true"><LifebuoyIcon size={30} /></span>
        <h2 id="safety-title" ref={titleRef} tabIndex={-1}>{screen.title}</h2>
        <div id="safety-desc">
          <p className="safety-lead">{screen.notEmergency}</p>
          <p>{screen.intro}</p>
        </div>
        <ContactList contacts={safety.contacts} />
        <p className="safety-demo">{screen.demoNote}</p>
        <button type="button" className="btn btn-secondary btn-block" disabled={busy} onClick={onDismiss}>{screen.dismiss}</button>
      </div>
    </div>
  );
}

/** The always-available entry point. "Tarvitsen apua nyt" is an explicit level-3 signal. */
export function HelpSheet({ safety, busy, onHelpNow, onContact, onClose }: {
  safety: Meta['safety']; busy: boolean; onHelpNow: () => void; onContact: () => void; onClose: () => void;
}) {
  return (
    <Sheet title={<><LifebuoyIcon size={20} /> Help now</>} onClose={onClose}>
      <p className="muted">Mieliluotsi is not an emergency service, and this conversation is not monitored all the time. If you need help right away:</p>
      <ContactList contacts={safety.contacts} />
      <div className="stack-sm">
        <button type="button" className="btn btn-rose btn-block" disabled={busy} onClick={onHelpNow}>I need help now</button>
        <button type="button" className="btn btn-secondary btn-block" disabled={busy} onClick={onContact}>
          <ChatIcon size={18} /> I want to talk to a professional
        </button>
        <p className="muted small">“I need help now” shows the safety instructions and sends an alert to the care team's work queue. Mieliluotsi does not
          call the emergency number for you.</p>
      </div>
    </Sheet>
  );
}
