"""Matching workflow around the pure engine in matching.py.

MatchingAgent runs matching when capacity opens (THERAPIST_SLOT_OPENED) or when a professional starts it. The client sees
the three best eligible options with the reasons and the unmet wishes, can ask for more options or for a professional's
help, and makes the choice. Selecting a therapist books the first suitable time (AppointmentAdapter). A client under a
pending professional review gets the proposals only after the review.
"""
from __future__ import annotations

from typing import Any, Optional

from app.valituki import adapters, content, fit_profile, insights, journey, matching, records, therapy, trends
from app.valituki.ai import AIProvider, DemoAIProvider
from app.valituki.labels import LANGUAGES, fmt_date, fmt_slot, fmt_slot_title, plural
from app.valituki.models import Booking, ClientProfile, MatchCandidate, MatchDecision, MatchRun, TherapistAvailability, ValitukiState
from app.valituki.store import add_days, find, get_therapist, next_id, now

AGENT = 'MatchingAgent'


class MatchingError(ValueError):
    """The matching action is not possible (HTTP 409)."""


def current_decision(state: ValitukiState, client_id: str) -> Optional[MatchDecision]:
    decisions = [d for d in state.matchDecisions if d.clientId == client_id and d.status != 'superseded']
    return decisions[-1] if decisions else None


def decision_candidates(state: ValitukiState, decision: MatchDecision) -> list[MatchCandidate]:
    by_id = {c.id: c for c in state.matchCandidates}
    return [by_id[cid] for cid in decision.candidateIds if cid in by_id]


def open_safety_level(state: ValitukiState, client_id: str) -> int:
    return max((o.level for o in state.safetyObservations if o.clientId == client_id and o.status == 'open'), default=0)


def build_input(state: ValitukiState, client: ClientProfile) -> matching.ClientMatchInput:
    """The matching input: only approved insights the client allows to be used in matching, plus the referral."""
    referral = adapters.waiting_list.referral_for(state, client.id)
    if referral is None:
        raise MatchingError('No referral information found.')
    approved = insights.for_client(state, client.id)
    practical = next((i for i in approved if i.kind == 'practical'), None)
    if practical is None:
        raise MatchingError('The practical wishes have not been approved – matching cannot start.')
    if not practical.sharing.matching:
        raise MatchingError('The practical wishes are not allowed in matching, so automatic matching cannot start. '
                            'The care team can help find a therapist.')
    used = ["The referral's service and required competence (a professional's assessment)", 'Age group']
    not_used: list[str] = []
    primary = [i for i in approved if i.kind == 'primary_goal']
    secondary = [i for i in approved if i.kind == 'secondary_goal']
    primary_topics = [t for i in primary if i.sharing.matching for t in i.structured.get('topics', [])]
    secondary_topics = [t for i in secondary if i.sharing.matching for t in i.structured.get('topics', [])]
    if any(i.sharing.matching for i in primary + secondary):
        used.append('Your goals (approved)')
    if any(not i.sharing.matching for i in primary + secondary):
        not_used.append('Some of your goals – you have not allowed them to be used in matching')
    style_insight = next((i for i in approved if i.kind == 'working_style'), None)
    style: dict[str, Optional[str]] = {}
    if style_insight and style_insight.sharing.matching:
        style = {k: style_insight.structured.get(k) for k in ('structure', 'exercises', 'approach', 'homework')}
        used.append('Your wishes about the way of working (approved)')
    elif style_insight:
        not_used.append('Your wish about the way of working – you have not allowed it to be used in matching')
    used.append('Your practical wishes: language, type of session and times (approved)')
    not_used += ['Check-in answers, journal entries and conversations', "Mieliluotsi's observations about your wellbeing",
                 'Gender or other background information – it is not inferred']
    flags = list(referral.flags)
    if open_safety_level(state, client.id) >= 2:
        flags.append('acute_safety_concern')
    structured = practical.structured
    return matching.ClientMatchInput(
        client_id=client.id, age=client.age, municipality=structured.get('location') or client.municipality,
        service_category=referral.serviceCategory, required_competencies=list(referral.requiredCompetencies),
        languages=list(structured.get('languages') or ['fi']), format=structured.get('format') or 'either',
        days=list(structured.get('days') or []), times=list(structured.get('times') or []),
        accessibility_needs=list(structured.get('accessibilityNeeds') or []), primary_topics=primary_topics,
        secondary_topics=[t for t in secondary_topics if t not in primary_topics], style=style, flags=sorted(set(flags)),
        personal_exclusions=list(client.personalExclusions), data_used=used, data_not_used=not_used)


# Hard criteria that describe fit. Capacity and free times change every week, so the preview does not exclude on them.
PREVIEW_FIT_FILTERS = ('active', 'service', 'role', 'age', 'competence', 'language', 'location', 'exclusion')


def preview(state: ValitukiState, client: ClientProfile) -> Optional[dict[str, Any]]:
    """A presenter's preview of how well the therapists fit the client with the data so far, before any matching run.

    The same engine scores the same approved data the real run would use; missing practical wishes count as "no wish".
    Nothing is saved or shown to the client. Therapists without a free time are scored with their first time after the
    horizon (so availability scores low) and marked as not available yet."""
    referral = adapters.waiting_list.referral_for(state, client.id)
    if referral is None:
        return None
    try:
        match_input = build_input(state, client)
    except MatchingError:
        match_input = matching.ClientMatchInput(
            client_id=client.id, age=client.age, municipality=client.municipality, service_category=referral.serviceCategory,
            required_competencies=list(referral.requiredCompetencies), languages=['fi'], format='either',
            flags=sorted(set(referral.flags)), personal_exclusions=list(client.personalExclusions))
    config = content.matching_config()
    horizon = int(config['slotHorizonDays'])
    later = f'{add_days(state.currentDate, horizon + 7)}T16:00'
    ranked, excluded = [], []
    for therapist in sorted(adapters.therapist_directory.therapists(state), key=lambda t: t.id):
        outcomes = matching.hard_filters(match_input, therapist, state.slots, state.currentDate, config)
        failed = [o for o in outcomes if not o.passed and o.key in PREVIEW_FIT_FILTERS]
        if failed:
            excluded.append({'name': therapist.name, 'reason': failed[0].reason})
            continue
        available = all(o.passed for o in outcomes)
        compatible = matching.compatible_slots(match_input, therapist, state.slots, state.currentDate, horizon)
        slot = matching.preferred_slot(match_input, compatible) if compatible else TherapistAvailability(
            id='preview', therapistId=therapist.id, start=later, formats=['remote'] if therapist.remote else ['in_person'],
            createdAt=later, updatedAt=later, createdBy='system', source='preview')
        components, _, _ = matching._components(match_input, therapist, slot, state.currentDate, config)
        total = round(sum(c.points for c in components), 1)
        label, label_text = matching.label_for(total, config)
        ranked.append({'id': f'preview-{therapist.id}', 'name': therapist.name, 'label': label, 'labelText': label_text,
                       'total': total, 'status': 'preview' if available else 'unavailable',
                       'components': [{'key': c.key, 'label': c.label, 'score': c.score} for c in components]})
    ranked.sort(key=lambda r: (-r['total'], r['name']))
    return {'candidates': ranked, 'excluded': excluded, 'dataUsed': match_input.data_used}


def readiness(state: ValitukiState, client: ClientProfile) -> list[dict[str, Any]]:
    """Deterministic readiness criteria (rule MATCH-READY-001), shown with pass / fail to the professional."""
    policy = content.rules()['readiness']
    completed = [c for c in trends.completed_checkins(state, client.id) if c.kind != 'baseline']
    episode = adapters.waiting_list.episode_for(state, client.id)
    practical = next((i for i in insights.for_client(state, client.id) if i.kind == 'practical'), None)
    open_review = any(o.clientId == client.id and o.status == 'open' and o.requiresHumanReview
                      and o.kind == 'trend_decline' for o in state.wellbeingObservations) or open_safety_level(state, client.id) >= 2
    return [
        {'key': 'profile', 'label': 'Therapy Fit Profile approved', 'passed': fit_profile.get(state, client.id) is not None},
        {'key': 'permission', 'label': 'Practical wishes allowed in matching',
         'passed': bool(practical and practical.sharing.matching)},
        {'key': 'checkins', 'label': f'At least {plural(int(policy["minCheckIns"]), "check-in")}',
         'passed': len(completed) >= int(policy['minCheckIns']), 'detail': f'{len(completed)} done'},
        {'key': 'review', 'label': 'No open observations that need a review', 'passed': not open_review},
        {'key': 'waitingList', 'label': 'The waiting list position allows booking a therapist',
         'passed': adapters.waiting_list.is_allocatable(state, client.id),
         'detail': f'from {fmt_date(episode.allocatableFrom)}' if episode else 'no waiting list information'},
    ]


def eligible_for_run(state: ValitukiState, client: ClientProfile) -> bool:
    phase_ok = client.journeyState == 'MATCHING_READY' or (client.journeyState == 'HUMAN_REVIEW_NEEDED'
                                                           and client.resumeState == 'MATCHING_READY')
    if not phase_ok:
        return False
    decision = current_decision(state, client.id)
    if decision is not None and decision.status not in ('no_candidates',):
        return False
    try:
        build_input(state, client)
    except MatchingError:
        return False
    return True


def _candidate_facts(scored) -> dict[str, Any]:
    return {'therapistName': scored.therapist.name, 'labelText': scored.label_text, 'reasons': scored.reasons,
            'unmetPreferences': scored.unmet, 'firstSlot': fmt_slot(scored.slot.start), 'whyText': scored.why}


def run_for_client(state: ValitukiState, client: ClientProfile, run: MatchRun, provider: AIProvider) -> MatchDecision:
    config = content.matching_config()
    match_input = build_input(state, client)
    evaluation = matching.evaluate(match_input, adapters.therapist_directory.therapists(state), state.slots, state.currentDate, config)
    run.excluded[client.id] = evaluation.excluded
    run.inputs[client.id] = match_input.as_dict()
    previous = current_decision(state, client.id)
    if previous:
        previous.status = 'superseded'
        previous.updatedAt = now(state)
    ranked = evaluation.ranked[: int(config['maxCandidates'])]
    explanations = provider.generate_match_explanations([_candidate_facts(s) for s in ranked])
    candidate_ids = []
    for rank, (scored, explanation) in enumerate(zip(ranked, explanations, strict=True), start=1):
        candidate = MatchCandidate(
            id=next_id(state, 'cand'), runId=run.id, clientId=client.id, therapistId=scored.therapist.id, rank=rank,
            totalPoints=scored.total, label=scored.label, labelText=scored.label_text, components=scored.components,
            reasons=scored.reasons, unmetPreferences=scored.unmet, firstSlotId=scored.slot.id, firstSlotStart=scored.slot.start,
            explanation=explanation.text, explanationSource=explanation.source, dataUsed=match_input.data_used,
            dataNotUsed=match_input.data_not_used)
        state.matchCandidates.append(candidate)
        candidate_ids.append(candidate.id)
    stamp = now(state)
    held = client.journeyState == 'HUMAN_REVIEW_NEEDED'
    status = 'no_candidates' if not candidate_ids else 'held_for_review' if held else 'proposed_to_client'
    decision = MatchDecision(id=next_id(state, 'dec'), clientId=client.id, runId=run.id, status=status, candidateIds=candidate_ids,
                             shownCount=int(config['shownCandidates']), releasedAt=stamp if status == 'proposed_to_client' else None,
                             createdAt=stamp, updatedAt=stamp, createdBy=records.agent_actor(AGENT), source='rule_based')
    state.matchDecisions.append(decision)
    run.clientIds.append(client.id)
    return decision


def run(state: ValitukiState, trigger_event, provider: Optional[AIProvider] = None, therapist_id: Optional[str] = None,
        client_ids: Optional[list[str]] = None) -> MatchRun:
    """Run matching for every eligible client (or the given ones). Each result is a MATCHES_GENERATED event."""
    provider = provider or DemoAIProvider()
    match_run = MatchRun(id=next_id(state, 'run'), trigger=trigger_event.type if trigger_event else 'MANUAL', createdAt=now(state),
                         configVersion=content.matching_config()['version'], therapistId=therapist_id)
    state.matchRuns.append(match_run)
    targets = [c for c in sorted(state.clients, key=lambda c: c.id) if eligible_for_run(state, c)
               and (client_ids is None or c.id in client_ids)]
    from app.valituki.agents import orchestrator  # local import: agents import this module

    for client in targets:
        decision = run_for_client(state, client, match_run, provider)
        top = decision_candidates(state, decision)[:decision.shownCount]
        event = journey.apply(state, client, 'MATCHES_GENERATED', actor=records.agent_actor(AGENT), source='rule_based',
                              payload={'runId': match_run.id, 'decisionId': decision.id, 'candidates': len(decision.candidateIds),
                                       'held': decision.status == 'held_for_review', 'trigger': match_run.trigger,
                                       'top': [get_therapist(state, c.therapistId).name for c in top]})
        orchestrator.dispatch(state, event, provider)
    return match_run


def release_held(state: ValitukiState, client: ClientProfile, provider: Optional[AIProvider] = None) -> Optional[MatchDecision]:
    decision = current_decision(state, client.id)
    if decision is None or decision.status != 'held_for_review' or client.journeyState != 'MATCHING_READY':
        return None
    decision.status = 'proposed_to_client'
    decision.releasedAt = decision.updatedAt = now(state)
    event = journey.apply(state, client, 'MATCHES_GENERATED', actor=records.agent_actor(AGENT), source='rule_based',
                          payload={'decisionId': decision.id, 'candidates': len(decision.candidateIds), 'held': False,
                                   'released': True})
    from app.valituki.agents import orchestrator

    orchestrator.dispatch(state, event, provider)
    return decision


def select(state: ValitukiState, client: ClientProfile, candidate_id: str, actor: str) -> Booking:
    """The client's choice. The first suitable time is booked through the AppointmentAdapter."""
    decision = current_decision(state, client.id)
    if decision is None or decision.status != 'proposed_to_client' or client.journeyState != 'MATCH_PROPOSED':
        raise MatchingError('There are no therapist suggestions to choose from.')
    visible = decision_candidates(state, decision)[:decision.shownCount]
    candidate = next((c for c in visible if c.id == candidate_id), None)
    if candidate is None:
        raise MatchingError('This suggestion cannot be chosen.')
    therapist = get_therapist(state, candidate.therapistId)
    if therapist.currentCapacity >= therapist.maxCapacity:
        raise MatchingError(f'{therapist.name}: the client place has already been taken. Choose another option or ask for help.')
    free = adapters.therapist_directory.free_slots(state, therapist.id)
    slot = next((s for s in free if s.id == candidate.firstSlotId), None) or next(iter(free), None)
    if slot is None:
        raise MatchingError(f'{therapist.name}: there are no free times left.')
    stamp = now(state)
    for other in decision_candidates(state, decision):
        other.status = 'selected' if other.id == candidate.id else 'not_selected'
    decision.status = 'client_selected'
    decision.selectedCandidateId = candidate.id
    decision.selectedAt = decision.updatedAt = stamp
    event = journey.apply(state, client, 'MATCH_SELECTED', actor=actor, source='client', therapist_id=therapist.id,
                          payload={'decisionId': decision.id, 'candidateId': candidate.id, 'therapistId': therapist.id,
                                   'rank': candidate.rank})
    prefs = next((i for i in insights.for_client(state, client.id) if i.kind == 'practical'), None)
    wanted = prefs.structured.get('format') if prefs else 'either'
    booking_format = 'remote' if 'remote' in slot.formats and wanted != 'in_person' else 'in_person'
    booking = adapters.appointments.book(state, Booking(
        id=next_id(state, 'book'), clientId=client.id, therapistId=therapist.id, slotId=slot.id, start=slot.start,
        format=booking_format, createdAt=stamp, updatedAt=stamp, createdBy=actor, source='appointment_adapter'))
    slot.status = 'booked'
    slot.bookedByClientId = client.id
    therapist.currentCapacity += 1
    if therapist.currentCapacity >= therapist.maxCapacity:
        adapters.therapist_directory.withdraw_slots(state, therapist.id)
    decision.bookingId = booking.id
    episode = adapters.waiting_list.episode_for(state, client.id)
    if episode:
        episode.status = 'allocated'
        episode.updatedAt = stamp
    therapy.start_episode(state, client, booking)
    from app.valituki.agents import orchestrator

    orchestrator.dispatch(state, event)
    booked = journey.apply(state, client, 'FIRST_SESSION_BOOKED', actor=records.agent_actor('NavigationAgent'),
                           source='appointment_adapter', therapist_id=therapist.id,
                           payload={'bookingId': booking.id, 'therapistId': therapist.id, 'start': booking.start,
                                    'startText': fmt_slot_title(booking.start)})
    orchestrator.dispatch(state, booked)
    return booking


def request_alternatives(state: ValitukiState, client: ClientProfile, actor: str) -> dict[str, Any]:
    decision = current_decision(state, client.id)
    if decision is None or decision.status != 'proposed_to_client':
        raise MatchingError('There are no suggestions.')
    remaining = len(decision.candidateIds) - decision.shownCount
    event = journey.apply(state, client, 'MATCH_ALTERNATIVES_REQUESTED', actor=actor, source='client',
                          payload={'decisionId': decision.id, 'remaining': max(0, remaining)})
    if remaining > 0:
        added = min(3, remaining)
        decision.shownCount += added
        records.act(state, agent=AGENT, type='show_alternatives', event=event, title='Showed the other options that meet all the criteria',
                    detail=f'{plural(added, "more option")} on the same grounds.')
        return {'added': added}
    records.act(state, agent=AGENT, type='show_alternatives', event=event, title='There are no other options right now',
                detail='There are no more free therapists who meet all the criteria. You can ask a professional to help you choose.')
    return {'added': 0}


def request_help(state: ValitukiState, client: ClientProfile, actor: str, note: str = '') -> None:
    from app.valituki.agents import base

    decision = current_decision(state, client.id)
    event = journey.apply(state, client, 'MATCH_HELP_REQUESTED', actor=actor, source='client',
                          payload={'decisionId': decision.id if decision else None})
    if decision:
        decision.helpRequested = True
        decision.updatedAt = now(state)
    base.create_task(state, client, agent='NavigationAgent', type='matching_help', priority='normal',
                     title='The client would like help choosing a therapist',
                     reason='The client chose "I want a professional to help me choose".',
                     suggested='Contact the client and go through the options together.',
                     data={'note': note.strip()[:300] or None})
    records.notify(state, audience='coordinator', client_id=client.id, kind='matching', event=event, agent='NavigationAgent',
                   title=f'{client.displayName} would like help with the choice',
                   body='The client wants to go through the options with a professional.')
    records.notify(state, audience='client', client_id=client.id, kind='contact', event=event, agent='NavigationAgent',
                   title='Your request has been passed on', body='The care team will contact you and go through the options with you. '
                   'The suggestions stay visible to you in the meantime.')
    records.act(state, agent='NavigationAgent', type='create_task', event=event, title='Asked a professional to help with the choice',
                detail='The care team received a task. The choice is still yours.')


def languages_text(codes: list[str]) -> str:
    return ', '.join(LANGUAGES.get(c, c) for c in codes)


def booking_of(state: ValitukiState, decision: MatchDecision) -> Optional[Booking]:
    return find(state.bookings, decision.bookingId, 'Booking') if decision.bookingId else None
