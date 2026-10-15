"""Mieliluotsi domain model.

Records carry provenance (createdAt, updatedAt, createdBy, source) and, where it matters, a status and the consent
scope the data is kept or shared under. All people and data in the demo are synthetic.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# Bump when the stored layout changes; an older state file is then rebuilt from the seed.
STATE_VERSION = 'valituki-3.1-en'  # 3.1: English texts; a saved Finnish state is rebuilt

JourneyState = Literal[
    'INVITED',
    'INTAKE',
    'WAITING_ACTIVE',
    'HUMAN_REVIEW_NEEDED',
    'MATCHING_READY',
    'MATCH_PROPOSED',
    'MATCH_ACCEPTED',
    'THERAPY_ACTIVE',
    'AFTERCARE',
    'SERVICE_ENDED',
]
Language = Literal['fi', 'sv', 'en']
Format = Literal['remote', 'in_person', 'either']
TimeOfDay = Literal['morning', 'daytime', 'evening']
Visibility = Literal['client', 'professional', 'both', 'private']  # private: the client's own practice, never shown to staff
Audience = Literal['client', 'coordinator', 'therapist']
AgentName = Literal['Orchestrator', 'SupportAgent', 'CheckInAgent', 'ObservationAgent', 'MatchingAgent', 'NavigationAgent',
                    'SafetyAgent']
TextSource = Literal['demo', 'live', 'fallback', 'fixed', 'client']
Mode = Literal['waiting_support', 'therapy_support', 'aftercare_support']
Domain = Literal['sleep', 'anxiety', 'energy', 'work', 'social']
Direction = Literal['worse', 'better']


class Provenance(BaseModel):
    createdAt: str
    updatedAt: str
    createdBy: str
    source: str


# --- People and consent ----------------------------------------------------------------------------------------------

class User(BaseModel):
    """A demo identity. The role switcher stands in for real authentication."""
    id: str
    role: Literal['client', 'coordinator', 'therapist']
    displayName: str
    clientId: Optional[str] = None
    therapistId: Optional[str] = None
    synthetic: bool = True


class ConsentScope(BaseModel):
    """Service-level consents. Sharing of individual insights is decided per item (InsightSharing)."""
    proactiveCheckins: bool = False  # Mieliluotsi may contact the client (check-ins, reminders)
    storeHistory: bool = False  # answers are stored so that change can be compared with the client's own baseline
    professionalMonitoring: bool = False  # the care team sees the wellbeing trend and Mieliluotsi's observations
    sharePractice: bool = False  # the therapist sees a summary of the practice (counts, thinking traps, 0–10 changes)


class ConsentRecord(Provenance):
    """Append-only: one record per change, so the consent history is auditable."""
    id: str
    clientId: str
    scope: ConsentScope
    changed: dict[str, bool] = {}
    version: int


class SafetyLock(BaseModel):
    """Normal support is paused until the client explicitly acknowledges the safety screen."""
    observationId: str
    activatedAt: str
    dismissedAt: Optional[str] = None


class StateChange(BaseModel):
    at: str
    fromState: Optional[str]
    toState: str
    eventId: str
    eventType: str


class TodayActivity(BaseModel):
    activityId: str
    date: str
    intro: str
    introSource: TextSource
    reason: str
    status: Literal['suggested', 'completed', 'skipped'] = 'suggested'


class ClientProfile(Provenance):
    id: str
    displayName: str
    firstName: str
    age: int
    municipality: str
    persona: str  # a short demo label for the presenter
    demoPrimary: bool = False
    journeyState: JourneyState
    resumeState: Optional[str] = None  # where HUMAN_REVIEW_NEEDED returns to
    stateHistory: list[StateChange] = []
    consent: ConsentScope = Field(default_factory=ConsentScope)
    consentGivenAt: Optional[str] = None
    intakeId: Optional[str] = None
    baseline: Optional[float] = None  # the client's own early wellbeing level on the 1–5 scale
    baselineCheckInIds: list[str] = []
    baselineAt: Optional[str] = None
    checkInDays: list[int] = []  # weekdays, 0 = Monday
    nextCheckInDate: Optional[str] = None
    nextCheckInKind: Literal['routine', 'extra'] = 'routine'
    communicationStyle: Literal['brief', 'warm'] = 'brief'
    # How Mieliluotsi keeps in touch: in the app (written) or by phone – it calls on the check-in days at callTime, asks
    # how the client is and does a short thought exercise by speech.
    contactChannel: Literal['app', 'phone'] = 'app'
    callTime: Optional[str] = None  # 'HH:MM' when contactChannel is 'phone'
    mode: Mode = 'waiting_support'
    automationPaused: bool = False
    matchingNotificationsPaused: bool = False
    personalExclusions: list[str] = []  # therapist ids the client asked to exclude
    safetyLock: Optional[SafetyLock] = None
    todayActivity: Optional[TodayActivity] = None
    recentSuggestions: list[str] = []  # the latest suggested activity ids (the agent rotates suggestions)
    preparationChecklist: list[dict[str, Any]] = []
    simulationProfile: str = 'none'
    simulationCursor: dict[str, int] = {}
    synthetic: bool = True


class Referral(Provenance):
    id: str
    clientId: str
    soughtHelpAt: str
    referredAt: str
    serviceCategory: str
    requiredCompetencies: list[str] = []
    flags: list[str] = []
    referrer: str
    assessedBy: str = ''
    summary: str = ''


class WaitingListEpisode(Provenance):
    """The client's place on the therapy waiting list. Clinical urgency is set only by a professional."""
    id: str
    clientId: str
    referralId: str
    startedAt: str
    allocatableFrom: str
    estimatedWait: str = ''
    clinicalUrgency: Literal['non_urgent', 'urgent'] = 'non_urgent'
    urgencySetBy: str = ''
    urgencySetAt: str = ''
    urgencyHistory: list[dict[str, Any]] = []
    status: Literal['waiting', 'allocated', 'ended'] = 'waiting'
    endedAt: Optional[str] = None


# --- Conversational intake -----------------------------------------------------------------------------------------

class IntakeMessage(BaseModel):
    id: str
    role: Literal['assistant', 'client']
    text: str
    questionKey: Optional[str] = None
    createdAt: str
    source: TextSource = 'client'
    safetyLevel: int = 0


class IntakeProposal(BaseModel):
    """One "Ymmärsinkö tilanteesi oikein?" card: an AI interpretation that stays a proposal until approved."""
    id: str
    category: Literal['goal', 'working_style', 'practical', 'difficult_times', 'helped_before']
    title: str
    text: str
    structured: dict[str, Any] = {}
    derivedFrom: list[str] = []
    userWords: list[str] = []  # verbatim quotes of what the client wrote, shown next to the interpretation
    source: TextSource = 'demo'
    included: bool = True
    editedByClient: bool = False


class IntakeSession(Provenance):
    id: str
    clientId: str
    status: Literal['consent', 'conversation', 'review', 'rhythm', 'completed']
    messages: list[IntakeMessage] = []
    answers: dict[str, str] = {}
    askedKeys: list[str] = []
    skippedKeys: list[str] = []
    pendingQuestionKey: Optional[str] = None
    proposals: list[IntakeProposal] = []
    proposalsSource: Optional[TextSource] = None
    proposedAt: Optional[str] = None
    confirmedAt: Optional[str] = None
    completedAt: Optional[str] = None


# --- Insights, memory and the Therapy Fit Profile ------------------------------------------------------------------

class InsightSharing(BaseModel):
    professional: bool = False  # 👩‍⚕️ may be shown to professionals (care coordinator, therapist)
    matching: bool = False  # 🧩 may be used in therapist matching


class ClientInsight(Provenance):
    """Something Mieliluotsi remembers about the client ("Mieliluotsi muistaa minusta").

    Only status == 'approved' insights are used anywhere. Proposed insights (AI interpretations, detected patterns)
    wait for the client's explicit decision.
    """
    id: str
    clientId: str
    category: Literal['goal', 'preference', 'helpful', 'challenge', 'therapist_wish']
    kind: Literal['primary_goal', 'secondary_goal', 'working_style', 'practical', 'difficult_times', 'helped_before',
                  'pattern', 'activity_helpful', 'activity_not_helpful', 'engagement']
    title: str
    text: str
    structured: dict[str, Any] = {}
    userWords: list[str] = []
    origin: Literal['user_said', 'ai_interpreted', 'observed', 'measured']
    sourceLabel: str
    status: Literal['proposed', 'approved', 'rejected', 'removed'] = 'proposed'
    sharing: InsightSharing = Field(default_factory=InsightSharing)
    evidence: dict[str, Any] = {}
    approvedAt: Optional[str] = None
    decidedAt: Optional[str] = None
    editedByClient: bool = False
    version: int = 1
    consentScope: str = 'private'


class InsightPermission(Provenance):
    """Append-only history of "Kuka saa käyttää tätä tietoa?" decisions."""
    id: str
    clientId: str
    insightId: str
    professional: bool
    matching: bool
    previous: Optional[dict[str, bool]] = None
    reason: str = ''


class Goal(Provenance):
    id: str
    clientId: str
    insightId: str
    priority: Literal['primary', 'secondary']
    text: str
    topics: list[str] = []
    status: Literal['active', 'archived'] = 'active'


class FitProfileChange(BaseModel):
    version: int
    at: str
    change: str
    agent: str


class TherapyFitProfile(Provenance):
    """A structured, evolving profile built only from approved insights and explicit choices."""
    id: str
    clientId: str
    version: int = 1
    status: Literal['active', 'archived'] = 'active'
    goals: dict[str, list[dict[str, Any]]] = Field(default_factory=lambda: {'primary': [], 'secondary': []})
    preferredWorkingStyle: dict[str, Any] = {}
    practicalPreferences: dict[str, Any] = {}
    clientApprovedInsights: list[str] = []
    selfCareResponses: list[dict[str, Any]] = []
    engagementPreferences: dict[str, Any] = {}
    changelog: list[FitProfileChange] = []


# --- Check-ins and wellbeing ---------------------------------------------------------------------------------------

class CheckIn(Provenance):
    id: str
    clientId: str
    kind: Literal['baseline', 'routine', 'extra', 'client_initiated']
    dueDate: str
    status: Literal['due', 'completed', 'missed']
    completedAt: Optional[str] = None
    mood: Optional[int] = None  # "Miten voit tänään?" 1–5
    anxiety: Optional[int] = None  # "Kuinka paljon ahdistusta tai jännitystä?" 1–5 (1 = ei lainkaan)
    changes: dict[str, Direction] = {}  # "Onko jokin näistä muuttunut?"
    noChange: bool = False
    note: str = ''  # optional free text, shown as a journal entry ("päiväkirjamerkintä")
    trackScore: Optional[int] = None  # therapist-configured tracked item, 1–5
    trackLabel: Optional[str] = None
    mode: Mode = 'waiting_support'
    retained: bool = True
    reminderSentAt: Optional[str] = None
    consentScope: str = 'storeHistory'


class WellbeingMetric(BaseModel):
    """One self-reported value, derived from a check-in (for charts and the explainable observations)."""
    id: str
    clientId: str
    checkInId: str
    date: str
    metric: str  # mood | sleep | anxiety | energy | work | social | track
    value: float
    source: str = 'self_report'


class WellbeingObservation(Provenance):
    id: str
    clientId: str
    kind: Literal['trend_decline', 'trend_improvement', 'missed_checkins', 'match_feedback']
    agent: str
    ruleId: str
    title: str
    reason: str
    clientText: Optional[str] = None
    explanation: list[dict[str, Any]] = []  # "Miksi asiakas nousi tarkistettavaksi?" – one row per signal
    underlyingData: dict[str, Any] = {}
    aiSummary: Optional[str] = None
    aiSummarySource: Optional[TextSource] = None
    requiresHumanReview: bool = True
    suggestedAction: str = ''
    status: Literal['open', 'reviewed', 'closed', 'info'] = 'open'
    taskId: Optional[str] = None
    reviewedBy: Optional[str] = None
    reviewedAt: Optional[str] = None
    reviewOutcome: Optional[str] = None
    reviewNote: Optional[str] = None


class SafetyTrigger(BaseModel):
    source: Literal['phrase_rule', 'structured_answer', 'explicit_action', 'ai_hint']
    ruleId: str
    level: int
    category: str
    detail: str = ''


class SafetyObservation(Provenance):
    id: str
    clientId: str
    level: int
    deterministicLevel: int
    aiHint: Optional[str] = None
    aiLevel: int = 0
    triggers: list[SafetyTrigger] = []
    context: Literal['chat', 'checkin', 'intake', 'button', 'demo', 'activity', 'practice', 'call']
    requiredHumanAction: str = ''
    status: Literal['open', 'reviewed', 'closed', 'info'] = 'open'
    taskId: Optional[str] = None
    clientAcknowledgedAt: Optional[str] = None
    reviewedBy: Optional[str] = None
    reviewedAt: Optional[str] = None
    reviewNote: Optional[str] = None
    reviewOutcome: Optional[str] = None


class ProfessionalReviewTask(Provenance):
    id: str
    clientId: str
    type: Literal['safety_review', 'trend_review', 'contact_request', 'engagement_check', 'matching_help',
                  'matching_review']
    priority: Literal['urgent', 'high', 'normal', 'low']
    agent: str
    title: str
    reason: str
    suggestedAction: str
    underlyingData: dict[str, Any] = {}
    handlingNote: str = ''
    status: Literal['open', 'contact_requested', 'completed', 'closed'] = 'open'
    observationId: Optional[str] = None
    outcome: Optional[str] = None
    completedBy: Optional[str] = None
    completedAt: Optional[str] = None


# --- Approved self-care content ------------------------------------------------------------------------------------

class ApprovedActivity(BaseModel):
    id: str
    title: str
    description: str
    purpose: str
    estimatedDuration: int  # minutes
    steps: list[str]
    caution: str
    suitableFor: list[str]
    avoidWhen: list[str]
    topics: list[str]
    sourcePlaceholder: str
    version: str
    approvedAt: str
    approvedBy: str


class ActivityCompletion(Provenance):
    id: str
    clientId: str
    activityId: str
    activityVersion: str
    status: Literal['completed', 'skipped']
    rating: Optional[int] = None  # "Kuinka hyödyllinen harjoitus oli?" 1–5
    note: str = ''
    mode: Mode = 'waiting_support'


# --- Agent records -------------------------------------------------------------------------------------------------

class AgentEvent(BaseModel):
    id: str
    seq: int
    type: str
    clientId: Optional[str] = None
    therapistId: Optional[str] = None
    occurredAt: str
    actor: str
    source: str
    payload: dict[str, Any] = {}
    stateBefore: Optional[str] = None
    stateAfter: Optional[str] = None


class AgentAction(BaseModel):
    """One autonomous step, shown in "Mitä Mieliluotsi teki?"."""
    id: str
    seq: int
    agent: str
    eventId: Optional[str] = None
    eventType: Optional[str] = None
    clientId: Optional[str] = None
    type: str
    title: str
    detail: str
    ruleId: Optional[str] = None
    visibility: Visibility = 'both'
    createdAt: str
    aiTask: Optional[str] = None
    aiSource: Optional[TextSource] = None


class AuditEvent(BaseModel):
    id: str
    seq: int
    at: str
    actor: str
    action: str
    detail: str
    clientId: Optional[str] = None
    eventId: Optional[str] = None
    data: dict[str, Any] = {}


class Notification(BaseModel):
    id: str
    audience: Audience
    clientId: Optional[str] = None
    therapistId: Optional[str] = None
    kind: Literal['info', 'checkin', 'activity', 'insight', 'matching', 'handover', 'safety', 'review', 'contact', 'therapy',
                  'practice']
    title: str
    body: str
    createdAt: str
    read: bool = False
    actionView: Optional[str] = None
    eventId: Optional[str] = None
    agent: Optional[str] = None


class ChatOption(BaseModel):
    value: str
    label: str
    hint: Optional[str] = None


class ChatWidget(BaseModel):
    """The structured answer a chat question expects (chips, a 0–10 scale, thinking traps, a ladder …) or an offer."""
    type: Literal['scale', 'scale5', 'choices', 'multi', 'traps', 'text', 'ladder', 'offer', 'summary']
    options: list[ChatOption] = []
    min: int = 0
    max: int = 10
    minLabel: str = ''
    maxLabel: str = ''
    placeholder: str = ''
    suggested: list[str] = []  # values Mieliluotsi proposes (e.g. thinking traps) – the client decides
    suggestedSource: Optional[TextSource] = None
    examples: list[str] = []  # example texts the client may take and edit (alternative thoughts, experiment plans)
    examplesSource: Optional[TextSource] = None
    steps: list[dict[str, Any]] = []  # proposed exposure ladder steps {text, expected}
    skippable: bool = False
    skipLabel: str = ''
    data: dict[str, Any] = {}


class ChatMessage(BaseModel):
    id: str
    clientId: str
    role: Literal['client', 'assistant']
    text: str
    createdAt: str
    safetyLevel: int = 0
    textSource: TextSource = 'client'
    approvedActivityId: Optional[str] = None
    suggestedNextAction: Optional[str] = None
    uncertainty: Optional[str] = None
    guardViolations: list[str] = []
    retained: bool = True
    kind: Literal['text', 'question', 'answer', 'skip', 'summary', 'offer', 'notice'] = 'text'
    sessionId: Optional[str] = None
    stepKey: Optional[str] = None
    widget: Optional[ChatWidget] = None
    value: Any = None  # the structured value of a client's answer
    answered: bool = False  # an offer that was already acted on


# --- Guided practice (CBT) -----------------------------------------------------------------------------------------

GuidedTool = Literal['checkin', 'thought_record', 'experiment', 'experiment_review', 'exposure', 'exposure_attempt']


class GuidedSession(Provenance):
    """One structured conversation in the chat (a check-in or a CBT tool). Rules decide the steps; a model only phrases."""
    id: str
    clientId: str
    tool: GuidedTool
    status: Literal['active', 'completed', 'stopped', 'expired']
    step: Optional[str] = None
    answers: dict[str, Any] = {}
    context: dict[str, Any] = {}  # prefill and links (taskId, ladderId, experimentId, thoughtRecordId, checkInId)
    startedFrom: str = 'chat'  # chat | home | library | task | agent | offer | demo
    resultId: Optional[str] = None
    mode: Mode = 'waiting_support'
    endedAt: Optional[str] = None


class ThoughtRecord(Provenance):
    """"Ajatuspäiväkirja" – private to the client unless they share the entry."""
    id: str
    clientId: str
    sessionId: Optional[str] = None
    situation: str
    thought: str
    emotions: list[str] = []
    intensityBefore: Optional[int] = None  # 0–10
    behaviour: str = ''
    traps: list[str] = []  # the thinking traps the client recognised
    suggestedTraps: list[str] = []  # what Mieliluotsi proposed (kept apart from the client's choice)
    evidenceFor: str = ''
    evidenceAgainst: str = ''
    alternative: str = ''
    intensityAfter: Optional[int] = None  # 0–10
    nextStep: str = 'none'
    shared: bool = False  # the client shares this entry with their therapist
    mode: Mode = 'waiting_support'


class Experiment(Provenance):
    """"Käyttäytymiskoe" – a feared prediction tested with a small, safe experiment."""
    id: str
    clientId: str
    sessionId: Optional[str] = None
    thoughtRecordId: Optional[str] = None
    prediction: str
    beliefBefore: Optional[int] = None  # 0–10
    plan: str
    plannedFor: Optional[str] = None
    status: Literal['planned', 'done', 'cancelled'] = 'planned'
    outcome: str = ''
    learned: str = ''
    beliefAfter: Optional[int] = None
    reviewedAt: Optional[str] = None
    taskId: Optional[str] = None
    shared: bool = False
    mode: Mode = 'waiting_support'


class ExposureAttempt(BaseModel):
    id: str
    date: str
    before: Optional[int] = None  # 0–10
    peak: Optional[int] = None
    after: Optional[int] = None
    note: str = ''


class ExposureStep(BaseModel):
    id: str
    text: str
    expected: int  # expected anxiety 0–10
    status: Literal['todo', 'doing', 'done'] = 'todo'
    attempts: list[ExposureAttempt] = []


class ExposureLadder(Provenance):
    """"Altistusporras" – graded exposure, easiest step first, at the client's own pace."""
    id: str
    clientId: str
    sessionId: Optional[str] = None
    goal: str
    goalAnxiety: Optional[int] = None
    steps: list[ExposureStep] = []
    status: Literal['active', 'completed', 'archived'] = 'active'
    shared: bool = False
    mode: Mode = 'waiting_support'


class PracticeTask(Provenance):
    """"Tehtävät" – agreed practice with a day: an exposure step, an experiment, an activity or the therapist's homework."""
    id: str
    clientId: str
    kind: Literal['exposure_step', 'experiment', 'activity', 'homework']
    title: str
    detail: str = ''
    dueDate: Optional[str] = None
    status: Literal['open', 'done', 'skipped'] = 'open'
    sourceId: Optional[str] = None  # ladder / experiment / activity id
    stepId: Optional[str] = None
    tool: Optional[str] = None  # homework: the guided tool to use
    assignedBy: str = 'client'  # client | agent:SupportAgent | therapist:<id>
    reminderSentAt: Optional[str] = None
    completedAt: Optional[str] = None
    mode: Mode = 'waiting_support'


# --- Therapists and matching ---------------------------------------------------------------------------------------

class WeeklyTime(BaseModel):
    weekday: int
    time: str
    formats: list[Literal['remote', 'in_person']]


class Therapist(BaseModel):
    id: str
    name: str
    professionalRole: str
    roleCategory: Literal['psychotherapist', 'psychologist', 'short_therapist', 'psychiatric_nurse']
    gender: Literal['female', 'male', 'other']  # used only if a client explicitly states a preference
    languages: list[Language]
    specialties: list[str]
    ageGroups: list[str]
    serviceCategories: list[str]
    workingStyle: str
    therapeuticApproaches: list[str]
    structuredLevel: int  # 1 exploratory … 5 structured
    directiveLevel: int  # 1 reflective … 5 actively challenging
    exerciseLevel: int  # 1 conversation … 5 concrete exercises
    homeworkLevel: int  # 1 none … 5 regular homework
    remote: bool
    inPerson: bool
    locations: list[str]
    accessibility: list[str] = []
    availableTimes: list[WeeklyTime] = []
    leadTimeDays: int = 7
    weeklyContinuity: bool = True
    currentCapacity: int
    maxCapacity: int
    active: bool = True
    inactiveReason: Optional[str] = None
    exclusionCriteria: list[str] = []
    bio: str = ''
    synthetic: bool = True


class TherapistAvailability(Provenance):
    """One bookable appointment slot, materialised from the therapist's calendar."""
    id: str
    therapistId: str
    start: str  # YYYY-MM-DDTHH:MM
    formats: list[Literal['remote', 'in_person']]
    status: Literal['free', 'booked'] = 'free'
    bookedByClientId: Optional[str] = None


class MatchComponent(BaseModel):
    key: str
    label: str
    weight: float
    score: float
    points: float
    explanation: str


class FilterOutcome(BaseModel):
    key: str
    label: str
    passed: bool
    reason: str


class MatchCandidate(BaseModel):
    id: str
    runId: str
    clientId: str
    therapistId: str
    rank: int
    totalPoints: float
    label: Literal['strong', 'good', 'possible']
    labelText: str
    components: list[MatchComponent]
    reasons: list[str]  # "Miksi Anna?" ✓ rows
    unmetPreferences: list[str]  # "Mitä toiveita ei pystytty täyttämään?"
    firstSlotId: Optional[str] = None
    firstSlotStart: Optional[str] = None
    explanation: str
    explanationSource: TextSource
    dataUsed: list[str]
    dataNotUsed: list[str] = []
    status: Literal['proposed', 'selected', 'not_selected', 'superseded'] = 'proposed'


class MatchRun(BaseModel):
    id: str
    trigger: str
    createdAt: str
    configVersion: str
    therapistId: Optional[str] = None
    clientIds: list[str] = []
    excluded: dict[str, list[dict[str, Any]]] = {}
    inputs: dict[str, dict[str, Any]] = {}  # the exact matching input per client (for transparency and tests)


class MatchDecision(Provenance):
    id: str
    clientId: str
    runId: str
    status: Literal['held_for_review', 'proposed_to_client', 'client_selected', 'superseded', 'no_candidates']
    candidateIds: list[str] = []
    shownCount: int = 3
    selectedCandidateId: Optional[str] = None
    helpRequested: bool = False
    releasedAt: Optional[str] = None
    selectedAt: Optional[str] = None
    bookingId: Optional[str] = None


class Booking(Provenance):
    id: str
    clientId: str
    therapistId: str
    slotId: str
    start: str
    format: str
    sessionNumber: int = 1
    status: Literal['booked', 'completed', 'cancelled'] = 'booked'


class MatchFeedback(Provenance):
    """"Miltä yhteistyö terapeutin kanssa tuntuu?" – never triggers an automatic rematch."""
    id: str
    clientId: str
    therapistId: str
    afterSession: int
    heard: int  # 1–5
    goalsUnderstood: int  # 1–5
    styleFit: int  # 1–5
    wantContinue: Literal['yes', 'unsure', 'no']
    wantDiscussAlternative: bool
    note: str = ''
    negative: bool
    reviewTaskId: Optional[str] = None


class TherapyEpisode(Provenance):
    id: str
    clientId: str
    therapistId: str
    bookingId: str
    status: Literal['planned', 'active', 'ended'] = 'planned'
    firstSessionAt: str
    startedAt: Optional[str] = None
    endedAt: Optional[str] = None
    sessionsHeld: int = 0
    configurationId: Optional[str] = None


class TherapistAgentConfiguration(Provenance):
    """The therapist-defined boundaries for Mieliluotsi between sessions."""
    id: str
    clientId: str
    therapistId: str
    primaryGoal: str
    allowedActivityIds: list[str]
    allowedTools: list[str] = []  # guided CBT tools the client may use between sessions
    homeworkTool: Optional[str] = None  # a weekly between-session task ("välitehtävä")
    homeworkNote: str = ''
    checkInsPerWeek: int
    checkInDays: list[int]
    track: str
    doNotAddress: str = ''
    version: int = 1
    active: bool = True


class AftercarePlan(Provenance):
    """"Seuranta terapian jälkeen": the therapist's maintenance plan once therapy has ended."""
    id: str
    clientId: str
    therapistId: str
    checkInsPerWeek: int = 1
    checkInDays: list[int] = []
    allowedTools: list[str] = []
    maintenance: str = ''  # what helped and what to keep practising – written by the therapist
    warningSigns: str = ''
    active: bool = True


# --- Handover ------------------------------------------------------------------------------------------------------

class HandoverSource(BaseModel):
    kind: str
    id: Optional[str] = None
    at: Optional[str] = None
    label: str


class HandoverSection(BaseModel):
    key: str
    title: str
    infoType: Literal['user_said', 'measured', 'ai_summary', 'professional_note', 'system']
    removable: bool = True
    editable: bool = False
    removed: bool = False
    edited: bool = False
    available: bool = True
    unavailableReason: Optional[str] = None
    content: Any = None
    text: Optional[str] = None
    sources: list[HandoverSource] = []
    note: Optional[str] = None


class HandoverEdits(BaseModel):
    removedSections: list[str] = []
    sectionTexts: dict[str, str] = {}
    questions: list[str] = []
    questionsEdited: bool = False
    includeChatHistory: bool = False  # never on by default


class HandoverSummary(Provenance):
    id: str
    clientId: str
    therapistId: Optional[str] = None
    status: Literal['draft', 'approved', 'withdrawn']
    version: int = 1
    edits: HandoverEdits = Field(default_factory=HandoverEdits)
    aiDraft: Optional[str] = None
    aiDraftSource: Optional[TextSource] = None
    suggestedQuestions: list[str] = []
    approvedSnapshot: Optional[list[HandoverSection]] = None
    approvedAt: Optional[str] = None
    withdrawnAt: Optional[str] = None
    consentScope: str = 'client_approved_sections'


class ProfessionalNote(Provenance):
    id: str
    clientId: str
    author: str
    text: str
    includeInHandover: bool = False
    observationId: Optional[str] = None


class PendingSlotOpening(BaseModel):
    id: str
    therapistId: str
    reason: str
    capacityChange: int = -1
    status: Literal['pending', 'opened'] = 'pending'


# --- Root ------------------------------------------------------------------------------------------------------------

class ValitukiState(BaseModel):
    version: str = STATE_VERSION
    synthetic: bool = True
    currentDate: str
    clockDate: str = ''
    clockMinutes: int = 0
    clockReact: bool = False
    demoStartDate: str
    users: list[User] = []
    clients: list[ClientProfile] = []
    referrals: list[Referral] = []
    episodes: list[WaitingListEpisode] = []
    consentRecords: list[ConsentRecord] = []
    intakes: list[IntakeSession] = []
    insights: list[ClientInsight] = []
    insightPermissions: list[InsightPermission] = []
    goals: list[Goal] = []
    fitProfiles: list[TherapyFitProfile] = []
    checkIns: list[CheckIn] = []
    metrics: list[WellbeingMetric] = []
    wellbeingObservations: list[WellbeingObservation] = []
    safetyObservations: list[SafetyObservation] = []
    tasks: list[ProfessionalReviewTask] = []
    activityCompletions: list[ActivityCompletion] = []
    events: list[AgentEvent] = []
    actions: list[AgentAction] = []
    therapists: list[Therapist] = []
    slots: list[TherapistAvailability] = []
    pendingSlotOpenings: list[PendingSlotOpening] = []
    matchRuns: list[MatchRun] = []
    matchCandidates: list[MatchCandidate] = []
    matchDecisions: list[MatchDecision] = []
    bookings: list[Booking] = []
    matchFeedback: list[MatchFeedback] = []
    therapyEpisodes: list[TherapyEpisode] = []
    therapistConfigs: list[TherapistAgentConfiguration] = []
    aftercarePlans: list[AftercarePlan] = []
    guidedSessions: list[GuidedSession] = []
    thoughtRecords: list[ThoughtRecord] = []
    experiments: list[Experiment] = []
    ladders: list[ExposureLadder] = []
    practiceTasks: list[PracticeTask] = []
    handovers: list[HandoverSummary] = []
    notes: list[ProfessionalNote] = []
    audit: list[AuditEvent] = []
    notifications: list[Notification] = []
    chat: list[ChatMessage] = []
    counters: dict[str, int] = Field(default_factory=dict)
