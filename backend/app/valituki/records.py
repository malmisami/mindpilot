"""Append-only records: the audit log, the agents' visible actions ("Mitä Mieliluotsi teki?") and notifications."""
from __future__ import annotations

from typing import Any, Optional

from app.valituki import adapters
from app.valituki.models import AgentAction, AgentEvent, AuditEvent, Notification, ValitukiState
from app.valituki.store import next_id, next_seq, now

AGENT = 'agent'
COORDINATOR = 'coordinator'
SYSTEM = 'system'
DEMO = 'demo'

AGENT_LABELS = {
    'Orchestrator': 'Orchestrator',
    'SupportAgent': 'Support agent',
    'CheckInAgent': 'Check-in agent',
    'ObservationAgent': 'Observation agent',
    'MatchingAgent': 'Matching agent',
    'NavigationAgent': 'Navigation agent',
    'SafetyAgent': 'Safety agent',
}


def client_actor(client_id: str) -> str:
    return f'client:{client_id}'


def therapist_actor(therapist_id: str) -> str:
    return f'therapist:{therapist_id}'


def agent_actor(agent: str) -> str:
    return f'agent:{agent}'


def is_professional(actor: str) -> bool:
    return actor == COORDINATOR or actor.startswith('coordinator') or actor.startswith('therapist:')


def audit(state: ValitukiState, *, actor: str, action: str, detail: str, client_id: Optional[str] = None,
          event_id: Optional[str] = None, data: Optional[dict[str, Any]] = None, at: Optional[str] = None) -> AuditEvent:
    entry = AuditEvent(id=next_id(state, 'aud'), seq=next_seq(state, 'audit'), at=now(state, at), actor=actor,
                       action=action, detail=detail, clientId=client_id, eventId=event_id, data=data or {})
    state.audit.append(entry)
    return entry


def act(state: ValitukiState, *, agent: str, type: str, title: str, detail: str, event: Optional[AgentEvent] = None,
        client_id: Optional[str] = None, rule_id: Optional[str] = None, visibility: str = 'both',
        ai_task: Optional[str] = None, ai_source: Optional[str] = None, at: Optional[str] = None) -> AgentAction:
    """Record one autonomous step of an agent. Every such step is shown in "Mitä Mieliluotsi teki?"."""
    action = AgentAction(
        id=next_id(state, 'act'), seq=next_seq(state, 'action'), agent=agent, eventId=event.id if event else None,
        eventType=event.type if event else None, clientId=client_id or (event.clientId if event else None), type=type,
        title=title, detail=detail, ruleId=rule_id, visibility=visibility, createdAt=now(state, at), aiTask=ai_task,
        aiSource=ai_source,
    )
    state.actions.append(action)
    state.audit.append(AuditEvent(id=next_id(state, 'aud'), seq=next_seq(state, 'audit'), at=action.createdAt,
                                  actor=agent_actor(agent), action=f'agent:{type}', detail=f'{title}. {detail}',
                                  clientId=action.clientId, eventId=action.eventId,
                                  data={'ruleId': rule_id} if rule_id else {}))
    return action


def notify(state: ValitukiState, *, audience: str, title: str, body: str, kind: str = 'info',
           client_id: Optional[str] = None, therapist_id: Optional[str] = None, action_view: Optional[str] = None,
           event: Optional[AgentEvent] = None, agent: Optional[str] = None) -> Notification:
    notification = Notification(id=next_id(state, 'ntf'), audience=audience, clientId=client_id,
                                therapistId=therapist_id, kind=kind, title=title, body=body, createdAt=now(state),
                                actionView=action_view, eventId=event.id if event else None, agent=agent)
    return adapters.notifications.send(state, notification)
