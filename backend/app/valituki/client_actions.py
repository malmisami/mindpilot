"""Actions the client takes: check-ins, activities, the support conversation, decisions about what Mieliluotsi remembers,
help requests, the therapist choice, the handover and the collaboration feedback after the first session.

Every free-text input passes the deterministic Safety Engine before anything else happens.
"""
from __future__ import annotations

from typing import Any, Optional

from app.valituki import content, handover, insights, intake, journey, matching_flow, practice, records, therapy
from app.valituki.agents import orchestrator, safety_agent, support
from app.valituki.ai import AIProvider, DemoAIProvider
from app.valituki.journey import ACTIVE_STATES, JourneyError
from app.valituki.labels import ANXIETY_SCALE, CONTACT_REASONS, DOMAINS, MOOD_SCALE
from app.valituki.models import (
    ActivityCompletion,
    ChatMessage,
    CheckIn,
    ClientProfile,
    GuidedSession,
    MatchFeedback,
    ValitukiState,
    WellbeingMetric,
)
from app.valituki.practice import PracticeError
from app.valituki.safety import SAFETY_REPLY, SAFETY_SCREEN, assess, evaluate_structured, evaluate_text, explicit_help_trigger
from app.valituki.store import next_id, now


class ClientActionError(ValueError):
    """The client action is not possible (HTTP 400/409)."""


def actor(client: ClientProfile) -> str:
    return records.client_actor(client.id)


def _require(client: ClientProfile, states: tuple[str, ...], what: str) -> None:
    if client.journeyState not in states:
        raise JourneyError(f'{what} is not possible in the stage "{journey.label(client.journeyState)}".')


# --- consent ---------------------------------------------------------------------------------------------------------

def set_consent(state: ValitukiState, client: ClientProfile, scope: dict[str, bool]) -> None:
    previous = client.consent.model_copy()
    intake.record_consent(state, client, scope, actor(client))
    changed = {k: v for k, v in client.consent.model_dump().items() if getattr(previous, k) != v}
    if not changed:
        return
    event = journey.apply(state, client, 'CONSENT_UPDATED', actor=actor(client), source='client', payload={'changed': changed})
    if changed.get('proactiveCheckins') is False:
        for due in [c for c in state.checkIns if c.clientId == client.id and c.status == 'due']:
            due.status = 'missed'
        records.act(state, agent='CheckInAgent', type='stop_proactive', event=event, title='Stopped the proactive check-ins',
                    detail='You can still do a check-in yourself, and the safety instructions are always available.')
    elif changed.get('proactiveCheckins') is True:
        client.nextCheckInDate = state.currentDate
        records.act(state, agent='CheckInAgent', type='resume_proactive', event=event, title='Resumed the check-ins',
                    detail='Consent was given.')


# --- check-ins -------------------------------------------------------------------------------------------------------

def submit_checkin(state: ValitukiState, client: ClientProfile, mood: int, changes: dict[str, str], note: str = '', *,
                   anxiety: Optional[int] = None, track_score: Optional[int] = None, no_change: bool = False,
                   provider: Optional[AIProvider] = None, who: Optional[str] = None, at: Optional[str] = None,
                   via_session: Optional[GuidedSession] = None) -> dict[str, Any]:
    """Mood 1–5 and anxiety 1–5 ("How much anxiety or nervousness?"), what changed and an optional journal note.

    Usually answered as a short conversation in the chat (practice.checkin); the simulation and the API call this directly,
    and the answer is then shown in the chat as one message."""
    _require(client, ACTIVE_STATES, 'Check-in')
    who = who or actor(client)
    if not 1 <= int(mood) <= 5:
        raise ClientActionError('Choose your wellbeing on a scale of 1–5.')
    if anxiety is not None and not 1 <= int(anxiety) <= 5:
        raise ClientActionError('Choose your anxiety on a scale of 1–5.')
    clean = {k: v for k, v in (changes or {}).items() if k in DOMAINS and v in ('worse', 'better')}
    note = (note or '').strip()[:1000]
    stamp = now(state, at)
    item = next((c for c in state.checkIns if c.clientId == client.id and c.status == 'due'), None)
    if item is None:
        config = therapy.active_config(state, client.id) if client.mode == 'therapy_support' else None
        item = CheckIn(id=next_id(state, 'chk'), clientId=client.id, kind='client_initiated', dueDate=state.currentDate, status='due',
                       mode=client.mode, trackLabel=config.track if config else None, createdAt=stamp, updatedAt=stamp,
                       createdBy=who, source='client')
        state.checkIns.append(item)
    retained = client.consent.storeHistory
    item.status = 'completed'
    item.completedAt = stamp
    item.updatedAt = stamp
    item.retained = retained
    item.mood = int(mood) if retained else None
    item.anxiety = int(anxiety) if retained and anxiety is not None else None
    item.changes = clean if retained else {}
    item.noChange = bool(no_change) and not clean
    item.note = note if retained else ''
    item.trackScore = int(track_score) if retained and track_score else None
    if retained:
        state.metrics.append(WellbeingMetric(id=next_id(state, 'met'), clientId=client.id, checkInId=item.id, date=stamp[:10],
                                             metric='mood', value=float(mood)))
        if anxiety is not None:
            state.metrics.append(WellbeingMetric(id=next_id(state, 'met'), clientId=client.id, checkInId=item.id, date=stamp[:10],
                                                 metric='anxiety_level', value=float(anxiety)))
        for domain, direction in clean.items():
            state.metrics.append(WellbeingMetric(id=next_id(state, 'met'), clientId=client.id, checkInId=item.id, date=stamp[:10],
                                                 metric=domain, value=-1.0 if direction == 'worse' else 1.0))
        if item.trackScore:
            state.metrics.append(WellbeingMetric(id=next_id(state, 'met'), clientId=client.id, checkInId=item.id, date=stamp[:10],
                                                 metric='track', value=float(item.trackScore)))
    _close_checkin_session(state, client, item, via_session, int(mood), anxiety, note)
    event = journey.apply(state, client, 'CHECKIN_COMPLETED', actor=who, source='client', at=stamp[11:16],
                          payload={'checkInId': item.id, 'retained': retained, 'mood': int(mood), 'anxiety': anxiety,
                                   'late': item.kind == 'client_initiated'})
    result = assess(evaluate_text(note) + evaluate_structured(mood=int(mood)))
    if result.final_level:
        safety_agent.raise_safety(state, client, result, context='checkin', actor=who)
    orchestrator.dispatch(state, event, provider or DemoAIProvider())  # interrupted by the SafetyAgent when level 3
    return {'checkInId': item.id, 'safetyLevel': result.final_level}


def _close_checkin_session(state: ValitukiState, client: ClientProfile, item: CheckIn, via_session: Optional[GuidedSession],
                           mood: int, anxiety: Optional[int], note: str) -> None:
    """The chat's check-in conversation ends with the check-in. An answer given elsewhere is shown in the chat as one line."""
    session = via_session or practice.active_session(state, client.id)
    if session is not None and session.tool == 'checkin':
        session.status = 'completed'
        session.resultId = item.id
        session.endedAt = item.completedAt
        session.step = None
    if via_session is None:
        parts = [f'Wellbeing {mood}/5 · {MOOD_SCALE[mood].lower()}']
        if anxiety is not None:
            parts.append(f'anxiety {anxiety}/5 · {ANXIETY_SCALE[int(anxiety)].lower()}')
        line = ' · '.join(parts) + (f'\n{note}' if note else '')
        practice.say(state, client, line, role='client', kind='answer', sessionId=session.id if session else None,
                     value={'mood': mood, 'anxiety': anxiety})


# --- activities --------------------------------------------------------------------------------------------------------

def _activity(activity_id: str):
    activity = content.activity(activity_id)
    if activity is None:
        raise ClientActionError('The exercise is not in the approved library.')
    return activity


def complete_activity(state: ValitukiState, client: ClientProfile, activity_id: str, rating: Optional[int], note: str = '', *,
                      at: Optional[str] = None) -> ActivityCompletion:
    _require(client, ACTIVE_STATES, 'Logging an exercise')
    activity = _activity(activity_id)
    stamp = now(state, at)
    rating = int(rating) if rating else None
    if rating is not None and not 1 <= rating <= 5:
        raise ClientActionError('Give a rating on a scale of 1–5.')
    completion = ActivityCompletion(id=next_id(state, 'actc'), clientId=client.id, activityId=activity.id, activityVersion=activity.version,
                                    status='completed', rating=rating, note=(note or '')[:300], mode=client.mode, createdAt=stamp,
                                    updatedAt=stamp, createdBy=actor(client), source='client')
    state.activityCompletions.append(completion)
    if client.todayActivity and client.todayActivity.activityId == activity.id:
        client.todayActivity.status = 'completed'
    event = journey.apply(state, client, 'ACTIVITY_COMPLETED', actor=actor(client), source='client', at=stamp[11:16],
                          payload={'activityId': activity.id, 'rating': rating, 'completionId': completion.id})
    triggers = evaluate_text(note)
    if triggers:
        safety_agent.raise_safety(state, client, assess(triggers), context='activity', actor=actor(client))
    orchestrator.dispatch(state, event)
    return completion


def skip_activity(state: ValitukiState, client: ClientProfile, activity_id: Optional[str] = None, *,
                  at: Optional[str] = None) -> Optional[ActivityCompletion]:
    _require(client, ACTIVE_STATES, 'Skipping an exercise')
    activity_id = activity_id or (client.todayActivity.activityId if client.todayActivity else None)
    if not activity_id:
        return None
    activity = _activity(activity_id)
    stamp = now(state, at)
    completion = ActivityCompletion(id=next_id(state, 'actc'), clientId=client.id, activityId=activity.id, activityVersion=activity.version,
                                    status='skipped', mode=client.mode, createdAt=stamp, updatedAt=stamp, createdBy=actor(client),
                                    source='client')
    state.activityCompletions.append(completion)
    if client.todayActivity and client.todayActivity.activityId == activity.id:
        client.todayActivity.status = 'skipped'
    event = journey.apply(state, client, 'ACTIVITY_SKIPPED', actor=actor(client), source='client', at=stamp[11:16],
                          payload={'activityId': activity.id})
    orchestrator.dispatch(state, event)
    return completion


# --- what Mieliluotsi remembers ------------------------------------------------------------------------------------------

def decide_insight(state: ValitukiState, client: ClientProfile, insight_id: str, decision: str) -> None:
    """"This feels right" / "This does not describe my situation" for a proposed insight (e.g. a detected pattern)."""
    item = insights.get(state, client, insight_id)
    if decision == 'approve':
        insights.approve(state, client, item, actor(client))
        event = journey.apply(state, client, 'INSIGHTS_APPROVED', actor=actor(client), source='client',
                              payload={'insightIds': [item.id], 'reason': f'You approved the observation: {item.text}'})
        orchestrator.dispatch(state, event)
    elif decision == 'reject':
        insights.reject(state, client, item, actor(client))
        records.act(state, agent='ObservationAgent', type='pattern_rejected', client_id=client.id,
                    title='Noted that the observation does not describe your situation',
                    detail='The observation is not used for anything. Thank you for the feedback.')
    else:
        raise ClientActionError('Unknown decision.')


def edit_insight(state: ValitukiState, client: ClientProfile, insight_id: str, text: str) -> None:
    from app.valituki import fit_profile

    item = insights.get(state, client, insight_id)
    insights.update_text(state, client, item, text, actor(client))
    fit_profile.rebuild(state, client, agent='NavigationAgent', reason=f'You edited the information: {item.title}')


def set_insight_sharing(state: ValitukiState, client: ClientProfile, insight_id: str, professional: bool, matching: bool) -> None:
    from app.valituki import fit_profile

    item = insights.get(state, client, insight_id)
    insights.set_sharing(state, client, item, professional=professional, matching=matching, actor=actor(client))
    fit_profile.rebuild(state, client, agent='NavigationAgent',
                        reason=f'Permission changed: {item.title} – ' + ('allowed in matching' if matching else 'not used in matching'))


def remove_insight(state: ValitukiState, client: ClientProfile, insight_id: str) -> None:
    from app.valituki import fit_profile

    item = insights.get(state, client, insight_id)
    insights.remove(state, client, item, actor(client))
    fit_profile.rebuild(state, client, agent='NavigationAgent', reason=f'You removed the information: {item.title}')


# --- conversation ----------------------------------------------------------------------------------------------------

def _message(state: ValitukiState, client: ClientProfile, role: str, text: str, **fields: Any) -> ChatMessage:
    message = ChatMessage(id=next_id(state, 'msg'), clientId=client.id, role=role, text=text, createdAt=now(state),
                          retained=client.consent.storeHistory, **fields)
    state.chat.append(message)
    return message


def send_message(state: ValitukiState, client: ClientProfile, text: str, provider: Optional[AIProvider] = None) -> dict[str, Any]:
    _require(client, ACTIVE_STATES, 'Chatting')
    text = text.strip()[:1500]
    if not text:
        raise ClientActionError('Write a message.')
    provider = provider or DemoAIProvider()
    session = practice.active_session(state, client.id)
    if session is not None and not support.locked(client):
        # A guided exercise is in progress: the message answers its current question (safety is checked there first).
        pre = assess(evaluate_text(text))
        if pre.final_level < 3:
            try:
                return practice.answer(state, client, text, provider, actor(client), from_text=True)
            except PracticeError:
                practice.say(state, client, text, role='client')
                if pre.final_level >= 1:
                    safety_agent.raise_safety(state, client, pre, context='practice', actor=actor(client))
                practice.reask(state, client)
                return {'safety': {'level': pre.final_level}, 'reask': True}
    _message(state, client, 'client', text)
    if support.locked(client):
        _message(state, client, 'assistant', SAFETY_REPLY, safetyLevel=3, textSource='fixed')
        return {'safety': {'level': 3, 'screen': SAFETY_SCREEN}, 'locked': True}
    triggers = evaluate_text(text)
    deterministic = assess(triggers)
    if deterministic.final_level >= 3:
        # A deterministic level-3 trigger interrupts before any language model is called.
        safety_agent.raise_safety(state, client, deterministic, context='chat', actor=actor(client))
        reply = _message(state, client, 'assistant', SAFETY_REPLY, safetyLevel=3, textSource='fixed')
        records.audit(state, actor=records.agent_actor('SafetyAgent'), action='chat_safety_interrupt', client_id=client.id,
                      detail='A deterministic rule triggered level 3 – the language model was not called.')
        return {'safety': {'level': 3, 'screen': SAFETY_SCREEN}, 'messageId': reply.id}
    response = support.respond(state, client, text, provider, deterministic.final_level)
    result = assess(triggers, ai_hint=response.safetyHint, ai_next_action=response.suggestedNextAction)
    if result.final_level >= 3:
        safety_agent.raise_safety(state, client, result, context='chat', actor=actor(client))
        reply = _message(state, client, 'assistant', SAFETY_REPLY, safetyLevel=3, textSource='fixed')
        return {'safety': {'level': 3, 'screen': SAFETY_SCREEN}, 'messageId': reply.id}
    tool = response.suggestedTool if response.suggestedTool in practice.allowed_tools(state, client) else None
    if tool:
        # The reply offers a guided tool; the client decides ("Yes, let's explore it" / "Not now").
        labels = {'thought_record': "Yes, let's explore it", 'exposure': "Let's build a ladder", 'experiment': "Let's plan an experiment",
                  'checkin': 'Do a check-in'}
        prefill = {'situation': text} if tool == 'thought_record' else {}
        reply = practice.offer(state, client, response.supportiveResponse, [(f'start:{tool}', labels[tool]), ('dismiss', 'Not now')],
                               group='chat', data={'prefill': prefill, 'tool': tool}, source=response.source)
        reply.safetyLevel, reply.guardViolations = result.final_level, response.violations
        reply.suggestedNextAction, reply.uncertainty = response.suggestedNextAction, response.uncertainty
    else:
        reply = _message(state, client, 'assistant', response.supportiveResponse, safetyLevel=result.final_level,
                         textSource=response.source, approvedActivityId=response.approvedActivityId,
                         suggestedNextAction=response.suggestedNextAction, uncertainty=response.uncertainty,
                         guardViolations=response.violations)
    records.audit(state, actor=records.agent_actor('SupportAgent'), action='chat_response', client_id=client.id,
                  detail=f'Reply: {response.source}' + (f'; rejected in the safety check: {", ".join(response.violations)}'
                                                          if response.violations else ''),
                  data={'approvedActivityId': response.approvedActivityId, 'deterministicLevel': result.deterministic_level,
                        'aiLevel': result.ai_level})
    if result.final_level >= 1:
        safety_agent.raise_safety(state, client, result, context='chat', actor=actor(client))
    return {'safety': {'level': result.final_level}, 'messageId': reply.id}


# --- guided practice (chat tools and tasks) ----------------------------------------------------------------------------------

def start_practice(state: ValitukiState, client: ClientProfile, tool: str, provider: Optional[AIProvider] = None, *,
                   prefill: Optional[dict[str, Any]] = None, started_from: str = 'chat') -> dict[str, Any]:
    _require(client, ACTIVE_STATES, 'An exercise')
    session = practice.start(state, client, tool, provider or DemoAIProvider(), actor(client), prefill=prefill,
                             started_from=started_from)
    return {'sessionId': session.id, 'tool': session.tool}


def answer_practice(state: ValitukiState, client: ClientProfile, value: Any, *, session_id: Optional[str] = None,
                    step_key: Optional[str] = None, skip: bool = False, provider: Optional[AIProvider] = None) -> dict[str, Any]:
    _require(client, ACTIVE_STATES, 'An exercise')
    return practice.answer(state, client, value, provider or DemoAIProvider(), actor(client), session_id=session_id,
                           step_key=step_key, skip=skip)


def stop_practice(state: ValitukiState, client: ClientProfile, session_id: Optional[str] = None) -> None:
    practice.stop(state, client, actor(client), session_id)


def choose_offer(state: ValitukiState, client: ClientProfile, message_id: str, option: str,
                 provider: Optional[AIProvider] = None) -> dict[str, Any]:
    _require(client, ACTIVE_STATES, 'Choosing')
    return practice.act_on_offer(state, client, message_id, option, provider or DemoAIProvider(), actor(client))


def task_action(state: ValitukiState, client: ClientProfile, task_id: str, action: str,
                provider: Optional[AIProvider] = None) -> dict[str, Any]:
    _require(client, ACTIVE_STATES, 'A task')
    if action == 'done':
        return practice.complete_task(state, client, task_id, provider or DemoAIProvider(), actor(client))
    if action == 'later':
        return {'dueDate': practice.postpone_task(state, client, task_id).dueDate}
    if action == 'skip':
        practice.skip_task(state, client, task_id)
        return {'skipped': True}
    raise ClientActionError('Unknown action.')


def set_practice_sharing(state: ValitukiState, client: ClientProfile, kind: str, item_id: str, shared: bool) -> None:
    practice.set_shared(state, client, kind, item_id, shared, actor(client))


def remove_practice_item(state: ValitukiState, client: ClientProfile, kind: str, item_id: str) -> None:
    practice.remove_item(state, client, kind, item_id, actor(client))


def request_human(state: ValitukiState, client: ClientProfile, reason: str, message: str = '') -> dict[str, Any]:
    _require(client, journey.ALL_OPEN, 'A contact request')
    reason = reason if reason in CONTACT_REASONS else 'other'
    message = (message or '').strip()[:600]
    event = journey.apply(state, client, 'USER_REQUESTED_HUMAN', actor=actor(client), source='client',
                          payload={'reason': reason, 'message': message or None})
    orchestrator.dispatch(state, event)
    result = assess(evaluate_text(message))
    if result.final_level:
        safety_agent.raise_safety(state, client, result, context='chat', actor=actor(client))
    return {'safety': {'level': result.final_level}}


def help_now(state: ValitukiState, client: ClientProfile) -> dict[str, Any]:
    safety_agent.raise_safety(state, client, assess([explicit_help_trigger()]), context='button', actor=actor(client))
    return {'safety': {'level': 3, 'screen': SAFETY_SCREEN}}


def dismiss_safety(state: ValitukiState, client: ClientProfile) -> None:
    lock = client.safetyLock
    if not lock or lock.dismissedAt:
        return
    lock.dismissedAt = now(state)
    observation = next((o for o in state.safetyObservations if o.id == lock.observationId), None)
    if observation:
        observation.clientAcknowledgedAt = lock.dismissedAt
    records.act(state, agent='SafetyAgent', type='safety_acknowledged', client_id=client.id,
                title='Safety instructions acknowledged – usual support continues',
                detail='The observation is still waiting for a professional review. The instructions are always behind the '
                       '"I need help now" button.')


# --- therapist matching, handover and feedback ------------------------------------------------------------------------

def select_candidate(state: ValitukiState, client: ClientProfile, candidate_id: str):
    return matching_flow.select(state, client, candidate_id, actor(client))


def request_alternatives(state: ValitukiState, client: ClientProfile):
    return matching_flow.request_alternatives(state, client, actor(client))


def request_matching_help(state: ValitukiState, client: ClientProfile, note: str = ''):
    return matching_flow.request_help(state, client, actor(client), note)


def toggle_checklist(state: ValitukiState, client: ClientProfile, item_id: str, done: bool) -> None:
    for item in client.preparationChecklist:
        if item['id'] == item_id:
            item['done'] = bool(done)


def update_handover(state: ValitukiState, client: ClientProfile, change: dict[str, Any]):
    return handover.update(state, client, change, actor(client))


def approve_handover(state: ValitukiState, client: ClientProfile):
    return handover.approve(state, client, actor(client))


def withdraw_handover(state: ValitukiState, client: ClientProfile):
    return handover.withdraw(state, client, actor(client))


def submit_match_feedback(state: ValitukiState, client: ClientProfile, data: dict[str, Any]) -> MatchFeedback:
    _require(client, ('THERAPY_ACTIVE', 'HUMAN_REVIEW_NEEDED'), 'Feedback on the collaboration')
    current = therapy.episode(state, client.id)
    if current is None or current.status != 'active':
        raise ClientActionError('Feedback can be given after the first session.')
    scores = [int(data[key]) for key in ('heard', 'goalsUnderstood', 'styleFit')]
    if any(s < 1 or s > 5 for s in scores):
        raise ClientActionError('Ratings must be between 1 and 5.')
    want_continue = data.get('wantContinue', 'unsure')
    if want_continue not in ('yes', 'unsure', 'no'):
        raise ClientActionError('Unknown answer.')
    discuss = bool(data.get('wantDiscussAlternative'))
    low = int(content.rules()['matchFeedback']['lowScore'])
    negative = min(scores) <= low or want_continue == 'no' or discuss
    stamp = now(state)
    feedback = MatchFeedback(id=next_id(state, 'mfb'), clientId=client.id, therapistId=current.therapistId,
                             afterSession=max(1, current.sessionsHeld), heard=scores[0], goalsUnderstood=scores[1], styleFit=scores[2],
                             wantContinue=want_continue, wantDiscussAlternative=discuss, note=str(data.get('note', ''))[:300],
                             negative=negative, createdAt=stamp, updatedAt=stamp, createdBy=actor(client), source='client')
    state.matchFeedback.append(feedback)
    event = journey.apply(state, client, 'MATCH_FEEDBACK_RECEIVED', actor=actor(client), source='client',
                          payload={'feedbackId': feedback.id, 'negative': negative})
    orchestrator.dispatch(state, event)
    return feedback


def mark_notifications_read(state: ValitukiState, client: ClientProfile) -> None:
    for notification in state.notifications:
        if notification.audience == 'client' and notification.clientId == client.id:
            notification.read = True
