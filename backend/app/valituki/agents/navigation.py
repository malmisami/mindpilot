"""NavigationAgent – guides the next service step and manages the hand-offs of the journey.

Invitation → intake → support plan → therapist search → matches → booking → user-approved handover → therapy →
therapist-guided between-session support. It also handles the client's own requests for a human.
"""
from __future__ import annotations

from app.valituki import fit_profile, handover, journey, matching_flow, records, therapy
from app.valituki.agents import base
from app.valituki.ai import DemoAIProvider
from app.valituki.labels import CONTACT_REASONS, count_word, fmt_slot_title, plural
from app.valituki.models import AgentEvent, ClientProfile, ValitukiState
from app.valituki.store import get_therapist, now

AGENT = 'NavigationAgent'


def _client(state: ValitukiState, event: AgentEvent) -> ClientProfile:
    return next(c for c in state.clients if c.id == event.clientId)


def on_enrolled(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = _client(state, event)
    records.notify(state, audience='client', client_id=client.id, kind='info', event=event, agent=AGENT, action_view='intake',
                   title='Support starts now, even if therapy does not start yet',
                   body='You are on the waiting list for therapy. Mieliluotsi is by your side while you wait – it starts with a '
                        'short conversation.')
    records.act(state, agent=AGENT, type='send_invitation', event=event, rule_id='NAV-001',
                title='Mieliluotsi sent an invitation right after the client joined the waiting list',
                detail='Using it is voluntary. Mieliluotsi is not a therapist or an emergency service.')


def on_insights_approved(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = _client(state, event)
    fit_profile.rebuild(state, client, agent=AGENT, create=True, reason=event.payload.get('reason', 'The approved information was updated'))


def on_baseline(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = _client(state, event)
    records.notify(state, audience='client', client_id=client.id, kind='info', event=event, agent=AGENT, action_view='today',
                   title='Mieliluotsi is now in use',
                   body='While you wait for your first therapy appointment, Mieliluotsi is by your side. You decide what information '
                        'is shared.')
    evaluate_readiness(state, client, provider)


def on_user_requested_human(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = _client(state, event)
    reason_label = CONTACT_REASONS.get(event.payload.get('reason', 'other'), 'Something else')
    task = base.create_task(state, client, agent=AGENT, type='contact_request',
                            priority='high' if event.payload.get('reason') == 'wellbeing' else 'normal',
                            title='The client asked to talk with a professional', reason=reason_label,
                            suggested='Contact the client and record the contact.',
                            data={'reason': event.payload.get('reason'), 'clientMessage': event.payload.get('message') or None},
                            handling_note=base.CONTACT_HANDLING)
    records.notify(state, audience='coordinator', client_id=client.id, kind='contact', event=event, agent=AGENT,
                   title=f'Contact request: {client.displayName}', body=reason_label)
    records.notify(state, audience='client', client_id=client.id, kind='contact', event=event, agent=AGENT, action_view='messages',
                   title='Your request has been passed on to the care team', body=base.CONTACT_HANDLING)
    records.act(state, agent=AGENT, type='forward_contact_request', event=event, rule_id='HUMAN-REQ-001',
                title='Passed the contact request on to the care team straight away', detail=f'Task {task.id}: {reason_label}.')


def on_review_completed(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = _client(state, event)
    outcome = event.payload.get('outcome') or 'Reviewed'
    records.notify(state, audience='client', client_id=client.id, kind='review', event=event, agent=AGENT, action_view='today',
                   title='A professional has reviewed your situation',
                   body=f'{outcome}. Support continues. You can always ask to talk with a professional.')
    records.act(state, agent=AGENT, type='resume_support', event=event, rule_id='NAV-REVIEW-001',
                title='Resumed support after the professional review', detail=f"The professional's decision: {outcome}.")
    matching_flow.release_held(state, client, provider)


def on_matching_ready(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = _client(state, event)
    records.notify(state, audience='client', client_id=client.id, kind='matching', event=event, agent=AGENT, action_view='matching',
                   title='We are looking for a therapist who suits your situation',
                   body='Your Therapy Fit Profile is ready. When a suitable therapist has a free slot, you will see the options and the '
                        'reasons for them.')
    records.act(state, agent=AGENT, type='enter_matching', event=event, rule_id='MATCH-READY-001',
                title='Mieliluotsi started the therapist search',
                detail='The readiness criteria were met (approved profile, matching permission, check-ins, waiting list position). '
                       'Matching runs when capacity opens.')


def on_matches_generated(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = _client(state, event)
    count = int(event.payload.get('candidates', 0))
    if count == 0:
        return
    if event.payload.get('held'):
        records.act(state, agent=AGENT, type='hold_matches', event=event, rule_id='NAV-HOLD-001',
                    title='The therapist suggestions are waiting for a professional review',
                    detail='The suggestions are shown once the open review request has been handled.')
        return
    shown = min(count, 3)
    headline = 'We found a therapist who suits your situation.' if shown == 1 else \
        f'We found {count_word(shown)} therapists who suit your situation.'
    records.notify(state, audience='client', client_id=client.id, kind='matching', event=event, agent=AGENT, action_view='matching',
                   title=headline,
                   body='For each one, you can see why they are suggested and which wishes could not be met. The choice is yours.')
    records.notify(state, audience='coordinator', client_id=client.id, kind='matching', event=event, agent=AGENT,
                   title=f'Matching ready: {client.displayName}',
                   body=f'{plural(shown, "option")} {"was" if shown == 1 else "were"} shown to the client.')


def on_match_selected(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = _client(state, event)
    therapist = get_therapist(state, event.payload['therapistId'])
    records.notify(state, audience='coordinator', client_id=client.id, kind='matching', event=event, agent=AGENT,
                   title=f'{client.displayName} chose a therapist',
                   body=f'Choice: {therapist.name}. The appointment was booked automatically.')
    records.act(state, agent=AGENT, type='forward_selection', event=event, rule_id='NAV-MATCH-001',
                title=f'Passed your choice on to appointment booking: {therapist.name}', detail='The first suitable time was booked.')


def on_first_session_booked(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = _client(state, event)
    therapist = get_therapist(state, event.payload['therapistId'])
    when = event.payload.get('startText') or fmt_slot_title(event.payload['start'])
    client.preparationChecklist = [
        {'id': 'handover', 'text': 'Check and approve the summary for the first session', 'done': False},
        {'id': 'topics', 'text': 'Choose 1–3 things you would like to start with', 'done': False},
        {'id': 'practical', 'text': 'Check the time and the link for the remote session', 'done': False},
    ]
    client.matchingNotificationsPaused = True
    records.act(state, agent=AGENT, type='book_first_session', event=event, rule_id='NAV-BOOK-001',
                title=f'Booked the first session: {when}', detail=f'{therapist.name}. AppointmentAdapter (demo).')
    record = handover.get_or_create(state, client, records.agent_actor(AGENT))
    handover.refresh_draft(state, client, record, provider or DemoAIProvider(), agent=AGENT)
    records.notify(state, audience='client', client_id=client.id, kind='handover', event=event, agent=AGENT, action_view='matching',
                   title='Your first session has been booked',
                   body=f'{therapist.name}, {when}. The summary for the first session is waiting for you – nothing is shared before '
                        'you approve it.')
    records.notify(state, audience='therapist', therapist_id=therapist.id, client_id=client.id, kind='matching', event=event,
                   agent=AGENT, title=f'New client: {client.displayName}',
                   body=f'First session {when}. The summary is visible once the client has approved it.')


def on_handover_approved(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = _client(state, event)
    therapist = get_therapist(state, event.payload['therapistId'])
    sections = len(event.payload.get('sections', []))
    records.notify(state, audience='therapist', therapist_id=therapist.id, client_id=client.id, kind='handover', event=event,
                   agent=AGENT, title=f'Summary approved by {client.firstName}',
                   body=f'{client.displayName} approved the summary for sharing before the first session.')
    records.act(state, agent=AGENT, type='share_handover', event=event, rule_id='HANDOVER-002',
                title=f'Shared the summary you approved with the therapist ({therapist.name})',
                detail=f'Only the parts you approved are included ({sections}). The chat history was not shared. You can withdraw '
                       'the sharing.')


def on_therapy_started(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = _client(state, event)
    therapist = get_therapist(state, event.payload['therapistId'])
    episode = therapy.episode(state, client.id)
    if episode:
        episode.status = 'active'
        episode.startedAt = event.occurredAt
        episode.sessionsHeld = max(1, episode.sessionsHeld)
    client.mode = 'therapy_support'
    client.todayActivity = None
    if client.journeyState == 'HUMAN_REVIEW_NEEDED':
        journey.set_resume_state(client, 'THERAPY_ACTIVE')
    first = therapist.name.split()[0]
    records.act(state, agent=AGENT, type='switch_mode', event=event, rule_id='THERAPY-001',
                title='Switched to between-session support',
                detail=f'Your therapist {first} sets how Mieliluotsi supports you between sessions. Until then, Mieliluotsi '
                       'continues with check-ins and safety instructions only.')
    records.notify(state, audience='client', client_id=client.id, kind='therapy', event=event, agent=AGENT, action_view='plan',
                   title='Therapy started',
                   body='Your therapist sets how Mieliluotsi supports you between sessions. Mieliluotsi does not replace your '
                        "therapist – it works within the limits your therapist sets.")
    records.notify(state, audience='client', client_id=client.id, kind='review', event=event, agent=AGENT, action_view='matching',
                   title='How does working with your therapist feel?',
                   body='Short feedback helps make sure the collaboration feels right. Your answers do not change the therapist '
                        'automatically.')
    records.notify(state, audience='therapist', therapist_id=therapist.id, client_id=client.id, kind='therapy', event=event,
                   agent=AGENT, title=f'Set up between-session support: {client.displayName}',
                   body='You can set the main goal, the allowed exercises, the check-in frequency, what is tracked and the topics '
                        'Mieliluotsi does not address.')


def on_therapy_ended(state: ValitukiState, event: AgentEvent, provider) -> None:
    from app.valituki import practice

    client = _client(state, event)
    plan = therapy.aftercare_plan(state, client.id)
    therapist = get_therapist(state, event.therapistId or (plan.therapistId if plan else ''))
    client.mode = 'aftercare_support'
    client.todayActivity = None
    if client.journeyState == 'HUMAN_REVIEW_NEEDED':
        journey.set_resume_state(client, 'AFTERCARE')
    first = therapist.name.split()[0]
    records.act(state, agent=AGENT, type='switch_mode', event=event, rule_id='AFTERCARE-001',
                title='Switched to follow-up after therapy',
                detail=f'Your therapist {first} drew up a maintenance plan. From now on, mood and anxiety are followed at the agreed '
                       'rhythm; if your wellbeing drops, the care team gets a review request.')
    records.notify(state, audience='client', client_id=client.id, kind='therapy', event=event, agent=AGENT, action_view='path',
                   title='Therapy ended – follow-up continues',
                   body='Mieliluotsi follows your mood and anxiety at the agreed rhythm, and the exercises are still available to you.')
    practice.say(state, client, f'Your therapy with {first} has ended – great work. Follow-up continues: I will ask about your '
                                'mood and anxiety at the agreed rhythm, and the exercises are still available to you. '
                                'You can find your maintenance plan on the Care pathway page.')


# --- daily rules ---------------------------------------------------------------------------------------------------------

def evaluate_readiness(state: ValitukiState, client: ClientProfile, provider) -> None:
    if client.journeyState != 'WAITING_ACTIVE':
        return
    criteria = matching_flow.readiness(state, client)
    if all(item['passed'] for item in criteria):
        event = journey.apply(state, client, 'MATCHING_READINESS_MET', actor=records.agent_actor(AGENT), source='rule_based',
                              payload={'ruleId': 'MATCH-READY-001', 'criteria': criteria})
        from app.valituki.agents import orchestrator

        orchestrator.dispatch(state, event, provider)


def hold_first_session(state: ValitukiState, client: ClientProfile, provider, at: str = '18:50') -> bool:
    """AppointmentAdapter signal: the first session was held → THERAPY_STARTED."""
    waiting = client.journeyState == 'MATCH_ACCEPTED' or (client.journeyState == 'HUMAN_REVIEW_NEEDED'
                                                           and client.resumeState == 'MATCH_ACCEPTED')
    booking = handover.active_booking(state, client.id)
    if not waiting or booking is None or booking.status != 'booked':
        return False
    booking.status = 'completed'
    booking.updatedAt = now(state, at)
    event = journey.apply(state, client, 'THERAPY_STARTED', actor='appointment_adapter', source='appointment_adapter',
                          therapist_id=booking.therapistId, payload={'bookingId': booking.id, 'therapistId': booking.therapistId})
    from app.valituki.agents import orchestrator

    orchestrator.dispatch(state, event, provider)
    return True


def therapy_progress(state: ValitukiState, client: ClientProfile, provider) -> None:
    booking = handover.active_booking(state, client.id)
    if booking and booking.status == 'booked' and booking.start[:10] < state.currentDate:
        hold_first_session(state, client, provider, at='09:00')
