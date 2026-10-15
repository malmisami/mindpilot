import type { ReactNode } from 'react';
import { api } from '../api';
import { useValituki } from '../context';
import { plural } from '../format';
import { FlagIcon, ForwardIcon, PlayIcon, PulseIcon, UserSearchIcon } from '../icons';

export interface DemoAction { label: string; icon: ReactNode; action: () => unknown }

/** The presenter's actions, shared by the demo dock and the step controller next to the phone. */
export function useDemoActions() {
  const { view, run, role, setRole, setClientId, setClientTab, setProTab, setProClientId } = useValituki();
  const demo = view.demo;
  const presenter = demo.presenter;

  async function openSlot() {
    const result = await run((s) => api.openSlot(s), (r) =>
      `${r.therapistName}: a client place opened up – MatchingAgent ran matching for ${plural(r.matchedClients.length, 'client')}.`);
    if (result && role === 'client') setClientTab('polku');
  }

  async function deteriorate(id: string) {
    const result = await run((s) => api.deteriorate(s, id), (r) =>
      r.trendChanged ? `Mieliluotsi noticed a change (${plural(r.days, 'day')} simulated). A review request was created for a professional.`
        : `${plural(r.days, 'day')} simulated – no change detected yet.`);
    if (result && role === 'client') setClientTab('koti');
  }

  async function firstSession(id: string) {
    await run((s) => api.firstSession(s, id), (r) => `The first session was held (${plural(r.days, 'day')} forward). Support between therapy sessions began.`);
  }

  async function endTherapy(id: string) {
    const result = await run((s) => api.demoEndTherapy(s, id), (r) =>
      `Therapy ended (${plural(r.sessions, 'session')}, ${plural(r.days, 'day')} forward). Follow-up after therapy began.`);
    if (result && role === 'client') setClientTab('polku');
  }

  const weeks = () => run((s) => api.advance(s, 14), (r) => `14 days simulated – Mieliluotsi took ${plural(r.agentActions, 'action')}.`);

  async function crisis() {
    setClientId('cl-crisis');
    setRole('client');
    await run((s) => api.crisis({ ...s, clientId: 'cl-crisis' }), () => 'Crisis path: the safety screen interrupted the usual support.');
  }

  /** Rebuild the demo at a prepared scene (Sami's journey). */
  async function jump(key: string) {
    if (!key) return;
    await run((s) => api.scene(s, key), () => `Demo moved to the stage: ${demo.scenes.find((sc) => sc.key === key)?.label ?? key}`);
    setClientId('cl-aino');
    setProClientId(null);
    setProTab('jono');
  }

  // The script follows Sami, so its next action always targets Sami.
  const NEXT: Record<string, DemoAction> = {
    weeks: { label: 'Simulate 14 days', icon: <ForwardIcon size={15} />, action: weeks },
    change: { label: 'Simulate a decline in wellbeing', icon: <PulseIcon size={15} />, action: () => deteriorate('cl-aino') },
    matches: { label: 'Open a free therapist slot', icon: <UserSearchIcon size={15} />, action: openSlot },
    firstSession: { label: 'Hold the 1st session', icon: <PlayIcon size={14} />, action: () => firstSession('cl-aino') },
    aftercare: { label: 'Therapy ends', icon: <FlagIcon size={14} />, action: () => endTherapy('cl-aino') },
  };
  const nextAction = presenter.nextKey ? NEXT[presenter.nextKey] : undefined;

  return { nextAction, weeks, deteriorate, openSlot, firstSession, endTherapy, crisis, jump };
}
