"""The 3-minute demo end to end through the HTTP API (the acceptance criteria)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.valituki import content

client = TestClient(app)
API = '/api/valituki'
Q = {'clientId': 'cl-aino'}


def ok(response) -> dict:
    assert response.status_code == 200, response.text
    return response.json()


def test_full_demo_journey():
    view = ok(client.post(f'{API}/demo/reset', params=Q))['view']
    assert view['meta']['syntheticNotice'] == 'All people and health information in the demo are entirely fictional.'
    assert view['meta']['tagline'] == 'Support starts now, even if therapy does not start yet.'
    aino = view['client']
    assert aino['journeyState'] == 'INVITED' and aino['intake']['status'] == 'not_started'
    demo = aino['intake']['demoAnswers']

    # 1–2: conversational intake, explicit approval, support starts
    ok(client.post(f'{API}/clients/cl-aino/intake/start', params=Q, json=aino['intake']['consentDefaults']))
    for _ in range(8):
        view = ok(client.get(f'{API}/view', params=Q))
        pending = view['client']['intake']['pendingQuestion']
        if not pending:
            break
        ok(client.post(f'{API}/clients/cl-aino/intake/answer', params=Q, json={'text': demo[pending['key']]}))
    view = ok(client.get(f'{API}/view', params=Q))
    assert view['client']['intake']['status'] == 'review'
    assert view['client']['memory']['groups'][0]['items'] == []  # nothing stored before approval
    ok(client.post(f'{API}/clients/cl-aino/intake/confirm', params=Q))
    view = ok(client.post(f'{API}/clients/cl-aino/intake/complete', params=Q,
                          json={'checkInDays': [0, 2, 5], 'communicationStyle': 'brief', 'mood': 3}))['view']
    assert view['client']['journeyState'] == 'WAITING_ACTIVE'
    assert view['client']['fitProfile']['version'] >= 1

    # 3: 14 days → check-ins, a useful activity and a pattern
    view = ok(client.post(f'{API}/demo/advance', params=Q, json={'days': 14}))['view']
    assert view['client']['memory']['pending'][0]['title'] == 'We noticed something'
    assert any(m['key'] == 'helpful' for m in view['client']['milestones'])
    ok(client.post(f'{API}/clients/cl-aino/insights/{view["client"]["memory"]["pending"][0]["id"]}/decision', params=Q,
                   json={'decision': 'approve'}))

    # 4: change detected → explainable review for the professional, urgency untouched
    view = ok(client.post(f'{API}/demo/deteriorate', params=Q, json={'clientId': 'cl-aino'}))['view']
    detail = view['professional']['details']['cl-aino']
    assert detail['openReview'] and len(detail['openReview']['explanation']) == 4
    assert detail['urgency']['label'] == 'Non-urgent'
    assert view['professional']['queue'][0]['clientId'] in ('cl-aino', 'cl-crisis')
    overview = {b['key']: b['value'] for b in view['professional']['overview']['buckets']}
    assert view['professional']['overview']['total'] >= 999 and overview['changeDetected'] >= 164
    ok(client.post(f'{API}/observations/{detail["openReview"]["id"]}/review', params=Q, json={'action': 'mark_reviewed'}))

    # 5: a therapist slot opens → matching runs → three explained options
    view = ok(client.post(f'{API}/demo/open-slot', params=Q))['view']
    candidates = view['client']['matching']['candidates']
    assert [c['therapist']['name'] for c in candidates] == ['Anna Laine', 'Laura Koski', 'Katja Salmi']
    assert candidates[0]['labelText'] == content.matching_config()['labels'][0]['text'] and candidates[0]['reasons']

    # 6: Sami chooses Anna and approves the handover
    view = ok(client.post(f'{API}/clients/cl-aino/matches/select', params=Q, json={'candidateId': candidates[0]['id']}))['view']
    assert view['client']['matching']['booking']['startText'] == 'Tue 17 Nov at 18:00'
    ok(client.post(f'{API}/clients/cl-aino/handover/approve', params=Q))

    # 7: Anna sees only the approved summary
    view = ok(client.get(f'{API}/view', params={**Q, 'therapistId': 'th-anna'}))
    row = next(r for r in view['therapist']['selected']['clients'] if r['clientId'] == 'cl-aino')
    assert row['handoverStatus'] == 'approved' and row['sections']

    # 8: therapy starts, the therapist configures the between-session agent
    view = ok(client.post(f'{API}/therapists/th-anna/clients/cl-aino/first-session', params={**Q, 'therapistId': 'th-anna'}))['view']
    plan = next(r for r in view['therapist']['selected']['clients'] if r['clientId'] == 'cl-aino')['therapy']['suggestedPlan']
    view = ok(client.put(f'{API}/therapists/th-anna/clients/cl-aino/plan', params={**Q, 'therapistId': 'th-anna'}, json=plan))['view']
    assert view['client']['mode']['statement'] == 'Your therapist Anna has set up this plan.'
    assert view['client']['mode']['title'] == 'Between-session support'


def test_safety_flow_and_scene_jumps():
    view = ok(client.post(f'{API}/demo/crisis', params={'clientId': 'cl-crisis'}))['view']
    assert view['client']['safety']['lockActive'] is True
    assert any(n['kind'] == 'safety' for n in view['professional']['notifications'])
    view = ok(client.post(f'{API}/demo/scene', params=Q, json={'scene': 'matches'}))['view']
    assert view['client']['journeyState'] == 'MATCH_PROPOSED'
    assert client.post(f'{API}/demo/scene', params=Q, json={'scene': 'nope'}).status_code == 400


def test_rules_are_enforced_by_the_api():
    ok(client.post(f'{API}/demo/reset', params=Q))
    response = client.post(f'{API}/clients/cl-aino/checkins', params=Q, json={'mood': 3})
    assert response.status_code == 409  # no check-ins before the intake
    assert response.json()['detail'] == 'Check-in is not possible in the stage "On the waiting list – Mieliluotsi not started yet".'
    response = client.post(f'{API}/clients/cl-mikko/urgency', params=Q, json={'urgency': 'urgent'})
    assert response.status_code == 200  # professionals may change urgency; agents cannot (see test_agent)
