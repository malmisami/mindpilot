import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from './api';
import type { ViewScope } from './api';
import ClientApp from './client/ClientApp';
import DemoDock from './components/DemoDock';
import { setDockSlot, useDockRoomy, useDockSide, useDockSlot } from './components/dockPlace';
import { ValitukiContext } from './context';
import type { ClientTab, ProTab, ValitukiContextValue } from './context';
import PitchScreen from './pitch/PitchScreen';
import ProfessionalApp from './pro/ProfessionalApp';
import TherapistApp from './therapist/TherapistApp';
import type { Mutation, Role, ValitukiView } from './types';

const ROLE_SLUGS: Record<Role, string> = { client: 'asiakas', professional: 'ammattilainen', therapist: 'terapeutti', pitch: 'konsepti' };
const SLUG_ROLES: Record<string, Role> = { asiakas: 'client', ammattilainen: 'professional', terapeutti: 'therapist', konsepti: 'pitch' };
const CLIENT_TABS: ClientTab[] = ['koti', 'keskustelu', 'harjoitukset', 'edistyminen', 'polku'];
// Deep links of the earlier client app keep working.
const OLD_TABS: Record<string, ClientTab> = { tanaan: 'koti', viestit: 'keskustelu', suunnitelma: 'harjoitukset', matkani: 'polku',
  terapeutti: 'polku', tietoni: 'koti' };
const DEFAULT_CLIENT = 'cl-aino';
const DEFAULT_THERAPIST = 'th-anna';

// Bumped by every mutation so that a view load started earlier never overwrites a newer mutation result.
let viewVersion = 0;

interface Route { role: Role; clientId: string; therapistId: string; tab: ClientTab; proClientId: string | null }

function parseHash(): Route {
  const [, roleSlug, id, tab] = window.location.hash.replace(/^#/, '').split('/');
  const role = SLUG_ROLES[roleSlug] ?? 'client';
  return {
    role,
    clientId: role === 'client' && id ? id : DEFAULT_CLIENT,
    therapistId: role === 'therapist' && id ? id : DEFAULT_THERAPIST,
    tab: CLIENT_TABS.includes(tab as ClientTab) ? (tab as ClientTab) : OLD_TABS[tab] ?? 'koti',
    proClientId: role === 'professional' && id ? id : null,
  };
}

export default function ValitukiApp() {
  const [initial] = useState(parseHash);
  const [role, setRoleState] = useState<Role>(initial.role);
  const [clientId, setClientIdState] = useState(initial.clientId);
  const [therapistId, setTherapistIdState] = useState(initial.therapistId);
  const [clientTab, setClientTab] = useState<ClientTab>(initial.tab);
  const [proTab, setProTab] = useState<ProTab>('jono');
  const [proClientId, setProClientId] = useState<string | null>(initial.proClientId);
  const [view, setView] = useState<ValitukiView | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState('');

  const scope: ViewScope = useMemo(() => ({ clientId, therapistId }), [clientId, therapistId]);

  useEffect(() => {
    let ignore = false;
    const version = viewVersion;
    api.view(scope)
      .then((data) => {
        if (ignore || version !== viewVersion) return;
        setView(data);
        setError(null);
      })
      .catch((e: Error) => { if (!ignore) setError(e.message); });
    return () => { ignore = true; };
  }, [scope]);

  useEffect(() => {
    function onHashChange() {
      const route = parseHash();
      setRoleState(route.role);
      if (route.role === 'client') { setClientIdState(route.clientId); setClientTab(route.tab); }
      if (route.role === 'therapist') setTherapistIdState(route.therapistId);
      if (route.role === 'professional') setProClientId(route.proClientId);
    }
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  useEffect(() => {
    const id = role === 'client' ? `/${clientId}/${clientTab}` : role === 'therapist' ? `/${therapistId}`
      : role === 'professional' && proClientId ? `/${proClientId}` : '';
    const hash = `#/${ROLE_SLUGS[role]}${id}`;
    if (window.location.hash !== hash) window.history.replaceState(null, '', hash);
  }, [role, clientId, therapistId, clientTab, proClientId]);

  useEffect(() => {
    if (!message) return;
    const timer = window.setTimeout(() => setMessage(''), 5200);
    return () => window.clearTimeout(timer);
  }, [message]);

  // The phone and the backstage fill the screen below the top bar and the demo dock (--stage-top), whatever their height.
  // Measured again once the view has loaded (the demo dock only appears then) and when the dock moves beside the panel.
  const stageRef = useRef<HTMLElement>(null);
  const loaded = view !== null;
  const dockSlot = useDockSlot();
  // The demo control beside the content in the other views too, when the presenter has moved it there: the narration
  // stays in the same place through the whole demo.
  const dockSide = useDockSide();
  const dockRoomy = useDockRoomy();
  const pageDock = dockSide && dockRoomy && role !== 'client';
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    const update = () => {
      const top = Math.round(stage.getBoundingClientRect().top + window.scrollY);
      stage.parentElement?.style.setProperty('--stage-top', `${top}px`);
      // The phone keeps an iPhone's proportions (836 px tall at full size) and is scaled down to the room below the dock.
      // On a phone the same phone, frame and all (396 × 836), scaled to the screen under the demo control with a margin.
      const room = Math.min(860, Math.max(540, window.innerHeight - top - 28));
      const zoom = window.innerWidth <= 640
        ? Math.min(1, (window.innerWidth - 24) / 396, Math.max(0.4, (window.innerHeight - top - 24) / 836))
        : Math.min(1, room / 836);
      stage.parentElement?.style.setProperty('--phone-zoom', zoom.toFixed(3));
    };
    update();
    const observer = new ResizeObserver(update);
    Array.from(stage.parentElement?.children ?? []).forEach((el) => { if (el !== stage) observer.observe(el); });
    window.addEventListener('resize', update);
    return () => { observer.disconnect(); window.removeEventListener('resize', update); };
  }, [role, loaded, dockSlot]);

  const run = useCallback(async <T,>(action: (s: ViewScope) => Promise<Mutation<T>>, describe?: (result: T) => string) => {
    setBusy(true);
    setError(null);
    viewVersion += 1;
    try {
      const response = await action(scope);
      setView(response.view);
      if (describe) setMessage(describe(response.result));
      return response.result;
    } catch (e) {
      setError((e as Error).message);
      return null;
    } finally {
      setBusy(false);
    }
  }, [scope]);

  const setRole = useCallback((next: Role) => { setRoleState(next); window.scrollTo({ top: 0 }); }, []);

  const ctx: ValitukiContextValue | null = view && {
    view, scope, role, busy, run, announce: setMessage, setRole,
    setClientId: (id: string) => setClientIdState(id),
    setTherapistId: (id: string) => setTherapistIdState(id),
    clientTab, setClientTab, proTab, setProTab, proClientId, setProClientId,
  };


  return (
    <div className={`vt role-${role}`}>
      {/* The demo dock is the only bar: the concept's stages and Seuraava (→) – on every view. */}
      {ctx && (
        <ValitukiContext.Provider value={ctx}>
          <DemoDock />
        </ValitukiContext.Provider>
      )}

      <main className="stage" id="main" ref={stageRef}>
        {error && <div className="alert alert-error" role="alert">{error}</div>}
        {!view && !error && <p className="loading" role="status">Loading Mieliluotsi…</p>}
        {ctx && (
          <ValitukiContext.Provider value={ctx}>
            {role === 'client' ? <ClientApp /> : (
              <div className={`page-layout ${pageDock ? 'has-dock' : ''}`}>
                <div className="page-main">
                  {role === 'professional' && <ProfessionalApp />}
                  {role === 'therapist' && <TherapistApp />}
                  {role === 'pitch' && <PitchScreen />}
                </div>
                {pageDock && <div className="dock-slot" ref={setDockSlot} />}
              </div>
            )}
          </ValitukiContext.Provider>
        )}
      </main>

      <div className={`toast ${message ? 'toast-on' : ''}`} role="status" aria-live="polite">{message}</div>

    </div>
  );
}
