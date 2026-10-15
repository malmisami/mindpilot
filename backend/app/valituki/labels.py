"""Display labels shared by the engine's explanations and the UI (sent to the frontend in the view meta)."""
from __future__ import annotations

from datetime import date

TOPICS = {
    'anxiety': 'anxiety and nervousness',
    'work_stress': 'work-related stress',
    'burnout': 'burnout',
    'stress': 'stress and strain',
    'sleep': 'sleep',
    'mood': 'mood',
    'relationships': 'relationships',
    'life_transitions': 'life changes',
    'loneliness': 'loneliness',
    'grief': 'loss and grief',
    'trauma': 'difficult experiences',
    'self_esteem': 'self-esteem',
    'panic': 'panic symptoms',
    'young_people': 'young people (13–17)',
}

LANGUAGES = {'fi': 'Finnish', 'sv': 'Swedish', 'en': 'English'}
FORMATS = {'remote': 'Remote session', 'in_person': 'In-person session', 'either': 'Remote or in-person session'}
TIMES = {'morning': 'morning', 'daytime': 'afternoon', 'evening': 'evening'}
WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
WEEKDAYS_SHORT = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
MONTHS_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

STYLE_DIMENSIONS = {
    'structure': {'label': 'Structure', 'values': {'structured': 'Clear structure and progression', 'balanced': 'Flexible structure',
                                                  'exploratory': 'Free, exploratory approach'}},
    'exercises': {'label': 'Exercises or conversation', 'values': {'concrete': 'Concrete exercises',
                                                                    'both': 'Exercises and conversation',
                                                                    'conversation': 'Mostly conversation'}},
    'approach': {'label': 'Challenge', 'values': {'directive': 'The therapist may challenge me actively',
                                                  'balanced': 'Both challenge and reflection',
                                                  'reflective': 'The therapist mainly helps me reflect'}},
    'homework': {'label': 'Between-session tasks', 'values': {'yes': 'Between-session tasks suit me',
                                                              'some': 'Between-session tasks sometimes',
                                                              'no': 'No between-session tasks'}},
}

DOMAINS = {'sleep': 'Sleep', 'anxiety': 'Anxiety', 'energy': 'Energy', 'work': 'Ability to work', 'social': 'Social life'}
MOOD_SCALE = {1: 'Very bad', 2: 'Bad', 3: 'Okay', 4: 'Good', 5: 'Very good'}
ANXIETY_SCALE = {1: 'Not at all', 2: 'A little', 3: 'Somewhat', 4: 'A lot', 5: 'Very much'}

# The kinds of practice shown in "Progress" (the tag on each completed item).
PRACTICE_KINDS = {
    'thought_record': 'Thoughts',
    'experiment': 'Behavioural experiment',
    'exposure': 'Exposure',
    'activity': 'Exercise',
    'checkin': 'Check-in',
    'homework': 'Between-session task',
}

SERVICE_CATEGORIES = {'short_therapy': 'Short-term therapy', 'psychotherapy': 'Rehabilitative psychotherapy'}
ROLE_CATEGORIES = {'psychotherapist': 'psychotherapist', 'psychologist': 'psychologist', 'short_therapist': 'short-term therapist',
                   'psychiatric_nurse': 'psychiatric nurse'}
AGE_GROUPS = {'13-17': '13–17 years', '18-29': '18–29 years', '30-64': '30–64 years', '65+': '65+ years'}
AGE_RANGES = {'13-17': (13, 17), '18-29': (18, 29), '30-64': (30, 64), '65+': (65, 130)}
ACCESSIBILITY = {
    'step_free': 'step-free access', 'induction_loop': 'induction loop', 'plain_language': 'plain language',
    'interpreter': 'interpreting available', 'captions': 'captions in remote sessions',
}
CLIENT_FLAGS = {
    'acute_safety_concern': 'open, unreviewed safety observation',
    'primary_substance_use': 'substance use as the primary care need',
    'needs_interpreter': 'needs interpreting',
}
URGENCY = {'non_urgent': 'Non-urgent', 'urgent': 'Urgent'}

CONSENTS = {
    'proactiveCheckins': {'title': 'Mieliluotsi may contact me',
                          'description': 'Check-in questions and reminders at the rhythm you choose.'},
    'storeHistory': {'title': 'My answers are stored',
                     'description': 'So that your wellbeing can be compared with your own baseline and changes can be noticed.'},
    'professionalMonitoring': {'title': 'The care team sees how my wellbeing is trending',
                               'description': "A professional sees a summary of your check-ins and Mieliluotsi's observations. "
                                              'Other information is shared only if you give permission.'},
    'sharePractice': {'title': 'My therapist sees my exercises',
                      'description': 'Once therapy starts: the number of exercises, the thinking traps you identified and the change '
                                     'in feeling 0–10. Thought diary entries are visible only if you share them yourself.'},
}

INFO_TYPES = {
    'user_said': "In the client's own words / approved by the client",
    'measured': 'Measured / self-reported',
    'ai_summary': 'AI summary',
    'professional_note': 'Professional note',
    'system': 'System information',
}

INSIGHT_CATEGORIES = {
    'goal': 'My goals',
    'preference': 'My wishes',
    'helpful': 'Things I have found helpful',
    'challenge': 'Everyday challenges',
    'therapist_wish': 'Wishes about the therapist',
}

INSIGHT_ORIGINS = {
    'user_said': 'In your own words',
    'ai_interpreted': 'AI interpretation you approved',
    'observed': 'Mieliluotsi observation you approved',
    'measured': 'From your own answers',
}

CONTACT_REASONS = {
    'wellbeing': 'I am worried about how I feel',
    'waiting': 'I want to ask about the waiting list',
    'matching': 'I need help choosing a therapist',
    'other': 'Something else',
}

AGENT_DESCRIPTIONS = {
    'SupportAgent': 'Conversational support, guided CBT exercises in the chat and introducing approved exercises',
    'CheckInAgent': 'Timing of check-ins and follow-up of missed check-ins',
    'ObservationAgent': "Changes against the client's own baseline and recurring observations",
    'MatchingAgent': 'Deterministic therapist matching and its explanations',
    'NavigationAgent': 'The next step on the care pathway and the hand-offs',
    'SafetyAgent': 'Deterministic safety rules – can interrupt everything else',
    'Orchestrator': 'Decides which agent handles an event',
}

# Conjunctions callers may still pass in Finnish ('ja', 'tai').
_CONJUNCTIONS = {'ja': 'and', 'tai': 'or'}


def allative(name: str) -> str:
    """English has no allative case: the name as it is ("to" belongs to the sentence)."""
    return name


def genitive(name: str) -> str:
    """'Sami's', 'James's'."""
    return f"{name}'s"


def topic(code: str) -> str:
    return TOPICS.get(code, code)


def join_fi(items: list[str], word: str = 'and') -> str:
    """'a', 'a and b', 'a, b and c' (`word` 'or' for alternatives; the Finnish 'ja' / 'tai' are accepted too)."""
    word = _CONJUNCTIONS.get(word, word)
    items = [item for item in items if item]
    if not items:
        return ''
    if len(items) == 1:
        return items[0]
    return ', '.join(items[:-1]) + f' {word} ' + items[-1]


def plural(count: int, singular: str, many: str | None = None) -> str:
    """'1 check-in', '3 check-ins', '2 entries'."""
    return f'{count} {singular if count == 1 else (many or singular + "s")}'


def fmt_num(value: float, digits: int = 1) -> str:
    return f'{value:.{digits}f}'


def fmt_date(iso: str | None) -> str:
    """'14 Oct'"""
    if not iso:
        return '–'
    y, m, d = iso[:10].split('-')
    return f'{int(d)} {MONTHS_SHORT[int(m) - 1]}'


def fmt_date_long(iso: str | None) -> str:
    """'14 Oct 2026'"""
    if not iso:
        return '–'
    y, m, d = iso[:10].split('-')
    return f'{int(d)} {MONTHS_SHORT[int(m) - 1]} {y}'


def fmt_slot(iso: str | None) -> str:
    """'Tue 17 Nov at 18:00'"""
    if not iso:
        return '–'
    day = date.fromisoformat(iso[:10])
    time = iso[11:16] if len(iso) >= 16 else ''
    return f'{WEEKDAYS_SHORT[day.weekday()]} {day.day} {MONTHS_SHORT[day.month - 1]}' + (f' at {time}' if time else '')


def fmt_slot_title(iso: str | None) -> str:
    """'Tue 17 Nov at 18:00' (capitalised for the start of a line)"""
    text = fmt_slot(iso)
    return text[:1].upper() + text[1:]


def days_text(days: list[int]) -> str:
    return join_fi([WEEKDAYS_SHORT[d] for d in sorted(days)])


def frequency_text(days: list[int]) -> str:
    count = len(days)
    if count == 0:
        return 'no regular check-ins'
    per_week = {1: 'once a week', 2: 'twice a week', 3: 'three times a week'}.get(count, f'{count} times a week')
    return f'{per_week} ({days_text(days)})'


def relative_label(iso: str | None, today: str) -> str:
    """'today', 'tomorrow' or 'Wed 21 Oct'"""
    if not iso:
        return '–'
    delta = (date.fromisoformat(iso[:10]) - date.fromisoformat(today[:10])).days
    if delta == 0:
        return 'today'
    if delta == 1:
        return 'tomorrow'
    return fmt_slot(iso[:10])


def count_word(count: int) -> str:
    return {1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six'}.get(count, str(count))
