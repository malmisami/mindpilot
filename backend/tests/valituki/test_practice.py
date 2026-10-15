"""Guided CBT practice in the chat: rules decide the steps, the model only phrases, safety first, private by default."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.valituki import ai, client_actions, content, handover, labels, matching_flow, practice, professional, simulation, therapy, view
from app.valituki.ai import ClaudeAIProvider, DemoAIProvider, GuidedTurn
from app.valituki.practice import PracticeError
from app.valituki.safety import SAFETY_REPLY
from app.valituki.store import add_days

from .conftest import client_of, run_intake

DEMO = content.client_spec('cl-aino')['practiceDemo']


def _chat(state, client_id='cl-aino'):
    return [m for m in state.chat if m.clientId == client_id]


def _thought_record(state, client, answers=None, actor='client:cl-aino'):
    practice.start(state, client, 'thought_record', DemoAIProvider(), actor, prefill={'situation': 'On Tuesday I have to present.'})
    practice.run_script(state, client, {'thought_record': {**DEMO['thought_record'], 'nextStep': 'none', **(answers or {})}},
                        actor=actor)
    return state.thoughtRecords[-1]


def test_the_chat_offers_a_guided_tool_and_the_client_decides(state):
    client = run_intake(state)
    client_actions.send_message(state, client, DEMO['message'])
    offer = _chat(state)[-1]
    assert offer.kind == 'offer' and offer.widget.data['tool'] == 'thought_record'
    assert [o.value for o in offer.widget.options] == ['start:thought_record', 'dismiss']
    assert practice.active_session(state, client.id) is None  # nothing starts before the client chooses
    client_actions.choose_offer(state, client, offer.id, 'start:thought_record')
    session = practice.active_session(state, client.id)
    assert session.tool == 'thought_record' and session.answers['situation'] == DEMO['message']
    assert session.step == 'thought'  # the situation the client already wrote is not asked again
    with pytest.raises(PracticeError):
        client_actions.choose_offer(state, client, offer.id, 'dismiss')  # an answered offer cannot be used twice


def test_thought_record_follows_the_rules_and_stays_private(state):
    client = run_intake(state)
    record = _thought_record(state, client)
    assert (record.intensityBefore, record.intensityAfter) == (8, 5)
    assert record.suggestedTraps == ['fortune_telling', 'mind_reading']  # phrase rules on "definitely mess up … notice"
    assert record.traps == ['fortune_telling', 'mind_reading'] and record.shared is False
    steps = [m.stepKey for m in _chat(state) if m.kind == 'question' and m.sessionId == record.sessionId]
    assert steps == ['thought', 'emotions', 'intensityBefore', 'behaviour', 'traps', 'evidenceFor', 'evidenceAgainst', 'alternative',
                     'intensityAfter', 'nextStep']
    questions = [m.text for m in _chat(state) if m.kind == 'question']
    assert all(q.count('?') <= 1 for q in questions)  # one question at a time
    assert any(m.kind == 'summary' and m.widget.data['change'] == {'label': 'Anxiety and nervousness', 'before': 8, 'after': 5,
                                                                    'max': 10} for m in _chat(state))
    # The journal is the client's own: never on a professional timeline, never in the coordinator's view.
    detail = view.professional_client(state, client)
    assert not any('thought' in row['title'].lower() for row in detail['timeline'])
    assert all(a['visibility'] != 'private' for a in view.professional_view(state)['timeline'])
    assert any(row['title'].startswith('Saved “Exploring a thought”') for row in view.client_view(state, client)['timeline'])


@pytest.mark.parametrize('phrase', ["I can't go on. I've started to think that I want to die.",
                                    'En jaksa enää. Olen alkanut ajatella, että haluaisin kuolla.'])
def test_a_level_three_phrase_in_an_exercise_interrupts_before_any_model_call(state, phrase):
    client = run_intake(state)

    class Spy(DemoAIProvider):
        calls = 0

        def generate_guided_turn(self, ctx):
            Spy.calls += 1
            return super().generate_guided_turn(ctx)

    spy = Spy()
    practice.start(state, client, 'thought_record', spy, 'client:cl-aino', prefill={'situation': 'A meeting tomorrow.'})
    before = Spy.calls
    result = practice.answer(state, client, phrase, spy, 'client:cl-aino')
    assert result['safety']['level'] == 3
    assert Spy.calls == before  # the next question was never generated
    session = state.guidedSessions[-1]
    assert session.status == 'stopped' and session.answers == {}
    assert _chat(state)[-1].text == SAFETY_REPLY
    assert client.safetyLock and not client.safetyLock.dismissedAt
    assert not state.thoughtRecords
    allowed, reason = practice.tool_allowed(state, client, 'thought_record')
    assert not allowed and 'safety instructions' in reason


def test_a_model_turn_is_validated_and_falls_back_to_the_approved_question(monkeypatch):
    replies = iter([
        ({'reflection': 'You have an anxiety disorder.', 'question': 'What did you think? And why?', 'safetyHint': 'NONE'}, None),
        ({'reflection': 'That thought sounds heavy.', 'question': 'What did you think right then?', 'safetyHint': 'NONE',
          'suggestedTraps': ['fortune_telling', 'not_a_trap'], 'examples': ["I've prepared, and I can feel nervous and still do well."]},
         None),
    ])
    monkeypatch.setattr(ai, '_json', lambda task, prompt, schema: next(replies))
    provider = ClaudeAIProvider()
    ctx = {'tool': 'thought_record', 'toolTitle': 'Exploring a thought', 'stepKey': 'thought', 'question': 'What did you think?',
           'approvedQuestion': 'What did you think?', 'previousKey': 'situation', 'previousValue': 'A meeting', 'answers': {},
           'suggestedTraps': ['mind_reading'], 'examples': ['An example'], 'ladder': [], 'trapCatalog': practice.trap_catalog(),
           'wantTraps': True, 'wantExamples': True, 'wantLadder': False}
    first = provider.generate_guided_turn(ctx)
    assert first.source == 'fallback' and first.question == 'What did you think?'
    assert 'diagnosis claim' in first.violations and 'more than one question' in first.violations
    second = provider.generate_guided_turn(ctx)
    assert second.source == 'live' and second.suggestedTraps == ['fortune_telling']  # unknown ids are dropped
    assert second.examples == ["I've prepared, and I can feel nervous and still do well."]


def test_a_model_can_only_add_caution_during_an_exercise(state):
    client = run_intake(state)

    class Worried(DemoAIProvider):
        def generate_guided_turn(self, ctx):
            turn = super().generate_guided_turn(ctx)
            return GuidedTurn(reflection=turn.reflection, question=turn.question, safetyHint='URGENT', source='live')

    practice.start(state, client, 'thought_record', Worried(), 'client:cl-aino')
    assert state.guidedSessions[-1].status == 'stopped'
    assert client.safetyLock is not None
    assert any(o.clientId == client.id and o.level == 3 and o.aiLevel == 3 for o in state.safetyObservations)


def test_the_check_in_runs_as_a_conversation_with_mood_and_anxiety(state):
    client = run_intake(state)
    client.simulationProfile = 'none'  # nobody answers for Sami – the question waits in the chat
    simulation.advance(state, 1)  # Saturday: the agent opens the due check-in in the chat
    session = practice.active_session(state, client.id)
    assert session.tool == 'checkin' and session.startedFrom == 'agent' and session.step == 'mood'
    assert _chat(state)[-2].text.startswith('Hi Sami! It is time for a short check-in')
    provider = DemoAIProvider()
    practice.answer(state, client, 3, provider, 'client:cl-aino')
    with pytest.raises(PracticeError):
        practice.answer(state, client, "I don't know", provider, 'client:cl-aino')  # an anxiety answer is needed
    practice.answer(state, client, '4', provider, 'client:cl-aino', from_text=True)
    practice.answer(state, client, ['sleep'], provider, 'client:cl-aino')
    practice.answer(state, client, "Tuesday's presentation makes me nervous.", provider, 'client:cl-aino')
    checkin = max((c for c in state.checkIns if c.clientId == client.id and c.status == 'completed'), key=lambda c: c.completedAt)
    assert (checkin.mood, checkin.anxiety) == (3, 4)
    assert checkin.changes == {'sleep': 'worse', 'anxiety': 'worse'}  # a high anxiety answer counts as "anxiety worse"
    assert session.status == 'completed' and session.resultId == checkin.id
    offer = _chat(state)[-1]
    assert offer.kind == 'offer' and offer.widget.data['prefill'] == {'situation': "Tuesday's presentation makes me nervous."}
    assert view.client_view(state, client)['progress']['series'][-1]['anxiety'] == 4


def test_exposure_ladder_task_and_attempt(state):
    client = run_intake(state)
    practice.replay(state, client, 'exposure', DEMO['exposure'], actor='client:cl-aino')
    ladder = state.ladders[-1]
    assert [s.expected for s in ladder.steps] == [3, 4, 5, 6, 7, 9] and ladder.steps[0].status == 'doing'
    task = next(t for t in state.practiceTasks if t.clientId == client.id and t.kind == 'exposure_step')
    assert task.dueDate == '2026-10-17' and task.title == ladder.steps[0].text
    result = client_actions.task_action(state, client, task.id, 'done')
    assert result == {'started': 'exposure_attempt'}
    practice.run_script(state, client, {'exposure_attempt': DEMO['exposure_attempt']}, actor='client:cl-aino')
    attempt = ladder.steps[0].attempts[0]
    assert (attempt.before, attempt.peak, attempt.after) == (4, 5, 2) and ladder.steps[0].status == 'done'
    follow = next(t for t in state.practiceTasks if t.status == 'open' and t.kind == 'exposure_step')
    assert follow.stepId == ladder.steps[1].id and task.status == 'done'
    completed = view.client_view(state, client)['practice']['completed']
    assert completed[0]['tag'] == labels.PRACTICE_KINDS['exposure'] and completed[0]['change'] == {'before': 5, 'after': 2}


def _typed(state, client, *answers):
    """Answer the active session's questions with typed chat text, one by one (as send_message does)."""
    for value in answers:
        practice.answer(state, client, value, DemoAIProvider(), 'client:cl-aino', from_text=True)


def test_typed_english_answers_drive_the_thought_record(state):
    client = run_intake(state)
    practice.start(state, client, 'thought_record', DemoAIProvider(), 'client:cl-aino',
                   prefill={'situation': 'On Tuesday I have to present the project to the whole team.'})
    _typed(state, client, "I'll definitely mess up, and everyone will notice that I'm nervous.")
    emotions = next(m for m in reversed(_chat(state)) if m.kind == 'question' and m.stepKey == 'emotions')
    assert emotions.widget.options[0].label == 'Anxiety'
    _typed(state, client, 'Anxious and nervous', 'eight out of ten', "I keep putting off the preparation.")
    assert any(m.text.startswith("That's very understandable – avoiding") for m in _chat(state))  # the avoidance cue
    question = _chat(state)[-1]
    assert question.stepKey == 'traps' and question.widget.suggested == ['fortune_telling', 'mind_reading']
    _typed(state, client, 'Fortune telling and mind reading', 'My voice shook last time.', "You've prepared well.",
           "I can't know in advance how it will go.", '5/10', "That's enough for now")
    record = state.thoughtRecords[-1]
    assert record.emotions == ['ahdistus', 'jannitys'] and (record.intensityBefore, record.intensityAfter) == (8, 5)
    assert record.traps == ['fortune_telling', 'mind_reading'] and record.nextStep == 'none'


def test_typed_finnish_answers_still_work(state):
    client = run_intake(state)
    practice.start(state, client, 'thought_record', DemoAIProvider(), 'client:cl-aino', prefill={'situation': 'Tiistain esitys.'})
    _typed(state, client, 'Mokaan varmasti, ja kaikki huomaavat, että jännitän.', 'ahdistus ja jännitys', 'kahdeksan',
           'Siirrän valmistelua.')
    assert _chat(state)[-1].widget.suggested == ['fortune_telling', 'mind_reading']
    _typed(state, client, 'ennustaminen ja ajatusten lukeminen')
    session = practice.active_session(state, client.id)
    assert session.answers['emotions'] == ['ahdistus', 'jannitys'] and session.answers['intensityBefore'] == 8
    assert session.answers['traps'] == ['fortune_telling', 'mind_reading']
    practice.stop(state, client, 'client:cl-aino')
    practice.start(state, client, 'checkin', DemoAIProvider(), 'client:cl-aino')
    _typed(state, client, 'kohtalaisesti', 'paljon', 'uni ja jaksaminen')
    session = practice.active_session(state, client.id)
    assert (session.answers['mood'], session.answers['anxiety'], session.answers['changes']) == (3, 4, ['sleep', 'energy'])


@pytest.mark.parametrize('goal, template', [('Giving a presentation to the team', 'presentation'),
                                            ('Esityksen pitäminen tiimille', 'presentation'),
                                            ('Making a phone call to the bank', 'phone'),
                                            ('Parties with people I don\'t know', 'social'),
                                            ('Going to the gym', 'generic')])
def test_the_ladder_template_follows_the_goal_in_both_languages(goal, template):
    assert practice.ladder_template(goal)['id'] == template


def test_typed_days_and_choices_in_both_languages(state):
    client = run_intake(state)
    practice.start(state, client, 'exposure', DemoAIProvider(), 'client:cl-aino')
    _typed(state, client, 'Giving a presentation to the team', 'seven')
    steps = [dict(s) for s in practice.ladder_template('presentation')['steps']]
    practice.answer(state, client, steps, DemoAIProvider(), 'client:cl-aino')  # the ladder is saved from its editor
    _typed(state, client, 'Practise the start of the presentation out loud')
    friday = next(d for d in (add_days(state.currentDate, n) for n in range(7)) if date.fromisoformat(d).weekday() == 4)
    _typed(state, client, 'On Friday')
    ladder = state.ladders[-1]
    task = next(t for t in state.practiceTasks if t.sourceId == ladder.id)
    assert ladder.goalAnxiety == 7 and task.dueDate == friday and task.title == ladder.steps[0].text
    client_actions.task_action(state, client, task.id, 'done')
    _typed(state, client, '4', 'viisi', '2', 'Calmer than I expected.', 'seuraavaan', 'huomenna')
    follow = next(t for t in state.practiceTasks if t.status == 'open' and t.kind == 'exposure_step')
    assert follow.stepId == ladder.steps[1].id and follow.dueDate == add_days(state.currentDate, 1)


def test_exposure_is_not_offered_when_distress_is_elevated(state):
    client = run_intake(state)
    client_actions.help_now(state, client)
    client_actions.dismiss_safety(state, client)
    allowed, reason = practice.tool_allowed(state, client, 'exposure')
    assert not allowed and 'more strain than usual' in reason
    assert practice.tool_allowed(state, client, 'thought_record')[0]


def test_the_therapist_decides_the_tools_and_the_weekly_homework(scene):
    state = scene('therapy')
    aino = client_of(state)
    episode = therapy.episode(state, aino.id)
    plan = {**therapy.suggested_plan(state, aino), 'allowedTools': ['thought_record'], 'homeworkTool': 'thought_record',
            'homeworkNote': 'Write down one meeting situation.'}
    therapy.configure(state, aino, episode.therapistId, plan, 'therapist:th-anna')
    allowed, reason = practice.tool_allowed(state, aino, 'exposure')
    assert not allowed and 'therapist' in reason
    homework = [t for t in state.practiceTasks if t.clientId == aino.id and t.kind == 'homework' and t.status == 'open']
    assert len(homework) == 1 and homework[0].assignedBy == 'therapist:th-anna'
    assert homework[0].detail == 'Write down one meeting situation.'
    assert client_actions.task_action(state, aino, homework[0].id, 'done') == {'started': 'thought_record'}
    practice.run_script(state, aino, {'thought_record': {**DEMO['thought_record'], 'nextStep': 'none'}}, actor='client:cl-aino')
    assert homework[0].status == 'done'
    renewed = [t for t in state.practiceTasks if t.clientId == aino.id and t.kind == 'homework' and t.status == 'open']
    assert len(renewed) == 1 and renewed[0].dueDate == add_days(homework[0].dueDate, 7)


def test_the_therapist_sees_a_summary_only_with_permission_and_entries_only_when_shared(scene):
    state = scene('therapy')
    aino = client_of(state)
    record = _thought_record(state, aino)
    since = therapy.episode(state, aino.id).startedAt
    summary = practice.therapist_summary(state, aino, since)
    assert summary['allowed'] and summary['stats']['thoughtRecords'] == 1 and summary['sharedRecords'] == []
    client_actions.set_practice_sharing(state, aino, 'thought_record', record.id, True)
    assert practice.therapist_summary(state, aino, since)['sharedRecords'][0]['thought'] == record.thought
    client_actions.set_consent(state, aino, {'sharePractice': False})
    summary = practice.therapist_summary(state, aino, since)
    assert summary['stats'] is None and len(summary['sharedRecords']) == 1  # an entry the client shared stays shared
    client_actions.remove_practice_item(state, aino, 'thought_record', record.id)
    assert practice.therapist_summary(state, aino, since)['sharedRecords'] == []


def test_the_handover_includes_only_an_aggregated_practice_summary(scene):
    state = scene('matches')
    aino = client_of(state)
    record = next(r for r in state.thoughtRecords if r.clientId == aino.id)
    decision = matching_flow.current_decision(state, aino.id)
    anna = next(c for c in matching_flow.decision_candidates(state, decision) if c.therapistId == 'th-anna')
    client_actions.select_candidate(state, aino, anna.id)
    sections = handover.build_sections(state, aino, handover.find(state, aino.id))
    section = next(s for s in sections if s.key == 'practice')
    assert section.available and section.infoType == 'measured'
    assert 'Exploring a thought 3 times' in section.content['text'] and 'Fortune telling' in section.content['text']
    assert record.thought not in str(section.content)  # journal entries are never copied into the handover


def test_therapy_ends_and_aftercare_follows_mood_and_anxiety(scene):
    state = scene('therapy')
    aino = client_of(state)
    result = simulation.end_therapy(state, aino, weeks=2)
    assert result['journeyState'] == 'AFTERCARE' and aino.mode == 'aftercare_support'
    assert aino.checkInDays == [2]  # once a week
    mode = therapy.mode_summary(state, aino)
    assert mode['title'] == 'Follow-up after therapy' and mode['maintenance'].startswith('Learnt in therapy')
    assert not [t for t in state.practiceTasks if t.clientId == aino.id and t.kind == 'homework' and t.status == 'open']
    assert practice.tool_allowed(state, aino, 'thought_record')[0]
    change = simulation.simulate_deterioration(state, aino, max_days=35)
    assert change['trendChanged'] and aino.journeyState == 'HUMAN_REVIEW_NEEDED' and aino.resumeState == 'AFTERCARE'
    observation = next(o for o in state.wellbeingObservations if o.clientId == aino.id and o.status == 'open')
    professional.review_observation(state, observation.id, 'mark_reviewed', 'Called – follow-up continues.')
    assert aino.journeyState == 'AFTERCARE'


def test_practice_api_end_to_end():
    api = TestClient(app)
    base, q = '/api/valituki', {'clientId': 'cl-aino'}

    def ok(response):
        assert response.status_code == 200, response.text
        return response.json()

    ok(api.post(f'{base}/demo/scene', params=q, json={'scene': 'intake'}))
    view_ = ok(api.post(f'{base}/clients/cl-aino/messages', params=q, json={'text': DEMO['message']}))['view']
    offer = view_['client']['chat'][-1]
    assert offer['kind'] == 'offer' and offer['actionable']
    choice = {'messageId': offer['id'], 'option': 'start:thought_record'}
    view_ = ok(api.post(f'{base}/clients/cl-aino/chat/offer', params=q, json=choice))['view']
    guided = view_['client']['guided']
    assert guided['tool'] == 'thought_record' and guided['stepKey'] == 'thought'
    assert guided['demoAnswer'] == DEMO['thought_record']['thought']
    for _ in range(12):
        guided = view_['client']['guided']
        if not guided or guided['tool'] != 'thought_record':
            break
        body = {'sessionId': guided['id'], 'stepKey': guided['stepKey'], 'value': guided['demoAnswer']}
        if guided['stepKey'] == 'nextStep':
            body['value'] = 'none'
        view_ = ok(api.post(f'{base}/clients/cl-aino/practice/answer', params=q, json=body))['view']
    practice_view = view_['client']['practice']
    assert practice_view['thoughtRecords'][0]['intensityAfter'] == 5 and practice_view['stats']['thoughtRecords'] == 1
    stale = api.post(f'{base}/clients/cl-aino/practice/answer', params=q, json={'sessionId': guided and guided['id'], 'value': 3})
    assert stale.status_code == 409
    record_id = practice_view['thoughtRecords'][0]['id']
    view_ = ok(api.put(f'{base}/clients/cl-aino/practice/thought_record/{record_id}/sharing', params=q, json={'shared': True}))['view']
    assert view_['client']['practice']['thoughtRecords'][0]['shared'] is True
    view_ = ok(api.post(f'{base}/clients/cl-aino/practice/start', params=q, json={'tool': 'exposure'}))['view']
    assert view_['client']['guided']['stepKey'] == 'goal'
    view_ = ok(api.post(f'{base}/clients/cl-aino/practice/stop', params=q, json={}))['view']
    assert view_['client']['guided'] is None and view_['client']['chat'][-1]['kind'] == 'notice'
    assert api.post(f'{base}/clients/cl-aino/practice/start', params=q, json={'tool': 'nope'}).status_code == 422
    scene = ok(api.post(f'{base}/demo/scene', params=q, json={'scene': 'weeks'}))['view']
    task = scene['client']['practice']['tasks'][0]
    assert task['dueLabel'] == 'Today' and task['actionLabel'] == 'Tell me how it went'
    view_ = ok(api.post(f'{base}/clients/cl-aino/tasks/{task["id"]}', params=q, json={'action': 'later'}))['view']
    assert view_['client']['practice']['tasks'][0]['dueLabel'] == 'Tomorrow'
    therapy_view = ok(api.post(f'{base}/demo/scene', params=q, json={'scene': 'therapy'}))['view']
    assert therapy_view['client']['mode']['homework']['tool'] == 'thought_record'
    row = next(r for r in ok(api.get(f'{base}/view', params={**q, 'therapistId': 'th-anna'}))['therapist']['selected']['clients']
               if r['clientId'] == 'cl-aino')
    ended = ok(api.post(f'{base}/therapists/th-anna/clients/cl-aino/end-therapy', params={**q, 'therapistId': 'th-anna'},
                        json=row['therapy']['suggestedAftercare']))['view']
    assert ended['client']['journeyState'] == 'AFTERCARE' and ended['client']['matching']['stage'] == 'aftercare'
    assert ai.effective_mode() == 'DEMO_AI_MODE'
