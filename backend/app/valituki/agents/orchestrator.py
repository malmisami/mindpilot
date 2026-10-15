"""Orchestrator – decides which agents an event activates, in which order, and runs the agents' daily rules.

No single prompt controls everything: every event is routed to named agents with narrow responsibilities. The
SafetyAgent has priority: while a client's immediate-safety lock is active, normal support, check-in and observation
agents are skipped for that client (the interruption is written to the audit log).
"""
from __future__ import annotations

from typing import Callable, Optional

from app.valituki import content, records
from app.valituki.agents import base, checkin, matching_agent, navigation, observation, safety_agent, support
from app.valituki.ai import AIProvider, DemoAIProvider
from app.valituki.journey import ACTIVE_STATES
from app.valituki.models import AgentEvent, ValitukiState

Handler = Callable[[ValitukiState, AgentEvent, AIProvider], None]

ROUTES: dict[str, list[tuple[str, Handler]]] = {
    'CLIENT_ENROLLED': [('NavigationAgent', navigation.on_enrolled)],
    'INSIGHTS_APPROVED': [('NavigationAgent', navigation.on_insights_approved)],
    'BASELINE_COMPLETED': [('CheckInAgent', checkin.on_baseline), ('SupportAgent', support.on_baseline),
                           ('NavigationAgent', navigation.on_baseline)],
    'CHECKIN_DUE': [('CheckInAgent', checkin.on_due), ('SupportAgent', support.on_checkin_due)],
    'CHECKIN_COMPLETED': [('ObservationAgent', observation.on_checkin_completed), ('SupportAgent', support.on_checkin_completed)],
    'CHECKIN_MISSED': [('CheckInAgent', checkin.on_missed)],
    'ACTIVITY_COMPLETED': [('SupportAgent', support.on_activity_completed)],
    'ACTIVITY_SKIPPED': [('SupportAgent', support.on_activity_skipped)],
    'WELLBEING_TREND_CHANGED': [('ObservationAgent', observation.on_trend_changed)],
    'PATTERN_DETECTED': [('ObservationAgent', observation.on_pattern_detected)],
    'USER_REQUESTED_HUMAN': [('NavigationAgent', navigation.on_user_requested_human)],
    'SAFETY_SIGNAL': [('SafetyAgent', safety_agent.on_safety_signal)],
    'HUMAN_REVIEW_COMPLETED': [('NavigationAgent', navigation.on_review_completed)],
    'MATCHING_READINESS_MET': [('NavigationAgent', navigation.on_matching_ready)],
    'THERAPIST_SLOT_OPENED': [('MatchingAgent', matching_agent.on_slot_opened)],
    'MATCHES_GENERATED': [('MatchingAgent', matching_agent.on_matches_generated), ('NavigationAgent', navigation.on_matches_generated)],
    'MATCH_SELECTED': [('NavigationAgent', navigation.on_match_selected)],
    'FIRST_SESSION_BOOKED': [('NavigationAgent', navigation.on_first_session_booked)],
    'HANDOVER_APPROVED': [('NavigationAgent', navigation.on_handover_approved)],
    'THERAPY_STARTED': [('NavigationAgent', navigation.on_therapy_started)],
    'THERAPIST_PLAN_CONFIGURED': [('CheckInAgent', checkin.on_plan_configured), ('SupportAgent', support.on_plan_configured)],
    'MATCH_FEEDBACK_RECEIVED': [('MatchingAgent', matching_agent.on_match_feedback)],
    'THOUGHT_RECORD_COMPLETED': [('SupportAgent', support.on_practice_completed)],
    'EXPERIMENT_PLANNED': [('SupportAgent', support.on_practice_completed)],
    'EXPERIMENT_REVIEWED': [('SupportAgent', support.on_practice_completed)],
    'EXPOSURE_LADDER_CREATED': [('SupportAgent', support.on_practice_completed)],
    'EXPOSURE_STEP_COMPLETED': [('SupportAgent', support.on_practice_completed)],
    'PRACTICE_TASK_COMPLETED': [('SupportAgent', support.on_practice_completed)],
    'THERAPY_ENDED': [('NavigationAgent', navigation.on_therapy_ended), ('CheckInAgent', checkin.on_therapy_ended)],
}

# Agents that keep working while the immediate-safety lock is active (everything else is interrupted).
RUNS_DURING_SAFETY_LOCK = {'SafetyAgent', 'NavigationAgent', 'MatchingAgent'}
INTERRUPTIBLE_EVENTS = {'CHECKIN_DUE', 'CHECKIN_COMPLETED', 'CHECKIN_MISSED', 'ACTIVITY_COMPLETED', 'ACTIVITY_SKIPPED',
                        'PATTERN_DETECTED', 'BASELINE_COMPLETED', 'THERAPIST_PLAN_CONFIGURED', 'THOUGHT_RECORD_COMPLETED',
                        'EXPERIMENT_PLANNED', 'EXPERIMENT_REVIEWED', 'EXPOSURE_LADDER_CREATED', 'EXPOSURE_STEP_COMPLETED',
                        'PRACTICE_TASK_COMPLETED'}


def agents_for(event_type: str) -> list[str]:
    return [name for name, _ in ROUTES.get(event_type, [])]


def dispatch(state: ValitukiState, event: AgentEvent, provider: Optional[AIProvider] = None) -> list[str]:
    """Run the agents routed to this event. Returns the names of the agents that ran."""
    provider = provider or DemoAIProvider()
    client = next((c for c in state.clients if c.id == event.clientId), None)
    locked = client is not None and base.safety_locked(client)
    ran, skipped = [], []
    for name, handler in ROUTES.get(event.type, []):
        if locked and event.type in INTERRUPTIBLE_EVENTS and name not in RUNS_DURING_SAFETY_LOCK:
            skipped.append(name)
            continue
        handler(state, event, provider)
        ran.append(name)
    if skipped:
        records.audit(state, actor=records.agent_actor('Orchestrator'), action='safety_interrupt', client_id=event.clientId,
                      event_id=event.id, detail=f'SafetyAgent interrupted the usual flow: {", ".join(skipped)} skipped '
                                                 f'({event.type}).', data={'skipped': skipped})
    return ran


def tick(state: ValitukiState, provider: Optional[AIProvider] = None) -> None:
    """The agents' daily rules for every client. Deterministic and idempotent within one demo day."""
    provider = provider or DemoAIProvider()
    at = content.rules()['clock']['dailyTickTime']
    for client in sorted(state.clients, key=lambda c: c.id):
        if client.journeyState in ACTIVE_STATES and not base.safety_locked(client):
            checkin.mark_missed(state, client, provider, at)
            support.remind_tasks(state, client, at)
            checkin.create_due(state, client, provider, at)
        navigation.evaluate_readiness(state, client, provider)
        navigation.therapy_progress(state, client, provider)
