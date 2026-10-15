"""Synthetic demo data, built by replaying about a month through the real engine.

Instead of hand-written records, the seed enrolls the synthetic clients on their dates, runs their intakes through the
conversational intake engine, runs the agents' daily rules, scripted client and therapist actions and the simulated
check-in answers day by day. Every event, observation, task and timeline entry in the demo is therefore produced by the
same deterministic rules the live demo uses. All people and health information in the demo are entirely fictional.
"""
from __future__ import annotations

from typing import Any

from app.valituki import adapters, client_actions, content, intake, journey, matching_flow, records, simulation, therapy
from app.valituki.agents import orchestrator
from app.valituki.ai import DemoAIProvider
from app.valituki.labels import URGENCY
from app.valituki.models import (
    ClientProfile,
    PendingSlotOpening,
    Referral,
    Therapist,
    User,
    ValitukiState,
    WaitingListEpisode,
)
from app.valituki.store import add_days, get_client, now

PROFESSIONAL_ASSESSOR = 'Health centre professional (synthetic)'


def _therapists(state: ValitukiState) -> None:
    for raw in content.seed_therapists()['therapists']:
        therapist = Therapist(**raw)
        state.therapists.append(therapist)
        state.users.append(User(id=f'u-{therapist.id}', role='therapist', displayName=therapist.name, therapistId=therapist.id))


def _enroll(state: ValitukiState, spec: dict[str, Any], today: str) -> ClientProfile:
    stamp = now(state)
    client = ClientProfile(
        id=spec['id'], displayName=spec['displayName'], firstName=spec['firstName'], age=spec['age'], municipality=spec['municipality'],
        persona=spec['persona'], demoPrimary=bool(spec.get('demoPrimary')), journeyState='INVITED',
        simulationProfile=spec.get('simulation', {}).get('profile', 'none'), createdAt=stamp, updatedAt=stamp,
        createdBy='waiting_list_adapter', source='adapter')
    state.clients.append(client)
    state.users.append(User(id=f'u-{client.id}', role='client', displayName=client.displayName, clientId=client.id))
    ref = spec['referral']
    referral = Referral(id=f'ref-{client.id[3:]}', clientId=client.id, soughtHelpAt=add_days(today, ref['soughtHelpOffset']),
                        referredAt=add_days(today, ref['offset']), serviceCategory=ref['serviceCategory'],
                        requiredCompetencies=ref['requiredCompetencies'], flags=ref['flags'], referrer=ref['referrer'],
                        assessedBy=ref.get('assessedBy', ''), summary=ref.get('summary', ''), createdAt=stamp, updatedAt=stamp,
                        createdBy='waiting_list_adapter', source='adapter')
    state.referrals.append(referral)
    urgency = ref.get('clinicalUrgency', 'non_urgent')
    state.episodes.append(WaitingListEpisode(
        id=f'epi-{client.id[3:]}', clientId=client.id, referralId=referral.id, startedAt=add_days(today, spec['waitingListOffset']),
        allocatableFrom=add_days(today, spec['allocatableOffset']), estimatedWait=ref.get('estimatedWait', ''),
        clinicalUrgency=urgency, urgencySetBy=ref.get('assessedBy') or PROFESSIONAL_ASSESSOR, urgencySetAt=referral.referredAt,
        urgencyHistory=[{'at': referral.referredAt, 'from': None, 'to': urgency, 'by': ref.get('assessedBy') or PROFESSIONAL_ASSESSOR,
                         'reason': 'Initial assessment'}],
        createdAt=stamp, updatedAt=stamp, createdBy='waiting_list_adapter', source='adapter'))
    records.audit(state, actor='waiting_list_adapter', action='waiting_list', client_id=client.id,
                  detail=f"Referral ({referral.referrer}) – urgency of care: {URGENCY[urgency]} (a professional's assessment).")
    event = journey.enroll(state, client, actor='waiting_list_adapter', source='adapter')
    orchestrator.dispatch(state, event, DemoAIProvider())
    return client


def _script(state: ValitukiState, client: ClientProfile, step: dict[str, Any]) -> None:
    action = step['action']
    who = records.client_actor(client.id)
    if action == 'complete_activity':
        client_actions.complete_activity(state, client, step['activityId'], step.get('rating'))
    elif action == 'select_match':
        decision = matching_flow.current_decision(state, client.id)
        candidates = matching_flow.decision_candidates(state, decision) if decision else []
        chosen = next((c for c in candidates if c.therapistId == step.get('therapistId')), candidates[0] if candidates else None)
        if chosen:
            if decision and chosen.rank > decision.shownCount:
                decision.shownCount = chosen.rank
            matching_flow.select(state, client, chosen.id, who)
    elif action == 'approve_handover':
        client_actions.approve_handover(state, client)
    elif action == 'therapist_plan':
        episode = therapy.episode(state, client.id)
        if episode and episode.status == 'active':
            therapy.configure(state, client, episode.therapistId, step['plan'], records.therapist_actor(episode.therapistId))
    elif action == 'match_feedback':
        client_actions.submit_match_feedback(state, client, step['values'])
    elif action == 'request_human':
        client_actions.request_human(state, client, step.get('reason', 'other'), step.get('message', ''))


def build_seed_state() -> ValitukiState:
    data = content.seed_clients()
    today = data['demoToday']
    start = int(data['seedStartOffset'])
    state = ValitukiState(currentDate=add_days(today, start), demoStartDate=today)
    state.users.append(User(id='u-coordinator', role='coordinator', displayName='Care coordinator Riikka (demo)'))
    _therapists(state)
    for opening in data['pendingSlotOpenings']:
        state.pendingSlotOpenings.append(PendingSlotOpening(**opening))

    for offset in range(start, 1):
        state.currentDate = add_days(today, offset)
        adapters.therapist_directory.sync_calendars(state)
        orchestrator.tick(state, DemoAIProvider())
        for opening in [o for o in data['slotOpenings'] if o['offset'] == offset]:
            simulation.open_slot(state, opening, actor='therapist_directory_adapter')
        for spec in data['clients']:
            if spec['enrollOffset'] == offset:
                _enroll(state, spec, today)
            script = spec.get('intake') or {}
            if script.get('mode') == 'seed' and script.get('offset') == offset:
                intake.run_scripted(state, get_client(state, spec['id']), script, records.client_actor(spec['id']), from_records=True)
            for step in [s for s in spec.get('script', []) if s['offset'] == offset]:
                _script(state, get_client(state, spec['id']), step)
        if offset < 0:  # today's check-ins are left open for the live demo
            simulation.run_client_day(state)
    for notification in state.notifications:  # the synthetic history has been "read"; only the last two days stay new
        notification.read = notification.createdAt[:10] < add_days(today, -1)
    records.audit(state, actor=records.SYSTEM, action='seed_ready',
                  detail=f'Synthetic demo built: {len(state.clients)} clients, {len(state.therapists)} therapists.')
    return state
