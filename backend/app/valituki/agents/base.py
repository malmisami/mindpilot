"""Helpers shared by the agents."""
from __future__ import annotations

from typing import Any, Optional

from app.valituki import adapters, records
from app.valituki.models import ClientProfile, ProfessionalReviewTask, ValitukiState
from app.valituki.store import next_id, now

CONTACT_HANDLING = ('Demo: the care team makes contact within two working days. Mieliluotsi is not monitored around the clock – '
                    'if you need help right away, call 112 or the Medical Helpline 116117.')


def create_task(state: ValitukiState, client: ClientProfile, *, agent: str, type: str, priority: str, title: str, reason: str,
                suggested: str, data: Optional[dict[str, Any]] = None, observation_id: Optional[str] = None,
                handling_note: str = '') -> ProfessionalReviewTask:
    stamp = now(state)
    task = ProfessionalReviewTask(id=next_id(state, 'task'), clientId=client.id, type=type, priority=priority, agent=agent,
                                  title=title, reason=reason, suggestedAction=suggested, underlyingData=data or {},
                                  handlingNote=handling_note, observationId=observation_id, createdAt=stamp, updatedAt=stamp,
                                  createdBy=records.agent_actor(agent), source='rule_based')
    return adapters.professional_tasks.create_task(state, task)


def open_review_items(state: ValitukiState, client_id: str) -> list[Any]:
    """Observations that keep a client in HUMAN_REVIEW_NEEDED until a professional has reviewed them."""
    items: list[Any] = [o for o in state.safetyObservations if o.clientId == client_id and o.status == 'open' and o.level >= 2]
    items += [o for o in state.wellbeingObservations if o.clientId == client_id and o.status == 'open'
              and o.kind == 'trend_decline']
    return items


def safety_locked(client: ClientProfile) -> bool:
    return bool(client.safetyLock and not client.safetyLock.dismissedAt)
