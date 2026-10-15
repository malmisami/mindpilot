"""Guided practice in the chat: the conversational check-in and cognitive behavioural (CBT) self-help tools.

Rules decide everything: which tools the client may use (the waiting-list protocol, the therapist's configuration or the
aftercare plan), the steps and their order, what counts as an answer, which thinking traps are proposed (phrase rules in
data/valituki/cbt.json) and what is stored. A language model may only phrase the reflection and the next question and
propose examples – validated by the output guard – and the client decides what to keep. Every free-text answer passes
the deterministic Safety Engine first; a level-3 signal interrupts the tool before anything else happens.

Tools: checkin · thought_record ("Exploring a thought") · experiment ("Behavioural experiment") + experiment_review ·
exposure ("Exposure ladder") + exposure_attempt. Results: CheckIn, ThoughtRecord, Experiment, ExposureLadder and
PracticeTask ("Tasks"). Journal entries are private unless the client shares an entry with their therapist.

Typed answers are understood in English and in Finnish: scale numbers ("8/10", "eight", "kahdeksan"), option labels and
their Finnish names, weekdays and the avoidance and thinking-trap phrase rules.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from statistics import mean
from typing import Any, Optional

from app.valituki import activities, content, journey, records, therapy
from app.valituki.labels import DOMAINS, MOOD_SCALE, PRACTICE_KINDS, fmt_slot, join_fi
from app.valituki.models import (
    ChatMessage,
    ChatOption,
    ChatWidget,
    ClientProfile,
    Experiment,
    ExposureAttempt,
    ExposureLadder,
    ExposureStep,
    GuidedSession,
    PracticeTask,
    ThoughtRecord,
    ValitukiState,
)
from app.valituki.safety import SAFETY_REPLY, assess, evaluate_text, normalize
from app.valituki.store import add_days, days_between, next_id, now

AGENT = 'SupportAgent'
CBT_TOOLS = ('thought_record', 'experiment', 'exposure')
PARENT = {'experiment_review': 'experiment', 'exposure_attempt': 'exposure'}
AVOIDANCE_WORDS = (r'(valt|jatin|jain pois|siir(ra|si|ta|re)|puolestani|perun|perua|lykka|en mennyt|jatan|en uskalla'
                   r"|\bavoid|\bput(ting)? (it |this |things |the [a-z]+ )?off\b|\bputs? off\b|postpon|procrastinat|\bdelay"
                   r"|\bcancel|\bcall(ed|ing)? (it )?off\b|\bskip(ped|ping)?\b|\bstay(ed|ing)? away\b|\bdidn ?'?t go\b"
                   r"|\b(don|didn) ?'?t dare\b|\btoo (scared|afraid) to\b|\bon my behalf\b|\binstead of me\b"
                   r"|\b(present|speak|do it|talk) for me\b|\bget out of\b|\bback(ed|ing)? out\b|\bpretend(ed)? to be (ill|sick)\b)")
MAX_TEXT = 600


class PracticeError(ValueError):
    """The practice action is not possible (HTTP 409)."""


# --- content -----------------------------------------------------------------------------------------------------------

def _cbt() -> dict[str, Any]:
    return content.cbt()


def flow(tool: str) -> dict[str, Any]:
    flows = _cbt()['flows']
    if tool not in flows:
        raise PracticeError('Unknown exercise.')
    return flows[tool]


def title(tool: str) -> str:
    return flow(tool)['title']


def text(key: str, **values: Any) -> str:
    return _fill(_cbt()['texts'][key], values)


def trap_catalog() -> list[dict[str, str]]:
    return [{'id': t['id'], 'label': t['label'], 'description': t['description']} for t in _cbt()['traps']]


def trap_label(trap_id: str) -> str:
    return next((t['label'] for t in _cbt()['traps'] if t['id'] == trap_id), trap_id)


def emotion_label(value: str) -> str:
    return next((e['label'] for e in _cbt()['emotions'] if e['value'] == value), value)


def emotions_text(values: list[str]) -> str:
    """'Anxiety and nervousness' – the first emotion capitalised, the rest in running text."""
    labels = [emotion_label(v) for v in values]
    return join_fi(labels[:1] + [label[:1].lower() + label[1:] for label in labels[1:]])


def detect_traps(thought: str) -> list[str]:
    """Phrase rules (data/valituki/cbt.json) → the thinking traps Mieliluotsi proposes. The client decides."""
    normalized = normalize(thought or '')
    found = [t['id'] for t in _cbt()['traps'] if any(re.search(p, normalized) for p in t['patterns'])]
    return found[:2]


def alternative_examples(traps: list[str]) -> list[str]:
    by_id = {t['id']: t['alternative'] for t in _cbt()['traps']}
    examples = [by_id[t] for t in traps if t in by_id][:2]
    return examples or ["This situation is hard for me, but I've got through hard situations before."]


def ladder_template(goal: str) -> dict[str, Any]:
    normalized = normalize(goal or '')
    templates = _cbt()['ladderTemplates']
    return next((t for t in templates if t['match'] and any(re.search(m, normalized) for m in t['match'])),
                next(t for t in templates if t['id'] == 'generic'))


def _fill(template: str, values: dict[str, Any]) -> str:
    return re.sub(r'\{(\w+)\}', lambda m: str(values.get(m.group(1), '') or ''), template)


def short(value: Any, limit: int = 60) -> str:
    text_value = str(value or '').strip().rstrip('.')
    return text_value if len(text_value) <= limit else text_value[:limit - 1].rstrip() + '…'


def _count(number: int, word: str) -> str:
    """'1 time', '3 times', '2 check-ins'."""
    return f'{number} {word}' + ('' if number == 1 else 's')


def _in_sentence(label: str) -> str:
    """A due label inside a sentence: 'today', 'tomorrow', 'overdue · Tue 14 Oct' (a weekday keeps its capital)."""
    first = label.split(' ', 1)[0]
    return label[:1].lower() + label[1:] if first in ('Today', 'Tomorrow', 'Overdue') else label


# --- permissions ---------------------------------------------------------------------------------------------------------

def _aftercare(state: ValitukiState, client_id: str):
    items = [p for p in state.aftercarePlans if p.clientId == client_id and p.active]
    return items[-1] if items else None


def tool_allowed(state: ValitukiState, client: ClientProfile, tool: str, *, continuation: bool = False) -> tuple[bool, str]:
    """Whether the client may use a tool now – and in plain words why not. Review steps of agreed tasks may always finish."""
    if client.journeyState not in journey.ACTIVE_STATES:
        return False, 'The exercises are available once you have started using Mieliluotsi.'
    if client.safetyLock and not client.safetyLock.dismissedAt:
        return False, 'The safety instructions are showing – please acknowledge them first.'
    if tool == 'checkin':
        return True, ''
    base = PARENT.get(tool, tool)
    meta = content.cbt_tool(base)
    if meta is None:
        return False, 'Unknown exercise.'
    if continuation and tool in PARENT:
        return True, ''
    blocked = set(meta.get('avoidWhen', [])) & activities.situation(state, client)
    if 'elevated_distress' in blocked:
        return False, 'Not right now: you have been under more strain than usual. Come back to this later or with your therapist.'
    if blocked:
        return False, 'Not right now.'
    if client.mode == 'therapy_support':
        config = therapy.active_config(state, client.id)
        if config is None:
            return False, 'Your therapist decides which exercises are used in Mieliluotsi between sessions.'
        if base not in config.allowedTools:
            return False, 'Your therapist has not allowed this in Mieliluotsi – go through it in your sessions.'
    if client.mode == 'aftercare_support':
        plan = _aftercare(state, client.id)
        if plan and plan.allowedTools and base not in plan.allowedTools:
            return False, 'Not part of your maintenance plan.'
    return True, ''


def allowed_tools(state: ValitukiState, client: ClientProfile) -> list[str]:
    return [t for t in ('checkin',) + CBT_TOOLS if tool_allowed(state, client, t)[0]]


# --- chat messages -------------------------------------------------------------------------------------------------------

def say(state: ValitukiState, client: ClientProfile, text_value: str, *, role: str = 'assistant', **fields: Any) -> ChatMessage:
    fields.setdefault('textSource', 'demo' if role == 'assistant' else 'client')
    message = ChatMessage(id=next_id(state, 'msg'), clientId=client.id, role=role, text=text_value, createdAt=now(state),
                          retained=client.consent.storeHistory, **fields)
    state.chat.append(message)
    return message


def offer(state: ValitukiState, client: ClientProfile, text_value: str, options: list[tuple[str, str]], *, group: str,
          data: Optional[dict[str, Any]] = None, source: str = 'demo') -> ChatMessage:
    """A Mieliluotsi message with buttons. A newer offer of the same group supersedes an older one."""
    for message in state.chat:
        if message.clientId == client.id and message.kind == 'offer' and not message.answered and \
                message.widget and message.widget.data.get('group') == group:
            message.answered = True
    widget = ChatWidget(type='offer', options=[ChatOption(value=v, label=label) for v, label in options],
                        data={**(data or {}), 'group': group})
    return say(state, client, text_value, kind='offer', widget=widget, textSource=source)


def close_offers(state: ValitukiState, client: ClientProfile, *, group: Optional[str] = None, task_id: Optional[str] = None) -> None:
    for message in state.chat:
        if message.clientId != client.id or message.kind != 'offer' or message.answered or not message.widget:
            continue
        data = message.widget.data
        if (group and data.get('group') == group) or (task_id and data.get('taskId') == task_id):
            message.answered = True


# --- sessions ------------------------------------------------------------------------------------------------------------

def active_session(state: ValitukiState, client_id: str) -> Optional[GuidedSession]:
    return next((s for s in reversed(state.guidedSessions) if s.clientId == client_id and s.status == 'active'), None)


def _steps(session: GuidedSession) -> list[dict[str, Any]]:
    steps = []
    for step in flow(session.tool)['steps']:
        condition = step.get('when')
        if condition == 'track' and not session.context.get('track'):
            continue
        if condition == 'continue' and session.answers.get('next') not in ('repeat', 'next'):
            continue
        steps.append(step)
    return steps


def _current(session: GuidedSession) -> Optional[dict[str, Any]]:
    return next((step for step in _steps(session) if step['key'] not in session.answers), None)


def _close(state: ValitukiState, session: GuidedSession, status: str) -> None:
    session.status = status  # type: ignore[assignment]
    session.endedAt = now(state)
    session.updatedAt = session.endedAt
    session.step = None


def _placeholders(session: GuidedSession) -> dict[str, Any]:
    answers, ctx = session.answers, session.context
    return {'thought_short': short(answers.get('thought'), 70), 'situation_short': short(answers.get('situation'), 70),
            'plan_short': short(ctx.get('plan') or answers.get('plan'), 70), 'step_text': short(ctx.get('stepText'), 80),
            'track': ctx.get('track', ''), 'prediction_short': short(answers.get('prediction'), 70)}


def _days(state: ValitukiState) -> list[ChatOption]:
    options = []
    for offset in range(7):
        day = add_days(state.currentDate, offset)
        label = 'Today' if offset == 0 else 'Tomorrow' if offset == 1 else fmt_slot(day)
        options.append(ChatOption(value=day, label=label))
    return options


def _next_step_options(state: ValitukiState, client: ClientProfile) -> list[ChatOption]:
    options = []
    if tool_allowed(state, client, 'experiment')[0]:
        options.append(ChatOption(value='experiment', label="I'll test the prediction with a behavioural experiment"))
    if tool_allowed(state, client, 'exposure')[0]:
        options.append(ChatOption(value='exposure', label="I'll practise the situation one step at a time"))
    allowed = {a.id for a in activities.allowed_library(state, client)}
    for activity_id, label in (('act-paced-breathing', 'Calm breathing 4–6 before the situation'),
                               ('act-worry-time', 'Worry time in the evening')):
        if activity_id in allowed:
            options.append(ChatOption(value=f'activity:{activity_id}', label=label))
            break
    options.append(ChatOption(value='none', label="That's enough for now"))
    return options


def _scale5_options(scale: str) -> list[ChatOption]:
    words = MOOD_SCALE if scale == 'mood' else {int(k): v for k, v in _cbt()['scales'][scale].items()}
    return [ChatOption(value=str(n), label=words[n]) for n in range(1, 6)]


def _widget(state: ValitukiState, client: ClientProfile, session: GuidedSession, step: dict[str, Any],
            proposals: dict[str, Any]) -> ChatWidget:
    kind = step['widget']
    widget = ChatWidget(type=kind, skippable=bool(step.get('skippable')), skipLabel=step.get('skipLabel', ''),
                        placeholder=step.get('placeholder', ''))
    if kind == 'scale':
        widget.min, widget.max = int(step.get('min', 0)), int(step.get('max', 10))
        widget.minLabel, widget.maxLabel = step.get('minLabel', ''), step.get('maxLabel', '')
    elif kind == 'scale5':
        widget.options = _scale5_options(step.get('scale', 'mood'))
        widget.min, widget.max = 1, 5
    elif kind == 'multi':
        if step.get('options') == 'emotions':
            widget.options = [ChatOption(value=e['value'], label=e['label']) for e in _cbt()['emotions']]
        else:
            widget.options = [ChatOption(value=k, label=v) for k, v in DOMAINS.items() if k != 'anxiety']
    elif kind == 'traps':
        widget.options = [ChatOption(value=t['id'], label=t['label'], hint=t['description']) for t in trap_catalog()]
        widget.suggested = list(proposals.get('suggestedTraps') or [])
        widget.suggestedSource = proposals.get('source')
    elif kind == 'text':
        if step.get('examples'):
            widget.examples = list(proposals.get('examples') or [])
            widget.examplesSource = proposals.get('source')
    elif kind == 'ladder':
        widget.steps = [dict(s) for s in proposals.get('ladder') or []]
        widget.suggestedSource = proposals.get('source')
    elif kind == 'choices':
        source = step.get('options')
        if source == 'next_steps':
            widget.options = _next_step_options(state, client)
        elif source == 'days':
            widget.options = _days(state)
        elif source == 'ladder_steps':
            widget.options = [ChatOption(value=str(i), label=f'{s["text"]} ({s["expected"]}/10)')
                              for i, s in enumerate(session.answers.get('ladder') or [])]
        elif source == 'attempt_next':
            options = [ChatOption(value='repeat', label="I'll repeat the same step")]
            if session.context.get('nextStepText'):
                upcoming = short(session.context['nextStepText'], 50)
                options.append(ChatOption(value='next', label=f"I'll move on to the next one: {upcoming}"))
            options.append(ChatOption(value='pause', label="I'll think about it"))
            widget.options = options
    return widget


def _proposals(state: ValitukiState, client: ClientProfile, session: GuidedSession, step: dict[str, Any]) -> dict[str, Any]:
    """Rule-based proposals for the step (thinking traps, example thoughts, ladder steps) – the demo/fallback answer."""
    answers = session.answers
    result: dict[str, Any] = {}
    if step['widget'] == 'traps':
        result['suggestedTraps'] = detect_traps(answers.get('thought', ''))
    if step.get('examples') == 'alternatives':
        chosen = [t for t in answers.get('traps') or [] if t] or detect_traps(answers.get('thought', ''))
        result['examples'] = alternative_examples(chosen)
    if step.get('examples') == 'experiment_plans':
        result['examples'] = ladder_template(f'{answers.get("prediction", "")} {session.context.get("situation", "")}')[
            'experimentPlans'][:2]
    if step['widget'] == 'ladder':
        result['ladder'] = [dict(s) for s in ladder_template(answers.get('goal', ''))['steps']]
    return result


def _ask(state: ValitukiState, client: ClientProfile, session: GuidedSession, provider, *, previous_key: Optional[str] = None,
         previous_value: Any = None, actor: str = '') -> None:
    step = _current(session)
    if step is None:
        _finish(state, client, session, provider, actor)
        return
    session.step = step['key']
    proposals = _proposals(state, client, session, step)
    question = _fill(step['question'], _placeholders(session))
    ctx = {
        'tool': session.tool, 'toolTitle': title(session.tool), 'stepKey': step['key'], 'question': question,
        'approvedQuestion': question, 'previousKey': previous_key, 'previousAnswer': _display_value(previous_key, previous_value),
        'previousValue': previous_value, 'answers': _public_answers(session), 'firstName': client.firstName,
        'communicationStyle': client.communicationStyle, 'goal': session.answers.get('goal'),
        'suggestedTraps': proposals.get('suggestedTraps'), 'examples': proposals.get('examples'), 'ladder': proposals.get('ladder'),
        'trapCatalog': trap_catalog(), 'wantTraps': step['widget'] == 'traps', 'wantExamples': step.get('examples') == 'alternatives',
        'wantLadder': step['widget'] == 'ladder',
    }
    turn = provider.generate_guided_turn(ctx)
    if turn.safetyHint and turn.safetyHint != 'NONE':
        result = assess([], ai_hint=turn.safetyHint)
        if result.final_level >= 1:
            from app.valituki.agents import safety_agent

            safety_agent.raise_safety(state, client, result, context='practice', actor=records.agent_actor(AGENT))
        if result.final_level >= 3:
            _close(state, session, 'stopped')
            session.answers = {}
            say(state, client, SAFETY_REPLY, safetyLevel=3, textSource='fixed', sessionId=session.id)
            return
    proposals = {'suggestedTraps': turn.suggestedTraps, 'examples': turn.examples, 'ladder': turn.ladder, 'source': turn.source}
    if turn.reflection:
        say(state, client, turn.reflection, kind='text', textSource=turn.source, sessionId=session.id)
    say(state, client, turn.question, kind='question', textSource=turn.source, sessionId=session.id, stepKey=step['key'],
        widget=_widget(state, client, session, step, proposals))


def _public_answers(session: GuidedSession) -> dict[str, Any]:
    return {k: v for k, v in session.answers.items() if v not in (None, '', [])}


def start(state: ValitukiState, client: ClientProfile, tool: str, provider, actor: str, *,
          prefill: Optional[dict[str, Any]] = None, context: Optional[dict[str, Any]] = None, started_from: str = 'chat',
          intro: Optional[str] = None, at: Optional[str] = None) -> GuidedSession:
    context = dict(context or {})
    allowed, reason = tool_allowed(state, client, tool, continuation=bool(context.get('taskId')))
    if not allowed:
        raise PracticeError(reason)
    stamp = now(state, at)
    current = active_session(state, client.id)
    if current:
        if current.tool == tool and not prefill and not context:
            return current
        _close(state, current, 'stopped')
        current.answers = {}
        if current.tool != 'checkin':
            say(state, client, 'The unfinished exercise was interrupted and was not saved.', kind='notice')
    if tool == 'checkin' and client.mode == 'therapy_support':
        config = therapy.active_config(state, client.id)
        if config:
            context['track'] = config.track
    answers = {k: v for k, v in (prefill or {}).items() if v not in (None, '', [])}
    session = GuidedSession(id=next_id(state, 'gs'), clientId=client.id, tool=tool, status='active', answers=answers,
                            context=context, startedFrom=started_from, mode=client.mode, createdAt=stamp, updatedAt=stamp,
                            createdBy=actor, source='agent' if actor.startswith('agent') else 'client')
    state.guidedSessions.append(session)
    intro_text = intro if intro is not None else flow(tool).get('intro')
    if intro_text:
        say(state, client, intro_text, sessionId=session.id)
    if tool in CBT_TOOLS:
        records.act(state, agent=AGENT, type='start_practice', client_id=client.id, visibility='private',
                    title=f'Started a guided exercise: {title(tool)}',
                    detail='Rules guide the steps of the exercise. You can skip questions or stop at any time.')
    _ask(state, client, session, provider, actor=actor)
    return session


def _require_active(state: ValitukiState, client: ClientProfile, session_id: Optional[str]) -> GuidedSession:
    session = active_session(state, client.id)
    if session is None or (session_id and session.id != session_id):
        raise PracticeError('This exercise is no longer in progress.')
    return session


def answer(state: ValitukiState, client: ClientProfile, value: Any, provider, actor: str, *, session_id: Optional[str] = None,
           step_key: Optional[str] = None, skip: bool = False, from_text: bool = False, at: Optional[str] = None) -> dict[str, Any]:
    session = _require_active(state, client, session_id)
    step = _current(session)
    if step is None:
        raise PracticeError('The exercise is already finished.')
    if step_key and step['key'] != step_key:
        raise PracticeError('This question has already been answered.')
    now(state, at)
    if skip:
        if not step.get('skippable'):
            raise PracticeError('This question needs an answer.')
        parsed, display = None, step.get('skipLabel') or "I'll skip this"
    else:
        parsed, display = _parse(state, client, session, step, value, from_text=from_text)
    free_text = ' '.join(_texts_of(parsed))
    result = assess(evaluate_text(free_text)) if free_text else assess([])
    say(state, client, display, role='client', kind='skip' if skip else 'answer', sessionId=session.id, stepKey=step['key'],
        value=parsed)
    if result.final_level >= 3:
        from app.valituki.agents import safety_agent

        safety_agent.raise_safety(state, client, result, context='practice', actor=actor)
        _close(state, session, 'stopped')
        session.answers = {}
        say(state, client, SAFETY_REPLY, safetyLevel=3, textSource='fixed', sessionId=session.id)
        records.audit(state, actor=records.agent_actor('SafetyAgent'), action='practice_safety_interrupt', client_id=client.id,
                      detail='A deterministic rule triggered level 3 during an exercise – the exercise was interrupted and no '
                             'language model was called.')
        return {'safety': {'level': 3}, 'sessionId': session.id, 'status': session.status}
    session.answers[step['key']] = parsed
    session.updatedAt = now(state)
    if result.final_level >= 1:
        from app.valituki.agents import safety_agent

        safety_agent.raise_safety(state, client, result, context='practice', actor=actor)
    _ask(state, client, session, provider, previous_key=step['key'], previous_value=parsed, actor=actor)
    return {'safety': {'level': result.final_level}, 'sessionId': session.id, 'status': session.status}


def reask(state: ValitukiState, client: ClientProfile) -> None:
    """A free-text message that does not answer the current choice/scale question: remind how to answer."""
    session = active_session(state, client.id)
    if session is None:
        return
    say(state, client, text('reask'), sessionId=session.id, kind='text', textSource='fixed')


def stop(state: ValitukiState, client: ClientProfile, actor: str, session_id: Optional[str] = None) -> None:
    session = _require_active(state, client, session_id)
    _close(state, session, 'stopped')
    session.answers = {}
    say(state, client, 'All right. You can do the check-in later.' if session.tool == 'checkin' else text('stopped'), kind='notice',
        sessionId=session.id)
    records.audit(state, actor=actor, action='practice_stopped', client_id=client.id,
                  detail=f'Exercise stopped: {title(session.tool)}')


def expire_checkin(state: ValitukiState, client: ClientProfile) -> None:
    session = active_session(state, client.id)
    if session and session.tool == 'checkin':
        _close(state, session, 'expired')


# --- answers -------------------------------------------------------------------------------------------------------------

def _texts_of(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item['text'] if isinstance(item, dict) else item for item in value if isinstance(item, (str, dict))]
    return []


# Typed answers are understood in English and in Finnish (the labels are English). Phrase rules run on normalised text.
NUMBER_WORDS = {'zero': 0, 'nolla': 0, 'one': 1, 'yksi': 1, 'two': 2, 'kaksi': 2, 'three': 3, 'kolme': 3, 'four': 4, 'nelja': 4,
                'five': 5, 'viisi': 5, 'six': 6, 'kuusi': 6, 'seven': 7, 'seitseman': 7, 'eight': 8, 'kahdeksan': 8,
                'nine': 9, 'yhdeksan': 9, 'ten': 10, 'kymmenen': 10}
NUMBER_RULE = re.compile(r'\b(' + '|'.join(NUMBER_WORDS) + r')\b')
# The Finnish 1–5 scale words: normalised answer → number.
SCALE5_FI = {
    'mood': {'tosi huonosti': 1, 'huonosti': 2, 'kohtalaisesti': 3, 'ihan ok': 3, 'hyvin': 4, 'tosi hyvin': 5},
    'anxiety': {'ei lainkaan': 1, 'ei yhtaan': 1, 'vahan': 2, 'jonkin verran': 3, 'paljon': 4, 'hyvin paljon': 5},
}
SCALE5_FI['track'] = SCALE5_FI['anxiety']
WEEKDAY_RULES = (r'maanantai\w*|monday|mon', r'tiistai\w*|tuesday|tues?', r'keskiviikko\w*|wednesday|wed',
                 r'torstai\w*|thursday|thu|thurs', r'perjantai\w*|friday|fri', r'lauantai\w*|saturday|sat',
                 r'sunnuntai\w*|sunday|sun')
# Answers to the button questions in Finnish or in free-form English: (phrase rule, option value or label).
TYPED_CHOICES: dict[str, tuple[tuple[str, str], ...]] = {
    'days': ((r'\b(tanaan|today|tonight|this evening)\b', 'Today'), (r'\b(huomenna|tomorrow)\b', 'Tomorrow')),
    'attempt_next': ((r'\b(toista\w*|uudelleen|uudestaan|repeat|again|same)\b', 'repeat'),
                     (r'\b(seuraava\w*|next|move on)\b', 'next'),
                     (r'\b(mietin|myohemmin|ei viela|think|not yet|later|pause|wait)\b', 'pause')),
    'next_steps': ((r'\b(koe|kokee\w*|ennuste\w*|experiment|test|prediction)\b', 'experiment'),
                   (r'\b(hengit\w*|breath\w*)\b', 'activity:act-paced-breathing'),
                   (r'\b(huoli\w*|worry|worries)\b', 'activity:act-worry-time'),
                   (r'\b(askel\w*|porra\w*|portaa\w*|harjoittel\w*|step|steps|ladder|exposure|practi[sc]e)\b', 'exposure'),
                   (r'\b(riittaa|ei mitaan|ei kiitos|ei nyt|enough|nothing|no thanks|not now|none)\b', 'none')),
    'domains': ((r'\b(uni|unet|nukku\w*|sleep\w*)\b', 'sleep'), (r'\b(jaksami\w*|vasymy\w*|energy|tired\w*)\b', 'energy'),
                (r'\b(tyo\w*|work\w*|job)\b', 'work'), (r'\b(sosiaali\w*|ihmissuht\w*|ystav\w*|social|friends)\b', 'social')),
}


def _int_in(text_value: Any, low: int, high: int) -> Optional[int]:
    if isinstance(text_value, bool):
        return None
    if isinstance(text_value, (int, float)):
        number = int(text_value)
    else:
        match = re.search(r'-?\d+', str(text_value or ''))
        if match:
            number = int(match.group())
        else:
            # A number in words ("eight", "kahdeksan") counts only in a short answer, not inside a longer message.
            normalized = normalize(str(text_value or ''))
            word = NUMBER_RULE.search(normalized) if len(normalized.split()) <= 5 else None
            if not word:
                return None
            number = NUMBER_WORDS[word.group(1)]
    return number if low <= number <= high else None


def _typed_rules(step: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """The phrase rules for typed answers to this step: data aliases (cbt.json) or the built-in choice rules."""
    if step['widget'] == 'traps':
        return tuple((rf'\b{re.escape(normalize(alias))}\b', t['id']) for t in _cbt()['traps'] for alias in t.get('aliases', []))
    if step.get('options') == 'emotions':
        return tuple((rf'\b{re.escape(normalize(alias))}\b', e['value']) for e in _cbt()['emotions'] for alias in e.get('aliases', []))
    return TYPED_CHOICES.get(step.get('options') or '', ())


def _match_option(options: list[ChatOption], raw: str, rules: tuple[tuple[str, str], ...] = ()) -> Optional[ChatOption]:
    wanted = normalize(raw)
    if not wanted:
        return None
    for option in options:
        if normalize(option.value) == wanted or normalize(option.label) == wanted:
            return option
    if wanted.isdigit() and 1 <= int(wanted) <= len(options):
        return options[int(wanted) - 1]
    found = next((o for o in options if wanted in normalize(o.label)), None)
    for pattern, target in rules:
        if found is None and re.search(pattern, wanted):
            goal = normalize(target)
            found = next((o for o in options if goal in (normalize(o.value), normalize(o.label))), None)
    return found


def _day_option(options: list[ChatOption], raw: str) -> Optional[ChatOption]:
    """"Friday" / "perjantaina" → the first offered day that is that weekday."""
    wanted = normalize(raw)
    weekday = next((i for i, rule in enumerate(WEEKDAY_RULES) if re.search(rf'\b({rule})\b', wanted)), None)
    if weekday is None:
        return None
    return next((o for o in options if re.fullmatch(r'\d{4}-\d\d-\d\d', o.value) and date.fromisoformat(o.value).weekday() == weekday),
                None)


def _parse(state: ValitukiState, client: ClientProfile, session: GuidedSession, step: dict[str, Any], value: Any, *,
           from_text: bool) -> tuple[Any, str]:
    kind = step['widget']
    widget = _widget(state, client, session, step, {})
    rules = _typed_rules(step)
    if kind == 'text':
        cleaned = str(value or '').strip()[:MAX_TEXT]
        if not cleaned:
            raise PracticeError('Write an answer or skip the question.')
        return cleaned, cleaned
    if kind == 'scale':
        number = _int_in(value, widget.min, widget.max)
        if number is None:
            raise PracticeError(f'Choose a number {widget.min}–{widget.max}.')
        return number, f'{number}/{widget.max}'
    if kind == 'scale5':
        number = _int_in(value, 1, 5)
        if number is None and isinstance(value, str):
            number = SCALE5_FI.get(step.get('scale', 'mood'), {}).get(normalize(value))
        if number is None and isinstance(value, str):
            option = _match_option(widget.options, value)
            number = int(option.value) if option else None
        if number is None:
            raise PracticeError('Choose an option 1–5.')
        return number, f'{number}/5 · {widget.options[number - 1].label}'
    if kind == 'choices':
        option = _match_option(widget.options, str(value or ''), rules)
        if option is None and step.get('options') == 'days':
            option = _day_option(widget.options, str(value or ''))
        if option is None:
            raise PracticeError('Choose one of the options.')
        return option.value, option.label
    if kind in ('multi', 'traps'):
        raw = value if isinstance(value, list) else [
            part for part in re.split(r',|;|\n|\b(?:ja|and)\b', str(value or ''), flags=re.IGNORECASE) if part.strip()]
        chosen: list[str] = []
        for item in raw:
            option = _match_option(widget.options, str(item), rules)
            if option and option.value not in chosen:
                chosen.append(option.value)
            elif kind == 'multi' and step.get('options') == 'emotions' and str(item).strip():
                chosen.append(str(item).strip()[:40])  # an emotion in the client's own words
        if not chosen:
            raise PracticeError('Choose at least one option or skip the question.')
        labels = {o.value: o.label for o in widget.options}
        return chosen, ', '.join(labels.get(c, c) for c in chosen)
    if kind == 'ladder':
        if from_text or not isinstance(value, list):
            raise PracticeError('Edit the ladder and save it.')
        steps = []
        for item in value[:8]:
            step_text = str((item or {}).get('text', '')).strip()[:140]
            expected = _int_in((item or {}).get('expected'), 0, 10)
            if step_text and expected is not None:
                steps.append({'text': step_text, 'expected': expected})
        if len(steps) < 2:
            raise PracticeError('The ladder needs at least two steps.')
        return steps, f'Ladder: {len(steps)} steps'
    raise PracticeError('Unknown answer type.')


def _display_value(key: Optional[str], value: Any) -> Any:
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return [f'{v["text"]} ({v["expected"]}/10)' for v in value]
    return value


def expects_text(state: ValitukiState, client: ClientProfile) -> bool:
    session = active_session(state, client.id)
    step = _current(session) if session else None
    return bool(step and step['widget'] == 'text')


# --- demo phrasing (DEMO_AI_MODE and the fallback for model texts) -------------------------------------------------------

def demo_reflection(ctx: dict[str, Any]) -> str:
    """A short, warm reflection of the previous answer, like a therapist in a chat: a sentence or two (the chat shows each
    sentence as its own bubble). It validates the feeling without agreeing that a feared outcome will happen."""
    key, value, answers = ctx.get('previousKey'), ctx.get('previousValue'), ctx.get('answers') or {}
    tool = ctx.get('tool')
    if key is None or value in (None, '', []) or tool == 'checkin':
        return ''
    if key == 'situation':
        return "Thank you for telling me. Let's go through the situation calmly."
    if key == 'thought':
        return 'Thank you for sharing that. A thought like that can feel very true when a situation makes you nervous.'
    if key == 'emotions':
        named = 'them' if len(value) > 1 else 'it'
        return (f'{emotions_text(value)} – thank you for naming {named}. '
                'Just naming a feeling often helps you step back from it a little.')
    if key in ('intensityBefore', 'goalAnxiety'):
        number = int(value)
        if key == 'goalAnxiety':
            return (f"{number}/10 is a lot. That's why the ladder starts from something clearly easier." if number >= 5
                    else f'{number}/10 – a good starting point.')
        if number >= 7:
            return f"{number}/10 is a strong feeling. It's good that you're pausing with it."
        return f'{number}/10 – the feeling is clearly there.' if number >= 4 else f'{number}/10 – thank you for rating it.'
    if key == 'behaviour':
        if re.search(AVOIDANCE_WORDS, normalize(str(value))):
            return ("That's very understandable – avoiding brings relief for a moment. "
                    'In the longer run, though, it can keep the nervousness going.')
        return 'Thank you for telling me that too.'
    if key == 'traps':
        return "Well spotted! Once you recognise a thinking trap, it's easier to loosen its grip."
    if key == 'evidenceFor':
        return "I understand why the thought feels true. Let's now look at it from another direction too."
    if key == 'evidenceAgainst':
        return "That's a kind and wise answer. We can often tell a friend exactly what we would need to hear ourselves."
    if key == 'alternative':
        return "That's a great thought! It won't take the nervousness away completely, but it can make it easier to bear."
    if key == 'intensityAfter':
        before = answers.get('intensityBefore')
        if isinstance(before, int) and value < before:
            return f'The feeling eased from {before}/10 to {value}/10. Even pausing for a moment can lighten how you feel.'
        if isinstance(before, int) and value == before:
            return f"The feeling stayed at {value}/10 – that's common too. A new thought often grows stronger with practice."
        return f'The feeling is now {value}/10. Thank you for trying.'
    if key == 'prediction':
        return "Thank you. Let's write the prediction down so you can later compare it with what really happened."
    if key == 'beliefBefore':
        return f'Right now you believe the prediction {value}/10.'
    if key == 'plan':
        return 'A good experiment – small and concrete.'
    if key == 'outcome':
        return 'Thank you for writing down what really happened.'
    if key == 'goal':
        return "Thank you. This will be the top step of your ladder – you don't need to go there straight away."
    if key == 'ladder':
        return f'All right – your ladder has {len(value)} steps.'
    if key == 'firstStep':
        return 'A good choice to start with.'
    if key == 'after':
        peak = answers.get('peak')
        if isinstance(peak, int) and value < peak:
            return (f'Your anxiety rose to {peak}/10 and eased to {value}/10. This is exactly how exposure works: the nervousness '
                    'eases when you stay in the situation.')
        return 'Thank you for taking the step – doing it is already practice.'
    return ''


# --- results -------------------------------------------------------------------------------------------------------------

def _summary(state: ValitukiState, client: ClientProfile, session: GuidedSession, kind: str, item_id: str, heading: str,
             rows: list[tuple[str, Any]], change: Optional[dict[str, Any]] = None) -> None:
    widget = ChatWidget(type='summary', data={
        'kind': kind, 'id': item_id, 'title': heading,
        'rows': [{'label': label, 'value': value} for label, value in rows if value not in (None, '', [])],
        'change': change})
    say(state, client, heading, kind='summary', widget=widget, sessionId=session.id)


def create_task(state: ValitukiState, client: ClientProfile, *, kind: str, title_text: str, detail: str = '',
                due: Optional[str] = None, source_id: Optional[str] = None, step_id: Optional[str] = None,
                tool: Optional[str] = None, assigned_by: str = 'client') -> PracticeTask:
    stamp = now(state)
    task = PracticeTask(id=next_id(state, 'ptask'), clientId=client.id, kind=kind, title=title_text, detail=detail,
                        dueDate=due or state.currentDate, sourceId=source_id, stepId=step_id, tool=tool, assignedBy=assigned_by,
                        mode=client.mode, createdAt=stamp, updatedAt=stamp, createdBy=assigned_by, source='practice')
    state.practiceTasks.append(task)
    return task


def _event(state: ValitukiState, client: ClientProfile, event_type: str, actor: str, payload: dict[str, Any]) -> None:
    from app.valituki.agents import orchestrator

    event = journey.apply(state, client, event_type, actor=actor, source='client', payload=payload)
    orchestrator.dispatch(state, event)


def _finish(state: ValitukiState, client: ClientProfile, session: GuidedSession, provider, actor: str) -> None:
    finishers = {'checkin': _finish_checkin, 'thought_record': _finish_thought_record, 'experiment': _finish_experiment,
                 'experiment_review': _finish_experiment_review, 'exposure': _finish_exposure,
                 'exposure_attempt': _finish_exposure_attempt}
    finishers[session.tool](state, client, session, provider, actor or records.client_actor(client.id))


def _finish_checkin(state: ValitukiState, client: ClientProfile, session: GuidedSession, provider, actor: str) -> None:
    from app.valituki import client_actions

    answers = session.answers
    changes = {domain: 'worse' for domain in answers.get('changes') or [] if domain in DOMAINS}
    anxiety = answers.get('anxiety')
    if isinstance(anxiety, int) and anxiety >= 4:
        changes['anxiety'] = 'worse'  # a high anxiety answer is what the pattern and trend rules call "anxiety worse"
    client_actions.submit_checkin(state, client, int(answers['mood']), changes, answers.get('note') or '', anxiety=anxiety,
                                  track_score=answers.get('track'), provider=provider, who=actor, via_session=session)


def _complete_linked_task(state: ValitukiState, client: ClientProfile, session: GuidedSession) -> Optional[PracticeTask]:
    task = next((t for t in state.practiceTasks if t.id == session.context.get('taskId') and t.clientId == client.id), None)
    if task and task.status == 'open':
        task.status = 'done'
        task.completedAt = now(state)
        task.updatedAt = task.completedAt
        close_offers(state, client, task_id=task.id)
    return task


def _finish_thought_record(state: ValitukiState, client: ClientProfile, session: GuidedSession, provider, actor: str) -> None:
    a = session.answers
    stamp = now(state)
    record = ThoughtRecord(
        id=next_id(state, 'tr'), clientId=client.id, sessionId=session.id, situation=a.get('situation') or '',
        thought=a.get('thought') or '', emotions=a.get('emotions') or [], intensityBefore=a.get('intensityBefore'),
        behaviour=a.get('behaviour') or '', traps=a.get('traps') or [], suggestedTraps=detect_traps(a.get('thought') or ''),
        evidenceFor=a.get('evidenceFor') or '', evidenceAgainst=a.get('evidenceAgainst') or '', alternative=a.get('alternative') or '',
        intensityAfter=a.get('intensityAfter'), nextStep=a.get('nextStep') or 'none', mode=client.mode, createdAt=stamp,
        updatedAt=stamp, createdBy=actor, source='guided_chat')
    state.thoughtRecords.append(record)
    _close(state, session, 'completed')
    session.resultId = record.id
    task = _complete_linked_task(state, client, session)
    emotions = emotions_text(record.emotions) or 'Feeling'
    _summary(state, client, session, 'thought_record', record.id, 'Thought diary', [
        ('Situation', record.situation), ('Thought', record.thought), ('Feeling', emotions), ('What I did', record.behaviour),
        ('Thinking trap', join_fi([trap_label(t) for t in record.traps])), ('Balanced thought', record.alternative)],
        change={'label': emotions, 'before': record.intensityBefore, 'after': record.intensityAfter, 'max': 10})
    _event(state, client, 'THOUGHT_RECORD_COMPLETED', actor, {'recordId': record.id, 'before': record.intensityBefore,
                                                              'after': record.intensityAfter, 'taskId': task.id if task else None})
    next_step = record.nextStep
    if next_step == 'experiment' and tool_allowed(state, client, 'experiment')[0]:
        start(state, client, 'experiment', provider, actor, prefill={'prediction': record.thought},
              context={'thoughtRecordId': record.id, 'situation': record.situation}, started_from='chain')
    elif next_step == 'exposure' and tool_allowed(state, client, 'exposure')[0]:
        # The ladder's goal is asked in the client's own short words ("Giving a presentation to the team"), not copied from
        # the situation.
        start(state, client, 'exposure', provider, actor, context={'thoughtRecordId': record.id, 'situation': record.situation},
              started_from='chain')
    elif next_step.startswith('activity:'):
        activity = content.activity(next_step.split(':', 1)[1])
        if activity:
            create_task(state, client, kind='activity', title_text=activity.title, detail='Agreed after exploring a thought.',
                        source_id=activity.id)
            say(state, client, f"I added this to your tasks: {activity.title}. You'll find the instructions on the Exercises page. "
                               + text('thought_record_done'))
    else:
        say(state, client, text('thought_record_done'))


def _finish_experiment(state: ValitukiState, client: ClientProfile, session: GuidedSession, provider, actor: str) -> None:
    a = session.answers
    stamp = now(state)
    experiment = Experiment(id=next_id(state, 'exp'), clientId=client.id, sessionId=session.id,
                            thoughtRecordId=session.context.get('thoughtRecordId'), prediction=a.get('prediction') or '',
                            beliefBefore=a.get('beliefBefore'), plan=a.get('plan') or '', plannedFor=a.get('when'),
                            mode=client.mode, createdAt=stamp, updatedAt=stamp, createdBy=actor, source='guided_chat')
    state.experiments.append(experiment)
    task = create_task(state, client, kind='experiment', title_text=f'Behavioural experiment: {short(experiment.plan, 80)}',
                       detail=f'Prediction: {short(experiment.prediction, 100)}', due=experiment.plannedFor, source_id=experiment.id)
    experiment.taskId = task.id
    _close(state, session, 'completed')
    session.resultId = experiment.id
    _summary(state, client, session, 'experiment', experiment.id, 'Behavioural experiment planned', [
        ('Prediction', experiment.prediction),
        ('Belief in the prediction', f'{experiment.beliefBefore}/10' if experiment.beliefBefore is not None else None),
        ('Experiment', experiment.plan), ('When', fmt_slot(experiment.plannedFor) if experiment.plannedFor else None)])
    _event(state, client, 'EXPERIMENT_PLANNED', actor, {'experimentId': experiment.id, 'taskId': task.id})
    say(state, client, text('experiment_done'))


def _finish_experiment_review(state: ValitukiState, client: ClientProfile, session: GuidedSession, provider, actor: str) -> None:
    a = session.answers
    experiment = next((e for e in state.experiments if e.id == session.context.get('experimentId')), None)
    if experiment is None:
        _close(state, session, 'stopped')
        return
    stamp = now(state)
    experiment.status = 'done'
    experiment.outcome = a.get('outcome') or ''
    experiment.learned = a.get('learned') or ''
    experiment.beliefAfter = a.get('beliefAfter')
    experiment.reviewedAt = stamp
    experiment.updatedAt = stamp
    _complete_linked_task(state, client, session)
    _close(state, session, 'completed')
    session.resultId = experiment.id
    _summary(state, client, session, 'experiment', experiment.id, 'Behavioural experiment result', [
        ('Prediction', experiment.prediction), ('What happened', experiment.outcome), ('What I learned', experiment.learned)],
        change={'label': 'Belief in the prediction', 'before': experiment.beliefBefore, 'after': experiment.beliefAfter, 'max': 10})
    _event(state, client, 'EXPERIMENT_REVIEWED', actor, {'experimentId': experiment.id, 'before': experiment.beliefBefore,
                                                         'after': experiment.beliefAfter})
    say(state, client, text('experiment_review_done'))


def _finish_exposure(state: ValitukiState, client: ClientProfile, session: GuidedSession, provider, actor: str) -> None:
    a = session.answers
    stamp = now(state)
    steps = [ExposureStep(id=next_id(state, 'ls'), text=s['text'], expected=int(s['expected'])) for s in a.get('ladder') or []]
    ladder = ExposureLadder(id=next_id(state, 'lad'), clientId=client.id, sessionId=session.id, goal=a.get('goal') or '',
                            goalAnxiety=a.get('goalAnxiety'), steps=steps, mode=client.mode, createdAt=stamp, updatedAt=stamp,
                            createdBy=actor, source='guided_chat')
    state.ladders.append(ladder)
    first_index = int(a.get('firstStep') or 0) if str(a.get('firstStep') or '0').isdigit() else 0
    first = steps[min(first_index, len(steps) - 1)]
    first.status = 'doing'
    task = create_task(state, client, kind='exposure_step', title_text=first.text,
                       detail=f'Exposure ladder: {short(ladder.goal, 80)} · expected nervousness {first.expected}/10', due=a.get('when'),
                       source_id=ladder.id, step_id=first.id)
    _close(state, session, 'completed')
    session.resultId = ladder.id
    _summary(state, client, session, 'exposure', ladder.id, 'Exposure ladder', [
        ('Goal', ladder.goal), ('Steps', [f'{s.text} ({s.expected}/10)' for s in steps]),
        ('First step', f'{first.text} – {fmt_slot(task.dueDate)}')])
    _event(state, client, 'EXPOSURE_LADDER_CREATED', actor, {'ladderId': ladder.id, 'taskId': task.id, 'steps': len(steps)})
    say(state, client, text('exposure_done'))


def _next_step(ladder: ExposureLadder, step: ExposureStep) -> Optional[ExposureStep]:
    later = [s for s in ladder.steps if s.status != 'done' and s.id != step.id and s.expected >= step.expected]
    return later[0] if later else next((s for s in ladder.steps if s.status != 'done' and s.id != step.id), None)


def _finish_exposure_attempt(state: ValitukiState, client: ClientProfile, session: GuidedSession, provider, actor: str) -> None:
    a = session.answers
    ladder = next((item for item in state.ladders if item.id == session.context.get('ladderId')), None)
    step = next((s for s in ladder.steps if s.id == session.context.get('stepId')), None) if ladder else None
    if ladder is None or step is None:
        _close(state, session, 'stopped')
        return
    attempt = ExposureAttempt(id=next_id(state, 'la'), date=state.currentDate, before=a.get('before'), peak=a.get('peak'),
                              after=a.get('after'), note=a.get('note') or '')
    step.attempts.append(attempt)
    step.status = 'done' if (attempt.after is not None and attempt.after <= 3) else 'doing'
    ladder.updatedAt = now(state)
    task = _complete_linked_task(state, client, session)
    _close(state, session, 'completed')
    session.resultId = ladder.id
    choice = a.get('next')
    upcoming = _next_step(ladder, step)
    follow: Optional[PracticeTask] = None
    if choice == 'next' and upcoming:
        if step.status != 'done':
            step.status = 'done'
        upcoming.status = 'doing'
        follow = create_task(state, client, kind='exposure_step', title_text=upcoming.text,
                             detail=f'Exposure ladder: {short(ladder.goal, 80)} · expected nervousness {upcoming.expected}/10',
                             due=a.get('when'), source_id=ladder.id, step_id=upcoming.id)
    elif choice == 'repeat':
        follow = create_task(state, client, kind='exposure_step', title_text=step.text,
                             detail=f'Repeat · exposure ladder: {short(ladder.goal, 80)}', due=a.get('when'), source_id=ladder.id,
                             step_id=step.id)
    if all(s.status == 'done' for s in ladder.steps):
        ladder.status = 'completed'
    _summary(state, client, session, 'exposure_attempt', ladder.id, f'Step done: {step.text}', [
        ('Ladder', ladder.goal), ('What I noticed', attempt.note),
        ('Next', f'{follow.title} – {fmt_slot(follow.dueDate)}' if follow else "You're still thinking – the ladder will wait")],
        change={'label': 'Anxiety', 'before': attempt.before, 'peak': attempt.peak, 'after': attempt.after, 'max': 10})
    _event(state, client, 'EXPOSURE_STEP_COMPLETED', actor, {'ladderId': ladder.id, 'stepId': step.id, 'before': attempt.before,
                                                             'peak': attempt.peak, 'after': attempt.after,
                                                             'taskId': task.id if task else None})
    say(state, client, text('exposure_attempt_done') + (' The whole ladder is now done – wonderful perseverance.'
                                                         if ladder.status == 'completed' else ''))


# --- tasks ---------------------------------------------------------------------------------------------------------------

def get_task(state: ValitukiState, client: ClientProfile, task_id: str) -> PracticeTask:
    task = next((t for t in state.practiceTasks if t.id == task_id and t.clientId == client.id), None)
    if task is None:
        raise PracticeError('Task not found.')
    return task


def complete_task(state: ValitukiState, client: ClientProfile, task_id: str, provider, actor: str, *,
                  started_from: str = 'task') -> dict[str, Any]:
    """"I did this" / "Tell me how it went": reviews run as a short guided conversation; simple tasks are marked done."""
    task = get_task(state, client, task_id)
    if task.status != 'open':
        raise PracticeError('This task has already been recorded.')
    if task.kind == 'exposure_step':
        ladder = next((item for item in state.ladders if item.id == task.sourceId), None)
        step = next((s for s in ladder.steps if s.id == task.stepId), None) if ladder else None
        if ladder is None or step is None:
            raise PracticeError('The ladder step was not found.')
        upcoming = _next_step(ladder, step)
        start(state, client, 'exposure_attempt', provider, actor, started_from=started_from,
              context={'taskId': task.id, 'ladderId': ladder.id, 'stepId': step.id, 'stepText': step.text,
                       'nextStepText': upcoming.text if upcoming else None})
        return {'started': 'exposure_attempt'}
    if task.kind == 'experiment':
        experiment = next((e for e in state.experiments if e.id == task.sourceId), None)
        if experiment is None:
            raise PracticeError('The experiment was not found.')
        start(state, client, 'experiment_review', provider, actor, started_from=started_from,
              context={'taskId': task.id, 'experimentId': experiment.id, 'plan': experiment.plan})
        return {'started': 'experiment_review'}
    if task.kind == 'homework' and task.tool and task.tool in CBT_TOOLS:
        start(state, client, task.tool, provider, actor, started_from=started_from, context={'taskId': task.id})
        return {'started': task.tool}
    task.status = 'done'
    task.completedAt = now(state)
    task.updatedAt = task.completedAt
    close_offers(state, client, task_id=task.id)
    if task.kind == 'activity' and task.sourceId and content.activity(task.sourceId):
        from app.valituki import client_actions

        client_actions.complete_activity(state, client, task.sourceId, None)
    _event(state, client, 'PRACTICE_TASK_COMPLETED', actor, {'taskId': task.id, 'kind': task.kind})
    return {'done': True}


def postpone_task(state: ValitukiState, client: ClientProfile, task_id: str) -> PracticeTask:
    task = get_task(state, client, task_id)
    if task.status != 'open':
        raise PracticeError('This task has already been recorded.')
    task.dueDate = add_days(max(task.dueDate or state.currentDate, state.currentDate), 1)
    task.reminderSentAt = None
    task.updatedAt = now(state)
    close_offers(state, client, task_id=task.id)
    return task


def skip_task(state: ValitukiState, client: ClientProfile, task_id: str) -> PracticeTask:
    task = get_task(state, client, task_id)
    if task.status != 'open':
        raise PracticeError('This task has already been recorded.')
    task.status = 'skipped'
    task.updatedAt = now(state)
    close_offers(state, client, task_id=task.id)
    records.act(state, agent=AGENT, type='task_skipped', client_id=client.id, visibility='private',
                title=f'You skipped a task: {task.title}',
                detail='Skipping is always allowed. You can come back to the exercise later.')
    return task


def remind_due_tasks(state: ValitukiState, client: ClientProfile, at: Optional[str] = None) -> None:
    """Daily (09:00): one chat nudge per task due today – the client can report, postpone or skip."""
    for task in [t for t in state.practiceTasks if t.clientId == client.id and t.status == 'open' and t.dueDate == state.currentDate
                 and not t.reminderSentAt]:
        task.reminderSentAt = now(state, at)
        if task.kind == 'homework':
            body = text('homework_due', title=task.title)
            options = [(f'task_done:{task.id}', 'Start now'), ('dismiss', 'Later')]
        else:
            body = text('task_due', title=task.title)
            label = 'Tell me how it went' if task.kind in ('exposure_step', 'experiment') else 'I did this'
            options = [(f'task_done:{task.id}', label), (f'task_later:{task.id}', 'Move to tomorrow'), (f'task_skip:{task.id}', 'Skip')]
        offer(state, client, body, options, group=f'task:{task.id}', data={'taskId': task.id})
        records.notify(state, audience='client', client_id=client.id, kind='practice', agent=AGENT, action_view='chat',
                       title="Today's agreed exercise", body=task.title)
        records.act(state, agent=AGENT, type='remind_task', client_id=client.id, rule_id='TASK-DUE-001', visibility='private',
                    title=f'Reminded you of an agreed exercise: {short(task.title, 70)}',
                    detail='The exercise can be done, postponed or skipped – skipping is always allowed.')


# --- offers --------------------------------------------------------------------------------------------------------------

def act_on_offer(state: ValitukiState, client: ClientProfile, message_id: str, option: str, provider, actor: str) -> dict[str, Any]:
    message = next((m for m in state.chat if m.id == message_id and m.clientId == client.id and m.kind == 'offer'), None)
    if message is None or message.widget is None:
        raise PracticeError('Message not found.')
    if message.answered:
        raise PracticeError('This has already been answered.')
    chosen = next((o for o in message.widget.options if o.value == option), None)
    if chosen is None:
        raise PracticeError('Unknown choice.')
    message.answered = True
    say(state, client, chosen.label, role='client', kind='answer', value=option)
    data = message.widget.data
    if option.startswith('start:'):
        start(state, client, option.split(':', 1)[1], provider, actor, prefill=data.get('prefill'), context=data.get('context'),
              started_from='offer')
        return {'started': option.split(':', 1)[1]}
    if option.startswith('task_done:'):
        return complete_task(state, client, option.split(':', 1)[1], provider, actor, started_from='offer')
    if option.startswith('task_later:'):
        task = postpone_task(state, client, option.split(':', 1)[1])
        say(state, client, f"Moved to {fmt_slot(task.dueDate)}. I'll remind you then.")
        return {'postponed': task.dueDate}
    if option.startswith('task_skip:'):
        skip_task(state, client, option.split(':', 1)[1])
        say(state, client, "All right, let's skip it this time. You can come back to the exercise at any time.")
        return {'skipped': True}
    say(state, client, 'All right. You can come back to this at any time.')
    return {'dismissed': True}


def offer_after_checkin(state: ValitukiState, client: ClientProfile, mood: int, anxiety: Optional[int], note: str) -> None:
    if client.safetyLock and not client.safetyLock.dismissedAt:
        return
    if not ((anxiety or 0) >= 4 or mood <= 2) or not tool_allowed(state, client, 'thought_record')[0]:
        return
    offer(state, client, text('checkin_offer'), [('start:thought_record', "Let's explore it"), ('dismiss', 'Not now')],
          group='checkin', data={'prefill': {'situation': note} if note else {}})


# --- sharing and removal -------------------------------------------------------------------------------------------------

def _collection(state: ValitukiState, kind: str) -> list:
    collections = {'thought_record': state.thoughtRecords, 'experiment': state.experiments, 'exposure': state.ladders}
    if kind not in collections:
        raise PracticeError('Unknown entry.')
    return collections[kind]


def set_shared(state: ValitukiState, client: ClientProfile, kind: str, item_id: str, shared: bool, actor: str) -> None:
    item = next((i for i in _collection(state, kind) if i.id == item_id and i.clientId == client.id), None)
    if item is None:
        raise PracticeError('Entry not found.')
    item.shared = bool(shared)
    item.updatedAt = now(state)
    records.audit(state, actor=actor, action='practice_sharing', client_id=client.id,
                  detail=f'{PRACTICE_KINDS.get(kind, kind)} {item_id}: '
                         + ('shared with the therapist' if shared else 'visible to the client only'))


def remove_item(state: ValitukiState, client: ClientProfile, kind: str, item_id: str, actor: str) -> None:
    collection = _collection(state, kind)
    item = next((i for i in collection if i.id == item_id and i.clientId == client.id), None)
    if item is None:
        raise PracticeError('Entry not found.')
    collection.remove(item)
    for task in state.practiceTasks:
        if task.clientId == client.id and task.sourceId == item_id and task.status == 'open':
            task.status = 'skipped'
    records.audit(state, actor=actor, action='practice_removed', client_id=client.id,
                  detail=f"{PRACTICE_KINDS.get(kind, kind)} removed at the client's request.")


# --- replay (seed, simulation and demo scenes run the same engine) ----------------------------------------------------------

def run_script(state: ValitukiState, client: ClientProfile, plans: dict[str, dict[str, Any]], *, actor: str,
               provider=None) -> None:
    """Answer the active session – and any tool it chains to – from scripted answers, exactly as the client would."""
    from app.valituki.ai import DemoAIProvider
    from app.valituki.store import begin_action

    provider = provider or DemoAIProvider()
    for _ in range(40):
        session = active_session(state, client.id)
        if session is None or session.tool not in plans:
            return
        step = _current(session)
        if step is None:
            return
        begin_action(state)  # each answer is a separate moment on the demo clock, as in the chat
        value = resolve_demo_value(state, client, session, step, plans[session.tool].get(step['key']))
        if value is None:
            if not step.get('skippable'):
                stop(state, client, actor, session.id)
                return
            answer(state, client, None, provider, actor, skip=True)
        else:
            answer(state, client, value, provider, actor)


def replay(state: ValitukiState, client: ClientProfile, tool: str, answers: dict[str, Any], *, actor: str,
           prefill: Optional[dict[str, Any]] = None, context: Optional[dict[str, Any]] = None, at: Optional[str] = None,
           started_from: str = 'demo', provider=None, chain: Optional[dict[str, dict[str, Any]]] = None) -> Optional[GuidedSession]:
    from app.valituki.ai import DemoAIProvider

    provider = provider or DemoAIProvider()
    if not tool_allowed(state, client, tool, continuation=bool((context or {}).get('taskId')))[0]:
        return None
    session = start(state, client, tool, provider, actor, prefill=prefill, context=context, started_from=started_from, at=at)
    run_script(state, client, {tool: answers, **(chain or {})}, actor=actor, provider=provider)
    return session


def demo_cbt(state: ValitukiState, client: ClientProfile, actor: str) -> None:
    """The live demo's CBT moment: the client writes about the coming situation → Mieliluotsi offers to look at it together →
    "Exploring a thought" → an exposure ladder with the first step as a task."""
    from app.valituki import client_actions
    from app.valituki.ai import DemoAIProvider
    from app.valituki.store import begin_action

    spec = content.client_spec(client.id).get('practiceDemo') or {}
    if not spec.get('message'):
        return
    begin_action(state)
    client_actions.send_message(state, client, spec['message'], DemoAIProvider())
    message = next((m for m in reversed(state.chat) if m.clientId == client.id and m.kind == 'offer' and not m.answered
                    and m.widget and m.widget.data.get('group') == 'chat'), None)
    if message is not None:
        begin_action(state)
        act_on_offer(state, client, message.id, 'start:thought_record', DemoAIProvider(), actor)
    run_script(state, client, {'thought_record': spec['thought_record'], 'exposure': spec['exposure']}, actor=actor)


def resolve_demo_value(state: ValitukiState, client: ClientProfile, session: GuidedSession, step: dict[str, Any], raw: Any) -> Any:
    """Demo answers may be relative ('+1' = tomorrow's option, 'template' = the proposed ladder)."""
    if raw is None:
        return None
    if step['widget'] == 'ladder' and raw == 'template':
        return [dict(s) for s in ladder_template(session.answers.get('goal', ''))['steps']]
    if step['widget'] == 'choices' and isinstance(raw, str) and re.fullmatch(r'\+\d+', raw):
        options = _widget(state, client, session, step, {}).options
        index = int(raw[1:])
        return options[min(index, len(options) - 1)].value if options else None
    if step['widget'] == 'choices' and step.get('options') == 'next_steps':
        values = {o.value for o in _widget(state, client, session, step, {}).options}
        return raw if raw in values else 'none'
    return raw


def demo_answer(state: ValitukiState, client: ClientProfile) -> Any:
    """The presenter's demo answer to the current question (clients.json → practiceDemo), resolved to a real value."""
    session = active_session(state, client.id)
    step = _current(session) if session else None
    if session is None or step is None:
        return None
    spec = content.client_spec(client.id).get('practiceDemo') or {}
    raw = (spec.get(session.tool) or {}).get(step['key'])
    return resolve_demo_value(state, client, session, step, raw)


# --- views ---------------------------------------------------------------------------------------------------------------

def _due_label(due: Optional[str], today: str) -> str:
    if not due:
        return ''
    delta = days_between(today, due)
    if delta == 0:
        return 'Today'
    if delta == 1:
        return 'Tomorrow'
    if delta < 0:
        return f'Overdue · {fmt_slot(due)}'
    return fmt_slot(due)


def _assigned_label(state: ValitukiState, assigned_by: str) -> str:
    if assigned_by.startswith('therapist:'):
        therapist = next((t for t in state.therapists if t.id == assigned_by.split(':', 1)[1]), None)
        return f'Therapist {therapist.name.split()[0]}' if therapist else 'Therapist'
    return 'Mieliluotsi' if assigned_by.startswith('agent') else 'You'


def task_row(state: ValitukiState, task: PracticeTask) -> dict[str, Any]:
    action = {'exposure_step': 'Tell me how it went', 'experiment': 'Tell me how it went', 'homework': 'Start'}.get(task.kind, 'I did this')
    return {'id': task.id, 'kind': task.kind, 'kindLabel': {'exposure_step': 'Exposure', 'experiment': 'Behavioural experiment',
                                                            'activity': 'Exercise', 'homework': 'Between-session task'}[task.kind],
            'title': task.title, 'detail': task.detail, 'dueDate': task.dueDate, 'dueLabel': _due_label(task.dueDate, state.currentDate),
            'overdue': bool(task.dueDate and task.status == 'open' and task.dueDate < state.currentDate), 'status': task.status,
            'actionLabel': action, 'assignedBy': task.assignedBy, 'assignedByLabel': _assigned_label(state, task.assignedBy),
            'sourceId': task.sourceId, 'stepId': task.stepId, 'tool': task.tool, 'completedAt': task.completedAt}


def _record_row(record: ThoughtRecord) -> dict[str, Any]:
    return {'id': record.id, 'date': record.createdAt, 'situation': record.situation, 'thought': record.thought,
            'emotions': [emotion_label(e) for e in record.emotions], 'intensityBefore': record.intensityBefore,
            'intensityAfter': record.intensityAfter, 'behaviour': record.behaviour,
            'traps': [{'id': t, 'label': trap_label(t)} for t in record.traps], 'evidenceFor': record.evidenceFor,
            'evidenceAgainst': record.evidenceAgainst, 'alternative': record.alternative, 'nextStep': record.nextStep,
            'shared': record.shared, 'mode': record.mode}


def _ladder_row(ladder: ExposureLadder) -> dict[str, Any]:
    done = len([s for s in ladder.steps if s.status == 'done'])
    return {'id': ladder.id, 'date': ladder.createdAt, 'goal': ladder.goal, 'goalAnxiety': ladder.goalAnxiety, 'status': ladder.status,
            'shared': ladder.shared, 'progress': {'done': done, 'total': len(ladder.steps)},
            'steps': [{'id': s.id, 'text': s.text, 'expected': s.expected, 'status': s.status,
                       'attempts': [a.model_dump() for a in s.attempts]} for s in ladder.steps]}


def _experiment_row(item: Experiment) -> dict[str, Any]:
    return {'id': item.id, 'date': item.createdAt, 'prediction': item.prediction, 'beliefBefore': item.beliefBefore, 'plan': item.plan,
            'plannedFor': item.plannedFor, 'status': item.status, 'outcome': item.outcome, 'learned': item.learned,
            'beliefAfter': item.beliefAfter, 'reviewedAt': item.reviewedAt, 'shared': item.shared}


def completed_items(state: ValitukiState, client: ClientProfile) -> list[dict[str, Any]]:
    """"Completed exercises" – newest first, each with its tag."""
    items: list[dict[str, Any]] = []
    for record in state.thoughtRecords:
        if record.clientId == client.id:
            items.append({'id': record.id, 'kind': 'thought_record', 'tag': PRACTICE_KINDS['thought_record'], 'at': record.createdAt,
                          'title': short(record.situation, 70) or 'Exploring a thought', 'detail': record.alternative or record.thought,
                          'change': {'before': record.intensityBefore, 'after': record.intensityAfter}})
    for item in state.experiments:
        if item.clientId == client.id and item.status == 'done':
            items.append({'id': item.id, 'kind': 'experiment', 'tag': PRACTICE_KINDS['experiment'], 'at': item.reviewedAt or item.createdAt,
                          'title': short(item.plan, 70), 'detail': item.learned or item.outcome,
                          'change': {'before': item.beliefBefore, 'after': item.beliefAfter}})
    for ladder in state.ladders:
        if ladder.clientId != client.id:
            continue
        for step in ladder.steps:
            for attempt in step.attempts:
                items.append({'id': attempt.id, 'kind': 'exposure', 'tag': PRACTICE_KINDS['exposure'], 'at': f'{attempt.date}T20:00',
                              'title': step.text, 'detail': attempt.note or f'Ladder: {short(ladder.goal, 60)}',
                              'change': {'before': attempt.peak, 'after': attempt.after}})
    for completion in state.activityCompletions:
        if completion.clientId == client.id and completion.status == 'completed':
            activity = content.activity(completion.activityId)
            items.append({'id': completion.id, 'kind': 'activity', 'tag': PRACTICE_KINDS['activity'], 'at': completion.createdAt,
                          'title': activity.title if activity else completion.activityId,
                          'detail': (f'Your rating {completion.rating}/5' if completion.rating
                                     else activity.description if activity else ''),
                          'change': None})
    return sorted(items, key=lambda i: i['at'], reverse=True)


def stats(state: ValitukiState, client_id: str, since: Optional[str] = None) -> dict[str, Any]:
    records_ = [r for r in state.thoughtRecords if r.clientId == client_id and (not since or r.createdAt >= since)]
    drops = [r.intensityBefore - r.intensityAfter for r in records_ if r.intensityBefore is not None and r.intensityAfter is not None]
    attempts = [a for lad in state.ladders if lad.clientId == client_id for s in lad.steps for a in s.attempts
                if not since or a.date >= since[:10]]
    experiments = [e for e in state.experiments if e.clientId == client_id and (not since or e.createdAt >= since)]
    traps: dict[str, int] = {}
    for record in records_:
        for trap in record.traps:
            traps[trap] = traps.get(trap, 0) + 1
    return {'thoughtRecords': len(records_), 'avgDrop': round(mean(drops), 1) if drops else None,
            'exposureAttempts': len(attempts), 'experiments': len(experiments),
            'experimentsDone': len([e for e in experiments if e.status == 'done']),
            'traps': [{'id': t, 'label': trap_label(t), 'count': n} for t, n in sorted(traps.items(), key=lambda kv: (-kv[1], kv[0]))]}


def tools_view(state: ValitukiState, client: ClientProfile) -> list[dict[str, Any]]:
    counts = {'thought_record': len([r for r in state.thoughtRecords if r.clientId == client.id]),
              'experiment': len([e for e in state.experiments if e.clientId == client.id]),
              'exposure': len([lad for lad in state.ladders if lad.clientId == client.id])}
    rows = []
    for meta in _cbt()['tools']:
        allowed, reason = tool_allowed(state, client, meta['id'])
        rows.append({**{k: meta[k] for k in ('id', 'title', 'kind', 'duration', 'description', 'purpose', 'caution', 'sourcePlaceholder',
                                             'version')}, 'allowed': allowed, 'lockedReason': reason or None,
                     'count': counts.get(meta['id'], 0)})
    return rows


def active_view(state: ValitukiState, client: ClientProfile) -> Optional[dict[str, Any]]:
    session = active_session(state, client.id)
    if session is None:
        return None
    steps = _steps(session)
    step = _current(session)
    question = next((m for m in reversed(state.chat) if m.sessionId == session.id and m.kind == 'question'
                     and step and m.stepKey == step['key']), None)
    return {'id': session.id, 'tool': session.tool, 'title': title(session.tool), 'startedFrom': session.startedFrom,
            'stepKey': step['key'] if step else None, 'stepIndex': (steps.index(step) + 1) if step else len(steps),
            'stepCount': len(steps), 'questionId': question.id if question else None,
            'questionText': question.text if question else None,
            'widget': question.widget.model_dump() if question and question.widget else None,
            'demoAnswer': demo_answer(state, client)}


def client_view(state: ValitukiState, client: ClientProfile) -> dict[str, Any]:
    tasks = sorted((t for t in state.practiceTasks if t.clientId == client.id),
                   key=lambda t: (t.status != 'open', t.dueDate or '', t.id))
    open_tasks = [task_row(state, t) for t in tasks if t.status == 'open']
    recent = [task_row(state, t) for t in sorted((t for t in tasks if t.status != 'open'), key=lambda t: t.updatedAt, reverse=True)[:5]]
    return {
        'tools': tools_view(state, client),
        'tasks': open_tasks,
        'recentTasks': recent,
        'thoughtRecords': [_record_row(r) for r in sorted((r for r in state.thoughtRecords if r.clientId == client.id),
                                                          key=lambda r: r.createdAt, reverse=True)],
        'experiments': [_experiment_row(e) for e in sorted((e for e in state.experiments if e.clientId == client.id),
                                                           key=lambda e: e.createdAt, reverse=True)],
        'ladders': [_ladder_row(lad) for lad in sorted((lad for lad in state.ladders if lad.clientId == client.id),
                                                       key=lambda lad: lad.createdAt, reverse=True)],
        'completed': completed_items(state, client)[:30],
        'stats': stats(state, client.id),
        'allowedTools': allowed_tools(state, client),
    }


def week_summary(state: ValitukiState, client: ClientProfile, series: list[dict[str, Any]]) -> dict[str, Any]:
    """"Your week" – a Wysa-style weekly review built only from the client's own answers (deterministic)."""
    today = date.fromisoformat(state.currentDate)
    start_day = today - timedelta(days=today.weekday())
    days = [(start_day + timedelta(days=i)).isoformat() for i in range(7)]
    by_day: dict[str, dict[str, Any]] = {}
    for point in series:
        if point['date'] in days:
            by_day[point['date']] = point
    week_start = days[0]
    sessions = [s for s in state.guidedSessions
                if s.clientId == client.id and s.status == 'completed' and (s.endedAt or '')[:10] >= week_start]
    checkins = [p for p in series if p['date'] >= week_start]
    records_ = [r for r in state.thoughtRecords if r.clientId == client.id and r.createdAt[:10] >= week_start]
    attempts = [(lad, s, a) for lad in state.ladders if lad.clientId == client.id for s in lad.steps for a in s.attempts
                if a.date >= week_start]
    came_up: list[str] = []
    high = [p for p in checkins if (p.get('anxiety') or 0) >= 4]
    if checkins:
        came_up.append(f'Your anxiety was raised in {len(high)}/{len(checkins)} check-ins.' if high
                       else f'You did {_count(len(checkins), "check-in")} – your anxiety stayed moderate.')
    week_stats = stats(state, client.id, since=week_start)
    if week_stats['traps']:
        top = week_stats['traps'][0]
        if top['count'] > 1:
            came_up.append(f'You recognised the thinking trap “{top["label"]}” {_count(top["count"], "time")}.')
        else:
            names = [f'“{t["label"]}”' for t in week_stats['traps'][:2]]
            came_up.append(f'You recognised the thinking trap {names[0]}.' if len(names) == 1
                           else f'You recognised the thinking traps {join_fi(names)}.')
    if records_ and week_stats['avgDrop'] is not None:
        came_up.append(f'Exploring a thought eased the strength of the feeling by {week_stats["avgDrop"]} points on average '
                       '(0–10).')
    for _ladder, step, attempt in attempts[-1:]:
        came_up.append(f'You did the exposure step “{short(step.text, 60)}” – anxiety {attempt.peak}/10 → {attempt.after}/10.')
    steps = [f'{t.title} ({_in_sentence(_due_label(t.dueDate, state.currentDate))})' for t in state.practiceTasks
             if t.clientId == client.id and t.status == 'open'][:3]
    words = next((r.alternative for r in sorted(state.thoughtRecords, key=lambda r: r.createdAt, reverse=True)
                  if r.clientId == client.id and r.alternative), None)
    weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    return {
        'start': days[0], 'end': days[-1], 'sessions': len(sessions),
        'days': [{'date': d, 'weekday': weekdays[i], 'mood': by_day.get(d, {}).get('mood'), 'anxiety': by_day.get(d, {}).get('anxiety'),
                  'future': d > state.currentDate} for i, d in enumerate(days)],
        'cameUp': came_up,
        'steps': steps,
        'words': words,
    }


def therapist_summary(state: ValitukiState, client: ClientProfile, since: Optional[str]) -> dict[str, Any]:
    """What the therapist sees between sessions: a summary only with the client's permission, entries only if shared."""
    allowed = client.consent.sharePractice
    shared_records = [_record_row(r) for r in sorted(state.thoughtRecords, key=lambda r: r.createdAt, reverse=True)
                      if r.clientId == client.id and r.shared]
    shared_ladders = [_ladder_row(lad) for lad in state.ladders if lad.clientId == client.id and (lad.shared or allowed)]
    homework = [task_row(state, t) for t in sorted(state.practiceTasks, key=lambda t: t.createdAt, reverse=True)
                if t.clientId == client.id and t.kind == 'homework'][:6]
    return {'allowed': allowed, 'stats': stats(state, client.id, since=since) if allowed else None,
            'sharedRecords': shared_records,
            'ladders': shared_ladders if allowed else [row for row in shared_ladders if row['shared']],
            'homework': homework}


def handover_facts(state: ValitukiState, client: ClientProfile) -> Optional[dict[str, Any]]:
    """The "What I have practised" handover section: aggregated only – journal entries are never included."""
    summary = stats(state, client.id)
    ladders = [lad for lad in state.ladders if lad.clientId == client.id]
    if not (summary['thoughtRecords'] or summary['experiments'] or ladders):
        return None
    parts = []
    if summary['thoughtRecords']:
        drop = f', the feeling eased by {summary["avgDrop"]} points on average (0–10)' if summary['avgDrop'] else ''
        parts.append(f'Exploring a thought {_count(summary["thoughtRecords"], "time")}{drop}')
    if summary['traps']:
        parts.append('thinking traps recognised: ' + join_fi([f'{t["label"]} ({t["count"]})' for t in summary['traps'][:3]]))
    if summary['experiments']:
        parts.append(f'behavioural experiments: {summary["experiments"]} ({summary["experimentsDone"]} done)')
    for ladder in ladders[:2]:
        done = len([s for s in ladder.steps if s.status == 'done'])
        parts.append(f'exposure ladder “{short(ladder.goal, 60)}”: {done}/{len(ladder.steps)} steps done')
    return {'text': '; '.join(parts) + '.', 'stats': summary,
            'ladders': [{'goal': lad.goal, 'done': len([s for s in lad.steps if s.status == 'done']), 'total': len(lad.steps)}
                        for lad in ladders]}
