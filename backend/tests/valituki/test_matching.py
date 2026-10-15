"""Transparent, deterministic matching built only from approved insights the client allows to be used."""
from __future__ import annotations

import random

from app.valituki import adapters, client_actions, content, insights, matching, matching_flow, simulation, view
from app.valituki.models import InsightSharing

from .conftest import run_intake


def _ready(state):
    client = run_intake(state)
    simulation.advance(state, 14)
    assert client.journeyState == 'MATCHING_READY'
    simulation.open_next_pending(state)
    return client


def test_three_explained_matches_for_aino(state):
    client = _ready(state)
    decision = matching_flow.current_decision(state, client.id)
    shown = matching_flow.decision_candidates(state, decision)[:decision.shownCount]
    assert [c.therapistId for c in shown] == ['th-anna', 'th-laura', 'th-katja']
    assert [c.label for c in shown] == ['strong', 'good', 'possible']
    anna = shown[0]
    assert anna.reasons[:5] == ['Works with anxiety and work-related stress', 'Uses a structured way of working',
                                'Offers concrete exercises', 'Remote session', 'The time fits your wish for evenings']
    assert anna.firstSlotStart.endswith('T18:00')
    assert anna.explanation.startswith('Anna meets all the criteria. Works with anxiety and work-related stress.')
    assert any('on a Wednesday' in u for u in shown[1].unmetPreferences)


def test_client_sees_labels_not_numeric_probabilities(state):
    _ready(state)
    candidates = view.build(state, 'cl-aino')['client']['matching']['candidates']
    assert candidates and all('totalPoints' not in c and 'components' not in c for c in candidates)
    assert {c['labelText'] for c in candidates} <= {item['text'] for item in content.matching_config()['labels']}


def test_unapproved_insight_cannot_be_used_for_matching(state):
    """Test 2: a proposed (unapproved) insight never reaches the matcher."""
    client = run_intake(state)
    insights.create(state, client, category='therapist_wish', kind='working_style', title='Proposal', text='Exploratory approach',
                    origin='ai_interpreted', source_label='test', actor='agent:test', source='test', status='proposed',
                    structured={'structure': 'exploratory', 'exercises': 'conversation'},
                    sharing=InsightSharing(professional=True, matching=True))
    match_input = matching_flow.build_input(state, client)
    assert match_input.style['structure'] == 'structured'
    assert match_input.style['exercises'] == 'concrete'
    pattern_like = insights.create(state, client, category='goal', kind='secondary_goal', title='Proposal', text='Sleep',
                                   origin='observed', source_label='test', actor='agent:test', source='test', status='proposed',
                                   structured={'topics': ['grief']}, sharing=InsightSharing(professional=True, matching=True))
    assert 'grief' not in matching_flow.build_input(state, client).secondary_topics
    assert pattern_like.status == 'proposed'


def test_therapist_with_no_capacity_is_excluded(state):
    """Test 3: Sari (10/10) and a full Anna are never proposed."""
    client = _ready(state)
    run = state.matchRuns[-1]
    sari = next(x for x in run.excluded[client.id] if x['therapistId'] == 'th-sari')
    assert any(f['key'] == 'capacity' for f in sari['failed'])
    config = content.matching_config()
    anna = next(t for t in state.therapists if t.id == 'th-anna')
    anna.currentCapacity = anna.maxCapacity
    evaluation = matching.evaluate(matching_flow.build_input(state, client), state.therapists, state.slots, state.currentDate, config)
    assert 'th-anna' not in [s.therapist.id for s in evaluation.ranked]


def test_therapist_failing_a_hard_eligibility_criterion_is_excluded(state):
    """Test 4: language, age group, active status, required competence and location are hard filters."""
    client = _ready(state)
    excluded = {x['therapistId']: {f['key'] for f in x['failed']} for x in state.matchRuns[-1].excluded[client.id]}
    assert 'language' in excluded['th-johanna']
    assert 'age' in excluded['th-elina']
    assert 'active' in excluded['th-tuomas']
    assert 'competence' in excluded['th-olli']
    assert 'location' in excluded['th-mikko']
    ranked = {c.therapistId for c in state.matchCandidates if c.clientId == client.id}
    assert not ranked & set(excluded)


def test_matching_ranking_is_deterministic(state):
    """Test 5: the same input gives the same ranking whatever the order of the directory."""
    client = _ready(state)
    config = content.matching_config()
    match_input = matching_flow.build_input(state, client)
    first = matching.evaluate(match_input, list(state.therapists), state.slots, state.currentDate, config)
    shuffled = list(state.therapists)
    random.Random(7).shuffle(shuffled)
    second = matching.evaluate(match_input, shuffled, list(reversed(state.slots)), state.currentDate, config)
    assert [(s.therapist.id, s.total) for s in first.ranked] == [(s.therapist.id, s.total) for s in second.ranked]


def test_user_can_revoke_matching_permission(state):
    """Test 6: the client changes "May be used in therapist matching" and the change is recorded."""
    client = run_intake(state)
    style = insights.for_client(state, client.id, kind='working_style')[0]
    assert style.sharing.matching
    client_actions.set_insight_sharing(state, client, style.id, professional=True, matching=False)
    assert not style.sharing.matching and style.consentScope == 'professional'
    record = [p for p in state.insightPermissions if p.insightId == style.id][-1]
    assert record.previous == {'professional': True, 'matching': True} and record.matching is False
    assert any(e.type == 'INSIGHT_PERMISSION_CHANGED' for e in state.events if e.clientId == client.id)


def test_revoked_information_is_excluded_from_future_matching(state):
    """Test 7: after revoking, the working style is not in the matching input and no style reasons appear."""
    client = run_intake(state)
    style = insights.for_client(state, client.id, kind='working_style')[0]
    client_actions.set_insight_sharing(state, client, style.id, professional=True, matching=False)
    simulation.advance(state, 14)
    simulation.open_next_pending(state)
    run = state.matchRuns[-1]
    assert run.inputs[client.id]['style'] == {}
    assert any('way of working' in line for line in run.inputs[client.id]['data_not_used'])
    for candidate in [c for c in state.matchCandidates if c.clientId == client.id]:
        assert not any(r.startswith(('Uses a structured', 'Offers concrete')) for r in candidate.reasons)
        component = next(c for c in candidate.components if c.key == 'workingStyle')
        assert component.explanation == 'Wishes about the way of working were not used in matching'


def test_practical_preferences_without_matching_permission_block_automatic_matching(state):
    client = run_intake(state)
    practical = insights.for_client(state, client.id, kind='practical')[0]
    client_actions.set_insight_sharing(state, client, practical.id, professional=True, matching=False)
    assert not matching_flow.eligible_for_run(state, client)


def test_selecting_a_therapist_books_the_first_suitable_time(state):
    client = _ready(state)
    decision = matching_flow.current_decision(state, client.id)
    anna = matching_flow.decision_candidates(state, decision)[0]
    before = next(t for t in state.therapists if t.id == 'th-anna').currentCapacity
    booking = client_actions.select_candidate(state, client, anna.id)
    assert booking.start == anna.firstSlotStart and booking.format == 'remote'
    assert client.journeyState == 'MATCH_ACCEPTED'
    assert next(t for t in state.therapists if t.id == 'th-anna').currentCapacity == before + 1
    assert adapters.waiting_list.episode_for(state, client.id).status == 'allocated'


def test_the_backstage_preview_ranks_therapists_before_any_run_and_saves_nothing(scene):
    from app.valituki import matching_flow

    start = scene('start')
    aino = next(c for c in start.clients if c.id == 'cl-aino')
    saved = start.model_dump_json()
    before = matching_flow.preview(start, aino)
    assert before['candidates'] and before['excluded'] and start.model_dump_json() == saved
    after = matching_flow.preview(scene('intake'), next(c for c in scene('intake').clients if c.id == 'cl-aino'))
    # The approved intake data changes the ranking; a well-fitting therapist without a free time is shown as unavailable.
    assert [c['name'] for c in after['candidates']] != [c['name'] for c in before['candidates']]
    assert any(c['status'] == 'unavailable' for c in after['candidates'])
