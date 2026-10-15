"""ObservationAgent – structured longitudinal change against the client's own baseline, and recurring patterns.

It creates observations and review tasks; it never diagnoses, never changes treatment and never changes clinical
urgency. A detected pattern is only a proposal ("We noticed something") until the client says it fits.
"""
from __future__ import annotations

from app.valituki import content, insights, journey, records, trends
from app.valituki.agents import base, checkin
from app.valituki.models import AgentEvent, ValitukiState, WellbeingObservation
from app.valituki.store import days_between, next_id, now

AGENT = 'ObservationAgent'
ORDINALS = {2: 'second', 3: 'third', 4: 'fourth', 5: 'fifth'}


def on_checkin_completed(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = next(c for c in state.clients if c.id == event.clientId)
    item = next(c for c in state.checkIns if c.id == event.payload['checkInId'])
    trends.update_baseline(state, client)
    if not item.retained or item.id in client.baselineCheckInIds:
        return
    trend = trends.evaluate(state, client)
    policy = content.rules()['trend']
    streak = trend.below_streak
    if streak >= 1 and trends.below_streak(state, client)[-1].id == item.id:
        nth = f' for the {ORDINALS.get(streak, f"{streak}th")} time in a row' if streak >= 2 else ''
        records.act(state, agent=AGENT, type='below_baseline', event=event, rule_id=trend.rule_id or 'TREND-WATCH',
                    title=f'Wellbeing was below own baseline{nth}',
                    detail=f'Check-in {item.mood}/5, own baseline {client.baseline}. '
                           'The comparison is with your own level, not with other people.')
    if trend.level == 2 and not any(o.clientId == client.id and o.status == 'open' and o.kind == 'trend_decline'
                                    for o in state.wellbeingObservations):
        changed = journey.apply(state, client, 'WELLBEING_TREND_CHANGED', actor=records.agent_actor(AGENT), source='rule_based',
                                payload={'ruleId': trend.rule_id, 'trend': trend.as_data(), 'clientText': trend.client_text,
                                         'professionalText': trend.professional_text})
        from app.valituki.agents import orchestrator

        orchestrator.dispatch(state, changed, provider)
    elif trend.level == 1:
        checkin.schedule_extra(state, client, event, policy['l1RuleId'],
                               'Wellbeing has been below their own level in two check-ins in a row. An extra check-in helps to '
                               'see whether the change continues.')
    elif trend.direction == 'improving' and not any(
            o.clientId == client.id and o.kind == 'trend_improvement'
            and days_between(o.createdAt, state.currentDate) < int(policy['improveCooldownDays']) for o in state.wellbeingObservations):
        stamp = now(state)
        state.wellbeingObservations.append(WellbeingObservation(
            id=next_id(state, 'obs'), clientId=client.id, kind='trend_improvement', agent=AGENT, ruleId=policy['improveRuleId'],
            title='A positive change against own baseline', reason=trend.professional_text, clientText=trend.client_text,
            requiresHumanReview=False, suggestedAction='No action needed.', status='info', createdAt=stamp, updatedAt=stamp,
            createdBy=records.agent_actor(AGENT), source='rule_based'))
        records.act(state, agent=AGENT, type='note_improvement', event=event, rule_id=policy['improveRuleId'],
                    title='Noted a positive change', detail=trend.client_text)

    pattern = trends.detect_workday_pattern(state, client)
    cooldown = int(content.rules()['patterns']['cooldownDays'])
    if pattern and not any(i.clientId == client.id and i.kind == 'pattern' and i.evidence.get('ruleId') == pattern['ruleId']
                           and days_between(i.createdAt, state.currentDate) < cooldown for i in state.insights):
        detected = journey.apply(state, client, 'PATTERN_DETECTED', actor=records.agent_actor(AGENT), source='rule_based',
                                 payload=pattern)
        from app.valituki.agents import orchestrator

        orchestrator.dispatch(state, detected, provider)


def on_trend_changed(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = next(c for c in state.clients if c.id == event.clientId)
    payload = event.payload
    trend = payload['trend']
    stamp = now(state)
    explanation = provider.generate_observation_explanation({'firstName': client.firstName, 'signals': trend['signals'],
                                                             'baseline': trend['baseline'], 'recent': trend['recent']})
    observation = WellbeingObservation(
        id=next_id(state, 'obs'), clientId=client.id, kind='trend_decline', agent=AGENT, ruleId=payload['ruleId'],
        title='Wellbeing below own baseline', reason=payload['professionalText'], clientText=payload['clientText'],
        explanation=trend['signals'], underlyingData=trend, aiSummary=explanation.text, aiSummarySource=explanation.source,
        requiresHumanReview=True, suggestedAction='Suggestion: a professional review.', status='open', createdAt=stamp,
        updatedAt=stamp, createdBy=records.agent_actor(AGENT), source='rule_based')
    state.wellbeingObservations.append(observation)
    task = base.create_task(state, client, agent=AGENT, type='trend_review', priority='normal',
                            title='Review request: wellbeing below own baseline', reason=payload['professionalText'],
                            suggested='Suggestion: a professional review. Mieliluotsi has not changed the urgency of care.',
                            data=trend, observation_id=observation.id, handling_note=base.CONTACT_HANDLING)
    observation.taskId = task.id
    records.notify(state, audience='coordinator', client_id=client.id, kind='review', event=event, agent=AGENT,
                   title=f'Review request: {client.displayName}',
                   body='Wellbeing below their own baseline. Mieliluotsi has not changed the urgency of care.')
    records.notify(state, audience='client', client_id=client.id, kind='review', event=event, agent=AGENT, action_view='today',
                   title='Mieliluotsi noticed a change',
                   body=f'{payload["clientText"]} I asked a professional to look at your situation. This observation is waiting for a '
                        'professional review. Mieliluotsi has not changed the urgency of your care. If you need help right away, call '
                        '112 or the Medical Helpline 116117.')
    records.act(state, agent=AGENT, type='request_review', event=event, rule_id=payload['ruleId'],
                title='Mieliluotsi created a review request for a professional',
                detail='This observation is waiting for a professional review. Mieliluotsi has not changed the urgency of care.',
                ai_task='generateObservationExplanation', ai_source=explanation.source)


def on_pattern_detected(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = next(c for c in state.clients if c.id == event.clientId)
    pattern = event.payload
    insights.create(state, client, category='challenge', kind='pattern', title='We noticed something', text=pattern['text'],
                    origin='observed', source_label="Mieliluotsi's observation from your check-ins", status='proposed',
                    actor=records.agent_actor(AGENT), source='rule_based',
                    structured={'domains': pattern['domains']},
                    evidence={**pattern['evidence'], 'ruleId': pattern['ruleId']})
    records.notify(state, audience='client', client_id=client.id, kind='insight', event=event, agent=AGENT, action_view='today',
                   title='We noticed something', body=f'{pattern["text"]} Does this ring true for you?')
    records.act(state, agent=AGENT, type='detect_pattern', event=event, rule_id=pattern['ruleId'],
                title='Mieliluotsi noticed a recurring pattern in the check-ins',
                detail=f'{pattern["text"]} The observation is waiting to see whether it rings true for you – without your approval '
                       'it is not used for anything.')
