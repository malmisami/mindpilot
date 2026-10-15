"""AIProvider: DEMO_AI_MODE without a key, LIVE_AI_MODE with validated output and deterministic fallbacks."""
from __future__ import annotations

import json

from app.config import settings
from app.valituki import ai, guard, scenes


def test_demo_ai_mode_works_without_api_key(monkeypatch):
    """Test 15: no key → deterministic provider, and the whole demo journey runs."""
    monkeypatch.setattr(settings, 'VALITUKI_AI_MODE', 'DEMO_AI_MODE')
    assert ai.effective_mode() == 'DEMO_AI_MODE'
    assert isinstance(ai.get_provider(), ai.DemoAIProvider)
    state = scenes.build_scene('therapy')
    assert next(c for c in state.clients if c.id == 'cl-aino').journeyState == 'THERAPY_ACTIVE'
    assert {a.aiSource for a in state.actions if a.aiSource} == {'demo'}


def test_live_mode_without_key_falls_back_to_demo(monkeypatch):
    monkeypatch.setattr(settings, 'VALITUKI_AI_MODE', 'LIVE_AI_MODE')
    assert ai.effective_mode() == 'DEMO_AI_MODE'
    assert 'ANTHROPIC_API_KEY is missing' in ai.status()['note']


def test_an_auth_token_also_enables_live_mode(monkeypatch):
    monkeypatch.setattr(settings, 'VALITUKI_AI_MODE', 'LIVE_AI_MODE')
    monkeypatch.setenv('ANTHROPIC_AUTH_TOKEN', 'test-token')
    assert ai.key_present() and ai.effective_mode() == 'LIVE_AI_MODE'
    assert isinstance(ai.get_provider(), ai.ClaudeAIProvider)
    assert isinstance(ai.get_provider(interactive=False), ai.DemoAIProvider)  # seeding and simulations stay deterministic


def test_a_key_pasted_into_env_is_picked_up_without_a_restart(monkeypatch):
    calls = []
    monkeypatch.setattr(ai, '_claude', lambda prompt, schema=None, max_tokens=8000: (calls.append(prompt) or
                                                                                     '{"reply": "The connection works."}', None))
    result = ai.set_mode('LIVE_AI_MODE')
    assert result['effectiveMode'] == 'DEMO_AI_MODE' and not result['keyPresent']
    assert result['check'] == {'ok': False, 'failure': 'API key missing', 'reply': None, 'ms': None, 'model': None}
    assert calls == []  # without a key the model is never called
    ai.ENV_FILE.write_text('VALITUKI_AI_MODEL=claude-opus-5\nANTHROPIC_API_KEY=test-key-from-env-file\n')
    check = ai.check_connection()
    assert check['ok'] and check['reply'] == 'The connection works.' and len(calls) == 1
    assert ai.status()['effectiveMode'] == 'LIVE_AI_MODE' and ai.status()['lastCall']['task'] == 'connectionCheck'
    assert ai.set_mode('DEMO_AI_MODE')['effectiveMode'] == 'DEMO_AI_MODE'


def test_a_failed_connection_check_names_the_reason(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-key')
    monkeypatch.setattr(ai, '_claude', lambda prompt, schema=None, max_tokens=8000: (None, 'API key not valid (401)'))
    check = ai.check_connection()
    assert check['ok'] is False and check['failure'] == 'API key not valid (401)'
    assert ai.status()['lastCall']['ok'] is False


def test_api_errors_become_readable_reasons():
    class Error:
        def __init__(self, status, message):
            self.status_code, self.body = status, {'type': 'error', 'error': {'type': 'x', 'message': message}}

    assert ai._status_failure(Error(401, 'invalid x-api-key')) == 'API key not valid (401)'
    assert ai._status_failure(Error(404, 'model: claude-x')) == 'model or address not found (404): model: claude-x'
    assert ai._status_failure(Error(500, 'boom')) == 'API error (500)'


def test_the_live_reply_gets_the_conversation_so_far(monkeypatch):
    from app.valituki import client_actions

    state = scenes.build_scene('intake')
    client = next(c for c in state.clients if c.id == 'cl-aino')
    prompts = []

    def fake(prompt, schema=None, max_tokens=8000):
        prompts.append(prompt)
        return ('{"supportiveResponse": "Thank you for telling me. What feels heaviest about it?", "acknowledgedUserNeed": "x", '
                '"approvedActivityId": null, "suggestedTool": "NONE", "suggestedNextAction": "NONE", "safetyHint": "NONE", '
                '"uncertainty": null}', None)

    monkeypatch.setattr(ai, '_claude', fake)
    client_actions.send_message(state, client, 'I have been really tired this week.', ai.ClaudeAIProvider())
    reply = client_actions.send_message(state, client, 'I sleep badly.', ai.ClaudeAIProvider())
    message = next(m for m in state.chat if m.id == reply['messageId'])
    assert message.textSource == 'live'
    context = json.loads(prompts[-1].split('Input (JSON):\n', 1)[1])
    assert context['message'] == 'I sleep badly.'
    texts = [m['text'] for m in context['recentConversation']]
    assert 'I have been really tired this week.' in texts and 'I sleep badly.' not in texts


def test_live_provider_rejects_unsafe_model_text(monkeypatch):
    monkeypatch.setattr(ai, '_claude', lambda prompt, schema=None, max_tokens=8000: (
        '{"supportiveResponse": "Sinulla on masennus. Olen aina täällä sinua varten.", "acknowledgedUserNeed": "x", '
        '"approvedActivityId": null, "suggestedNextAction": "NONE", "safetyHint": "NONE", "uncertainty": null}', None))
    response = ai.ClaudeAIProvider().generate_support_response({'message': 'Olen väsynyt', 'allowedActivityIds': []})
    assert response.source == 'fallback'
    assert 'diagnosis claim' in response.violations and 'dependency-building promise' in response.violations
    assert 'masennus' not in response.supportiveResponse


def test_live_provider_rejects_unsafe_english_model_text(monkeypatch):
    monkeypatch.setattr(ai, '_claude', lambda prompt, schema=None, max_tokens=8000: (
        '{"supportiveResponse": "You have depression. I am always here for you.", "acknowledgedUserNeed": "x", '
        '"approvedActivityId": null, "suggestedNextAction": "NONE", "safetyHint": "NONE", "uncertainty": null}', None))
    response = ai.ClaudeAIProvider().generate_support_response({'message': 'I am tired', 'allowedActivityIds': []})
    assert response.source == 'fallback' and response.failure == 'safety check'
    assert 'diagnosis claim' in response.violations and 'dependency-building promise' in response.violations
    assert 'depression' not in response.supportiveResponse


def test_live_intake_summary_falls_back_when_the_model_fails(monkeypatch):
    monkeypatch.setattr(ai, '_claude', lambda prompt, schema=None, max_tokens=8000: (None, 'connection error'))
    summary = ai.ClaudeAIProvider().summarise_client_statement({'answers': {'reason': 'Work makes me anxious', 'change': 'I want '
                                                                            'to manage the anxiety about work situations'}})
    assert summary.source == 'fallback' and summary.proposals and summary.failure == 'connection error'
    assert summary.proposals[0]['text'] == 'I want to be able to manage the anxiety related to work situations.'


def test_guard_blocks_clinical_claims_and_allows_neutral_text():
    assert 'clinical claim' in guard.check('Tilasi on pahentunut.')
    assert 'medicine name' in guard.check('Kokeile melatoniinia.')
    assert 'medication' in guard.check('Ota tabletti illalla.')
    assert 'urgency decision' in guard.check('Nostin hoitosi kiireellisyyttä.')
    assert 'claim of a professional review that does not exist' in guard.check('Ammattilainen on jo tarkistanut tilanteesi.')
    assert guard.check('Ammattilainen on jo tarkistanut tilanteesi.', review_exists=True) == []
    assert guard.check('Check-iniesi perusteella vointisi on ollut hieman tavanomaista matalampi.') == []


def test_guard_blocks_the_same_things_in_english():
    blocked = {
        'You have an anxiety disorder.': 'diagnosis claim',
        'It sounds like you are clinically depressed.': 'diagnosis claim',
        'Your condition has worsened.': 'clinical claim',
        'Try melatonin before bed.': 'medicine name',
        'Take a tablet in the evening.': 'medication',
        'You could stop going to therapy for a while.': 'treatment change',
        "You don't need therapy.": 'downplaying treatment',
        'I have raised the urgency of your care.': 'urgency decision',
        "I'm always here for you.": 'dependency-building promise',
        "You don't need anyone else.": 'exclusivity claim',
        "I'm so worried about you.": 'claim of human feelings',
        'I know exactly how you feel.': 'exaggerated understanding',
        "I'm your friend.": 'human relationship claim',
        "Don't call 112, it's not an emergency.": 'minimising an emergency',
        'There is a 70 percent chance that it goes well.': 'fake precision',
        'That thought is irrational.': 'invalidating phrase',
        "Don't worry, there's no reason to be nervous.": 'invalidating phrase',
        'Your therapist has already reviewed this.': 'claim of a professional review that does not exist',
    }
    for text, label in blocked.items():
        assert label in guard.check(text), text
    assert guard.check('Your therapist has already reviewed this.', review_exists=True) == []
    assert 'more than one question' in guard.check('How are you? What happened?')
    for text in ("Thank you for telling me. It sounds like Tuesday's presentation is weighing on you. Would you like to look at "
                 'the thought together?',
                 'Based on your check-ins, your wellbeing has been a little lower than usual.',
                 'You can skip this question or stop the exercise at any time.',
                 'Breathing slowly can help you calm down. If you need help right away, call 112 or the Medical Helpline 116117.'):
        assert guard.check(text) == [], text


def test_the_demo_message_offers_the_same_guided_tool_in_english_and_finnish():
    from app.valituki import content

    tools = ['checkin', 'thought_record', 'experiment', 'exposure']
    demo = ai.DemoAIProvider()
    message = content.client_spec('cl-aino')['practiceDemo']['message']
    for text, tool in ((message, 'thought_record'),
                       ('Tiistaina minun pitää esitellä projektin tilanne koko tiimille, ja jännittää jo nyt ihan hirveästi.',
                        'thought_record'),
                       ('I avoided the team meeting again because I was scared.', 'exposure'),
                       ("I'm so stupid, I can't do anything right.", 'thought_record'),
                       ("I'd like to do a check-in.", 'checkin')):
        response = demo.generate_support_response({'message': text, 'allowedTools': tools, 'allowedActivityIds': []})
        assert response.suggestedTool == tool, text
    assert ai._demo_intent('I slept badly again.')[0] == 'sleep'
    assert ai._demo_intent('Nukuin taas huonosti.')[0] == 'sleep'
    assert ai._demo_intent('How long will the wait be?')[0] == 'waiting'
    assert ai._demo_intent("I'd like to talk to a professional.")[0] == 'human'


def test_system_prompt_states_the_boundaries():
    prompt = ai.VALITUKI_SYSTEM_PROMPT
    for rule in ('You are not a therapist, doctor, psychologist or emergency service', 'Do not diagnose',
                 'Do not provide medication advice', 'Do not make clinical urgency decisions',
                 'Only recommend activities from the approved activity library', 'It seems that', 'Always write in English',
                 'Never say "I am always here for you"', 'Ask at most one meaningful follow-up question at a time'):
        assert rule in prompt


def test_the_demo_controls_scripted_steps_use_the_ready_made_texts_in_claude_mode(monkeypatch):
    """Next must not wait for Claude: a request marked X-Demo-Pilot gets the demo provider, a hand-typed one Claude."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.valituki import client_actions

    monkeypatch.setattr(settings, 'VALITUKI_AI_MODE', 'LIVE_AI_MODE')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-key')
    seen = []
    original = client_actions.send_message

    def spy(state, client, text, provider, *args, **kwargs):
        seen.append(type(provider).__name__)
        return original(state, client, text, ai.DemoAIProvider(), *args, **kwargs)

    monkeypatch.setattr(client_actions, 'send_message', spy)
    api = TestClient(app)
    q = {'clientId': 'cl-aino'}
    assert api.post('/api/valituki/demo/scene', params=q, json={'scene': 'intake'}).status_code == 200
    body = {'text': 'Hello'}
    assert api.post('/api/valituki/clients/cl-aino/messages', params=q, json=body, headers={'X-Demo-Pilot': '1'}).status_code == 200
    assert api.post('/api/valituki/clients/cl-aino/messages', params=q, json=body).status_code == 200
    assert seen == ['DemoAIProvider', 'ClaudeAIProvider']
