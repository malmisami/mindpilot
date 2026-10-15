"""Change detection against the client's own baseline, and recurring patterns ("We noticed something").

The client is compared primarily with themselves. The baseline is the mean of the first check-ins (the "How are you
today?" answer at the end of the intake plus the first routine check-ins). "Consecutive" means consecutive *completed*
check-ins: a missed check-in never counts as a change in wellbeing – it is reported separately as a missed check-in.
Thresholds are demo policies in data/valituki/rules.json.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from statistics import mean
from typing import Any, Optional

from app.valituki import content
from app.valituki.labels import DOMAINS, fmt_date, fmt_num, join_fi, plural
from app.valituki.models import CheckIn, ClientProfile, ValitukiState
from app.valituki.safety import normalize
from app.valituki.store import add_days, days_between, weekday

DIRECTION_LABELS = {
    'improving': 'A little better than usual',
    'stable': 'Fairly stable',
    'declining': 'A little lower than usual',
    'insufficient': 'Becomes clearer after a few check-ins',
}
DIRECTION_ARROWS = {'improving': '↑', 'stable': '→', 'declining': '↓', 'insufficient': '·'}
# Work words in a journal note (normalised text): Finnish and English.
WORK_WORDS = (r'\btyo|\btoi(ssa|hin|den|ta)\b|palaver|esity|toimisto'
              r'|\bwork|\bjob\b|\bmeeting|presentation|\boffice|\bboss\b|colleague|deadline')


@dataclass
class TrendResult:
    direction: str  # improving | stable | declining | insufficient
    level: int  # 0 none, 1 extra check-in, 2 professional review
    rule_id: Optional[str]
    baseline: Optional[float]
    recent: Optional[float]
    below_streak: int = 0
    checkin_ids: list[str] = field(default_factory=list)
    signals: list[dict[str, Any]] = field(default_factory=list)
    client_text: str = ''
    professional_text: str = ''

    def as_data(self) -> dict[str, Any]:
        return {'direction': self.direction, 'level': self.level, 'ruleId': self.rule_id, 'baseline': self.baseline,
                'recent': self.recent, 'belowStreak': self.below_streak, 'checkInIds': self.checkin_ids,
                'signals': self.signals}


def _policy() -> dict[str, Any]:
    return content.rules()['trend']


def completed_checkins(state: ValitukiState, client_id: str) -> list[CheckIn]:
    items = [c for c in state.checkIns if c.clientId == client_id and c.status == 'completed' and c.retained
             and c.mood is not None]
    return sorted(items, key=lambda c: (c.completedAt or '', c.id))


def update_baseline(state: ValitukiState, client: ClientProfile) -> None:
    """The baseline is fixed once enough check-ins exist; before that it is the provisional mean."""
    needed = int(_policy()['baselineCheckIns'])
    if len(client.baselineCheckInIds) >= needed:
        return
    items = completed_checkins(state, client.id)[:needed]
    if not items:
        return
    client.baselineCheckInIds = [c.id for c in items]
    client.baseline = round(mean(c.mood for c in items), 2)  # type: ignore[misc]
    client.baselineAt = items[-1].completedAt


def _is_below(value: float, baseline: float) -> bool:
    return value <= baseline - float(_policy()['belowBy']) + 1e-9


def _post_baseline(state: ValitukiState, client: ClientProfile) -> list[CheckIn]:
    return [c for c in completed_checkins(state, client.id) if c.id not in client.baselineCheckInIds]


def below_streak(state: ValitukiState, client: ClientProfile) -> list[CheckIn]:
    if client.baseline is None:
        return []
    streak: list[CheckIn] = []
    for checkin in reversed(_post_baseline(state, client)):
        if not _is_below(float(checkin.mood or 0), client.baseline):
            break
        streak.append(checkin)
    return list(reversed(streak))


def _domain_rows(window: list[CheckIn], minimum: int, first_name: str) -> list[dict[str, Any]]:
    rows = []
    for domain, label in DOMAINS.items():
        worse = [c for c in window if c.changes.get(domain) == 'worse']
        if domain == 'work' and worse:
            latest = worse[-1]
            rows.append({'kind': 'domain_work', 'domain': 'work', 'count': len(worse), 'of': len(window),
                         'text': f'{first_name} said their ability to work had got worse ({fmt_date(latest.completedAt)})'})
        elif len(worse) >= minimum:
            rows.append({'kind': f'domain_{domain}', 'domain': domain, 'count': len(worse), 'of': len(window),
                         'text': f'{label} worse in {len(worse)} of the last {plural(len(window), "check-in")}'})
    return rows


def missed_between(state: ValitukiState, client_id: str, start: str) -> list[CheckIn]:
    return sorted((c for c in state.checkIns if c.clientId == client_id and c.status == 'missed' and c.dueDate >= start[:10]),
                  key=lambda c: c.dueDate)


def evaluate(state: ValitukiState, client: ClientProfile) -> TrendResult:
    policy = _policy()
    if client.baseline is None:
        return TrendResult('insufficient', 0, None, None, None, client_text='The baseline is recorded at the first check-in.',
                           professional_text='No baseline yet.')
    post = _post_baseline(state, client)
    if not post:
        return TrendResult('insufficient', 0, None, client.baseline, None,
                           client_text='Your own baseline has been recorded. The direction becomes clearer after a few check-ins.',
                           professional_text=f'Own baseline {fmt_num(client.baseline)} / 5. No check-ins to compare yet.')
    window = post[-int(policy['window']):]
    recent = round(mean(c.mood for c in window), 2)  # type: ignore[misc]
    streak = below_streak(state, client)
    level = 2 if len(streak) >= int(policy['l2Count']) else 1 if len(streak) >= int(policy['l1Count']) else 0
    rule_id = policy['l2RuleId'] if level == 2 else policy['l1RuleId'] if level == 1 else None
    if level >= 1 or (streak and recent < client.baseline - 0.4):
        direction = 'declining'
    elif recent >= client.baseline + float(policy['improveBy']):
        direction, rule_id = 'improving', policy['improveRuleId']
    else:
        direction = 'stable'

    domain_window = post[-int(policy['domainWindow']):]
    signals: list[dict[str, Any]] = []
    if streak:
        values = ', '.join(f'{c.mood}/5' for c in streak)
        signals.append({'kind': 'below_baseline', 'count': len(streak),
                        'text': f'Wellbeing below their own baseline in {len(streak)} check-ins in a row '
                                f'({values}; baseline {fmt_num(client.baseline)})'})
    domain_rows = _domain_rows(domain_window, int(policy['domainWorseMin']), client.firstName)
    signals += [r for r in domain_rows if r['domain'] != 'work']
    if streak:
        missed = missed_between(state, client.id, streak[0].completedAt or streak[0].dueDate)
        if missed:
            count = 'One check-in was' if len(missed) == 1 else f'{len(missed)} check-ins were'
            signals.append({'kind': 'missed', 'count': len(missed),
                            'text': f'{count} missed ({join_fi([fmt_date(c.dueDate) for c in missed])})'})
    signals += [r for r in domain_rows if r['domain'] == 'work']

    worse_labels = [DOMAINS[r['domain']].lower() for r in signals if r.get('domain')]
    if direction == 'declining':
        client_text = 'Your wellbeing has been a little lower than usual in recent days.'
        if worse_labels:
            client_text += f' The change shows especially in: {join_fi(worse_labels)}.'
    elif direction == 'improving':
        client_text = 'Your wellbeing has been a little better than usual recently.'
    else:
        client_text = 'Your wellbeing has stayed at about your own level.'
    last = 'the last check-in' if len(window) == 1 else f'the last {len(window)} check-ins'
    professional_text = (f'Self-reported wellbeing (1–5): own baseline {fmt_num(client.baseline)}, {last} '
                         f'{fmt_num(recent)} on average.')
    return TrendResult(direction, level, rule_id, client.baseline, recent, len(streak), [c.id for c in window], signals,
                       client_text, professional_text)


def series(state: ValitukiState, client: ClientProfile, *, include_notes: bool = False) -> list[dict[str, Any]]:
    """Points for the wellbeing chart. Free-text notes are the client's journal and are left out unless asked for."""
    rows = []
    for c in completed_checkins(state, client.id):
        row = {'id': c.id, 'date': (c.completedAt or c.dueDate)[:10], 'at': c.completedAt, 'mood': c.mood, 'anxiety': c.anxiety,
               'kind': c.kind,
               'changes': dict(c.changes), 'mode': c.mode, 'trackScore': c.trackScore,
               'belowBaseline': client.baseline is not None and c.id not in client.baselineCheckInIds
               and _is_below(float(c.mood or 0), client.baseline)}
        if include_notes:
            row['note'] = c.note
        rows.append(row)
    return rows


# --- patterns ------------------------------------------------------------------------------------------------------------

def detect_workday_pattern(state: ValitukiState, client: ClientProfile) -> Optional[dict[str, Any]]:
    """PATTERN-WORKDAY-EVE-001: more anxiety (and/or weaker sleep) on evenings before workdays than before days off."""
    policy = content.rules()['patterns']
    since = add_days(state.currentDate, -int(policy['windowDays']))
    items = [c for c in completed_checkins(state, client.id) if c.kind != 'baseline' and (c.completedAt or '')[:10] >= since]
    if len(items) < int(policy['minCheckIns']):
        return None
    before_work = [c for c in items if weekday(c.completedAt or c.dueDate) in (6, 0, 1, 2, 3)]
    before_off = [c for c in items if weekday(c.completedAt or c.dueDate) in (4, 5)]
    minimum = int(policy['minPerGroup'])
    if len(before_work) < minimum or len(before_off) < minimum:
        return None

    def share(group: list[CheckIn], domain: str) -> float:
        return len([c for c in group if c.changes.get(domain) == 'worse']) / len(group)

    found = []
    shares = {}
    for domain in ('anxiety', 'sleep'):
        work, off = share(before_work, domain), share(before_off, domain)
        shares[domain] = {'beforeWorkdays': round(work, 2), 'beforeDaysOff': round(off, 2)}
        if work >= float(policy['minShare']) and work - off >= float(policy['minShareDiff']):
            found.append(domain)
    if not found:
        return None
    notes = [c for c in before_work if c.note and re.search(WORK_WORDS, normalize(c.note))]
    first = (items[0].completedAt or items[0].dueDate)[:10]
    last = (items[-1].completedAt or items[-1].dueDate)[:10]
    span = days_between(first, last)
    period = 'during the past week' if span <= 7 else 'during the past two weeks' if span <= 14 else 'during the past three weeks'
    what = join_fi([{'anxiety': 'more anxiety than average', 'sleep': 'poorer sleep'}[d] for d in found])
    text = f'On evenings before workdays, you have reported {what} {period}.'
    return {
        'ruleId': policy['ruleId'], 'domains': found, 'text': text,
        'evidence': {'checkIns': len(items), 'journalEntries': len(notes), 'beforeWorkdays': len(before_work),
                     'beforeDaysOff': len(before_off), 'shares': shares, 'period': [first, last],
                     'basis': [plural(len(items), 'check-in'), plural(len(notes), 'journal entry', 'journal entries') if notes else None,
                               'not a diagnosis']},
    }


def weekday_name(iso: str) -> str:
    return ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][date.fromisoformat(iso[:10]).weekday()]
