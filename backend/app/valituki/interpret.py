"""Deterministic interpretation used by DEMO_AI_MODE (and as the fallback of LIVE_AI_MODE) in the conversational intake.

Everything produced here is a *proposal*: it is shown to the client as "Did I understand your situation correctly?" and becomes
stored information only after the client explicitly approves it. The rules only look at what the client wrote; nothing
is inferred about demographics or health status beyond the client's own words. The patterns understand Finnish and
English; the generated sentences are English.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from app.valituki.labels import FORMATS, LANGUAGES, WEEKDAYS, join_fi
from app.valituki.safety import normalize

OPENING_KEY = 'reason'
OPENING_QUESTION = 'Tell me in your own words why you sought help.'

QUESTIONS: dict[str, str] = {
    'change': 'What would you most like to change?',
    'difficult_times': 'When is it usually hardest for you?',
    'helped_before': 'What kind of support has helped you before?',
    'exercises': 'Would you like therapy to offer more concrete exercises or more exploratory conversation?',
    'challenge': 'Would you like the therapist to challenge you actively, or mainly to help you reflect?',
    'practical': 'What practical things should we take into account – for example language, remote or in-person sessions and '
                 'suitable times?',
}
PLAN: list[str] = list(QUESTIONS)
MAX_FOLLOW_UPS = 6
MIN_ANSWERS_TO_FINISH = 2

# Every pattern runs on the normalised text (lower case, ASCII) and is bilingual: Finnish first, then English.
WORK = (r'\btyo|\btoi(ssa|hin|den|ta)\b|palaver|esity|toimisto'
        r'|\bwork|\bjob\b|\boffice\b|meeting|presentation|colleague|\bboss\b|manager|workplace|\bcareer')
SLEEP = (r'nuku|nukk|nukah|\bun(i|en|ta|et)\b|youn|unettom|valvo'
         r'|\bsleep|\bslept|\basleep|insomnia|\bawake\b|bedtime')
ANXIETY = r'ahdist|jannit|pelk|pelo|anxi|nervous|afraid|scared|\bfear|panic|dread'

GOAL_RULES: list[tuple[str, list[str], str, list[str]]] = [
    ('trauma', [r'onnettomu|trauma|painajai|accident|nightmare|\bcrash'],
     'I want to be able to work through a difficult experience so that fear does not limit my everyday life.',
     ['trauma', 'anxiety']),
    ('work_anxiety', [ANXIETY, WORK],
     'I want to be able to manage the anxiety related to work situations.', ['anxiety', 'work_stress']),
    ('burnout', [r'uupu|loppuun|burn(ed|t)?[ -]?out|exhaust|worn out', WORK], 'I want to recover from burnout and cope at work.',
     ['burnout', 'work_stress']),
    ('transition', [r'\beron\b|\bero\b|erosin|avioero|muutto|muutin|elamanmuuto'
                    r'|divorce|break.?up|broke up|separat|split up|\bmov(ed|ing) (house|home|to|away|out)\b|relocat|life change'],
     'I want to find a direction in the middle of a life change.', ['life_transitions', 'relationships']),
    ('grief', [r'kuoli|surun|\bsuru|menetys|menetin|menetyksen'
               r'|\bdied\b|death|passed away|grie|\bloss\b|\blost (my|a)\b|bereave|mourn'],
     'I want to learn to live with the loss.', ['grief', 'mood']),
    ('anxiety', [r'ahdist|jannit|paniik|pelk|anxi|nervous|panic|afraid|scared|\bfear'],
     'I want to learn to manage anxiety in everyday life.', ['anxiety']),
    ('loneliness', [r'yksinai|lonel|isolat'], 'I want to feel less lonely and find connection with others.', ['loneliness']),
    ('mood', [r'mieliala|alakulo|masentu|ei mikaan|kiinnosta'
              r'|\bmood\b|depress|\b(feel|feeling|felt|been) (low|down|flat)\b|nothing (seems|feels|is) (interesting|fun|enjoyable)'
              r'|interest|motivat'],
     'I want to find ways to cope with low mood.', ['mood']),
    ('stress', [r'stress|kuormit|kiire|overload|overwhelm|pressure|\bbusy\b|strain'],
     'I want to get my stress and strain under control.', ['stress']),
    ('sleep', [SLEEP], 'I want to sleep better.', ['sleep']),
]

SECONDARY_RULES: list[tuple[str, str, str, list[str]]] = [
    ('sleep', SLEEP, 'I want to sleep better.', ['sleep']),
    ('loneliness', r'yksinai|lonel|isolat', 'I want to feel less lonely.', ['loneliness']),
    ('stress', r'stress|kuormit|overload|overwhelm|strain', 'I want to get my stress and strain under control.', ['stress']),
    ('mood', r'joita odottaa|jotain mukavaa|iloa|look forward to|something (nice|pleasant|enjoyable)|\bjoy\b',
     'I want to find things in everyday life to look forward to.', ['mood']),
]

CARD_TITLES = {
    'goal': 'Goal',
    'working_style': 'Way of working',
    'practical': 'Practical wishes',
    'difficult_times': 'Hardest moments',
    'helped_before': 'What has helped before',
}


def question_text(key: str) -> str:
    return OPENING_QUESTION if key == OPENING_KEY else QUESTIONS[key]


def next_question_key(asked: list[str]) -> Optional[str]:
    remaining = [key for key in PLAN if key not in asked]
    if len([k for k in asked if k != OPENING_KEY]) >= MAX_FOLLOW_UPS or not remaining:
        return None
    return remaining[0]


def demo_acknowledgement(key: Optional[str], answer: str) -> str:
    """A short, neutral acknowledgement. It reflects the client's words without interpreting their health."""
    text = normalize(answer or '')
    if not text:
        return "Okay, let's skip this question."
    if key == OPENING_KEY:
        if re.search(WORK, text):
            return 'Thank you for telling me. It sounds like situations at work are central here.'
        if re.search(SLEEP, text):
            return 'Thank you for telling me. It sounds like your sleep has suffered too.'
        return 'Thank you for telling me.'
    return {
        'change': 'Thank you. This can become a goal – you will check it yourself at the end.',
        'difficult_times': 'Thank you. Recognising these moments helps to time the support well.',
        'helped_before': 'Good to know what has helped.',
        'exercises': 'Thank you, this helps to find a way of working that suits you.',
        'challenge': 'Okay.',
    }.get(key or '', 'Thank you.')


# --- extraction -------------------------------------------------------------------------------------------------------

def _match_all(patterns: list[str], text: str) -> bool:
    return all(re.search(pattern, text) for pattern in patterns)


def _sentences(text: str, limit: int = 2, max_chars: int = 200) -> str:
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    short = ' '.join(parts[:limit]).strip()
    return short if len(short) <= max_chars else short[: max_chars - 1].rstrip() + '…'


def extract_goals(answers: dict[str, str]) -> Optional[dict[str, Any]]:
    stated = normalize(' '.join(answers.get(k, '') for k in ('reason', 'change')))
    if not stated:
        return None
    primary = None
    for key, patterns, sentence, topics in GOAL_RULES:
        if _match_all(patterns, stated):
            primary = {'rule': key, 'text': sentence, 'topics': topics}
            break
    if primary is None:
        own = _sentences(answers.get('change') or answers.get('reason') or '', 1, 140)
        primary = {'rule': 'own_words', 'text': own, 'topics': []}
    everything = normalize(' '.join(answers.get(k, '') for k in ('reason', 'change', 'difficult_times')))
    secondary = []
    for key, pattern, sentence, topics in SECONDARY_RULES:
        if set(topics) & set(primary['topics']) or not re.search(pattern, everything):
            continue
        if key == 'sleep' and primary['rule'] == 'work_anxiety':
            sentence = 'I want anxiety to stop taking away my sleep before workdays.'
        secondary.append({'rule': key, 'text': sentence, 'topics': topics})
        if len(secondary) == 2:
            break
    return {'primary': primary, 'secondary': secondary}


def extract_working_style(answers: dict[str, str]) -> dict[str, Optional[str]]:
    exercises_text = normalize(answers.get('exercises', ''))
    challenge_text = normalize(answers.get('challenge', ''))
    context = normalize(' '.join(answers.get(k, '') for k in ('exercises', 'helped_before', 'change')))

    concrete = bool(re.search(r'konkreett|harjoit|kaytannon|keino|vinkk|tyokalu|lista|ohje'
                              r'|concrete|exercise|practical|technique|\btools?\b|\btips?\b|method|\blists?\b|instruction|strateg'
                              r'|hands.on', exercises_text))
    talk = bool(re.search(r'keskust|pohti|puhu|tutki|\btalk|conversation|discuss|reflect|explor|ponder', exercises_text))
    if re.search(r'molemmat|kumpikin|seka |\bboth\b|a mix|mixture|combination', exercises_text):
        exercises = 'both'
    elif concrete and talk:
        exercises = 'conversation' if re.search(r'enemman (keskust|pohti|puhu)|more (talk|conversation|discuss|reflect|explor)',
                                                exercises_text) else \
            'concrete' if re.search(r'enemman (konkreet|harjoit)|more (concrete|exercise|practical)', exercises_text) else 'both'
    elif concrete:
        exercises = 'concrete'
    elif talk:
        exercises = 'conversation'
    else:
        exercises = None

    if re.search(r'selke|struktur|jarjest|etenemi|suunnitelm|rutiin|lista'
                 r'|\bclear|structur|organi[sz]|step.by.step|progress|\bplan|routine|\blists?\b', context):
        structure = 'structured'
    elif re.search(r'vapaa|tutkiv|pohti|\bfree|explor|reflect|ponder|open.ended', context):
        structure = 'exploratory'
    else:
        structure = None

    if re.search(r"pohti|kuuntel|rauhalli|lempe|ei liikaa haast|mieluummin auttaa"
                 r"|reflect|listen|\bcalm|gentle|not (too much |too )?challeng|rather (help|reflect)|help me (think|reflect)"
                 r"|(don'?t|don t|do not|not) challenge|without challeng|no challeng", challenge_text):
        approach = 'reflective'
    elif re.search(r'haast|challeng', challenge_text):
        approach = 'directive'
    else:
        approach = None

    if re.search(r"ei (valitehtav|kotitehtav|tehtav)|en halua (valitehtav|kotitehtav|tehtav)"
                 r"|\bno (homework|between.session tasks?|tasks?)\b|(don'?t|don t|do not) want (any )?(homework|tasks|between.session)"
                 r"|without (homework|tasks)", context):
        homework = 'no'
    elif re.search(r'valitehtav|kotitehtav|tehtavat(kin)? sopi|homework|between.session task|\btasks (suit|are fine|are ok|work)',
                   context):
        homework = 'yes'
    else:
        homework = None
    return {'structure': structure, 'exercises': exercises, 'approach': approach, 'homework': homework}


def working_style_text(style: dict[str, Optional[str]]) -> str:
    parts = []
    exercises, structure = style.get('exercises'), style.get('structure')
    if exercises == 'concrete' and structure == 'structured':
        parts.append('You like concrete exercises and clear progress.')
    elif exercises == 'concrete':
        parts.append('You like concrete exercises.')
    elif exercises == 'conversation' and structure == 'exploratory':
        parts.append('You would like more conversation and reflecting together than ready-made exercises.')
    elif exercises == 'conversation':
        parts.append('You would like more conversation than exercises.')
    elif exercises == 'both':
        parts.append('Both exercises and conversation suit you.')
    elif structure == 'structured':
        parts.append('You like clear progress.')
    elif structure == 'exploratory':
        parts.append('You like a freer, exploratory approach.')
    if style.get('approach') == 'directive':
        parts.append('The therapist may also challenge you.')
    elif style.get('approach') == 'reflective':
        parts.append('You would like a calm approach where the therapist helps you reflect rather than challenges you.')
    if style.get('homework') == 'yes':
        parts.append('Between-session tasks suit you.')
    elif style.get('homework') == 'no':
        parts.append('You would rather not have between-session tasks.')
    return ' '.join(parts)


WEEKDAY_PATTERNS = [r'maanantai|monday', r'tiistai|tuesday', r'keskiviikko|wednesday', r'torstai|thursday', r'perjantai|friday',
                    r'lauantai|saturday', r'sunnuntai|sunday']
# The practical summary in English: 'evenings (Tuesday or Thursday)'.
TIME_PHRASES = {'morning': 'mornings', 'daytime': 'afternoons', 'evening': 'evenings'}


def extract_practical(answers: dict[str, str], municipality: str) -> dict[str, Any]:
    text = normalize(answers.get('practical', ''))
    languages = [code for code, pattern in (('fi', r'suome|suomi|finnish'), ('sv', r'ruotsi|svenska|pa svenska|swedish'),
                                             ('en', r'englanti|englann|english')) if re.search(pattern, text)]
    language_stated = bool(languages)
    if not languages:
        languages = ['fi']
    remote = bool(re.search(r'\beta|etavastaanot|etana|video|verkossa|kotoa|remote|\bonline\b|from home|distance', text))
    in_person = bool(re.search(r'lahivastaanot|lahella|paikan paalla|vastaanotolla|kasvokkain'
                               r'|in.person|face.to.face|on site|nearby|close to home|at the (clinic|practice|office)', text))
    fmt = 'either' if remote == in_person else 'remote' if remote else 'in_person'
    days = [index for index, pattern in enumerate(WEEKDAY_PATTERNS) if re.search(pattern, text)]
    times = [key for key, pattern in (('morning', r'aamupai|aamuisin|aamulla|\baamu|morning'),
                                      ('daytime', r'iltapai|paivalla|paivaisin|paivasaikaan|\bpaiva'
                                                  r'|afternoon|during the day|daytime|\bmidday|lunchtime'),
                                      ('evening', r'ilta(?!pai)|\billa|illoin|iltaisin|evening|\bnights?\b'))
             if re.search(pattern, text)]
    return {'languages': languages, 'languageStated': language_stated, 'format': fmt, 'location': municipality,
            'days': days, 'times': times, 'accessibilityNeeds': []}


def practical_text(practical: dict[str, Any]) -> str:
    place = f' ({practical["location"]})' if practical['format'] != 'remote' and practical.get('location') else ''
    parts = [FORMATS[practical['format']] + place]
    languages = join_fi([LANGUAGES.get(code, code) for code in practical.get('languages') or []], 'or')
    if languages:
        parts.append(f'in {languages}')
    if practical.get('times'):
        times = join_fi([TIME_PHRASES.get(t, t) for t in practical['times']], 'or')
        if practical.get('days'):
            times += f' ({join_fi([WEEKDAYS[d] for d in practical["days"]], "or")})'
        parts.append(times)
    elif practical.get('days'):
        parts.append(join_fi([WEEKDAYS[d] for d in practical['days']], 'or'))
    return ', '.join(parts) + '.'


def extract(answers: dict[str, str], municipality: str) -> list[dict[str, Any]]:
    """Deterministic proposals ("Did I understand your situation correctly?")."""
    proposals: list[dict[str, Any]] = []
    goals = extract_goals(answers)
    if goals:
        text = goals['primary']['text']
        proposals.append({
            'category': 'goal', 'title': CARD_TITLES['goal'], 'text': text,
            'structured': {'primary': {'text': text, 'topics': goals['primary']['topics']},
                           'secondary': [{'text': g['text'], 'topics': g['topics']} for g in goals['secondary']],
                           'hope': answers.get('change', '').strip()},
            'derivedFrom': [k for k in ('reason', 'change') if answers.get(k)],
            'userWords': [answers[k].strip() for k in ('change',) if answers.get(k)],
        })
    style = extract_working_style(answers)
    if any(style.values()):
        proposals.append({'category': 'working_style', 'title': CARD_TITLES['working_style'], 'text': working_style_text(style),
                          'structured': style, 'derivedFrom': [k for k in ('exercises', 'challenge', 'helped_before') if answers.get(k)],
                          'userWords': [answers[k].strip() for k in ('exercises', 'challenge') if answers.get(k)]})
    practical = extract_practical(answers, municipality)
    proposals.append({'category': 'practical', 'title': CARD_TITLES['practical'], 'text': practical_text(practical),
                      'structured': practical, 'derivedFrom': ['practical'] if answers.get('practical') else [],
                      'userWords': [answers['practical'].strip()] if answers.get('practical') else []})
    if answers.get('difficult_times', '').strip():
        proposals.append({'category': 'difficult_times', 'title': CARD_TITLES['difficult_times'],
                          'text': 'It is often hardest: ' + _lower_first(_sentences(answers['difficult_times'], 1, 160)),
                          'structured': {}, 'derivedFrom': ['difficult_times'],
                          'userWords': [answers['difficult_times'].strip()]})
    if answers.get('helped_before', '').strip():
        proposals.append({'category': 'helped_before', 'title': CARD_TITLES['helped_before'],
                          'text': 'What has helped before: ' + _lower_first(_sentences(answers['helped_before'], 2, 180)),
                          'structured': {}, 'derivedFrom': ['helped_before'], 'userWords': [answers['helped_before'].strip()]})
    return proposals


# Words that keep their capital after "It is often hardest: " (English proper nouns and "I").
_KEEP_CAPITAL = re.compile(r"(I|I'm|I've|I'd|I'll|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Mieliluotsi)s?\b")


def _lower_first(text: str) -> str:
    if not text or text[:2].isupper() or _KEEP_CAPITAL.match(text):
        return text
    return text[:1].lower() + text[1:]
