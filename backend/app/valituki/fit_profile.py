"""TherapyFitProfile – a structured profile that becomes richer during the waiting period.

It is rebuilt from approved insights, the client's own activity ratings and explicit engagement choices only. Nothing
unapproved and nothing inferred about demographics enters it. Each dimension remembers which insight it came from and
whether the client allows it to be used in matching, so the matcher can check the permission at the moment of use.
"""
from __future__ import annotations

from statistics import mean
from typing import Any, Optional

from app.valituki import content, insights, records
from app.valituki.labels import frequency_text
from app.valituki.models import ClientProfile, FitProfileChange, TherapyFitProfile, ValitukiState
from app.valituki.store import next_id, now


def get(state: ValitukiState, client_id: str) -> Optional[TherapyFitProfile]:
    return next((p for p in state.fitProfiles if p.clientId == client_id and p.status == 'active'), None)


def _usage(insight) -> dict[str, Any]:
    return {'insightId': insight.id, 'professional': insight.sharing.professional, 'matching': insight.sharing.matching,
            'editedByClient': insight.editedByClient}


def self_care_responses(state: ValitukiState, client_id: str) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for completion in sorted((c for c in state.activityCompletions if c.clientId == client_id), key=lambda c: c.createdAt):
        activity = content.activity(completion.activityId)
        row = rows.setdefault(completion.activityId, {'activityId': completion.activityId,
                                                      'title': activity.title if activity else completion.activityId,
                                                      'tried': 0, 'skipped': 0, 'ratings': [], 'lastAt': None})
        if completion.status == 'completed':
            row['tried'] += 1
            if completion.rating:
                row['ratings'].append(completion.rating)
        else:
            row['skipped'] += 1
        row['lastAt'] = completion.createdAt
    result = []
    for row in rows.values():
        ratings = row.pop('ratings')
        row['latestRating'] = ratings[-1] if ratings else None
        row['averageRating'] = round(mean(ratings), 1) if ratings else None
        row['helpful'] = bool(ratings and ratings[-1] >= 4)
        result.append(row)
    return sorted(result, key=lambda r: (-(r['latestRating'] or 0), r['title']))


def compute(state: ValitukiState, client: ClientProfile) -> dict[str, Any]:
    approved = insights.for_client(state, client.id)
    goals: dict[str, list[dict[str, Any]]] = {'primary': [], 'secondary': []}
    for insight in approved:
        if insight.kind in ('primary_goal', 'secondary_goal'):
            goals['primary' if insight.kind == 'primary_goal' else 'secondary'].append(
                {'text': insight.text, 'topics': list(insight.structured.get('topics', [])), **_usage(insight)})
    style = next((i for i in approved if i.kind == 'working_style'), None)
    practical = next((i for i in approved if i.kind == 'practical'), None)
    return {
        'goals': goals,
        'preferredWorkingStyle': ({**{k: style.structured.get(k) for k in ('structure', 'exercises', 'approach', 'homework')},
                                   'text': style.text, **_usage(style)} if style else {}),
        'practicalPreferences': ({**{k: practical.structured.get(k) for k in ('languages', 'format', 'location', 'days',
                                                                               'times', 'accessibilityNeeds')},
                                  'text': practical.text, **_usage(practical)} if practical else {}),
        'clientApprovedInsights': [i.id for i in approved],
        'selfCareResponses': self_care_responses(state, client.id),
        'engagementPreferences': {'checkInDays': list(client.checkInDays), 'frequencyText': frequency_text(client.checkInDays),
                                  'communicationStyle': client.communicationStyle} if client.checkInDays else {},
    }


FIELDS = ('goals', 'preferredWorkingStyle', 'practicalPreferences', 'clientApprovedInsights', 'selfCareResponses',
          'engagementPreferences')


def rebuild(state: ValitukiState, client: ClientProfile, *, reason: str, agent: str = 'NavigationAgent',
            create: bool = False, visible: bool = True) -> Optional[TherapyFitProfile]:
    """Recompute the profile; a real change bumps the version and is logged as an agent action."""
    profile = get(state, client.id)
    if profile is None and not create:
        return None
    data = compute(state, client)
    stamp = now(state)
    if profile is None:
        profile = TherapyFitProfile(id=next_id(state, 'fit'), clientId=client.id, createdAt=stamp, updatedAt=stamp,
                                    createdBy=records.agent_actor(agent), source='client_approved_insights', **data)
        profile.changelog.append(FitProfileChange(version=1, at=stamp, change=reason, agent=agent))
        state.fitProfiles.append(profile)
        records.act(state, agent=agent, type='create_fit_profile', client_id=client.id, rule_id='FIT-001',
                    title='Created the Therapy Fit Profile from the information you approved',
                    detail='Only what you approved went into the profile. You can edit the information and how it may be used '
                           'on the My data page.')
        return profile
    if all(getattr(profile, key) == data[key] for key in FIELDS):
        return profile
    for key in FIELDS:
        setattr(profile, key, data[key])
    profile.version += 1
    profile.updatedAt = stamp
    profile.changelog.append(FitProfileChange(version=profile.version, at=stamp, change=reason, agent=agent))
    if visible:
        records.act(state, agent=agent, type='update_fit_profile', client_id=client.id, rule_id='FIT-002',
                    title=f'Therapy Fit Profile updated (version {profile.version})', detail=reason)
    return profile
