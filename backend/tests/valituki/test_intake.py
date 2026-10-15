"""Conversational intake: interpretations stay proposals until the client approves them."""
from __future__ import annotations

import pytest

from app.valituki import content, fit_profile, insights, intake, interpret, matching_flow, records
from app.valituki.ai import DemoAIProvider
from app.valituki.matching_flow import MatchingError

from .conftest import client_of

CONSENT = {'proactiveCheckins': True, 'storeHistory': True, 'professionalMonitoring': True}


def _converse(state, client):
    answers = content.client_spec(client.id)['intake']['answers']
    who = records.client_actor(client.id)
    session = intake.start(state, client, CONSENT, who)
    while session.status == 'conversation':
        intake.answer(state, client, answers[session.pendingQuestionKey], DemoAIProvider(), who)
    return session


def test_intake_asks_focused_questions_one_at_a_time(state):
    client = client_of(state)
    session = intake.start(state, client, CONSENT, records.client_actor(client.id))
    assert session.messages[-1].text == 'Tell me in your own words why you sought help.'
    intake.answer(state, client, 'My work-related anxiety has grown, and I get nervous about meetings.', DemoAIProvider(),
                  'client:cl-aino')
    questions = [m for m in session.messages if m.role == 'assistant' and m.questionKey]
    assert questions[-1].text.count('?') == 1
    assert session.pendingQuestionKey == 'change'
    assert session.messages[-2].text == 'Thank you for telling me. It sounds like situations at work are central here.'


def test_conversational_intake_does_not_automatically_approve_inferred_information(state):
    """Test 1: AI inferences are proposals – nothing is stored, profiled or matchable before explicit approval."""
    client = client_of(state)
    session = _converse(state, client)
    assert session.status == 'review'
    assert {p.category for p in session.proposals} >= {'goal', 'working_style', 'practical'}
    goal = next(p for p in session.proposals if p.category == 'goal')
    assert goal.text == 'I want to be able to manage the anxiety related to work situations.'
    assert insights.for_client(state, client.id) == []
    assert insights.for_client(state, client.id, status=None) == []
    assert fit_profile.get(state, client.id) is None
    with pytest.raises(MatchingError):
        matching_flow.build_input(state, client)

    intake.confirm(state, client, records.client_actor(client.id))
    approved = insights.for_client(state, client.id)
    assert {i.kind for i in approved} >= {'primary_goal', 'working_style', 'practical'}
    assert all(i.status == 'approved' and i.approvedAt for i in approved)
    assert fit_profile.get(state, client.id) is not None


def test_excluded_or_edited_proposals_are_respected(state):
    client = client_of(state)
    session = _converse(state, client)
    style = next(p for p in session.proposals if p.category == 'working_style')
    goal = next(p for p in session.proposals if p.category == 'goal')
    intake.update_proposal(state, client, style.id, {'included': False})
    intake.update_proposal(state, client, goal.id, {'text': 'I want to get through meetings without sleepless nights.'})
    intake.confirm(state, client, records.client_actor(client.id))
    kinds = {i.kind for i in insights.for_client(state, client.id)}
    assert 'working_style' not in kinds
    primary = insights.for_client(state, client.id, kind='primary_goal')[0]
    assert primary.text == 'I want to get through meetings without sleepless nights.'
    assert primary.origin == 'user_said' and primary.editedByClient


def test_intake_completion_starts_support_immediately(state):
    client = client_of(state)
    _converse(state, client)
    intake.confirm(state, client, 'client:cl-aino')
    intake.complete(state, client, {'checkInDays': [0, 2, 5], 'communicationStyle': 'brief'}, 3, 'client:cl-aino')
    assert client.journeyState == 'WAITING_ACTIVE'
    assert client.baseline == 3
    assert client.nextCheckInDate
    assert any(a.clientId == client.id and a.type == 'create_plan' for a in state.actions)
    assert client.todayActivity is not None


def test_the_client_can_choose_calls_instead_of_writing(state):
    """Vointipuhelu: the check-in days stay, Mieliluotsi calls at the chosen time; the choice is in the profile."""
    from app.valituki.view import client_view

    client = client_of(state)
    _converse(state, client)
    intake.confirm(state, client, 'client:cl-aino')
    intake.complete(state, client, {'checkInDays': [0, 2, 5], 'contactChannel': 'phone', 'callTime': '09:00'}, None, 'client:cl-aino')
    assert client.contactChannel == 'phone' and client.callTime == '09:00'
    check = client_view(state, client)['checkIn']
    assert check['channel'] == 'phone' and check['callTime'] == '09:00' and check['needsBaseline']
    rhythm = next(i for i in state.insights if i.clientId == client.id and i.kind == 'engagement')
    assert rhythm.text.startswith('Wellbeing call 3× a week at 09:00') and rhythm.structured['contactChannel'] == 'phone'
    # An unknown time falls back to the evening; the app channel needs no time.
    other = client_of(state, 'cl-mikko')
    assert other.contactChannel == 'app' and other.callTime is None


def test_the_client_can_start_from_the_records_without_an_intake_conversation(state):
    """No separate intake conversation: with consent the referral and the assessment visit become the starting profile,
    labelled as such, and the next screen is the rhythm."""
    client = client_of(state)
    known = content.client_spec(client.id)['intake']['answers']
    session = intake.start_from_records(state, client, CONSENT, known, 'client:cl-aino')
    assert session.status == 'rhythm'
    assert session.messages == [] and session.pendingQuestionKey is None
    approved = insights.for_client(state, client.id)
    assert {i.kind for i in approved} >= {'primary_goal', 'working_style', 'practical'}
    assert all(i.sourceLabel.startswith('Records') for i in approved)
    assert fit_profile.get(state, client.id) is not None
    assert any(a.action == 'intake_from_records' for a in state.audit)
    intake.complete(state, client, {'checkInDays': [0, 4], 'communicationStyle': 'brief'}, None, 'client:cl-aino')
    assert client.journeyState == 'WAITING_ACTIVE'
    # Without anything to build on the client goes straight to the rhythm; the profile grows from the conversations.
    other = client_of(state, 'cl-noora')
    assert intake.start_from_records(state, other, CONSENT, {}, 'client:cl-noora').status == 'rhythm'
    assert insights.for_client(state, other.id) == []


def test_todays_wellbeing_can_be_answered_on_the_home_screen_after_the_intake(state):
    client = client_of(state)
    _converse(state, client)
    intake.confirm(state, client, 'client:cl-aino')
    intake.complete(state, client, {'checkInDays': [0, 2, 5], 'communicationStyle': 'brief'}, None, 'client:cl-aino')
    assert client.journeyState == 'WAITING_ACTIVE'
    assert client.baseline is None
    assert intake.needs_baseline(state, client)
    intake.record_baseline(state, client, 3, 'client:cl-aino', anxiety=3)
    assert client.baseline == 3
    assert not intake.needs_baseline(state, client)
    with pytest.raises(intake.IntakeError):
        intake.record_baseline(state, client, 4, 'client:cl-aino')


def test_safety_phrase_in_intake_interrupts_the_conversation(state):
    client = client_of(state)
    session = intake.start(state, client, CONSENT, 'client:cl-aino')
    result = intake.answer(state, client, "I can't cope any more, I want to die.", DemoAIProvider(), 'client:cl-aino')
    assert result['safety']['level'] == 3
    assert client.safetyLock and not client.safetyLock.dismissedAt
    assert session.messages[-1].source == 'fixed' and '112' in session.messages[-1].text


def test_finnish_safety_phrase_in_intake_still_interrupts(state):
    client = client_of(state)
    intake.start(state, client, CONSENT, 'client:cl-aino')
    result = intake.answer(state, client, 'En jaksa enää, haluaisin kuolla.', DemoAIProvider(), 'client:cl-aino')
    assert result['safety']['level'] == 3


FINNISH_ANSWERS = {
    'reason': 'Olen hakenut apua, koska työhön liittyvä ahdistus on kasvanut. Jännitän palavereja niin, että nukun huonosti.',
    'change': 'Haluaisin pystyä hallitsemaan työtilanteisiin liittyvää ahdistusta.',
    'exercises': 'Konkreettisia harjoituksia ja selkeää etenemistä. Välitehtävätkin sopivat minulle.',
    'challenge': 'Saa haastaa, kunhan ote on selkeä.',
    'practical': 'Etävastaanotto sopisi parhaiten, suomeksi. Tiistai- tai torstai-illat käyvät.',
}


def test_finnish_and_english_answers_are_interpreted_the_same_way():
    """The interpretation is bilingual: the persona's English answers and the same answers in Finnish give the same proposals,
    written in English."""
    english = content.client_spec('cl-aino')['intake']['answers']

    def structured(answers):
        proposals = [p for p in interpret.extract(answers, 'Espoo') if p['category'] in ('goal', 'working_style', 'practical')]
        return {p['category']: (p['text'], p['structured'].get('primary', {}).get('topics'),
                                {k: v for k, v in p['structured'].items() if k not in ('primary', 'secondary', 'hope')})
                for p in proposals}

    assert structured(english) == structured(FINNISH_ANSWERS)
    goal, style, practical = (structured(english)[k] for k in ('goal', 'working_style', 'practical'))
    assert goal[:2] == ('I want to be able to manage the anxiety related to work situations.', ['anxiety', 'work_stress'])
    assert style[2] == {'structure': 'structured', 'exercises': 'concrete', 'approach': 'directive', 'homework': 'yes'}
    assert style[0] == ('You like concrete exercises and clear progress. The therapist may also challenge you. '
                        'Between-session tasks suit you.')
    assert practical[2]['format'] == 'remote' and practical[2]['languages'] == ['fi'] and practical[2]['days'] == [1, 3]
    assert practical[0] == 'Remote session, in Finnish, evenings (Tuesday or Thursday).'
    turku = interpret.extract_practical({'practical': 'In person in Turku, in Finnish or Swedish. Mornings.'}, 'Turku')
    assert turku['languages'] == ['fi', 'sv'] and turku['format'] == 'in_person' and turku['times'] == ['morning']
