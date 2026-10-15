"""Therapy mode: after therapy starts, the therapist defines how Mieliluotsi may support the client between sessions.

Before therapy the agent runs under the approved waiting-list support protocol. After THERAPY_STARTED it switches to
"Between-session support" and may only operate inside the therapist's TherapistAgentConfiguration: the primary goal, the
allowed activities and guided CBT tools, a weekly between-session task, the check-in frequency, the
tracked item and the topics it must not address. When therapy ends (THERAPY_ENDED) the therapist's maintenance plan
(AftercarePlan) takes over: mood and anxiety are followed weekly and a change goes back to the care team.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from app.valituki import content, insights, journey, records
from app.valituki.labels import WEEKDAYS_SHORT, frequency_text
from app.valituki.labels import fmt_date_long as labels_date
from app.valituki.models import AftercarePlan, ClientProfile, TherapistAgentConfiguration, TherapyEpisode, ValitukiState
from app.valituki.store import get_therapist, next_id, now

PROTOCOL_VERSION = 'Waiting-time support protocol demo-2 (approved 1 Sep 2026, placeholder)'
WAITING_CAPABILITIES = ['Check-ins: mood and anxiety', 'Guided CBT exercises in the chat', 'Approved self-care exercises',
                        'Service navigation', 'Detecting changes', 'Preparing the matching']
CBT_TOOLS = ('thought_record', 'experiment', 'exposure')
TOOL_TITLES = {'thought_record': 'Exploring a thought', 'experiment': 'Behavioural experiment', 'exposure': 'Exposure ladder'}
BETWEEN_SESSION_PREFERENCE = ['act-values', 'act-activity-planning', 'act-small-next-step', 'act-sleep-reflection',
                              'act-paced-breathing', 'act-grounding', 'act-worry-time', 'act-support-network']


class TherapyError(ValueError):
    """The therapy-mode action is not possible (HTTP 409)."""


def episode(state: ValitukiState, client_id: str) -> Optional[TherapyEpisode]:
    items = [e for e in state.therapyEpisodes if e.clientId == client_id and e.status != 'ended']
    return items[-1] if items else None


def last_episode(state: ValitukiState, client_id: str) -> Optional[TherapyEpisode]:
    items = [e for e in state.therapyEpisodes if e.clientId == client_id]
    return items[-1] if items else None


def aftercare_plan(state: ValitukiState, client_id: str) -> Optional[AftercarePlan]:
    items = [p for p in state.aftercarePlans if p.clientId == client_id and p.active]
    return items[-1] if items else None


def active_config(state: ValitukiState, client_id: str) -> Optional[TherapistAgentConfiguration]:
    items = [c for c in state.therapistConfigs if c.clientId == client_id and c.active]
    return items[-1] if items else None


def days_for(per_week: int) -> list[int]:
    options = content.rules()['checkins']['frequencyOptions']
    if str(per_week) not in options:
        raise TherapyError('The check-in frequency must be 1, 2 or 3 times a week.')
    return list(options[str(per_week)])


def _goal_phrase(text: str) -> str:
    """'I want to be able to manage my nervousness.' → 'Manage my nervousness' (Finnish goals keep working too)."""
    phrase = re.sub(r"^(haluan|i want to|i would like to|i'd like to)\s+", '', text.strip().rstrip('.'), flags=re.IGNORECASE)
    phrase = re.sub(r'^be able to\s+', '', phrase, flags=re.IGNORECASE)
    phrase = re.sub(r'^pystyä hallitsemaan', 'hallita', phrase)
    phrase = re.sub(r'^pystyä käsittelemään', 'käsitellä', phrase)
    return phrase[:1].upper() + phrase[1:]


def suggested_plan(state: ValitukiState, client: ClientProfile) -> dict[str, Any]:
    """A starting point for the therapist, built from the client's approved information only."""
    goals = insights.active_goals(state, client.id)
    rated = {}
    for completion in state.activityCompletions:
        if completion.clientId == client.id and completion.rating:
            rated[completion.activityId] = completion.rating
    helpful = [aid for aid, rating in sorted(rated.items()) if rating >= 4]
    low = {aid for aid, rating in rated.items() if rating <= 2}
    allowed = list(helpful)
    for activity_id in BETWEEN_SESSION_PREFERENCE:
        if len(allowed) >= 3:
            break
        if activity_id not in allowed and activity_id not in low:
            allowed.append(activity_id)
    pattern = next((i for i in insights.for_client(state, client.id, kind='pattern')), None)
    if pattern and 'anxiety' in pattern.structured.get('domains', []):
        track = 'Anxiety related to office days'
    elif goals:
        track = 'Wellbeing in relation to the main goal'
    else:
        track = 'General wellbeing'
    anxious = any({'anxiety', 'work_stress', 'panic'} & set(g.topics) for g in goals)
    used = [t for t in CBT_TOOLS if any(getattr(item, 'clientId', None) == client.id for item in
                                        {'thought_record': state.thoughtRecords, 'experiment': state.experiments,
                                         'exposure': state.ladders}[t])]
    tools = used or (list(CBT_TOOLS) if anxious else ['thought_record'])
    homework = 'thought_record' if 'thought_record' in tools else None
    note = ('Before a meeting: write down the situation, the thought and the feeling 0–10, and look for a more balanced thought. '
            'Bring the entries to the session if you like.' if anxious
            else 'Write down one situation from the week: the thought, the feeling 0–10 and a more balanced thought.')
    return {'primaryGoal': _goal_phrase(goals[0].text) if goals else '', 'allowedActivityIds': allowed,
            'allowedTools': tools, 'homeworkTool': homework, 'homeworkNote': note if homework else '', 'checkInsPerWeek': 2,
            'track': track, 'doNotAddress': ''}


def configure(state: ValitukiState, client: ClientProfile, therapist_id: str, plan: dict[str, Any],
              actor: str) -> TherapistAgentConfiguration:
    current = episode(state, client.id)
    if current is None or current.therapistId != therapist_id:
        raise TherapyError("Only the client's own therapist can set up the between-session support.")
    if current.status != 'active':
        raise TherapyError('Mieliluotsi can be set up once the first session has been held.')
    library = {a.id for a in content.activities()}
    allowed = [a for a in plan.get('allowedActivityIds', []) if a in library]
    if len(allowed) != len(plan.get('allowedActivityIds', [])):
        raise TherapyError('Only exercises from the approved library can be allowed.')
    primary_goal = str(plan.get('primaryGoal', '')).strip()[:200]
    if not primary_goal:
        raise TherapyError('Write down the main goal.')
    tools = [t for t in plan.get('allowedTools') or [] if t in CBT_TOOLS]
    if len(tools) != len(plan.get('allowedTools') or []):
        raise TherapyError('Only approved CBT tools can be allowed.')
    homework = plan.get('homeworkTool') or None
    if homework is not None and homework not in CBT_TOOLS:
        raise TherapyError('Only an approved CBT tool can be given as a between-session task.')
    if homework and homework not in tools:
        tools.append(homework)  # a tool given as homework is always allowed
    per_week = int(plan.get('checkInsPerWeek', 2))
    check_days = days_for(per_week)
    stamp = now(state)
    previous = active_config(state, client.id)
    if previous:
        previous.active = False
        previous.updatedAt = stamp
    config = TherapistAgentConfiguration(
        id=next_id(state, 'tcfg'), clientId=client.id, therapistId=therapist_id, primaryGoal=primary_goal,
        allowedActivityIds=allowed, allowedTools=tools, homeworkTool=homework,
        homeworkNote=str(plan.get('homeworkNote') or '').strip()[:300] if homework else '', checkInsPerWeek=per_week,
        checkInDays=check_days,
        track=str(plan.get('track', '')).strip()[:120] or 'General wellbeing', doNotAddress=str(plan.get('doNotAddress', '')).strip()[:400],
        version=(previous.version + 1) if previous else 1, createdAt=stamp, updatedAt=stamp, createdBy=actor, source='therapist')
    state.therapistConfigs.append(config)
    current.configurationId = config.id
    current.updatedAt = stamp
    event = journey.apply(state, client, 'THERAPIST_PLAN_CONFIGURED', actor=actor, source='therapist',
                          therapist_id=therapist_id, payload={'configurationId': config.id, 'version': config.version})
    from app.valituki.agents import orchestrator  # local import: the agents import this module

    orchestrator.dispatch(state, event)
    return config


def suggested_aftercare(state: ValitukiState, client: ClientProfile) -> dict[str, Any]:
    """A starting point for the maintenance plan, from the client's approved information and practice only."""
    config = active_config(state, client.id)
    tools = list(config.allowedTools) if config and config.allowedTools else list(CBT_TOOLS)
    helpful = sorted({content.activity(c.activityId).title for c in state.activityCompletions  # type: ignore[union-attr]
                      if c.clientId == client.id and (c.rating or 0) >= 4 and content.activity(c.activityId)})
    parts = []
    if any(r.clientId == client.id for r in state.thoughtRecords):
        parts.append('keep exploring your thoughts when the nervousness rises')
    if any(lad.clientId == client.id for lad in state.ladders):
        parts.append('keep up the steps of the exposure ladder – avoidance feeds nervousness')
    if helpful:
        parts.append('found helpful: ' + ', '.join(helpful).lower())
    maintenance = ('Learnt in therapy: ' + '; '.join(parts) + '.') if parts else 'Keep using what you learnt in therapy at your own pace.'
    return {'checkInsPerWeek': 1, 'allowedTools': tools, 'maintenance': maintenance,
            'warningSigns': 'If your sleep gets worse and you start avoiding meetings again for several weeks, contact the care team.'}


def end_therapy(state: ValitukiState, client: ClientProfile, therapist_id: str, plan: dict[str, Any], actor: str) -> AftercarePlan:
    """THERAPY_ENDED: the episode ends and the maintenance plan starts ("Follow-up after therapy")."""
    current = episode(state, client.id)
    if current is None or current.therapistId != therapist_id:
        raise TherapyError("Only the client's own therapist can end the therapy.")
    if current.status != 'active':
        raise TherapyError('Therapy is not in progress.')
    per_week = int(plan.get('checkInsPerWeek', 1))
    check_days = days_for(per_week)
    tools = [t for t in plan.get('allowedTools') or [] if t in CBT_TOOLS]
    stamp = now(state)
    current.status = 'ended'
    current.endedAt = stamp
    current.updatedAt = stamp
    config = active_config(state, client.id)
    if config:
        config.active = False
        config.updatedAt = stamp
    for previous in [p for p in state.aftercarePlans if p.clientId == client.id and p.active]:
        previous.active = False
    for task in [t for t in state.practiceTasks if t.clientId == client.id and t.kind == 'homework' and t.status == 'open']:
        task.status = 'skipped'
    record = AftercarePlan(id=next_id(state, 'afc'), clientId=client.id, therapistId=therapist_id, checkInsPerWeek=per_week,
                           checkInDays=check_days, allowedTools=tools, maintenance=str(plan.get('maintenance') or '').strip()[:600],
                           warningSigns=str(plan.get('warningSigns') or '').strip()[:300], createdAt=stamp, updatedAt=stamp,
                           createdBy=actor, source='therapist')
    state.aftercarePlans.append(record)
    event = journey.apply(state, client, 'THERAPY_ENDED', actor=actor, source='therapist', therapist_id=therapist_id,
                          payload={'aftercarePlanId': record.id, 'sessions': current.sessionsHeld})
    from app.valituki.agents import orchestrator  # local import: the agents import this module

    orchestrator.dispatch(state, event)
    return record


def mode_summary(state: ValitukiState, client: ClientProfile) -> dict[str, Any]:
    if client.mode == 'aftercare_support':
        plan = aftercare_plan(state, client.id)
        last = last_episode(state, client.id)
        therapist = get_therapist(state, plan.therapistId) if plan else None
        first_name = therapist.name.split()[0] if therapist else 'Therapist'
        ended = f' on {labels_date(last.endedAt)}' if last and last.endedAt else ''
        return {'mode': 'aftercare_support', 'title': 'Follow-up after therapy', 'configured': True,
                'controlledBy': f'Maintenance plan (therapist {therapist.name})' if therapist else 'Maintenance plan',
                'therapistName': therapist.name if therapist else None, 'therapistFirstName': first_name,
                'statement': f'Therapy ended{ended}. Mieliluotsi follows your mood and anxiety, and the care team is told about '
                             'any change.',
                'checkIns': frequency_text(client.checkInDays), 'maintenance': plan.maintenance if plan else '',
                'warningSigns': plan.warningSigns if plan else '',
                'allowedTools': [{'id': t, 'title': TOOL_TITLES[t]} for t in (plan.allowedTools if plan else [])],
                'capabilities': [f'Mood and anxiety {frequency_text(client.checkInDays)}', 'Your own CBT exercises',
                                 'Maintenance plan', 'The care team is told if your wellbeing drops', 'Safety instructions']}
    if client.mode != 'therapy_support':
        return {'mode': 'waiting_support', 'title': 'Mieliluotsi', 'controlledBy': 'Approved waiting-time support protocol',
                'protocol': PROTOCOL_VERSION, 'capabilities': WAITING_CAPABILITIES, 'configured': True,
                'checkIns': frequency_text(client.checkInDays)}
    config = active_config(state, client.id)
    current = episode(state, client.id)
    therapist = get_therapist(state, current.therapistId) if current else None
    first_name = therapist.name.split()[0] if therapist else 'Therapist'
    who = f'Your therapist {first_name}' if therapist else 'Your therapist'
    base = {'mode': 'therapy_support', 'title': 'Between-session support',
            'therapistName': therapist.name if therapist else None, 'therapistFirstName': first_name}
    if config is None:
        return {**base, 'configured': False, 'controlledBy': f'Therapist {therapist.name}' if therapist else 'Therapist',
                'statement': f'{who} sets how Mieliluotsi supports you between sessions. Until then, '
                             'Mieliluotsi continues with check-ins and safety instructions only.',
                'checkIns': frequency_text(client.checkInDays), 'capabilities': ['Check-ins', 'Safety instructions']}
    activities = [a for a in content.activities() if a.id in config.allowedActivityIds]
    return {**base, 'configured': True, 'controlledBy': f'Therapist {therapist.name}' if therapist else 'Therapist',
            'statement': f'{who} has set up this plan.',
            'configuredAt': config.createdAt, 'version': config.version, 'primaryGoal': config.primaryGoal,
            'allowedActivities': [{'id': a.id, 'title': a.title} for a in activities], 'checkInsPerWeek': config.checkInsPerWeek,
            'allowedTools': [{'id': t, 'title': TOOL_TITLES[t]} for t in config.allowedTools],
            'homework': {'tool': config.homeworkTool, 'title': TOOL_TITLES[config.homeworkTool], 'note': config.homeworkNote}
            if config.homeworkTool else None,
            'checkIns': frequency_text(config.checkInDays), 'checkInDays': [WEEKDAYS_SHORT[d] for d in config.checkInDays],
            'track': config.track, 'doNotAddress': config.doNotAddress,
            'capabilities': ["Check-ins at the therapist's rhythm", 'Only the exercises and CBT tools the therapist allows',
                             f'Tracking: {config.track}', 'Safety instructions']}


def start_episode(state: ValitukiState, client: ClientProfile, booking) -> TherapyEpisode:
    stamp = now(state)
    item = TherapyEpisode(id=next_id(state, 'thep'), clientId=client.id, therapistId=booking.therapistId, bookingId=booking.id,
                          status='planned', firstSessionAt=booking.start, createdAt=stamp, updatedAt=stamp,
                          createdBy=records.agent_actor('NavigationAgent'), source='appointment_adapter')
    state.therapyEpisodes.append(item)
    return item
