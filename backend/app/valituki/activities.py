"""Selection from the curated, pre-approved self-care library (data/valituki/activities.json).

Only library items can be recommended. Before therapy the waiting-list protocol allows the whole library (minus items
that should be avoided in the client's situation); in therapy only the activities the therapist allowed. The selection is
deterministic; a language model may at most personalise the short introduction (validated by the output guard).
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

from app.valituki import content, insights, therapy
from app.valituki.labels import join_fi, topic
from app.valituki.models import ApprovedActivity, ClientProfile, ValitukiState
from app.valituki.store import days_between

TOPIC_TAGS = {
    'anxiety': 'anxiety', 'panic': 'anxiety', 'work_stress': 'work_stress', 'burnout': 'stress', 'stress': 'stress',
    'sleep': 'sleep', 'mood': 'low_mood', 'grief': 'low_mood', 'loneliness': 'loneliness', 'relationships': 'loneliness',
    'life_transitions': 'stress', 'self_esteem': 'low_mood', 'trauma': 'anxiety',
}


def client_topics(state: ValitukiState, client: ClientProfile) -> list[str]:
    topics: list[str] = []
    for goal in insights.active_goals(state, client.id):
        for code in goal.topics:
            if code not in topics:
                topics.append(code)
    return topics


def situation(state: ValitukiState, client: ClientProfile, *, elevated: bool = False) -> set[str]:
    tags = {'between_sessions'} if client.mode in ('therapy_support', 'aftercare_support') else {'waiting_list'}
    tags |= {TOPIC_TAGS[t] for t in client_topics(state, client) if t in TOPIC_TAGS}
    if client.safetyLock and not client.safetyLock.dismissedAt:
        tags.add('acute_crisis')
    open_safety = any(o.clientId == client.id and o.status == 'open' and o.level >= 2 for o in state.safetyObservations)
    if elevated or open_safety:
        tags.add('elevated_distress')
    return tags


def allowed_library(state: ValitukiState, client: ClientProfile, *, elevated: bool = False) -> list[ApprovedActivity]:
    """The approved activities the agent may offer right now (the protocol or the therapist's configuration)."""
    tags = situation(state, client, elevated=elevated)
    library = content.activities()
    if client.mode == 'therapy_support':
        config = therapy.active_config(state, client.id)
        permitted = set(config.allowedActivityIds) if config else set()
        library = [a for a in library if a.id in permitted]
    return [a for a in library if not (set(a.avoidWhen) & tags)]


def select(state: ValitukiState, client: ClientProfile, *, elevated: bool = False) -> tuple[Optional[ApprovedActivity], str]:
    tags = situation(state, client, elevated=elevated)
    if 'acute_crisis' in tags:
        return None, 'Exercises are not suggested while the safety instructions are showing.'
    candidates = allowed_library(state, client, elevated=elevated)
    if client.mode == 'therapy_support' and not therapy.active_config(state, client.id):
        return None, 'The therapist has not yet chosen the allowed exercises.'
    completions = [c for c in state.activityCompletions if c.clientId == client.id]
    recent = {c.activityId for c in completions if days_between(c.createdAt, state.currentDate) < 2}
    skipped = Counter(c.activityId for c in completions if c.status == 'skipped' and days_between(c.createdAt, state.currentDate) <= 14)
    ratings = {c.activityId: c.rating for c in completions if c.rating}
    last_done = {c.activityId: days_between(c.createdAt, state.currentDate) for c in completions}
    topics = set(client_topics(state, client))
    fresh = [a for a in candidates if a.id not in recent and skipped[a.id] < 2] or candidates
    if not fresh:
        return None, 'None of the allowed exercises suits the situation right now.'

    def score(activity: ApprovedActivity) -> float:
        topic_hits = len(set(activity.topics) & topics)
        tag_hits = len(set(activity.suitableFor) & tags)
        helpful = 1.5 if (ratings.get(activity.id) or 0) >= 4 else -1 if (ratings.get(activity.id) or 5) <= 2 else 0
        freshness = min(last_done.get(activity.id, 21), 14) / 14
        repeated = client.recentSuggestions[-3:].count(activity.id) * 2.5
        return topic_hits * 3 + tag_hits + helpful + freshness - repeated

    best = sorted(fresh, key=lambda a: (-score(a), a.id))[0]
    matched = sorted(set(best.topics) & topics)
    if client.mode == 'therapy_support':
        reason = 'Chosen from the exercises your therapist has allowed.'
    elif matched:
        reason = f'Chosen from the approved library because it relates to your goals: {join_fi([topic(t) for t in matched])}.'
    else:
        reason = 'Chosen from the approved library as a light exercise for the waiting time.'
    return best, reason


def goal_text_for(state: ValitukiState, client: ClientProfile, activity: ApprovedActivity) -> Optional[str]:
    goals = insights.active_goals(state, client.id)
    for goal in goals:
        if set(goal.topics) & set(activity.topics):
            return goal.text
    return goals[0].text if goals else None


def template_intro(activity: ApprovedActivity, goal_text: Optional[str]) -> str:
    """The deterministic introduction used in DEMO_AI_MODE and whenever a model text is not accepted."""
    text = activity.purpose
    if goal_text:
        short = goal_text.strip().rstrip('.')
        short = short if len(short) <= 90 else short[:87].rstrip() + '…'
        text += f' Your goal: "{short}". This could be one small step in that direction.'
    return text + ' You can also skip the exercise.'
