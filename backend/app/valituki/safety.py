"""Deterministic Safety Engine.

Levels:
  0 – normal support
  1 – additional check-in suggested
  2 – human review recommended
  3 – immediate safety information displayed

Signals: deterministic phrase rules (data/valituki/safety_rules.json), structured answers (a very low 1/5 mood), the
explicit "I need help now" action. An optional language-model hint is an *additional* signal only: the final level
is the maximum of the deterministic level and the hint, so a model can raise a level but never lower a deterministic
trigger.

The phrase rules are intentionally conservative (negations are not interpreted): a false alarm shows help contacts, a
missed signal could hide a risk. The rules are a demo policy and require clinical validation.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

from app.valituki import content
from app.valituki.models import SafetyTrigger

LEVEL_LABELS = {
    0: 'Normal support',
    1: 'Additional check-in suggested',
    2: 'Professional review recommended',
    3: 'Immediate safety information shown',
}

# A model's advisory hint mapped onto the same scale. Used only to raise a level.
AI_HINT_LEVELS = {'NONE': 0, 'REVIEW': 2, 'URGENT': 3}

EXPLICIT_HELP_RULE = 'SAF-L3-EXPLICIT-HELP'

SAFETY_CONTACTS = [
    {'id': 'emergency', 'label': 'Immediate emergency', 'action': 'call 112', 'number': '112', 'tel': '112',
     'when': 'If you are in immediate danger or your life is at risk.'},
    {'id': 'paivystysapu', 'label': 'Urgent health problem', 'action': 'Medical Helpline 116117', 'number': '116117',
     'tel': '116117', 'when': 'Urgent health advice and guidance to the right place of care.'},
    {'id': 'mieli', 'label': 'MIELI Crisis Helpline', 'action': '09 2525 0111', 'number': '09 2525 0111', 'tel': '0925250111',
     'when': 'Someone to talk to in a crisis.'},
]

SAFETY_SCREEN = {
    'title': 'Do you need help right now?',
    'notEmergency': 'Mieliluotsi is not an emergency service, and this conversation is not monitored all the time.',
    'intro': 'If you are in danger or need help right away, contact one of these directly:',
    'demoNote': 'Demo: a synthetic alert was created in the professional\'s work queue. Mieliluotsi has not contacted the emergency '
                'response centre or any other service.',
    'dismiss': 'I have read the information – back to Mieliluotsi',
}

SAFETY_REPLY = ('I want to make sure you get help right away. Mieliluotsi is not an emergency service, and this conversation is '
                'not monitored all the time. In an immediate emergency, call 112. For an urgent health problem, call the Medical '
                'Helpline 116117. MIELI Crisis Helpline 09 2525 0111.')

LEVEL2_CLIENT_TEXT = ('Thank you for telling me. I asked a professional to look at your situation. This observation is waiting '
                      'for a professional review. If you need help right away, call 112 or the Medical Helpline 116117.')


@dataclass
class SafetyResult:
    deterministic_level: int
    ai_hint: Optional[str]
    ai_level: int
    final_level: int
    triggers: list[SafetyTrigger] = field(default_factory=list)

    @property
    def label(self) -> str:
        return LEVEL_LABELS[self.final_level]


def normalize(text: str) -> str:
    """Lower case, strip diacritics (ä → a, ö → o, å → a) and punctuation, collapse whitespace."""
    decomposed = unicodedata.normalize('NFKD', text.lower())
    ascii_text = ''.join(ch for ch in decomposed if not unicodedata.combining(ch))
    ascii_text = re.sub(r"[^a-z0-9' -]+", ' ', ascii_text)
    return re.sub(r'\s+', ' ', ascii_text).strip()


@lru_cache(maxsize=4)
def _compiled(version: str) -> list[tuple[dict, list[re.Pattern]]]:
    rules = content.safety_rules()
    return [(rule, [re.compile(pattern) for pattern in rule['patterns']]) for rule in rules['phraseRules']]


def evaluate_text(text: Optional[str]) -> list[SafetyTrigger]:
    """Phrase rules. The trigger stores the rule and category, never the client's full text."""
    if not text or not text.strip():
        return []
    normalized = normalize(text)
    triggers: list[SafetyTrigger] = []
    for rule, patterns in _compiled(content.safety_rules()['version']):
        if any(pattern.search(normalized) for pattern in patterns):
            triggers.append(SafetyTrigger(source='phrase_rule', ruleId=rule['id'], level=int(rule['level']),
                                          category=rule['category'], detail='Recognised phrase in the text'))
    return triggers


def evaluate_structured(*, mood: Optional[int] = None) -> list[SafetyTrigger]:
    floor = content.safety_rules()['structured']['moodFloor']
    if mood is not None and mood <= int(floor['threshold']):
        return [SafetyTrigger(source='structured_answer', ruleId=floor['ruleId'], level=int(floor['level']),
                              category='Very low wellbeing', detail=f'Wellbeing {mood}/5')]
    return []


def explicit_help_trigger() -> SafetyTrigger:
    return SafetyTrigger(source='explicit_action', ruleId=EXPLICIT_HELP_RULE, level=3, category='Client asked for help now',
                         detail='Button "I need help now"')


def assess(triggers: list[SafetyTrigger], ai_hint: Optional[str] = None,
           ai_next_action: Optional[str] = None) -> SafetyResult:
    """Combine deterministic triggers with the optional model hint. The model can only raise the level."""
    deterministic = max((t.level for t in triggers if t.source != 'ai_hint'), default=0)
    ai_level = AI_HINT_LEVELS.get((ai_hint or 'NONE').upper(), 0)
    if ai_next_action == 'SAFETY_FLOW':
        ai_level = max(ai_level, 3)
    final = max(deterministic, ai_level)
    all_triggers = [t for t in triggers if t.source != 'ai_hint']
    if ai_level > 0:
        all_triggers.append(SafetyTrigger(source='ai_hint', ruleId='AI-HINT', level=ai_level,
                                          category='Additional signal from the language model (advisory)',
                                          detail=f'safetyHint={ai_hint or "NONE"}, suggestedNextAction={ai_next_action or "NONE"}'))
    return SafetyResult(deterministic_level=deterministic, ai_hint=ai_hint, ai_level=ai_level, final_level=final,
                        triggers=all_triggers)
