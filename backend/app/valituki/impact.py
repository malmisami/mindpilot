"""Impact view ("Vaikuttavuus"). Every figure is a synthetic demo value – never a real outcome."""
from __future__ import annotations

from typing import Any

from app.valituki import content, handover
from app.valituki.journey import WAITING_STATES
from app.valituki.models import ValitukiState


def metrics(state: ValitukiState) -> dict[str, Any]:
    cohort = content.cohort()
    closed = [c for c in state.checkIns if c.status in ('completed', 'missed') and c.kind not in ('baseline', 'client_initiated')]
    completed = [c for c in closed if c.status == 'completed']
    waiting = [c for c in state.clients if c.journeyState in WAITING_STATES]
    live = {
        'checkInCompletion': f'{round(100 * len(completed) / len(closed))} %' if closed else '–',
        'changesSurfaced': str(len([o for o in state.wellbeingObservations if o.kind == 'trend_decline'])),
        'humanContacts': str(len({t.clientId for t in state.tasks if t.type == 'contact_request'})),
        'handovers': str(len([h for h in state.handovers if h.status == 'approved'])),
        'activeSupport': f'{len([c for c in waiting if c.baseline is not None])}/{len(waiting)}',
        'matchAcceptance': str(len([d for d in state.matchDecisions if d.status == 'client_selected'])),
        'rematch': str(len([f for f in state.matchFeedback if f.negative])),
        'firstSessions': str(len([b for b in state.bookings if b.status == 'completed' or handover.active_booking(state, b.clientId)])),
    }
    rows = [{**item, 'demoValue': live.get(item['key'])} for item in cohort['impact']]
    return {'label': cohort['impactLabel'], 'metrics': rows,
            'liveNote': 'The small figures ("In this demo") are calculated from the fictional demo clients.'}
