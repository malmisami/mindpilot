"""Wellbeing call: the client describes how they are, Mieliluotsi proposes a 1–5 level, the client confirms or corrects it."""
from __future__ import annotations

import pytest

from app.valituki import ai, client_actions
from app.valituki.ai import DemoAIProvider, FeelingEstimate
from app.valituki.client_actions import ClientActionError
from app.valituki.safety import SAFETY_REPLY

from .conftest import client_of, run_intake


def test_the_demo_proposes_a_level_from_the_clients_own_words():
    mood = lambda text: ai.demo_feeling_level('mood', text)  # noqa: E731
    assert mood("Honestly it's been an awful day") == 1
    assert mood("Pretty tired and a bit down") == 2
    assert mood("Not great, if I'm honest") == 2
    assert mood("Not bad, just a normal day") == 3
    assert mood("It's okay I suppose") == 3
    assert mood('Good, I slept well') == 4
    assert mood('Really good actually!') == 5
    assert mood('Aika väsynyt ja alakuloinen') == 2
    assert mood("I'd say about a three") == 3
    assert mood('Maybe 4 out of 5') == 4
    assert mood('I went to the shop') is None
    anxiety = lambda text: ai.demo_feeling_level('anxiety', text)  # noqa: E731
    assert anxiety('Not anxious at all today') == 1
    assert anxiety('Not very nervous') == 2
    assert anxiety('A bit nervous about tomorrow') == 2
    assert anxiety('Somewhat tense') == 3
    assert anxiety("I've been really anxious about the presentation") == 4
    assert anxiety('Completely overwhelmed, I had a panic attack') == 5
    assert anxiety('Jännittää tosi paljon') == 4
    assert anxiety('Pretty calm') == 1


def test_a_call_proposes_a_level_and_does_not_store_the_words(state):
    client = run_intake(state)
    chat_before = len(state.chat)
    result = client_actions.estimate_feeling(state, client, 'mood', 'Pretty tired and a bit down today', DemoAIProvider())
    assert result == {'scale': 'mood', 'value': 2, 'label': 'Bad', 'reflection': 'That sounds like a heavy day.',
                      'source': 'demo', 'safety': {'level': 0}}
    assert len(state.chat) == chat_before
    assert not any('tired and a bit down' in (entry.detail or '') for entry in state.audit)
    unclear = client_actions.estimate_feeling(state, client, 'anxiety', 'I went for a walk', DemoAIProvider())
    assert unclear['value'] is None and unclear['label'] is None
    with pytest.raises(ClientActionError):
        client_actions.estimate_feeling(state, client, 'mood', '   ', DemoAIProvider())


def test_a_crisis_phrase_stops_the_call_before_any_model_is_called(state):
    client = run_intake(state)

    class Counting(DemoAIProvider):
        calls = 0

        def estimate_feeling(self, ctx):
            Counting.calls += 1
            return super().estimate_feeling(ctx)

    result = client_actions.estimate_feeling(state, client, 'mood', "Awful. I've started to think that I'd like to die.", Counting())
    assert result['safety']['level'] == 3 and Counting.calls == 0
    assert client.safetyLock and state.chat[-1].text == SAFETY_REPLY
    assert state.safetyObservations[-1].context == 'call'


def test_the_models_safety_hint_can_raise_the_level(state):
    client = run_intake(state)

    class Worried(DemoAIProvider):
        def estimate_feeling(self, ctx):
            return FeelingEstimate(value=1, reflection='That sounds really hard.', safetyHint='REVIEW', source='live')

    result = client_actions.estimate_feeling(state, client, 'mood', 'Everything is just grey', Worried())
    assert result['value'] == 1 and result['safety']['level'] == 2
    assert client_of(state).safetyLock is None


def test_a_live_estimate_is_guarded(monkeypatch):
    monkeypatch.setattr(ai, '_claude', lambda prompt, schema=None, max_tokens=8000: (
        '{"value": 2, "reflection": "You have depression, take your medication.", "safetyHint": "NONE"}', None))
    estimate = ai.ClaudeAIProvider().estimate_feeling({'scale': 'mood', 'text': 'Tired and down', 'scaleLabels': {}})
    assert estimate.source == 'fallback' and estimate.value == 2 and estimate.reflection == 'That sounds like a heavy day.'
    monkeypatch.setattr(ai, '_claude', lambda prompt, schema=None, max_tokens=8000: (
        '{"value": 3, "reflection": "It sounds like a so-so day, a bit flat.", "safetyHint": "NONE"}', None))
    estimate = ai.ClaudeAIProvider().estimate_feeling({'scale': 'mood', 'text': 'Meh, kind of flat', 'scaleLabels': {}})
    assert (estimate.value, estimate.source) == (3, 'live')
