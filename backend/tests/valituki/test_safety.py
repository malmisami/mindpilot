"""Deterministic Safety Engine and SafetyAgent."""
from __future__ import annotations

from app.valituki import client_actions, simulation
from app.valituki.ai import DemoAIProvider, SupportResponse
from app.valituki.safety import SAFETY_CONTACTS, SAFETY_SCREEN, assess, evaluate_text, explicit_help_trigger

from .conftest import client_of


def test_deterministic_phrases_are_detected():
    assert max(t.level for t in evaluate_text('Olen alkanut ajatella, että haluaisin kuolla.')) == 3
    assert max(t.level for t in evaluate_text('Tuntuu toivottomalta.')) == 2
    assert evaluate_text('Ihan tavallinen päivä, vähän väsyttää.') == []


def test_english_phrases_are_detected_as_well():
    level = lambda text: max((t.level for t in evaluate_text(text)), default=0)  # noqa: E731
    for text in ("I've started to think that I'd like to die.", 'I want to kill myself', 'Everyone would be better off without me',
                 "I don't want to live anymore", 'I’ve been cutting myself', "I'm going to take all my pills",
                 'I want to hurt someone', "I'm not safe at home"):
        assert level(text) == 3, text
    for text in ("I can't go on", 'I can’t cope any more', 'It all feels hopeless', 'Nobody cares about me'):
        assert level(text) == 2, text
    for text in ("I can't sleep", 'I feel so lonely', 'I had a panic attack', 'Today has been really bad'):
        assert level(text) == 1, text
    for text in ('Just a normal day, a bit tired.', "I don't want to hurt her feelings", "I'm in danger of missing the deadline",
                 "On Tuesday I have to present the project status to the whole team, and I'm already terribly nervous about it."):
        assert evaluate_text(text) == [], text
    rules = {t.ruleId for t in evaluate_text("I can't cope any more. I've started to think that I'd like to die.")}
    assert rules == {'SAF-L3-SUICIDE-EN', 'SAF-L2-HOPELESS-EN'}


def test_safety_trigger_interrupts_normal_agent_flow(state):
    """Test 11: level 3 locks normal support; check-ins, suggestions and model replies stop until acknowledged."""
    client = client_of(state, 'cl-crisis')
    result = simulation.crisis(state)
    assert result['safety']['level'] == 3
    assert client.safetyLock and client.safetyLock.dismissedAt is None
    assert client.todayActivity is None
    reply = [m for m in state.chat if m.clientId == client.id][-1]
    assert reply.textSource == 'fixed' and '112' in reply.text and '116117' in reply.text

    actions_before = {a.id for a in state.actions if a.clientId == client.id}
    client_actions.submit_checkin(state, client, 3, {}, '')
    new = [a for a in state.actions if a.clientId == client.id and a.id not in actions_before]
    assert not [a for a in new if a.agent in ('SupportAgent', 'ObservationAgent')]
    assert any(e.action == 'safety_interrupt' and e.clientId == client.id for e in state.audit)
    simulation.advance(state, 7)
    assert not [a for a in state.actions if a.clientId == client.id and a.id not in actions_before and a.type == 'send_checkin']

    locked = client_actions.send_message(state, client, 'Hello', DemoAIProvider())
    assert locked['locked'] is True
    alert = next(t for t in state.tasks if t.clientId == client.id and t.type == 'safety_review')
    assert alert.priority == 'urgent' and alert.title.startswith('DEMO ALERT')

    client_actions.dismiss_safety(state, client)
    assert client.safetyLock.dismissedAt


def test_llm_output_cannot_downgrade_a_deterministic_safety_level():
    """Test 12: the final level is max(deterministic, model hint)."""
    triggers = evaluate_text('Haluan kuolla.')
    result = assess(triggers, ai_hint='NONE', ai_next_action='NONE')
    assert result.deterministic_level == 3 and result.final_level == 3
    raised = assess([], ai_hint='URGENT')
    assert raised.final_level == 3 and raised.deterministic_level == 0


def test_level_three_in_chat_interrupts_before_any_model_call(state):
    client = client_of(state, 'cl-mikko')

    class CountingProvider(DemoAIProvider):
        calls = 0

        def generate_support_response(self, ctx):
            CountingProvider.calls += 1
            return SupportResponse('All good.', '', None, 'NONE', 'NONE', None)

    result = client_actions.send_message(state, client, 'En halua enää elää.', CountingProvider())
    assert result['safety']['level'] == 3 and CountingProvider.calls == 0
    client_actions.dismiss_safety(state, client)
    result = client_actions.send_message(state, client, "I don't want to live any more.", CountingProvider())
    assert result['safety']['level'] == 3 and CountingProvider.calls == 0


def test_model_hint_is_honoured_even_when_rules_find_nothing(state):
    client = client_of(state, 'cl-mikko')

    class WorriedProvider(DemoAIProvider):
        def generate_support_response(self, ctx):
            return SupportResponse('Thank you for telling me.', '', None, 'SAFETY_FLOW', 'URGENT', None, source='live')

    result = client_actions.send_message(state, client, 'Everything feels a bit much right now.', WorriedProvider())
    assert result['safety']['level'] == 3 and client.safetyLock


def test_help_now_button_shows_contacts_and_never_claims_emergency_contact(state):
    client = client_of(state, 'cl-mikko')
    client_actions.help_now(state, client)
    assert client.safetyLock
    assert [c['number'] for c in SAFETY_CONTACTS] == ['112', '116117', '09 2525 0111']
    assert SAFETY_SCREEN['title'] == 'Do you need help right now?'
    assert 'is not an emergency service' in SAFETY_SCREEN['notEmergency']
    assert 'has not contacted the emergency response centre' in SAFETY_SCREEN['demoNote']
    assert explicit_help_trigger().level == 3
