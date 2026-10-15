"""Agentic behaviour: observations and review tasks, never clinical decisions."""
from __future__ import annotations

import re

import pytest

from app.valituki import (
    adapters,
    client_actions,
    content,
    fit_profile,
    insights,
    labels,
    professional,
    records,
    simulation,
    therapy,
    trends,
)
from app.valituki.agents import orchestrator
from app.valituki.professional import PermissionDenied
from app.valituki.safety import normalize

from .conftest import client_of, run_intake


def test_ai_cannot_independently_alter_waiting_list_priority(state):
    """Test 8: a worsening trend creates a review request, but clinical urgency stays as the professional set it."""
    client = run_intake(state)
    episode = adapters.waiting_list.episode_for(state, client.id)
    before = (episode.clinicalUrgency, episode.urgencySetBy, list(episode.urgencyHistory))
    simulation.advance(state, 14)
    simulation.simulate_deterioration(state, client)
    assert client.journeyState == 'HUMAN_REVIEW_NEEDED'
    assert (episode.clinicalUrgency, episode.urgencySetBy, episode.urgencyHistory) == before
    for agent in records.AGENT_LABELS:
        with pytest.raises(PermissionDenied):
            professional.set_clinical_urgency(state, client, 'urgent', records.agent_actor(agent))
    assert episode.clinicalUrgency == 'non_urgent'
    professional.set_clinical_urgency(state, client, 'urgent', records.COORDINATOR, 'Called, agreed on an urgent assessment')
    assert episode.clinicalUrgency == 'urgent' and episode.urgencySetBy == professional.COORDINATOR_NAME


def test_worsening_wellbeing_generates_an_explainable_human_review_task(state):
    """Test 9: three consecutive check-ins below the own baseline → review request with the reasons."""
    client = run_intake(state)
    simulation.advance(state, 14)
    result = simulation.simulate_deterioration(state, client)
    assert result['trendChanged'] and result['currentDate'] == '2026-11-04'
    observation = next(o for o in state.wellbeingObservations if o.clientId == client.id and o.kind == 'trend_decline')
    task = next(t for t in state.tasks if t.observationId == observation.id)
    assert task.type == 'trend_review' and task.status == 'open' and task.agent == 'ObservationAgent'
    texts = [row['text'] for row in observation.explanation]
    assert texts[0].startswith('Wellbeing below their own baseline in 3 check-ins in a row')
    assert any(t.startswith('Sleep worse in') for t in texts)
    assert any('missed' in t for t in texts)
    assert any('ability to work had got worse' in t for t in texts)
    assert observation.suggestedAction == 'Suggestion: a professional review.'
    titles = [a.title for a in state.actions if a.clientId == client.id]
    assert 'Mieliluotsi noticed that a check-in is missing' in titles
    assert 'We sent Sami a reminder' in titles
    assert 'Wellbeing was below own baseline for the third time in a row' in titles
    assert 'Mieliluotsi created a review request for a professional' in titles
    note = next(n for n in state.notifications if n.clientId == client.id and n.title == 'Mieliluotsi noticed a change')
    assert 'has not changed the urgency of your care' in note.body


def test_one_missed_checkin_alone_does_not_produce_a_clinical_conclusion(state):
    """Test 10: a missed check-in → gentle reminder only."""
    client = run_intake(state)
    client.simulationProfile = 'none'
    simulation.advance(state, 1)  # Saturday check-in becomes due and is left undone
    simulation.advance(state, 1)  # Sunday tick marks it missed
    missed = [c for c in state.checkIns if c.clientId == client.id and c.status == 'missed']
    assert len(missed) == 1
    assert any(a.type == 'send_reminder' for a in state.actions if a.clientId == client.id)
    assert not [o for o in state.wellbeingObservations if o.clientId == client.id]
    assert not [t for t in state.tasks if t.clientId == client.id]
    assert trends.evaluate(state, client).direction != 'declining'
    assert client.journeyState == 'WAITING_ACTIVE'


def test_repeated_missed_checkins_create_only_a_low_priority_engagement_task(state):
    task = next(t for t in state.tasks if t.clientId == 'cl-sara')
    assert task.type == 'engagement_check' and task.priority == 'low'
    observation = next(o for o in state.wellbeingObservations if o.id == task.observationId)
    assert not observation.requiresHumanReview and 'not a clinical observation' in observation.reason
    assert client_of(state, 'cl-sara').journeyState != 'HUMAN_REVIEW_NEEDED'


def test_detected_pattern_needs_the_clients_approval(state):
    client = run_intake(state)
    simulation.advance(state, 14)
    pattern = insights.for_client(state, client.id, status='proposed', kind='pattern')[0]
    assert pattern.text.startswith('On evenings before workdays, you have reported more anxiety than average')
    assert pattern.evidence['checkIns'] == 6 and 'not a diagnosis' in pattern.evidence['basis']
    assert pattern.evidence['basis'][0] == '6 check-ins'
    assert pattern.id not in fit_profile.get(state, client.id).clientApprovedInsights
    client_actions.decide_insight(state, client, pattern.id, 'approve')
    assert pattern.status == 'approved'
    assert pattern.id in fit_profile.get(state, client.id).clientApprovedInsights


def test_professional_review_resumes_the_journey(state):
    client = run_intake(state)
    simulation.advance(state, 14)
    simulation.simulate_deterioration(state, client)
    observation = next(o for o in state.wellbeingObservations if o.clientId == client.id and o.status == 'open')
    professional.review_observation(state, observation.id, 'mark_reviewed', 'Called.')
    assert client.journeyState == 'MATCHING_READY'
    assert observation.reviewedBy == professional.COORDINATOR_NAME


def test_therapist_configuration_changes_agent_behaviour(scene):
    state = scene('therapy')
    client = client_of(state)
    config = therapy.active_config(state, client.id)
    assert client.mode == 'therapy_support' and config is not None
    assert config.allowedActivityIds == ['act-grounding', 'act-values', 'act-activity-planning']
    assert client.checkInDays == config.checkInDays == [0, 4]
    summary = therapy.mode_summary(state, client)
    assert summary['statement'] == 'Your therapist Anna has set up this plan.'
    simulation.advance(state, 7)
    suggested = [a for a in state.actions if a.clientId == client.id and a.type == 'select_activity'
                 and a.createdAt >= config.createdAt]
    allowed = [a.title for a in content.activities() if a.id in config.allowedActivityIds]
    assert suggested and all(any(t in a.title for t in allowed) for a in suggested)
    tracked = [c for c in state.checkIns if c.clientId == client.id and c.status == 'completed' and c.createdAt >= config.createdAt]
    assert tracked and all(c.trackLabel == 'Anxiety related to office days' for c in tracked)


def test_only_the_clients_own_therapist_can_configure(scene):
    state = scene('therapy')
    client = client_of(state)
    with pytest.raises(therapy.TherapyError):
        therapy.configure(state, client, 'th-laura', therapy.suggested_plan(state, client), 'therapist:th-laura')


def test_negative_match_feedback_requests_review_without_rematch(state):
    maria = client_of(state, 'cl-maria')
    task = next(t for t in state.tasks if t.clientId == maria.id and t.type == 'matching_review')
    assert task.title == 'Matching review requested' and task.status == 'open'
    bookings = [b for b in state.bookings if b.clientId == maria.id]
    assert len(bookings) == 1 and maria.journeyState == 'THERAPY_ACTIVE'
    assert len([d for d in state.matchDecisions if d.clientId == maria.id]) == 1


def test_every_autonomous_action_is_attributed_to_a_named_agent(scene):
    state = scene('therapy')
    assert state.actions
    assert {a.agent for a in state.actions} <= set(records.AGENT_LABELS)
    assert {'SupportAgent', 'CheckInAgent', 'ObservationAgent', 'MatchingAgent', 'NavigationAgent'} <= {a.agent for a in state.actions}
    audited = {e.detail.split('.')[0] for e in state.audit if e.actor.startswith('agent:')}
    assert all(a.title in audited for a in state.actions[-20:])


def test_orchestrator_routes_events_to_named_agents():
    assert orchestrator.agents_for('CHECKIN_COMPLETED') == ['ObservationAgent', 'SupportAgent']
    assert orchestrator.agents_for('THERAPIST_SLOT_OPENED') == ['MatchingAgent']
    assert orchestrator.agents_for('SAFETY_SIGNAL') == ['SafetyAgent']


def test_work_notes_are_recognised_in_finnish_and_english():
    for note in ('Huomenna palaveri, jännittää', 'Big meeting at work tomorrow', 'Presentation at the office on Tuesday'):
        assert re.search(trends.WORK_WORDS, normalize(note))
    assert not re.search(trends.WORK_WORDS, normalize('Slept well and went for a walk in the network of paths'))


def test_goal_phrases_in_english_and_finnish():
    assert therapy._goal_phrase('I want to be able to manage my nervousness at work.') == 'Manage my nervousness at work'
    assert therapy._goal_phrase('Haluan pystyä hallitsemaan jännitystä.') == 'Hallita jännitystä'


def test_labels_are_english():
    assert labels.fmt_slot_title('2026-11-17T18:00') == 'Tue 17 Nov at 18:00'
    assert labels.fmt_date('2026-10-14') == '14 Oct' and labels.fmt_date_long('2026-10-14') == '14 Oct 2026'
    assert labels.frequency_text([0, 2, 5]) == 'three times a week (Mon, Wed and Sat)'
    assert labels.frequency_text([1]) == 'once a week (Tue)'
    assert labels.join_fi(['a', 'b', 'c']) == 'a, b and c' and labels.join_fi(['a', 'b'], 'tai') == 'a or b'
    assert labels.relative_label('2026-10-16', '2026-10-15') == 'tomorrow'
    assert labels.relative_label('2026-10-21', '2026-10-15') == 'Wed 21 Oct'
    assert labels.plural(1, 'check-in') == '1 check-in' and labels.plural(2, 'entry', 'entries') == '2 entries'
