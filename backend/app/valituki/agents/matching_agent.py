"""MatchingAgent – triggers deterministic matching when capacity opens and explains the result in plain language.

It never re-matches on its own: negative feedback after the first sessions creates a "Matching review requested" task for
a professional.
"""
from __future__ import annotations

from app.valituki import adapters, content, matching_flow, records
from app.valituki.agents import base
from app.valituki.labels import count_word, fmt_slot
from app.valituki.models import AgentEvent, ValitukiState
from app.valituki.store import get_therapist

AGENT = 'MatchingAgent'


def on_slot_opened(state: ValitukiState, event: AgentEvent, provider) -> None:
    therapist = get_therapist(state, event.therapistId)
    created = adapters.therapist_directory.sync_calendars(state, therapist.id)
    first = min((s.start for s in created), default=None)
    records.act(state, agent=AGENT, type='detect_capacity', event=event, visibility='professional', rule_id='CAP-001',
                title=f'Detected a client place that opened up: {therapist.name}',
                detail=f'{event.payload.get("reason", "")} First new time: {fmt_slot(first)}. Matching runs for everyone whose '
                       'therapist search is under way.')
    matching_flow.run(state, event, provider, therapist_id=therapist.id)


def on_matches_generated(state: ValitukiState, event: AgentEvent, provider) -> None:
    count = int(event.payload.get('candidates', 0))
    if event.payload.get('released'):
        return
    if count == 0:
        records.act(state, agent=AGENT, type='run_matching', event=event, visibility='professional', rule_id='MATCH-RUN-001',
                    title='Ran the matching – no free therapists who meet all the criteria were found',
                    detail='Matching runs again when capacity opens.')
        return
    shown = min(count, int(content.matching_config()['shownCandidates']))
    top = ', '.join(event.payload.get('top', []))
    records.act(state, agent=AGENT, type='run_matching', event=event, rule_id='MATCH-RUN-001',
                title=f'Ran the therapist matching – found {count_word(shown)} suitable options' if shown > 1
                else 'Ran the therapist matching – found one suitable option',
                detail=f'{top}. Hard criteria (language, remote session, capacity, competence…) first, then a transparent '
                       'weighted fit. The explanations were phrased from the matching criteria only.',
                ai_task='generateMatchExplanation')


def on_match_feedback(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = next(c for c in state.clients if c.id == event.clientId)
    feedback = next(f for f in state.matchFeedback if f.id == event.payload['feedbackId'])
    therapist = get_therapist(state, feedback.therapistId)
    if not feedback.negative:
        records.act(state, agent=AGENT, type='store_feedback', event=event, rule_id='MATCH-FEEDBACK-001',
                    title='Saved the feedback on the collaboration',
                    detail='The feedback helps assess the quality of the matching. Thank you!')
        return
    task = base.create_task(
        state, client, agent=AGENT, type='matching_review', priority='normal', title='Matching review requested',
        reason=f'The feedback on the collaboration (therapist {therapist.name}) was negative (feeling heard {feedback.heard}/5, '
               f'goals understood {feedback.goalsUnderstood}/5, way of working {feedback.styleFit}/5).',
        suggested='Talk with the client. The therapist is not changed automatically.',
        data={'feedbackId': feedback.id, 'note': feedback.note or None, 'wantContinue': feedback.wantContinue,
              'wantDiscussAlternative': feedback.wantDiscussAlternative})
    feedback.reviewTaskId = task.id
    records.notify(state, audience='coordinator', client_id=client.id, kind='review', event=event, agent=AGENT,
                   title=f'Matching review requested: {client.displayName}',
                   body='The feedback on the collaboration was negative. No automatic change.')
    records.notify(state, audience='client', client_id=client.id, kind='contact', event=event, agent=AGENT, action_view='matching',
                   title='Thank you for the feedback',
                   body='The therapist is not changed automatically. The care team will contact you and go through the situation with you.')
    records.act(state, agent=AGENT, type='request_matching_review', event=event, rule_id='MATCH-FEEDBACK-001',
                title='Asked a professional to review the matching',
                detail='Negative feedback does not change the therapist automatically – the decision is made together with a '
                       'professional.')
