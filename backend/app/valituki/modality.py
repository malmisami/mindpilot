"""Which therapy approach fits the client – a transparent, rule-based suggestion next to therapist matching.

The approaches and their profiles live in data/valituki/modalities.json (a demo table a clinical owner would approve).
Two components, each 0–1, weighted to 0–100 like therapist matching:

- goals: how well the approach suits the client's approved goal topics (the referral's topics until the client has
  approved goals of their own);
- workingStyle: the client's approved working-style wishes against the approach's typical way of working, on the same
  1–5 levels as the therapists' in matching.

Practice during the wait is not counted: only cognitive behavioural therapy has guided exercises in the app, so it would
always gain from them. Only data the client allows to be used in matching is used, as in therapist matching. No language
model takes part and the same input always gives the same order. It is a suggestion for the professional's decision, not
a treatment recommendation.
"""
from __future__ import annotations

from statistics import mean
from typing import Any

from app.valituki import adapters, content, insights
from app.valituki.labels import join_fi, topic
from app.valituki.matching import STYLE_TARGETS
from app.valituki.models import ClientProfile, ValitukiState
from app.valituki.safety import normalize

COMPONENTS = (('goals', 'Goals'), ('workingStyle', 'Working style'))


def config() -> dict[str, Any]:
    return content.load('modalities.json')


def _topics(state: ValitukiState, client: ClientProfile) -> tuple[dict[str, float], str]:
    """The goal topics with their weights (primary goals weigh more, as in matching) – or the referral's."""
    weights = content.matching_config()['goalWeights']
    topics: dict[str, float] = {}
    for insight in insights.for_client(state, client.id):
        if insight.kind in ('primary_goal', 'secondary_goal') and insight.sharing.matching:
            weight = float(weights['primary' if insight.kind == 'primary_goal' else 'secondary'])
            for key in insight.structured.get('topics', []):
                topics[key] = max(topics.get(key, 0.0), weight)
    if topics:
        return topics, 'goals'
    referral = adapters.waiting_list.referral_for(state, client.id)
    return {key: 1.0 for key in (referral.requiredCompetencies if referral else [])}, 'referral'


def _style(state: ValitukiState, client: ClientProfile) -> dict[str, str]:
    insight = next((i for i in insights.for_client(state, client.id, kind='working_style') if i.sharing.matching), None)
    return {key: value for key in STYLE_TARGETS if insight and (value := insight.structured.get(key))}


def rank(state: ValitukiState, client: ClientProfile) -> dict[str, Any]:
    cfg = config()
    weights, neutral = cfg['weights'], float(cfg['neutralScore'])
    topics, topic_source = _topics(state, client)
    style = _style(state, client)
    pool = [t for t in adapters.therapist_directory.therapists(state) if t.active]
    rows = []
    for modality in cfg['modalities']:
        # Goals: the weighted share of the client's topics the approach suits.
        goal = (sum(w * float(modality['topics'].get(key, 0.0)) for key, w in topics.items()) / sum(topics.values())
                if topics else neutral)
        # Working style: 1 − distance / 4 on each wish the client has approved, as for the therapists.
        fits = [1 - abs(STYLE_TARGETS[key][1][wish] - int(modality['style'][key])) / 4 for key, wish in style.items()]
        working = mean(fits) if fits else neutral
        scores = {'goals': goal, 'workingStyle': working}
        known = {'goals': bool(topics), 'workingStyle': bool(style)}
        details = {
            'goals': (f'{"Goals" if topic_source == "goals" else "Referral"}: '
                      + join_fi([topic(key).lower() for key in topics])) if topics else 'No goals yet',
            'workingStyle': 'Approved working-style wishes' if style else 'No working-style wishes yet',
        }
        total = round(sum(float(weights[key]) * scores[key] for key, _ in COMPONENTS), 1)
        # The approach names are compared without case or diacritics, so the Finnish and the English names both match.
        names = {normalize(name) for name in modality['approaches']}
        offered = [t.name for t in pool if any(normalize(name) in names for name in t.therapeuticApproaches)]
        rows.append({'id': modality['id'], 'label': modality['label'], 'total': total,
                     'therapists': len(offered),
                     'components': [{'key': key, 'label': label, 'score': round(scores[key], 3), 'known': known[key],
                                     'detail': details[key]} for key, label in COMPONENTS]})
    rows.sort(key=lambda r: (-r['total'], r['label']))
    return {'rows': rows, 'version': cfg['version']}
