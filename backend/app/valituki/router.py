"""Mieliluotsi API. Each mutation runs in one repository transaction (nothing is saved if it fails) and returns the refreshed
view models, so the UI never calls a language model or computes state itself."""
from __future__ import annotations

from typing import Any, Callable, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, ValidationError

from app.valituki import ai, client_actions, content, intake, professional, scenes, simulation, store, therapy, view
from app.valituki.client_actions import ClientActionError
from app.valituki.handover import HandoverError
from app.valituki.insights import InsightError
from app.valituki.intake import IntakeError
from app.valituki.journey import JourneyError
from app.valituki.matching_flow import MatchingError
from app.valituki.models import ValitukiState
from app.valituki.practice import PracticeError
from app.valituki.professional import PermissionDenied, ProfessionalError
from app.valituki.scenes import SceneError
from app.valituki.simulation import SimulationError
from app.valituki.store import NotFoundError, get_client, repository
from app.valituki.therapy import TherapyError

router = APIRouter(prefix='/api/valituki', tags=['Mieliluotsi'])

ERRORS: dict[type[Exception], int] = {
    NotFoundError: 404, JourneyError: 409, ClientActionError: 400, HandoverError: 409, MatchingError: 409, ProfessionalError: 409,
    SimulationError: 409, IntakeError: 409, InsightError: 409, TherapyError: 409, PermissionDenied: 403, SceneError: 400,
    PracticeError: 409,
}


def _run(action: Callable[[ValitukiState], Any], client_id: Optional[str], therapist_id: Optional[str]) -> dict[str, Any]:
    try:
        with repository.transaction() as state:
            store.begin_action(state)
            result = action(state)
            data = view.build(state, client_id, therapist_id)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail='Invalid input: ' + '; '.join(
            f'{".".join(str(p) for p in err["loc"])}: {err["msg"]}' for err in exc.errors()[:3])) from exc
    except tuple(ERRORS) as exc:
        raise HTTPException(status_code=ERRORS[type(exc)], detail=str(exc)) from exc
    return {'result': jsonable_encoder(result), 'view': data}


ClientQ = Query(default=None, alias='clientId')
TherapistQ = Query(default=None, alias='therapistId')


# --- request bodies -------------------------------------------------------------------------------------------------

class ConsentBody(BaseModel):
    proactiveCheckins: Optional[bool] = None
    storeHistory: Optional[bool] = None
    professionalMonitoring: Optional[bool] = None
    sharePractice: Optional[bool] = None


class TextBody(BaseModel):
    text: str


class ProposalBody(BaseModel):
    text: Optional[str] = None
    included: Optional[bool] = None
    structured: Optional[dict[str, Any]] = None


class CompleteIntakeBody(BaseModel):
    checkInDays: list[int]
    communicationStyle: Literal['brief', 'warm'] = 'brief'
    contactChannel: Literal['app', 'phone'] = 'app'
    callTime: Optional[str] = None
    mood: Optional[int] = Field(default=None, ge=1, le=5)  # or later from the home screen (/baseline)
    anxiety: Optional[int] = Field(default=None, ge=1, le=5)


class BaselineBody(BaseModel):
    mood: int = Field(ge=1, le=5)
    anxiety: Optional[int] = Field(default=None, ge=1, le=5)


class CheckInBody(BaseModel):
    mood: int = Field(ge=1, le=5)
    anxiety: Optional[int] = Field(default=None, ge=1, le=5)
    changes: dict[str, Literal['worse', 'better']] = {}
    noChange: bool = False
    note: str = ''
    trackScore: Optional[int] = Field(default=None, ge=1, le=5)


class ActivityBody(BaseModel):
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    note: str = ''


class DecisionBody(BaseModel):
    decision: Literal['approve', 'reject']


class SharingBody(BaseModel):
    professional: bool
    matching: bool


class HumanBody(BaseModel):
    reason: str = 'other'
    message: str = ''


class CandidateBody(BaseModel):
    candidateId: str


class NoteText(BaseModel):
    note: str = ''


class ChecklistBody(BaseModel):
    itemId: str
    done: bool


class HandoverBody(BaseModel):
    action: Literal['remove', 'restore', 'edit']
    section: str
    text: Optional[str] = None
    questions: Optional[list[str]] = None


class FeedbackBody(BaseModel):
    heard: int = Field(ge=1, le=5)
    goalsUnderstood: int = Field(ge=1, le=5)
    styleFit: int = Field(ge=1, le=5)
    wantContinue: Literal['yes', 'unsure', 'no'] = 'unsure'
    wantDiscussAlternative: bool = False
    note: str = ''


class ReviewBody(BaseModel):
    action: Literal['mark_reviewed', 'contact', 'no_action', 'frequency']
    note: str = ''
    perWeek: Optional[int] = None


class TaskBody(BaseModel):
    action: Literal['contact', 'complete', 'close']
    note: str = ''


class FrequencyBody(BaseModel):
    perWeek: int


class UrgencyBody(BaseModel):
    urgency: Literal['non_urgent', 'urgent']
    reason: str = ''


class NoteBody(BaseModel):
    text: str
    includeInHandover: bool = False


class PlanBody(BaseModel):
    primaryGoal: str
    allowedActivityIds: list[str]
    allowedTools: list[str] = []
    homeworkTool: Optional[str] = None
    homeworkNote: str = ''
    checkInsPerWeek: int = 2
    track: str = ''
    doNotAddress: str = ''


class AftercareBody(BaseModel):
    checkInsPerWeek: int = 1
    allowedTools: list[str] = []
    maintenance: str = ''
    warningSigns: str = ''


class PracticeStartBody(BaseModel):
    tool: Literal['checkin', 'thought_record', 'experiment', 'exposure']
    prefill: dict[str, Any] = {}
    startedFrom: str = 'chat'


class PracticeAnswerBody(BaseModel):
    sessionId: Optional[str] = None
    stepKey: Optional[str] = None
    value: Any = None
    skip: bool = False


class PracticeStopBody(BaseModel):
    sessionId: Optional[str] = None


class OfferBody(BaseModel):
    messageId: str
    option: str


class TaskActionBody(BaseModel):
    action: Literal['done', 'later', 'skip']


class SharedBody(BaseModel):
    shared: bool


class AdvanceBody(BaseModel):
    days: int = 1


class DemoClientBody(BaseModel):
    clientId: str = 'cl-aino'


class SceneBody(BaseModel):
    scene: str


# --- read -------------------------------------------------------------------------------------------------------------

@router.get('/view')
def get_view(client_id: Optional[str] = ClientQ, therapist_id: Optional[str] = TherapistQ) -> dict[str, Any]:
    return view.build(repository.load(), client_id, therapist_id)


@router.get('/status')
def get_status() -> dict[str, Any]:
    state = repository.load()
    return {'status': 'ok', 'currentDate': state.currentDate, 'ai': ai.status(), 'synthetic': True}


# --- AI connection (presenter) -------------------------------------------------------------------------------------------

class AIModeBody(BaseModel):
    mode: Literal['DEMO_AI_MODE', 'LIVE_AI_MODE']


def _with_view(result: dict[str, Any], client_id: Optional[str], therapist_id: Optional[str]) -> dict[str, Any]:
    return {'result': jsonable_encoder(result), 'view': view.build(repository.load(), client_id, therapist_id)}


@router.put('/ai/mode')
def put_ai_mode(body: AIModeBody, client_id: Optional[str] = ClientQ, therapist_id: Optional[str] = TherapistQ):
    """Demo ↔ Claude. Switching to Claude re-reads the key from .env and tests the connection at once."""
    return _with_view(ai.set_mode(body.mode), client_id, therapist_id)


@router.post('/ai/check')
def post_ai_check(client_id: Optional[str] = ClientQ, therapist_id: Optional[str] = TherapistQ):
    check = ai.check_connection()  # first: it re-reads .env, which the status then reflects
    return _with_view({**ai.status(), 'check': check}, client_id, therapist_id)


# --- client: intake ----------------------------------------------------------------------------------------------------

def _client(state: ValitukiState, client_id: str):
    return get_client(state, client_id)


class StartIntakeBody(ConsentBody):
    # The client app's start: the profile from the records (the referral and the assessment visit), no intake conversation.
    fromRecords: bool = False


@router.post('/clients/{client_id}/intake/start')
def post_intake_start(client_id: str, body: StartIntakeBody, therapist_id: Optional[str] = TherapistQ):
    consent = {k: v for k, v in body.model_dump(exclude={'fromRecords'}).items() if v is not None}

    def begin(s):
        client = _client(s, client_id)
        if body.fromRecords:
            known = (content.client_spec(client.id).get('intake') or {}).get('answers') or {}
            return intake.start_from_records(s, client, consent, known, client_actions.actor(client)).id
        return intake.start(s, client, consent, client_actions.actor(client)).id

    return _run(begin, client_id, therapist_id)


@router.post('/clients/{client_id}/intake/answer')
def post_intake_answer(client_id: str, body: TextBody, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: intake.answer(s, _client(s, client_id), body.text, ai.get_provider(),
                                        client_actions.actor(_client(s, client_id))), client_id, therapist_id)


@router.post('/clients/{client_id}/intake/skip')
def post_intake_skip(client_id: str, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: intake.skip(s, _client(s, client_id), ai.get_provider(), client_actions.actor(_client(s, client_id))),
                client_id, therapist_id)


@router.post('/clients/{client_id}/intake/finish')
def post_intake_finish(client_id: str, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: intake.finish(s, _client(s, client_id), ai.get_provider()), client_id, therapist_id)


@router.put('/clients/{client_id}/intake/proposals/{proposal_id}')
def put_proposal(client_id: str, proposal_id: str, body: ProposalBody, therapist_id: Optional[str] = TherapistQ):
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    return _run(lambda s: intake.update_proposal(s, _client(s, client_id), proposal_id, changes).model_dump(), client_id, therapist_id)


@router.post('/clients/{client_id}/intake/confirm')
def post_intake_confirm(client_id: str, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: intake.confirm(s, _client(s, client_id), client_actions.actor(_client(s, client_id))), client_id, therapist_id)


@router.post('/clients/{client_id}/intake/complete')
def post_intake_complete(client_id: str, body: CompleteIntakeBody, therapist_id: Optional[str] = TherapistQ):
    rhythm = {'checkInDays': body.checkInDays, 'communicationStyle': body.communicationStyle,
              'contactChannel': body.contactChannel, 'callTime': body.callTime}
    return _run(lambda s: intake.complete(s, _client(s, client_id), rhythm, body.mood, client_actions.actor(_client(s, client_id)),
                                          ai.get_provider(), anxiety=body.anxiety), client_id, therapist_id)


@router.post('/clients/{client_id}/baseline')
def post_baseline(client_id: str, body: BaselineBody, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: intake.record_baseline(s, _client(s, client_id), body.mood, client_actions.actor(_client(s, client_id)),
                                                 anxiety=body.anxiety), client_id, therapist_id)


# --- client: support -----------------------------------------------------------------------------------------------------

@router.put('/clients/{client_id}/consent')
def put_consent(client_id: str, body: ConsentBody, therapist_id: Optional[str] = TherapistQ):
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    return _run(lambda s: client_actions.set_consent(s, _client(s, client_id), changes), client_id, therapist_id)


@router.post('/clients/{client_id}/checkins')
def post_checkin(client_id: str, body: CheckInBody, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.submit_checkin(s, _client(s, client_id), body.mood, body.changes, body.note,
                                                        anxiety=body.anxiety, track_score=body.trackScore, no_change=body.noChange,
                                                        provider=ai.get_provider()),
                client_id, therapist_id)


@router.post('/clients/{client_id}/activities/{activity_id}/complete')
def post_activity_done(client_id: str, activity_id: str, body: ActivityBody, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.complete_activity(s, _client(s, client_id), activity_id, body.rating, body.note).id,
                client_id, therapist_id)


@router.post('/clients/{client_id}/activities/{activity_id}/skip')
def post_activity_skip(client_id: str, activity_id: str, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: bool(client_actions.skip_activity(s, _client(s, client_id), activity_id)), client_id, therapist_id)


@router.post('/clients/{client_id}/insights/{insight_id}/decision')
def post_insight_decision(client_id: str, insight_id: str, body: DecisionBody, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.decide_insight(s, _client(s, client_id), insight_id, body.decision), client_id, therapist_id)


@router.put('/clients/{client_id}/insights/{insight_id}')
def put_insight(client_id: str, insight_id: str, body: TextBody, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.edit_insight(s, _client(s, client_id), insight_id, body.text), client_id, therapist_id)


@router.put('/clients/{client_id}/insights/{insight_id}/sharing')
def put_insight_sharing(client_id: str, insight_id: str, body: SharingBody, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.set_insight_sharing(s, _client(s, client_id), insight_id, body.professional, body.matching),
                client_id, therapist_id)


@router.delete('/clients/{client_id}/insights/{insight_id}')
def delete_insight(client_id: str, insight_id: str, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.remove_insight(s, _client(s, client_id), insight_id), client_id, therapist_id)


@router.post('/clients/{client_id}/messages')
def post_message(client_id: str, body: TextBody, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.send_message(s, _client(s, client_id), body.text, ai.get_provider()), client_id, therapist_id)


@router.post('/clients/{client_id}/practice/start')
def post_practice_start(client_id: str, body: PracticeStartBody, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.start_practice(s, _client(s, client_id), body.tool, ai.get_provider(), prefill=body.prefill,
                                                        started_from=body.startedFrom), client_id, therapist_id)


@router.post('/clients/{client_id}/practice/answer')
def post_practice_answer(client_id: str, body: PracticeAnswerBody, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.answer_practice(s, _client(s, client_id), body.value, session_id=body.sessionId,
                                                         step_key=body.stepKey, skip=body.skip, provider=ai.get_provider()),
                client_id, therapist_id)


@router.post('/clients/{client_id}/practice/stop')
def post_practice_stop(client_id: str, body: PracticeStopBody, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.stop_practice(s, _client(s, client_id), body.sessionId), client_id, therapist_id)


@router.post('/clients/{client_id}/chat/offer')
def post_chat_offer(client_id: str, body: OfferBody, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.choose_offer(s, _client(s, client_id), body.messageId, body.option, ai.get_provider()),
                client_id, therapist_id)


@router.post('/clients/{client_id}/tasks/{task_id}')
def post_task_action(client_id: str, task_id: str, body: TaskActionBody, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.task_action(s, _client(s, client_id), task_id, body.action, ai.get_provider()),
                client_id, therapist_id)


@router.put('/clients/{client_id}/practice/{kind}/{item_id}/sharing')
def put_practice_sharing(client_id: str, kind: str, item_id: str, body: SharedBody, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.set_practice_sharing(s, _client(s, client_id), kind, item_id, body.shared),
                client_id, therapist_id)


@router.delete('/clients/{client_id}/practice/{kind}/{item_id}')
def delete_practice_item(client_id: str, kind: str, item_id: str, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.remove_practice_item(s, _client(s, client_id), kind, item_id), client_id, therapist_id)


@router.post('/clients/{client_id}/request-human')
def post_request_human(client_id: str, body: HumanBody, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.request_human(s, _client(s, client_id), body.reason, body.message), client_id, therapist_id)


@router.post('/clients/{client_id}/help-now')
def post_help_now(client_id: str, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.help_now(s, _client(s, client_id)), client_id, therapist_id)


@router.post('/clients/{client_id}/safety/dismiss')
def post_dismiss_safety(client_id: str, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.dismiss_safety(s, _client(s, client_id)), client_id, therapist_id)


@router.post('/clients/{client_id}/matches/select')
def post_select(client_id: str, body: CandidateBody, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.select_candidate(s, _client(s, client_id), body.candidateId).id, client_id, therapist_id)


@router.post('/clients/{client_id}/matches/more')
def post_more(client_id: str, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.request_alternatives(s, _client(s, client_id)), client_id, therapist_id)


@router.post('/clients/{client_id}/matches/help')
def post_match_help(client_id: str, body: NoteText, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.request_matching_help(s, _client(s, client_id), body.note), client_id, therapist_id)


@router.post('/clients/{client_id}/checklist')
def post_checklist(client_id: str, body: ChecklistBody, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.toggle_checklist(s, _client(s, client_id), body.itemId, body.done), client_id, therapist_id)


@router.put('/clients/{client_id}/handover')
def put_handover(client_id: str, body: HandoverBody, therapist_id: Optional[str] = TherapistQ):
    change = {k: v for k, v in body.model_dump().items() if v is not None}
    return _run(lambda s: client_actions.update_handover(s, _client(s, client_id), change).status, client_id, therapist_id)


@router.post('/clients/{client_id}/handover/approve')
def post_handover_approve(client_id: str, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.approve_handover(s, _client(s, client_id)).status, client_id, therapist_id)


@router.post('/clients/{client_id}/handover/withdraw')
def post_handover_withdraw(client_id: str, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.withdraw_handover(s, _client(s, client_id)).status, client_id, therapist_id)


@router.post('/clients/{client_id}/match-feedback')
def post_match_feedback(client_id: str, body: FeedbackBody, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.submit_match_feedback(s, _client(s, client_id), body.model_dump()).negative,
                client_id, therapist_id)


@router.post('/clients/{client_id}/notifications/read')
def post_notifications_read(client_id: str, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: client_actions.mark_notifications_read(s, _client(s, client_id)), client_id, therapist_id)


# --- professional ------------------------------------------------------------------------------------------------------

@router.post('/observations/{observation_id}/review')
def post_review(observation_id: str, body: ReviewBody, client_id: Optional[str] = ClientQ, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: professional.review_observation(s, observation_id, body.action, body.note, body.perWeek), client_id, therapist_id)


@router.post('/tasks/{task_id}/action')
def post_task(task_id: str, body: TaskBody, client_id: Optional[str] = ClientQ, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: professional.task_action(s, task_id, body.action, body.note), client_id, therapist_id)


@router.post('/clients/{target_id}/checkin-frequency')
def post_frequency(target_id: str, body: FrequencyBody, client_id: Optional[str] = ClientQ, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: professional.set_checkin_frequency(s, professional.ensure_active(s, target_id), body.perWeek),
                client_id, therapist_id)


@router.post('/clients/{target_id}/urgency')
def post_urgency(target_id: str, body: UrgencyBody, client_id: Optional[str] = ClientQ, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: professional.set_clinical_urgency(s, professional.ensure_active(s, target_id), body.urgency, professional.ACTOR,
                                                            body.reason), client_id, therapist_id)


@router.post('/clients/{target_id}/notes')
def post_note(target_id: str, body: NoteBody, client_id: Optional[str] = ClientQ, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: professional.add_note(s, get_client(s, target_id), body.text, body.includeInHandover).id, client_id, therapist_id)


@router.post('/clients/{target_id}/matching/run')
def post_matching_run(target_id: str, client_id: Optional[str] = ClientQ, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: professional.run_matching(s, get_client(s, target_id)).id, client_id, therapist_id)


# --- therapist ---------------------------------------------------------------------------------------------------------

@router.put('/therapists/{tid}/clients/{target_id}/plan')
def put_plan(tid: str, target_id: str, body: PlanBody, client_id: Optional[str] = ClientQ, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: therapy.configure(s, get_client(s, target_id), tid, body.model_dump(), f'therapist:{tid}').id,
                client_id, therapist_id or tid)


@router.post('/therapists/{tid}/clients/{target_id}/end-therapy')
def post_end_therapy(tid: str, target_id: str, body: AftercareBody, client_id: Optional[str] = ClientQ,
                     therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: therapy.end_therapy(s, get_client(s, target_id), tid, body.model_dump(), f'therapist:{tid}').id,
                client_id, therapist_id or tid)


@router.post('/therapists/{tid}/clients/{target_id}/first-session')
def post_first_session(tid: str, target_id: str, client_id: Optional[str] = ClientQ, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: simulation.hold_first_session(s, get_client(s, target_id)), client_id, therapist_id or tid)


# --- demo controls ------------------------------------------------------------------------------------------------------

@router.post('/demo/advance')
def post_advance(body: AdvanceBody, client_id: Optional[str] = ClientQ, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: simulation.advance(s, body.days), client_id, therapist_id)


@router.post('/demo/open-slot')
def post_open_slot(client_id: Optional[str] = ClientQ, therapist_id: Optional[str] = TherapistQ):
    return _run(simulation.open_next_pending, client_id, therapist_id)


@router.post('/demo/deteriorate')
def post_deteriorate(body: DemoClientBody, client_id: Optional[str] = ClientQ, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: simulation.simulate_deterioration(s, get_client(s, body.clientId)), client_id or body.clientId, therapist_id)


@router.post('/demo/stabilize')
def post_stabilize(body: DemoClientBody, client_id: Optional[str] = ClientQ, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: simulation.simulate_stable(s, get_client(s, body.clientId)), client_id or body.clientId, therapist_id)


@router.post('/demo/first-session')
def post_demo_first_session(body: DemoClientBody, client_id: Optional[str] = ClientQ, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: simulation.hold_first_session(s, get_client(s, body.clientId)), client_id or body.clientId, therapist_id)


@router.post('/demo/end-therapy')
def post_demo_end_therapy(body: DemoClientBody, client_id: Optional[str] = ClientQ, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: simulation.end_therapy(s, get_client(s, body.clientId)), client_id or body.clientId, therapist_id)


@router.post('/demo/crisis')
def post_crisis(client_id: Optional[str] = ClientQ, therapist_id: Optional[str] = TherapistQ):
    return _run(lambda s: simulation.crisis(s), client_id or 'cl-crisis', therapist_id)


@router.post('/demo/reset')
def post_reset(client_id: Optional[str] = ClientQ, therapist_id: Optional[str] = TherapistQ):
    state = repository.reset()
    return {'result': {'reset': True}, 'view': view.build(state, client_id, therapist_id)}


@router.post('/demo/scene')
def post_scene(body: SceneBody, client_id: Optional[str] = ClientQ, therapist_id: Optional[str] = TherapistQ):
    try:
        state = repository.replace(scenes.build_scene(body.scene))
    except SceneError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'result': {'scene': body.scene}, 'view': view.build(state, client_id, therapist_id)}
