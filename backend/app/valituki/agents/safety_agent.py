"""SafetyAgent – deterministic safety triggers. It runs before every other agent and can interrupt the normal flow.

Level 3 shows the immediate safety information, pauses normal support until the client acknowledges it and creates a
synthetic professional alert. Level 2 asks a professional to review, level 1 schedules an additional check-in. The agent
never claims that emergency services were contacted.
"""
from __future__ import annotations

from typing import Optional

from app.valituki import journey, records
from app.valituki.agents import base
from app.valituki.models import AgentEvent, ClientProfile, SafetyLock, SafetyObservation, ValitukiState
from app.valituki.safety import LEVEL2_CLIENT_TEXT, LEVEL_LABELS, SafetyResult
from app.valituki.store import next_id, now

AGENT = 'SafetyAgent'


def raise_safety(state: ValitukiState, client: ClientProfile, result: SafetyResult, *, context: str,
                 actor: str) -> Optional[SafetyObservation]:
    """Record a safety observation for a non-zero combined level and emit SAFETY_SIGNAL."""
    level = result.final_level
    if level == 0:
        return None
    stamp = now(state)
    existing = next((o for o in state.safetyObservations if o.clientId == client.id and o.status == 'open'
                     and o.level >= level and o.createdAt[:10] == state.currentDate), None)
    if existing:
        existing.triggers.extend(result.triggers)
        existing.updatedAt = stamp
        observation, is_new = existing, False
    else:
        required = {3: 'Review the situation right away following the agreed process and record the actions taken.',
                    2: 'Review the observation and decide whether to contact the client.',
                    1: 'No action needed; an additional check-in has been planned.'}[level]
        observation = SafetyObservation(
            id=next_id(state, 'saf'), clientId=client.id, level=level, deterministicLevel=result.deterministic_level,
            aiHint=result.ai_hint, aiLevel=result.ai_level, triggers=result.triggers, context=context, requiredHumanAction=required,
            status='open' if level >= 2 else 'info', createdAt=stamp, updatedAt=stamp, createdBy=actor,
            source='ai_hint' if result.deterministic_level < level else 'rule_based')
        state.safetyObservations.append(observation)
        is_new = True
    if level >= 3:
        from app.valituki import practice

        session = practice.active_session(state, client.id)
        if session:  # the person needs help now – the exercise does not continue on its own
            session.status = 'stopped'
            session.answers = {}
            session.endedAt = stamp
    event = journey.apply(state, client, 'SAFETY_SIGNAL', actor=actor, source='safety_engine',
                          payload={'level': level, 'observationId': observation.id, 'context': context, 'new': is_new,
                                   'deterministicLevel': result.deterministic_level, 'aiLevel': result.ai_level,
                                   'rules': sorted({t.ruleId for t in result.triggers})})
    from app.valituki.agents import orchestrator

    orchestrator.dispatch(state, event)
    return observation


def on_safety_signal(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = next(c for c in state.clients if c.id == event.clientId)
    level = int(event.payload['level'])
    observation = next(o for o in state.safetyObservations if o.id == event.payload['observationId'])
    rules = ', '.join(event.payload.get('rules', []))
    is_new = bool(event.payload.get('new'))
    if level >= 2 and is_new:
        task = base.create_task(
            state, client, agent=AGENT, type='safety_review', priority='urgent' if level == 3 else 'high',
            title='Safety observation awaiting review' if level == 2 else 'DEMO ALERT: immediate safety information shown',
            reason=f'{LEVEL_LABELS[level]}. Triggers: {", ".join(sorted({t.category for t in observation.triggers}))}.',
            suggested=observation.requiredHumanAction, observation_id=observation.id,
            data={'level': level, 'rules': rules, 'context': event.payload.get('context')},
            handling_note=base.CONTACT_HANDLING if level == 2 else '')
        observation.taskId = task.id
    if level == 3:
        client.safetyLock = SafetyLock(observationId=observation.id, activatedAt=event.occurredAt)
        client.todayActivity = None
        records.notify(state, audience='coordinator', client_id=client.id, kind='safety', event=event, agent=AGENT,
                       title=f'DEMO ALERT: {client.displayName} – immediate safety information shown',
                       body='The client was shown the 112, Medical Helpline 116117 and MIELI Crisis Helpline information. Mieliluotsi '
                            'has not contacted the emergency services. Review the situation following the agreed process.')
        records.act(state, agent=AGENT, type='safety_interrupt', event=event, rule_id=rules,
                    title='Paused normal support and showed the safety information',
                    detail='Shown: immediate emergency 112, Medical Helpline 116117 and MIELI Crisis Helpline 09 2525 0111. A '
                           'synthetic alert was created in the professional\'s work queue. Mieliluotsi has not contacted the '
                           'emergency services.')
    elif level == 2 and is_new:
        records.notify(state, audience='coordinator', client_id=client.id, kind='review', event=event, agent=AGENT,
                       title=f'Review requested: {client.displayName}', body=f'Safety observation (level 2). Rules: {rules}.')
        records.notify(state, audience='client', client_id=client.id, kind='review', event=event, agent=AGENT, action_view='today',
                       title='I asked a professional to look at your situation', body=LEVEL2_CLIENT_TEXT)
        records.act(state, agent=AGENT, type='request_human_review', event=event, rule_id=rules,
                    title='Asked a professional to review the situation',
                    detail='This observation is waiting for a professional review. Mieliluotsi has not changed the urgency of '
                           'your care.')
    elif level == 1:
        from app.valituki.agents import checkin

        checkin.schedule_extra(state, client, event, rules or 'SAF-L1',
                               'The answer showed signs of strain, so the client is asked how they are again tomorrow.')
