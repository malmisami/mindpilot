"""The user-approved handover: only approved, shareable data reaches the therapist; no chat history by default."""
from __future__ import annotations

from app.valituki import client_actions, handover, insights, view
from app.valituki.ai import DemoAIProvider

from .conftest import client_of


def _booked(scene):
    state = scene('handover')
    return state, client_of(state)


def test_handover_excludes_full_chat_history_by_default(scene):
    """Test 13."""
    state, client = _booked(scene)
    client_actions.send_message(state, client, 'Jännittää huomista palaveria.', DemoAIProvider())
    client_actions.send_message(state, client, "I'm nervous about tomorrow's meeting.", DemoAIProvider())
    record = handover.find(state, client.id)
    sections = handover.build_sections(state, client, record)
    assert 'chat' not in {s.key for s in sections}
    sharing = next(s for s in sections if s.key == 'sharing')
    assert sharing.content['chatHistoryIncluded'] is False
    assert 'The chat history is not shared' in sharing.content['statement']
    client_actions.approve_handover(state, client)
    snapshot_text = str([s.model_dump() for s in record.approvedSnapshot])
    assert 'Jännittää huomista palaveria' not in snapshot_text
    assert "nervous about tomorrow's meeting" not in snapshot_text


def test_therapist_sees_nothing_before_approval_and_then_exactly_what_the_client_shared(scene):
    """Test 14: the draft is the client's – the therapist sees nothing until the client approves it."""
    state = scene('matches')
    client = client_of(state)
    decision = next(d for d in state.matchDecisions if d.clientId == client.id and d.status == 'proposed_to_client')
    client_actions.select_candidate(state, client, decision.candidateIds[0])
    anna_view = view.therapist_view(state, 'th-anna')['selected']
    row = next(r for r in anna_view['clients'] if r['clientId'] == client.id)
    assert row['handoverStatus'] == 'draft' and row['sections'] is None

    helped = insights.for_client(state, client.id, kind='helped_before')[0]
    client_actions.set_insight_sharing(state, client, helped.id, professional=False, matching=False)
    client_actions.update_handover(state, client, {'action': 'remove', 'section': 'ai_summary'})
    client_actions.approve_handover(state, client)
    row = next(r for r in view.therapist_view(state, 'th-anna')['selected']['clients'] if r['clientId'] == client.id)
    keys = {s['key'] for s in row['sections']}
    assert 'ai_summary' not in keys and {'goals', 'wellbeing', 'questions', 'sharing'} <= keys
    assert helped.text not in str(row['sections'])
    assert row['sections'] == [s.model_dump() for s in handover.find(state, client.id).approvedSnapshot]

    # An edit makes it a draft again: shared only once the client approves the new version.
    client_actions.update_handover(state, client, {'action': 'edit', 'section': 'hopes', 'text': 'I want to learn to cope with nerves.'})
    row = next(r for r in view.therapist_view(state, 'th-anna')['selected']['clients'] if r['clientId'] == client.id)
    assert row['handoverStatus'] == 'draft' and row['sections'] is None


def test_sections_distinguish_information_types(scene):
    state, client = _booked(scene)
    record = handover.find(state, client.id)
    types = {s.key: s.infoType for s in record.approvedSnapshot}
    assert types['goals'] == 'user_said'
    assert types['wellbeing'] == 'measured'
    assert types['ai_summary'] == 'ai_summary'
    assert types['professional'] == 'professional_note'
    assert record.aiDraftSource == 'demo'


def test_withdrawing_the_handover_removes_it_from_the_therapist(scene):
    state, client = _booked(scene)
    client_actions.withdraw_handover(state, client)
    row = next(r for r in view.therapist_view(state, 'th-anna')['selected']['clients'] if r['clientId'] == client.id)
    assert row['handoverStatus'] == 'withdrawn' and row['sections'] is None
