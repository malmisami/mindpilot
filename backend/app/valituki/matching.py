"""Transparent, deterministic therapist matching. No language model takes part in eligibility or ranking.

Step 1 – hard filters: active status, service eligibility, appropriate professional role, age group, the competence the
referral requires, language, remote / location requirement, exclusion criteria, capacity and actual availability.
Step 2 – weighted fit with the editable weights in data/valituki/matching_config.json.

The points are an ordering aid, never shown to the client as a number and never a clinical probability. The input is
built only from client-approved insights that the client allows to be used in matching (see matching_flow.build_input);
nothing is inferred. The function is pure: the same input always gives the same ranking.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.valituki import content
from app.valituki.labels import (
    ACCESSIBILITY,
    AGE_GROUPS,
    AGE_RANGES,
    CLIENT_FLAGS,
    LANGUAGES,
    ROLE_CATEGORIES,
    SERVICE_CATEGORIES,
    fmt_slot,
    join_fi,
    plural,
    topic,
)
from app.valituki.models import FilterOutcome, MatchComponent, Therapist, TherapistAvailability
from app.valituki.store import days_between, weekday

FILTER_LABELS = {
    'active': 'Active therapist',
    'service': 'Service eligibility',
    'role': 'Professional group',
    'age': 'Age group',
    'competence': 'Competence the referral requires',
    'language': 'Language',
    'location': 'Remote session or location',
    'exclusion': 'Exclusion criteria',
    'capacity': 'Free client place',
    'availability': 'Free time in the coming weeks',
}

COMPONENT_LABELS = {
    'goalCompetence': 'Goals and competence',
    'workingStyle': 'Way of working',
    'userPreferences': 'Own wishes',
    'languageAccessibility': 'Language and accessibility',
    'availabilityContinuity': 'Availability and continuity',
    'logistics': 'Logistics',
}

# The topic as the object of "Works with …" (the names were Finnish case forms; English needs only the plain noun).
TOPIC_GENITIVE = {
    'anxiety': 'anxiety', 'work_stress': 'work-related stress', 'sleep': 'sleep', 'burnout': 'burnout',
    'stress': 'stress', 'mood': 'mood', 'relationships': 'relationships', 'life_transitions': 'life changes',
    'loneliness': 'loneliness', 'grief': 'grief', 'trauma': 'difficult experiences', 'self_esteem': 'self-esteem',
    'panic': 'panic symptoms', 'young_people': 'young people',
}
TIME_ILLATIVE = {'morning': 'mornings', 'daytime': 'afternoons', 'evening': 'evenings'}
TIME_PLURAL = TIME_ILLATIVE
TIME_ADVERB = {'morning': 'in the morning', 'daytime': 'in the afternoon', 'evening': 'in the evening'}
WEEKDAY_ESSIVE = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
WEEKDAY_PARTITIVE = ['Mondays', 'Tuesdays', 'Wednesdays', 'Thursdays', 'Fridays', 'Saturdays', 'Sundays']
STYLE_TARGETS = {
    'structure': ('structuredLevel', {'structured': 5, 'balanced': 3, 'exploratory': 1}),
    'exercises': ('exerciseLevel', {'concrete': 5, 'both': 3, 'conversation': 1}),
    'approach': ('directiveLevel', {'directive': 5, 'balanced': 3, 'reflective': 1}),
    'homework': ('homeworkLevel', {'yes': 5, 'some': 3, 'no': 1}),
}


@dataclass
class ClientMatchInput:
    client_id: str
    age: int
    municipality: str
    service_category: str
    required_competencies: list[str]
    languages: list[str]
    format: str
    days: list[int] = field(default_factory=list)
    times: list[str] = field(default_factory=list)
    accessibility_needs: list[str] = field(default_factory=list)
    primary_topics: list[str] = field(default_factory=list)
    secondary_topics: list[str] = field(default_factory=list)
    style: dict[str, Optional[str]] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    personal_exclusions: list[str] = field(default_factory=list)
    data_used: list[str] = field(default_factory=list)
    data_not_used: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class Scored:
    therapist: Therapist
    total: float
    label: str
    label_text: str
    components: list[MatchComponent]
    reasons: list[str]
    unmet: list[str]
    slot: TherapistAvailability
    why: str


@dataclass
class Evaluation:
    ranked: list[Scored]
    excluded: list[dict[str, Any]]
    config_version: str


def time_bucket(start: str) -> str:
    hour = int(start[11:13])
    return 'morning' if hour < 12 else 'daytime' if hour < 16 else 'evening'


def _in_area(client: ClientMatchInput, therapist: Therapist) -> bool:
    return client.municipality.lower() in {loc.lower() for loc in therapist.locations}


def _wanted_formats(client: ClientMatchInput) -> set[str]:
    return {'remote', 'in_person'} if client.format == 'either' else {client.format}


def compatible_slots(client: ClientMatchInput, therapist: Therapist, slots: list[TherapistAvailability], today: str,
                     horizon: int) -> list[TherapistAvailability]:
    wanted = _wanted_formats(client)
    result = []
    for slot in slots:
        if slot.therapistId != therapist.id or slot.status != 'free' or slot.start[:10] <= today:
            continue
        if days_between(today, slot.start) > horizon:
            continue
        formats = set(slot.formats) & wanted
        if formats == {'in_person'} and not _in_area(client, therapist):
            continue
        if formats:
            result.append(slot)
    return sorted(result, key=lambda s: (s.start, s.id))


def preferred_slot(client: ClientMatchInput, compatible: list[TherapistAvailability]) -> TherapistAvailability:
    """The first slot that fits the stated day and time wishes best (both, then time, then day, then the earliest)."""
    def fits(slot: TherapistAvailability) -> tuple[bool, bool]:
        return (not client.times or time_bucket(slot.start) in client.times,
                not client.days or weekday(slot.start) in client.days)

    for want in ((True, True), (True, False), (False, True)):
        for slot in compatible:
            time_ok, day_ok = fits(slot)
            if (not want[0] or time_ok) and (not want[1] or day_ok):
                return slot
    return compatible[0]


def hard_filters(client: ClientMatchInput, therapist: Therapist, slots: list[TherapistAvailability], today: str,
                 config: dict[str, Any]) -> list[FilterOutcome]:
    outcomes: list[FilterOutcome] = []

    def add(key: str, passed: bool, reason: str) -> None:
        outcomes.append(FilterOutcome(key=key, label=FILTER_LABELS[key], passed=passed, reason=reason))

    add('active', therapist.active,
        'Active' if therapist.active else f'Not taking new clients ({therapist.inactiveReason or "not active"})')
    service_ok = client.service_category in therapist.serviceCategories
    add('service', service_ok, f'{SERVICE_CATEGORIES.get(client.service_category, client.service_category)} '
        + ("is among the therapist's services" if service_ok else "is not among the therapist's services"))
    roles = config['roleEligibility'].get(client.service_category, [])
    role_ok = therapist.roleCategory in roles
    add('role', role_ok, f'{ROLE_CATEGORIES[therapist.roleCategory].capitalize()} '
        + ("– suits the referral's service" if role_ok else "– does not suit the referral's service"))
    age_ok = any(AGE_RANGES[g][0] <= client.age <= AGE_RANGES[g][1] for g in therapist.ageGroups if g in AGE_RANGES)
    add('age', age_ok, 'Age group fits' if age_ok
        else f'Only sees clients aged {join_fi([AGE_GROUPS.get(g, g) for g in therapist.ageGroups], "or")}')
    missing = [c for c in client.required_competencies if c not in therapist.specialties]
    add('competence', not missing, 'Has the competence the referral requires' if not missing
        else f'Missing: {join_fi([topic(c) for c in missing])}')
    shared = [lang for lang in client.languages if lang in therapist.languages]
    add('language', bool(shared), f'Shared language: {join_fi([LANGUAGES[x] for x in shared])}' if shared else
        f'No shared language (therapist: {join_fi([LANGUAGES[x] for x in therapist.languages])})')
    wanted = _wanted_formats(client)
    remote_ok = 'remote' in wanted and therapist.remote
    local_ok = 'in_person' in wanted and therapist.inPerson and _in_area(client, therapist)
    if remote_ok or local_ok:
        where = 'Remote session possible' if remote_ok else f'In-person session: {", ".join(therapist.locations)}'
    else:
        where = 'In-person sessions only: ' + ', '.join(therapist.locations) if not therapist.remote else 'Remote sessions only'
    add('location', remote_ok or local_ok, where)
    blocked = sorted(set(therapist.exclusionCriteria) & set(client.flags))
    personal = therapist.id in client.personal_exclusions
    add('exclusion', not blocked and not personal, 'No exclusion criteria' if not blocked and not personal else
        ('The client asked to exclude this therapist' if personal
         else f'Exclusion criterion: {join_fi([CLIENT_FLAGS.get(b, b) for b in blocked])}'))
    capacity_ok = therapist.currentCapacity < therapist.maxCapacity
    add('capacity', capacity_ok, plural(therapist.maxCapacity - therapist.currentCapacity, 'free place') if capacity_ok
        else f'No free client places ({therapist.currentCapacity}/{therapist.maxCapacity})')
    compatible = compatible_slots(client, therapist, slots, today, int(config['slotHorizonDays'])) if capacity_ok else []
    add('availability', bool(compatible), f'First suitable time: {fmt_slot(compatible[0].start)}' if compatible
        else 'No suitable free times in the coming weeks')
    return outcomes


def _components(client: ClientMatchInput, therapist: Therapist, slot: TherapistAvailability, today: str,
                config: dict[str, Any]) -> tuple[list[MatchComponent], list[str], list[str]]:
    weights = config['weights']
    reasons: list[str] = []
    unmet: list[str] = []
    components: list[MatchComponent] = []

    def add(key: str, score: float, explanation: str) -> None:
        score = max(0.0, min(1.0, score))
        weight = float(weights[key])
        components.append(MatchComponent(key=key, label=COMPONENT_LABELS[key], weight=weight, score=round(score, 3),
                                         points=round(score * weight, 1), explanation=explanation))

    # Goals and competence
    goal_weights = config['goalWeights']
    topics = [(t, goal_weights['primary']) for t in client.primary_topics] + \
             [(t, goal_weights['secondary']) for t in client.secondary_topics if t not in client.primary_topics]
    if topics:
        total = sum(w for _, w in topics)
        hits = [t for t, _ in topics if t in therapist.specialties]
        score = sum(w for t, w in topics if t in therapist.specialties) / total
        primary_hits = [t for t in client.primary_topics if t in therapist.specialties]
        secondary_hits = [t for t in client.secondary_topics if t in therapist.specialties and t not in client.primary_topics]
        if primary_hits:
            reasons.append(f'Works with {join_fi([TOPIC_GENITIVE.get(t, topic(t)) for t in primary_hits])}')
        if secondary_hits:
            reasons.append(f'Also works with {join_fi([TOPIC_GENITIVE.get(t, topic(t)) for t in secondary_hits])}')
        misses = [t for t, _ in topics if t not in therapist.specialties]
        if misses:
            unmet.append(f'No recorded special competence in {join_fi([topic(t) for t in misses])}')
        add('goalCompetence', score, f'{len(hits)}/{len(topics)} of your goal areas are among their areas of competence')
    else:
        add('goalCompetence', 0.5, 'Goals were not used in matching')

    # Working style
    style_scores = []
    for dimension, (attribute, targets) in STYLE_TARGETS.items():
        wish = client.style.get(dimension)
        if not wish:
            continue
        level = getattr(therapist, attribute)
        diff = abs(targets[wish] - level)
        style_scores.append(1 - diff / 4)
        if dimension == 'structure' and wish == 'structured' and level >= 4:
            reasons.append('Uses a structured way of working')
        elif dimension == 'structure' and wish == 'exploratory' and level <= 2:
            reasons.append('An exploratory, conversational approach')
        elif dimension == 'exercises' and wish == 'concrete' and level >= 4:
            reasons.append('Offers concrete exercises')
        elif dimension == 'exercises' and wish == 'conversation' and level <= 2:
            reasons.append('Focuses on conversation rather than exercises')
        elif dimension == 'approach' and wish == 'directive' and level >= 4:
            reasons.append('Challenges actively when needed')
        elif dimension == 'approach' and wish == 'reflective' and level <= 2:
            reasons.append('A calm approach that supports reflection')
        elif dimension == 'homework' and wish == 'yes' and level >= 4:
            reasons.append('Uses between-session tasks')
        if diff >= 2:
            unmet.append({
                'structure': 'The way of working is more flexible than the clear progression you hoped for' if wish == 'structured'
                else 'The way of working is more structured than you hoped for',
                'exercises': 'Fewer concrete exercises than you hoped for' if wish == 'concrete'
                else 'More exercises than you hoped for',
                'approach': 'Challenges less than you hoped for' if wish == 'directive' else 'Challenges more than you hoped for',
                'homework': 'Fewer between-session tasks than you hoped for' if wish == 'yes'
                else 'More between-session tasks than you hoped for',
            }[dimension])
    if style_scores:
        style_score = sum(style_scores) / len(style_scores)
        add('workingStyle', style_score, f'{therapist.workingStyle} – matches your wishes '
            f'{"well" if style_score >= 0.8 else "partly" if style_score >= 0.5 else "poorly"}')
    else:
        add('workingStyle', float(config['neutralStyleScore']), 'Wishes about the way of working were not used in matching')

    # The client's own preferences: time of day and weekday (time of day weighs more – configurable)
    pref_weights = config.get('preferenceWeights', {'time': 0.5, 'day': 0.5})
    parts: list[tuple[float, float]] = []
    notes: list[str] = []
    bucket, day = time_bucket(slot.start), weekday(slot.start)
    if client.times:
        ok = bucket in client.times
        parts.append((float(pref_weights['time']), 1.0 if ok else 0.0))
        notes.append('time fits' if ok else 'time does not fit')
        if ok:
            reasons.append(f'The time fits your wish for {join_fi([TIME_ILLATIVE[t] for t in client.times], "or")}')
        else:
            unmet.append(f'The free times are {TIME_ADVERB[bucket]} – you wished for '
                         f'{join_fi([TIME_PLURAL[t] for t in client.times], "or")}')
    if client.days:
        ok = day in client.days
        parts.append((float(pref_weights['day']), 1.0 if ok else 0.0))
        notes.append('day fits' if ok else 'day does not fit')
        if not ok:
            unmet.append(f'The first free time is on a {WEEKDAY_ESSIVE[day]} – you wished for '
                         f'{join_fi([WEEKDAY_PARTITIVE[d] for d in client.days], "or")}')
    preference = sum(w * s for w, s in parts) / sum(w for w, _ in parts) if parts else 1.0
    add('userPreferences', preference, '; '.join(notes).capitalize() or 'No time wishes')

    # Language and accessibility
    primary = client.languages[0] if client.languages else 'fi'
    lang_score = 0.6 if primary in therapist.languages else 0.3
    if primary in therapist.languages and primary == 'fi':
        reasons.append('Sessions in Finnish')
    elif primary in therapist.languages:
        reasons.append(f'Sessions in {LANGUAGES[primary]}')
    else:
        unmet.append(f'Your primary language ({LANGUAGES[primary]}) is not available')
    needs = client.accessibility_needs
    covered = [n for n in needs if n in therapist.accessibility]
    lang_score += 0.4 * (len(covered) / len(needs) if needs else 1.0)
    for need in needs:
        if need not in covered:
            unmet.append(f'Accessibility need not met: {ACCESSIBILITY.get(need, need)}')
    add('languageAccessibility', lang_score, f'{LANGUAGES[primary]}: {"yes" if primary in therapist.languages else "no"}'
        + (f'; accessibility {len(covered)}/{len(needs)}' if needs else ''))

    # Availability and continuity
    days = days_between(today, slot.start)
    availability = next(item['score'] for item in config['availabilityScores'] if days <= item['maxDays'])
    add('availabilityContinuity', 0.7 * availability + 0.3 * (1.0 if therapist.weeklyContinuity else 0.0),
        f'First suitable time in {plural(days, "day")}; '
        + ('weekly continuity' if therapist.weeklyContinuity else 'sessions less often than weekly'))
    if not therapist.weeklyContinuity:
        unmet.append('Sessions less often than once a week')

    # Logistics
    if 'remote' in slot.formats and 'remote' in _wanted_formats(client) and therapist.remote:
        logistics, text = 1.0, 'Remote session'
        reasons.append('Remote session')
    else:
        logistics, text = (1.0 if _in_area(client, therapist) else 0.6), f'In-person session: {", ".join(therapist.locations)}'
        reasons.append(f'In-person session: {", ".join(therapist.locations)}')
    add('logistics', logistics, text)
    return components, reasons, unmet


def label_for(total: float, config: dict[str, Any]) -> tuple[str, str]:
    for item in config['labels']:
        if total >= float(item['min']):
            return item['key'], item['text']
    last = config['labels'][-1]
    return last['key'], last['text']


REASON_ORDER = ['Also works with', 'Works with ', 'Uses a structured', 'An exploratory', 'Offers concrete',
                'Focuses on conversation', 'Remote session', 'In-person session', 'The time fits', 'Challenges', 'A calm',
                'Uses between-session', 'Sessions in']
REASON_RANK = {'Also works with': 9, 'Works with ': 0, 'Uses a structured': 1, 'An exploratory': 1, 'Offers concrete': 2,
               'Focuses on conversation': 2, 'Remote session': 3, 'In-person session': 3, 'The time fits': 4, 'Challenges': 10,
               'A calm': 10, 'Uses between-session': 11, 'Sessions in': 12}


def _order_reasons(reasons: list[str]) -> list[str]:
    """The strongest, most concrete reasons first (goal fit, working style, format, time), details after."""
    def key(reason: str) -> int:
        prefix = next((p for p in REASON_ORDER if reason.startswith(p)), None)
        return REASON_RANK.get(prefix, 20) if prefix else 20
    return sorted(dict.fromkeys(reasons), key=key)


def evaluate(client: ClientMatchInput, therapists: list[Therapist], slots: list[TherapistAvailability], today: str,
             config: Optional[dict[str, Any]] = None) -> Evaluation:
    """Pure function: the same input always gives the same ranking, whatever the order of `therapists`."""
    config = config or content.matching_config()
    horizon = int(config['slotHorizonDays'])
    ranked: list[Scored] = []
    excluded: list[dict[str, Any]] = []
    for therapist in sorted(therapists, key=lambda t: t.id):
        outcomes = hard_filters(client, therapist, slots, today, config)
        failed = [o for o in outcomes if not o.passed]
        if failed:
            excluded.append({'therapistId': therapist.id, 'name': therapist.name, 'failed': [o.model_dump() for o in failed]})
            continue
        slot = preferred_slot(client, compatible_slots(client, therapist, slots, today, horizon))
        components, reasons, unmet = _components(client, therapist, slot, today, config)
        total = round(sum(c.points for c in components), 1)
        key, text = label_for(total, config)
        first_name = therapist.name.split()[0]
        ordered = _order_reasons(reasons)
        why = (f'{first_name} meets all the criteria. ' + '. '.join(ordered[:3]) + '.' if ordered
               else f'{first_name} meets all the criteria.')
        ranked.append(Scored(therapist, total, key, text, components, ordered, unmet, slot, why))
    ranked.sort(key=lambda s: (-s.total, s.slot.start, s.therapist.id))
    return Evaluation(ranked=ranked, excluded=excluded, config_version=config['version'])
