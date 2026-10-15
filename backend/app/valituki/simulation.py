"""Demo time machine. The controls stand in for time passing and for external systems, and run the same agents as real use.

Synthetic clients answer their check-ins according to a deterministic simulation profile (data/valituki/clients.json).
The client being demoed live can still act by hand: a check-in answered manually is simply no longer due when the day is
simulated. Simulations always use DEMO_AI_MODE texts so that a replayed demo is identical every time.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from app.valituki import adapters, client_actions, content, journey, practice, records, therapy
from app.valituki.agents import navigation, orchestrator
from app.valituki.ai import DemoAIProvider
from app.valituki.models import ClientProfile, ValitukiState
from app.valituki.store import add_days, days_between, get_client, get_therapist, now, weekday

STABLE_OFFSETS = [0, 1, 0, 0, -1, 0, 1]
PROFILE_LABELS = {'scripted': 'Scripted demo path', 'stable': 'Stable', 'deteriorating': 'Declining',
                  'missing': 'Check-ins missed', 'none': 'No simulated use'}


class SimulationError(ValueError):
    """The demo control cannot run (HTTP 409)."""


def _spec(client: ClientProfile) -> dict[str, Any]:
    return content.client_spec(client.id).get('simulation', {})


def _cursor(client: ClientProfile, key: str) -> int:
    return client.simulationCursor.get(key, 0)


def _advance_cursor(client: ClientProfile, key: str) -> None:
    client.simulationCursor[key] = _cursor(client, key) + 1


def _generic_stable(client: ClientProfile, index: int, time: str) -> dict[str, Any]:
    base = int(round(client.baseline or 3))
    mood = max(1, min(5, base + STABLE_OFFSETS[index % len(STABLE_OFFSETS)]))
    changes = {'sleep': 'better'} if index % 5 == 1 else {}
    return {'mood': mood, 'changes': changes, 'note': '', 'time': time}


def simulated_anxiety(entry: dict[str, Any]) -> int:
    """Anxiety 1–5 for a simulated answer: given in the script, otherwise derived from the mood and the anxiety change."""
    if entry.get('anxiety') is not None:
        return int(entry['anxiety'])
    value = 3 if entry.get('changes', {}).get('anxiety') == 'worse' else 2
    if int(entry['mood']) <= 2:
        value += 1
    elif int(entry['mood']) >= 4:
        value -= 1
    return max(1, min(5, value))


def next_answer(client: ClientProfile, default_time: str, day: Optional[str] = None) -> Optional[dict[str, Any]]:
    """The simulated answer to the client's next due check-in, or None when the check-in is left undone."""
    spec = _spec(client)
    profile = client.simulationProfile
    time = spec.get('answerTime', default_time)
    if profile == 'none':
        return None
    if profile == 'missing':
        answered = _cursor(client, 'missing')
        _advance_cursor(client, 'missing')
        return _generic_stable(client, answered, time) if answered < int(spec.get('answerFirst', 2)) else None
    if profile == 'deteriorating':
        if len(client.baselineCheckInIds) < int(content.rules()['trend']['baselineCheckIns']):
            return _generic_stable(client, _cursor(client, 'stable'), time)  # the own baseline is established first
        script = spec.get('deterioration', [])
        index = _cursor(client, 'deterioration')
        _advance_cursor(client, 'deterioration')
        if index < len(script):
            entry = script[index]
            return None if entry.get('skip') else {**entry, 'time': entry.get('time', time)}
        return {'mood': max(1, int(round(client.baseline or 3)) - 1), 'changes': {'sleep': 'worse'}, 'note': '', 'time': time}
    if profile == 'scripted' and day and _rhythm_changed(client):
        entry = _by_evening(client, spec.get('checkIns', []), day)
        if entry is not None:
            return {**entry, 'time': entry.get('time', time)}
    elif profile == 'scripted':
        script = spec.get('checkIns', [])
        index = _cursor(client, 'checkIns')
        if index < len(script):
            _advance_cursor(client, 'checkIns')
            entry = script[index]
            return None if entry.get('skip') else {**entry, 'time': entry.get('time', time)}
    recovery = spec.get('recovery') or []
    if recovery and client.mode in ('therapy_support', 'aftercare_support'):
        # From the start of therapy: a steady recovery above the own baseline – the script once, then its calm tail again.
        index = _cursor(client, 'recovery')
        _advance_cursor(client, 'recovery')
        tail = recovery[len(recovery) // 2:]
        entry = recovery[index] if index < len(recovery) else tail[(index - len(recovery)) % len(tail)]
        return {**entry, 'time': entry.get('time', time)}
    stable = spec.get('stable') or []
    index = _cursor(client, 'stable')
    _advance_cursor(client, 'stable')
    if stable:
        entry = stable[index % len(stable)]
        return {**entry, 'time': entry.get('time', time)}
    return _generic_stable(client, index, time)


def _rhythm_changed(client: ClientProfile) -> bool:
    """The client chose another check-in rhythm than the one the scripted answers were written for."""
    designed = (content.client_spec(client.id).get('intake') or {}).get('rhythm', {}).get('checkInDays')
    return bool(designed) and sorted(client.checkInDays) != sorted(designed)


def _by_evening(client: ClientProfile, script: list[dict[str, Any]], day: str) -> Optional[dict[str, Any]]:
    """The scripted answers by the evening they belong to, for another rhythm: the tense answers on evenings before a
    workday, the calmer ones before a day off – so the story (and the pattern drawn from it) stays the same on any days."""
    before_work = weekday(day) not in (4, 5)
    pool = [e for e in script if not e.get('skip') and (e.get('changes', {}).get('anxiety') == 'worse') == before_work]
    key = 'checkIns-work' if before_work else 'checkIns-off'
    index = _cursor(client, key)
    if index >= len(pool):
        return None
    _advance_cursor(client, key)
    return pool[index]


def _day_actions(state: ValitukiState, client: ClientProfile) -> list[tuple[str, Callable[[], None]]]:
    """The client's simulated actions for the current demo day, each with its clock time."""
    if client.journeyState not in journey.ACTIVE_STATES or (client.safetyLock and not client.safetyLock.dismissedAt):
        return []
    default_time = content.rules()['clock']['defaultAnswerTime']
    actions: list[tuple[str, Callable[[], None]]] = []
    due = next((c for c in state.checkIns if c.clientId == client.id and c.status == 'due' and c.dueDate == state.currentDate), None)
    if due is not None:
        entry = next_answer(client, default_time, state.currentDate)
        if entry is not None:
            config = therapy.active_config(state, client.id) if client.mode == 'therapy_support' else None

            def answer(entry: dict[str, Any] = entry, track: bool = config is not None) -> None:
                if not any(c.clientId == client.id and c.status == 'due' for c in state.checkIns):
                    return  # answered by hand already
                client_actions.submit_checkin(state, client, int(entry['mood']), entry.get('changes', {}), entry.get('note', ''),
                                              anxiety=simulated_anxiety(entry),
                                              track_score=max(1, min(5, 6 - int(entry['mood']))) if track else None,
                                              provider=DemoAIProvider(), who=f'{records.client_actor(client.id)}:simulated',
                                              at=entry.get('time'))
            actions.append((entry.get('time', default_time), answer))
    spec = _spec(client)
    session = next((s for s in state.intakes if s.id == client.intakeId), None)
    if client.simulationProfile == 'scripted' and session and session.completedAt:
        day = days_between(session.completedAt, state.currentDate)
        for item in [a for a in spec.get('activities', []) if a['dayOffset'] == day]:
            def activity(item: dict[str, Any] = item) -> None:
                if item['action'] == 'complete':
                    client_actions.complete_activity(state, client, item['activityId'], item.get('rating'), item.get('note', ''),
                                                     at=item.get('time'))
                elif client.todayActivity and client.todayActivity.status == 'suggested':
                    client_actions.skip_activity(state, client, at=item.get('time'))
            actions.append((item.get('time', default_time), activity))
        for item in [p for p in spec.get('practice', []) if p['dayOffset'] == day]:
            actions.append((item.get('time', default_time), lambda item=item: _practice_step(state, client, item)))
    elif client.simulationProfile == 'stable' and not client.demoPrimary and due is not None and client.todayActivity:
        if (days_between(state.demoStartDate, state.currentDate) + len(client.id)) % 3 == 0:
            today = client.todayActivity

            def practise_today(today=today) -> None:
                current = client.todayActivity
                if current and current.status == 'suggested' and current.activityId == today.activityId:
                    client_actions.complete_activity(state, client, today.activityId, 4, at='19:00')
            actions.append(('19:00', practise_today))
    return actions


def _practice_step(state: ValitukiState, client: ClientProfile, item: dict[str, Any]) -> None:
    """A scripted piece of the demo client's own practice, run through the same guided engine as the chat."""
    who = f'{records.client_actor(client.id)}:simulated'
    at = item.get('time')
    if practice.active_session(state, client.id) is not None and practice.active_session(state, client.id).tool == 'checkin':
        practice.expire_checkin(state, client)
    action = item['action']
    if action == 'tool':
        practice.replay(state, client, item['tool'], item.get('answers', {}), actor=who, prefill=item.get('prefill'), at=at,
                        started_from='simulation')
    elif action == 'ladder_if_missing':
        if not any(lad.clientId == client.id for lad in state.ladders):
            practice.replay(state, client, 'exposure', item.get('answers', {}), actor=who, at=at, started_from='simulation')
    elif action in ('exposure_attempt', 'experiment_review'):
        kind = 'exposure_step' if action == 'exposure_attempt' else 'experiment'
        task = next((t for t in sorted(state.practiceTasks, key=lambda t: (t.dueDate or '', t.id))
                     if t.clientId == client.id and t.kind == kind and t.status == 'open'), None)
        if task is None:
            return
        context: dict[str, Any] = {'taskId': task.id}
        if kind == 'exposure_step':
            ladder = next((lad for lad in state.ladders if lad.id == task.sourceId), None)
            step = next((s for s in ladder.steps if s.id == task.stepId), None) if ladder else None
            if ladder is None or step is None:
                return
            upcoming = practice._next_step(ladder, step)
            context.update({'ladderId': ladder.id, 'stepId': step.id, 'stepText': step.text,
                            'nextStepText': upcoming.text if upcoming else None})
        else:
            experiment = next((e for e in state.experiments if e.id == task.sourceId), None)
            if experiment is None:
                return
            context.update({'experimentId': experiment.id, 'plan': experiment.plan})
        practice.replay(state, client, action, item.get('answers', {}), actor=who, context=context, at=at,
                        started_from='simulation')


def simulate_day(state: ValitukiState) -> None:
    state.currentDate = add_days(state.currentDate, 1)
    # Messages the client did not allow to be stored are kept for the day's conversation only.
    state.chat = [m for m in state.chat if m.retained or m.createdAt[:10] >= state.currentDate]
    records.audit(state, actor=records.DEMO, action='demo_day', detail=f'Demo day: {state.currentDate}', at='08:00')
    adapters.therapist_directory.sync_calendars(state)
    orchestrator.tick(state, DemoAIProvider())
    run_client_day(state)


def run_client_day(state: ValitukiState) -> None:
    actions: list[tuple[str, str, Callable[[], None]]] = []
    for client in sorted(state.clients, key=lambda c: c.id):
        actions += [(time, client.id, fn) for time, fn in _day_actions(state, client)]
    for _, _, fn in sorted(actions, key=lambda a: (a[0], a[1])):
        fn()


def advance(state: ValitukiState, days: int) -> dict[str, Any]:
    if days < 1 or days > 31:
        raise SimulationError('The number of days must be 1–31.')
    actions_before = len(state.actions)
    for _ in range(days):
        simulate_day(state)
    return {'days': days, 'currentDate': state.currentDate, 'agentActions': len(state.actions) - actions_before}


def _events_since(state: ValitukiState, seq: int, client_id: str, event_type: str) -> list:
    return [e for e in state.events if e.seq > seq and e.clientId == client_id and e.type == event_type]


def _require_active(client: ClientProfile) -> None:
    if client.journeyState not in journey.ACTIVE_STATES:
        raise SimulationError(f'{client.firstName} is not using Mieliluotsi yet – set it up first.')
    if not client.consent.proactiveCheckins or client.automationPaused:
        raise SimulationError('Check-ins are not in use for this client (consent or pause).')


# The decline comes after this many ordinary days with Mieliluotsi – as in the demo's story ("Two weeks later").
ORDINARY_DAYS_BEFORE_DECLINE = 14


def simulate_deterioration(state: ValitukiState, client: ClientProfile, max_days: int = 14) -> dict[str, Any]:
    _require_active(client)
    from app.valituki import intake

    # The ordinary weeks first, when they have not been simulated yet: the check-ins the "We noticed something" pattern is
    # drawn from come before the decline, so the observation is on the home screen once wellbeing has declined.
    session = intake.session_for(state, client)
    started = (session.completedAt if session and session.completedAt else state.currentDate)[:10]
    ordinary = 0
    while days_between(started, state.currentDate) < ORDINARY_DAYS_BEFORE_DECLINE:
        simulate_day(state)
        ordinary += 1
    start_seq = state.events[-1].seq if state.events else 0
    client.simulationProfile = 'deteriorating'
    client.simulationCursor['deterioration'] = 0
    records.audit(state, actor=records.DEMO, action='demo_profile', client_id=client.id,
                  detail='Demo: the simulated check-in answers were changed to declining.')
    days = 0
    while days < max_days and not _events_since(state, start_seq, client.id, 'WELLBEING_TREND_CHANGED'):
        simulate_day(state)
        days += 1
    triggered = bool(_events_since(state, start_seq, client.id, 'WELLBEING_TREND_CHANGED'))
    if triggered:
        client.simulationProfile = 'stable'
    return {'days': ordinary + days, 'trendChanged': triggered, 'currentDate': state.currentDate, 'journeyState': client.journeyState}


def simulate_stable(state: ValitukiState, client: ClientProfile, max_days: int = 7) -> dict[str, Any]:
    _require_active(client)
    start_seq = state.events[-1].seq if state.events else 0
    client.simulationProfile = 'stable'
    records.audit(state, actor=records.DEMO, action='demo_profile', client_id=client.id,
                  detail='Demo: the simulated check-in answers were changed to stable.')
    days = 0
    while days < max_days and len(_events_since(state, start_seq, client.id, 'CHECKIN_COMPLETED')) < 2:
        simulate_day(state)
        days += 1
    return {'days': days, 'checkIns': len(_events_since(state, start_seq, client.id, 'CHECKIN_COMPLETED')),
            'currentDate': state.currentDate}


def open_slot(state: ValitukiState, spec: dict[str, Any], *, actor: str = records.DEMO) -> Any:
    """A therapist's capacity changes (TherapistDirectoryAdapter) → THERAPIST_SLOT_OPENED → MatchingAgent runs matching."""
    therapist = get_therapist(state, spec['therapistId'])
    therapist.currentCapacity = max(0, therapist.currentCapacity + int(spec.get('capacityChange', -1)))
    event = journey.record_event(state, 'THERAPIST_SLOT_OPENED', actor=actor, source='therapist_directory_adapter',
                                 therapist_id=therapist.id,
                                 payload={'reason': spec.get('reason', ''),
                                          'capacity': f'{therapist.currentCapacity}/{therapist.maxCapacity}'})
    records.audit(state, actor='therapist_directory_adapter', action='capacity_changed', event_id=event.id,
                  detail=f'{therapist.name}: {spec.get("reason", "")} Capacity {therapist.currentCapacity}/{therapist.maxCapacity}.')
    orchestrator.dispatch(state, event, DemoAIProvider())
    return event


def open_next_pending(state: ValitukiState) -> dict[str, Any]:
    pending = next((p for p in state.pendingSlotOpenings if p.status == 'pending'), None)
    if pending is None:
        raise SimulationError('There are no more slots to open in the demo. Reset the demo or carry on without.')
    pending.status = 'opened'
    event = open_slot(state, pending.model_dump())
    run = state.matchRuns[-1] if state.matchRuns else None
    return {'therapistName': get_therapist(state, pending.therapistId).name, 'reason': pending.reason, 'eventId': event.id,
            'matchedClients': run.clientIds if run and run.createdAt >= event.occurredAt else []}


def hold_first_session(state: ValitukiState, client: ClientProfile) -> dict[str, Any]:
    """Moves the demo clock to the first session and marks it held (AppointmentAdapter) → THERAPY_STARTED."""
    from app.valituki import handover

    booking = handover.active_booking(state, client.id)
    if booking is None or journey.effective_state(client) != 'MATCH_ACCEPTED':
        raise SimulationError('No first session has been booked.')
    days = 0
    while state.currentDate < booking.start[:10] and days < 31:
        simulate_day(state)
        days += 1
    if booking.status == 'booked':
        navigation.hold_first_session(state, client, DemoAIProvider(), at=_after(booking.start, 50))
    return {'days': days, 'currentDate': state.currentDate, 'journeyState': client.journeyState}


def end_therapy(state: ValitukiState, client: ClientProfile, weeks: int = 4) -> dict[str, Any]:
    """Demo: the short therapy runs its course (weekly sessions for a few weeks) and the therapist ends it with the
    suggested maintenance plan → AFTERCARE."""
    episode = therapy.episode(state, client.id)
    if episode is None or episode.status != 'active':
        raise SimulationError('Therapy is not in progress – hold the first session first.')
    if therapy.active_config(state, client.id) is None:
        therapy.configure(state, client, episode.therapistId, therapy.suggested_plan(state, client),
                          records.therapist_actor(episode.therapistId))
    days = 0
    for _ in range(max(1, weeks) * 7):
        simulate_day(state)
        days += 1
        if days % 7 == 0:
            episode.sessionsHeld += 1
    therapy.end_therapy(state, client, episode.therapistId, therapy.suggested_aftercare(state, client),
                        records.therapist_actor(episode.therapistId))
    return {'days': days, 'currentDate': state.currentDate, 'journeyState': client.journeyState,
            'sessions': episode.sessionsHeld}


def _after(start: str, minutes: int) -> str:
    hours, mins = int(start[11:13]), int(start[14:16]) + minutes
    hours, mins = hours + mins // 60, mins % 60
    return f'{min(hours, 23):02d}:{mins:02d}'


def crisis(state: ValitukiState, client_id: str = 'cl-crisis') -> dict[str, Any]:
    client = get_client(state, client_id)
    message = (content.client_spec(client.id).get('safetyDemoMessage')
               or "I can't cope any more. I've started to think that I'd like to die.")
    now(state, '21:30')
    return {'clientId': client.id, **client_actions.send_message(state, client, message, DemoAIProvider())}
