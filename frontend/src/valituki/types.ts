/* View models returned by the Mieliluotsi API (backend/app/valituki/view.py). The UI never computes state itself. */

export type Role = 'client' | 'professional' | 'therapist' | 'pitch';
export type TextSource = 'demo' | 'live' | 'fallback' | 'fixed' | 'client';
export type InfoType = 'user_said' | 'measured' | 'ai_summary' | 'professional_note' | 'system';
export type Direction = 'worse' | 'better';

export interface Mutation<T = unknown> { result: T; view: ValitukiView }

/** A wellbeing call: where the client's own words fall on the 1–5 scale – a proposal they confirm or correct. Only
    `safety` comes back when a safety rule stopped the call. */
export interface FeelingProposal {
  safety: { level: number };
  scale?: 'mood' | 'anxiety'; value?: number | null; label?: string | null; reflection?: string; source?: string;
}

export interface SafetyContact { id: string; label: string; action: string; number: string; tel: string; when: string }

export interface ApprovedActivity {
  id: string; title: string; description: string; purpose: string; estimatedDuration: number; steps: string[]; caution: string;
  suitableFor: string[]; avoidWhen: string[]; topics: string[]; sourcePlaceholder: string; version: string; approvedAt: string;
  approvedBy: string;
}

export interface AIStatus {
  configuredMode: 'DEMO_AI_MODE' | 'LIVE_AI_MODE'; effectiveMode: 'DEMO_AI_MODE' | 'LIVE_AI_MODE'; keyPresent: boolean;
  model: string | null; note: string;
  lastCall: { task: string | null; ok: boolean | null; failure: string | null; ms: number | null; model: string | null };
}

/** A small call through the conversation's own path: did Claude answer, and how fast. */
export interface AICheck { ok: boolean; failure: string | null; reply: string | null; ms: number | null; model: string | null }

export interface Meta {
  appName: string; tagline: string; syntheticNotice: string; notMedicalDevice: string; disclaimers: string[];
  ai: AIStatus;
  currentDate: string; demoStartDate: string; legacyEnabled: boolean;
  labels: {
    topics: Record<string, string>; languages: Record<string, string>; formats: Record<string, string>; times: Record<string, string>;
    weekdays: string[]; weekdaysShort: string[];
    styleDimensions: Record<string, { label: string; values: Record<string, string> }>;
    domains: Record<string, string>; moodScale: Record<string, string>; anxietyScale: Record<string, string>;
    practiceKinds: Record<string, string>;
    consents: Record<string, { title: string; description: string }>;
    infoTypes: Record<InfoType, string>; insightCategories: Record<string, string>; insightOrigins: Record<string, string>;
    contactReasons: Record<string, string>; journeyStates: Record<string, string>; events: Record<string, string>;
    safetyLevels: Record<string, string>; trendDirections: Record<string, string>; agents: Record<string, string>;
    agentDescriptions: Record<string, string>; urgency: Record<string, string>; serviceCategories: Record<string, string>;
  };
  safety: { contacts: SafetyContact[]; screen: { title: string; notEmergency: string; intro: string; demoNote: string; dismiss: string } };
  matching: { version: string; weights: Record<string, number>; labels: { key: string; min: number; text: string }[]; note: string };
  library: { version: string; approvalNote: string; activities: ApprovedActivity[] };
  cbt: { version: string; approvalNote: string; tools: CbtToolMeta[]; traps: { id: string; label: string; description: string }[];
    emotions: { value: string; label: string }[] };
  adapters: { name: string; mock: string; production: string }[];
  routes: Record<string, string[]>;
  checkInFrequencyOptions: { perWeek: number; days: number[]; label: string }[];
}

export interface PresenterStep { n: number; key: string; title: string; done: boolean; hint: string; scene: string }

export interface DemoInfo {
  currentDate: string;
  clients: { id: string; displayName: string; firstName: string; persona: string; journeyState: string; stateLabel: string; demoPrimary: boolean }[];
  therapists: { id: string; name: string }[];
  nextSlotOpening: { therapistName: string; reason: string } | null;
  scenes: { key: string; label: string }[];
  presenter: { steps: PresenterStep[]; next: number | null; nextKey: string | null; hint: string };
}

export interface TimelineEntry {
  id: string; at: string; seq: number; kind: 'agent' | 'client'; agent: string | null; agentLabel: string; title: string;
  detail: string; ruleId: string | null; aiTask: string | null; aiSource: TextSource | null; type: string;
}

export interface Notification {
  id: string; audience: string; clientId: string | null; therapistId: string | null; kind: string; title: string; body: string;
  createdAt: string; read: boolean; actionView: string | null; agent: string | null;
}

export interface ChatOption { value: string; label: string; hint: string | null }

export interface ChatWidget {
  type: 'scale' | 'scale5' | 'choices' | 'multi' | 'traps' | 'text' | 'ladder' | 'offer' | 'summary';
  options: ChatOption[]; min: number; max: number; minLabel: string; maxLabel: string; placeholder: string;
  suggested: string[]; suggestedSource: TextSource | null; examples: string[]; examplesSource: TextSource | null;
  steps: LadderStepInput[]; skippable: boolean; skipLabel: string; data: Record<string, unknown>;
}

export interface LadderStepInput { text: string; expected: number }

export interface SummaryData {
  kind: string; id: string; title: string; rows: { label: string; value: string | string[] }[];
  change: { label: string; before: number | null; after: number | null; peak?: number | null; max: number } | null;
}

export interface ChatMessage {
  id: string; role: 'client' | 'assistant'; text: string; createdAt: string; safetyLevel: number; textSource: TextSource;
  approvedActivityId: string | null; suggestedNextAction: string | null; uncertainty: string | null; guardViolations: string[];
  kind: 'text' | 'question' | 'answer' | 'skip' | 'summary' | 'offer' | 'notice';
  sessionId: string | null; stepKey: string | null; widget: ChatWidget | null; value: unknown; answered: boolean; actionable: boolean;
}

export type ToolId = 'checkin' | 'thought_record' | 'experiment' | 'exposure';

export interface GuidedView {
  id: string; tool: string; title: string; startedFrom: string; stepKey: string | null; stepIndex: number; stepCount: number;
  questionId: string | null; questionText: string | null; widget: ChatWidget | null; demoAnswer: unknown;
}

export interface CbtToolMeta {
  id: ToolId; title: string; kind: string; duration: number; description: string; purpose: string; caution: string;
  sourcePlaceholder: string; version: string; topics?: string[];
}

export interface PracticeTool extends CbtToolMeta { allowed: boolean; lockedReason: string | null; count: number }

export interface PracticeTask {
  id: string; kind: 'exposure_step' | 'experiment' | 'activity' | 'homework'; kindLabel: string; title: string; detail: string;
  dueDate: string | null; dueLabel: string; overdue: boolean; status: 'open' | 'done' | 'skipped'; actionLabel: string;
  assignedBy: string; assignedByLabel: string; sourceId: string | null; stepId: string | null; tool: string | null;
  completedAt: string | null;
}

export interface ThoughtRecordRow {
  id: string; date: string; situation: string; thought: string; emotions: string[]; intensityBefore: number | null;
  intensityAfter: number | null; behaviour: string; traps: { id: string; label: string }[]; evidenceFor: string;
  evidenceAgainst: string; alternative: string; nextStep: string; shared: boolean; mode: string;
}

export interface ExperimentRow {
  id: string; date: string; prediction: string; beliefBefore: number | null; plan: string; plannedFor: string | null;
  status: 'planned' | 'done' | 'cancelled'; outcome: string; learned: string; beliefAfter: number | null; reviewedAt: string | null;
  shared: boolean;
}

export interface ExposureAttempt { id: string; date: string; before: number | null; peak: number | null; after: number | null; note: string }

export interface LadderRow {
  id: string; date: string; goal: string; goalAnxiety: number | null; status: 'active' | 'completed' | 'archived'; shared: boolean;
  progress: { done: number; total: number };
  steps: { id: string; text: string; expected: number; status: 'todo' | 'doing' | 'done'; attempts: ExposureAttempt[] }[];
}

export interface CompletedItem {
  id: string; kind: string; tag: string; at: string; title: string; detail: string; change: { before: number | null; after: number | null } | null;
}

export interface PracticeStats {
  thoughtRecords: number; avgDrop: number | null; exposureAttempts: number; experiments: number; experimentsDone: number;
  traps: { id: string; label: string; count: number }[];
}

export interface PracticeView {
  tools: PracticeTool[]; tasks: PracticeTask[]; recentTasks: PracticeTask[]; thoughtRecords: ThoughtRecordRow[];
  experiments: ExperimentRow[]; ladders: LadderRow[]; completed: CompletedItem[]; stats: PracticeStats; allowedTools: string[];
}

export interface WeekSummary {
  start: string; end: string; sessions: number;
  days: { date: string; weekday: string; mood: number | null; anxiety: number | null; future: boolean }[];
  cameUp: string[]; steps: string[]; words: string | null;
}

export interface IntakeMessage { id: string; role: 'assistant' | 'client'; text: string; questionKey: string | null; createdAt: string; source: TextSource }

export interface IntakeProposal {
  id: string; category: 'goal' | 'working_style' | 'practical' | 'difficult_times' | 'helped_before'; title: string; text: string;
  structured: Record<string, unknown>; derivedFrom: string[]; userWords: string[]; source: TextSource; included: boolean;
  editedByClient: boolean;
}

export interface ConsentScope { proactiveCheckins: boolean; storeHistory: boolean; professionalMonitoring: boolean; sharePractice: boolean }

export interface IntakeView {
  status: 'not_started' | 'consent' | 'conversation' | 'review' | 'rhythm' | 'completed';
  messages: IntakeMessage[];
  pendingQuestion: { key: string; text: string; demoAnswer: string | null } | null;
  answeredCount: number; canFinish: boolean; proposals: IntakeProposal[]; proposalsSource: TextSource | null;
  consentDefaults: ConsentScope; demoAnswers: Record<string, string> | null;
  demoRhythm: { checkInDays: number[]; communicationStyle: 'brief' | 'warm' } | null; demoMood: number | null;
  plan: { key: string; question: string }[];
}

export interface SeriesPoint {
  id: string; date: string; at: string | null; mood: number | null; anxiety: number | null; kind: string;
  changes: Record<string, Direction>; mode: string; trackScore: number | null; belowBaseline: boolean; note?: string;
}

export interface TodayActivity extends ApprovedActivity { intro: string; introSource: TextSource; reason: string; status: 'suggested' | 'completed' | 'skipped' }

export interface ModeSummary {
  mode: 'waiting_support' | 'therapy_support' | 'aftercare_support'; title: string; controlledBy: string; configured: boolean;
  capabilities: string[]; checkIns?: string; protocol?: string; statement?: string; therapistName?: string; therapistFirstName?: string;
  configuredAt?: string; version?: number; primaryGoal?: string; allowedActivities?: { id: string; title: string }[];
  allowedTools?: { id: string; title: string }[]; homework?: { tool: string; title: string; note: string } | null;
  maintenance?: string; warningSigns?: string; checkInsPerWeek?: number; checkInDays?: string[]; track?: string; doNotAddress?: string;
}

export interface SelfCareResponse { activityId: string; title: string; tried: number; skipped: number; latestRating: number | null; averageRating: number | null; helpful: boolean; lastAt: string | null }

export interface FitProfile {
  id: string; version: number; goals: { primary: GoalRef[]; secondary: GoalRef[] };
  preferredWorkingStyle: Record<string, unknown> & { text?: string; matching?: boolean; professional?: boolean };
  practicalPreferences: Record<string, unknown> & { text?: string; matching?: boolean; professional?: boolean };
  clientApprovedInsights: string[]; selfCareResponses: SelfCareResponse[];
  engagementPreferences: { checkInDays?: number[]; frequencyText?: string; communicationStyle?: string };
  changelog: { version: number; at: string; change: string; agent: string }[];
  styleRows: { key: string; label: string; value: string | null }[];
  practicalRows: { label: string; value: string }[];
}

export interface GoalRef { text: string; topics: string[]; insightId: string; professional: boolean; matching: boolean }

export interface TherapistPublic {
  id: string; name: string; firstName: string; role: string; languages: string[]; specialties: string[]; approaches: string[];
  workingStyle: string; levels: Record<string, number>; formats: string[]; availableTimes: string[]; accessibility: string[]; bio: string;
  syntheticLabel: string;
}

export interface Candidate {
  id: string; rank: number; label: 'strong' | 'good' | 'possible'; labelText: string; therapist: TherapistPublic; reasons: string[];
  unmet: string[]; explanation: string; explanationSource: TextSource; firstSlotStart: string | null; firstSlotText: string;
  status: string; dataUsed: string[]; dataNotUsed: string[];
  components?: { key: string; label: string; weight: number; score: number; points: number; explanation: string }[];
  totalPoints?: number;
}

export interface HandoverSection {
  key: string; title: string; infoType: InfoType; removable: boolean; editable: boolean; removed: boolean; edited: boolean;
  available: boolean; unavailableReason: string | null; content: unknown; text: string | null;
  sources: { kind: string; id: string | null; at: string | null; label: string }[]; note: string | null;
}

export interface HandoverView {
  id: string; status: 'draft' | 'approved' | 'withdrawn'; statusLabel: string; approvedAt: string | null; therapistName: string | null;
  sections: HandoverSection[]; approvedKeys: string[]; aiDraftSource: TextSource | null; chatHistoryIncluded: boolean;
}

export interface BackstageMatch {
  therapistCount: number; ran: boolean; excluded: { name: string; reason: string }[];
  candidates: { id: string; name: string; label: 'strong' | 'good' | 'possible'; labelText: string; total: number; status: string;
    components: { key: string; label: string; score: number }[] }[];
  readiness: Criterion[] | null; chosen: string | null;
}

/** Which therapy approach fits the client: goals and working style, 0–100 by rules. */
export interface BackstageModality {
  version: string;
  rows: { id: string; label: string; total: number; therapists: number;
    components: { key: string; label: string; score: number; known: boolean; detail: string }[] }[];
}

export interface Criterion { key: string; label: string; passed: boolean; detail?: string }

export interface MatchingView {
  stage: 'no_profile' | 'on_hold' | 'building' | 'searching' | 'choose' | 'booked' | 'therapy' | 'aftercare';
  decision: { id: string; status: string; shownCount: number; total: number; canShowMore: boolean; helpRequested: boolean } | null;
  candidates: Candidate[];
  booking: { start: string; startText: string; format: string; status: string; therapist: TherapistPublic } | null;
  checklist: { id: string; text: string; done: boolean }[];
  readiness: Criterion[] | null;
  handover: HandoverView | null;
  feedback: { eligible: boolean; given: { id: string; heard: number; goalsUnderstood: number; styleFit: number; negative: boolean }[] };
}

export interface InsightRow {
  id: string; category: string; kind: string; title: string; text: string; origin: string; originLabel: string; sourceLabel: string;
  date: string; status: string; sharing: { professional: boolean; matching: boolean }; userWords: string[];
  evidence: { basis?: (string | null)[]; checkIns?: number; journalEntries?: number; ruleId?: string };
  editedByClient: boolean; version: number; editable: boolean;
}

export interface Milestone {
  key: string; date: string | null; title: string; text: string; tone: string; quote: string | null; status: 'done' | 'current' | 'upcoming';
  note: string | null;
}

export interface ClientView {
  id: string; displayName: string; firstName: string; age: number; municipality: string; persona: string; journeyState: string;
  stateLabel: string; phase: string; demoPrimary: boolean; modeKey: 'waiting_support' | 'therapy_support' | 'aftercare_support';
  waiting: { soughtHelpAt: string | null; startedAt: string | null; daysWaiting: number | null; estimatedWait: string; service: string;
    statusLabel: string; reviewPending: boolean; reviewText: string | null };
  intake: IntakeView;
  checkIn: { due: { id: string; kind: string; dueDate: string; trackLabel: string | null } | null; nextDate: string | null;
    nextLabel: string | null; days: number[]; frequencyText: string; trackLabel: string | null; proactive: boolean;
    needsBaseline: boolean; channel: 'app' | 'phone'; callTime: string | null };
  trend: { direction: string; label: string; text: string; arrow: string; baseline: number | null; series: SeriesPoint[]; historyStored: boolean };
  today: TodayActivity | null;
  mode: ModeSummary;
  plan: { goals: { id: string; text: string; priority: string }[];
    library: { id: string; title: string; description: string; estimatedDuration: number; allowed: boolean; response: SelfCareResponse | null }[] };
  fitProfile: FitProfile | null;
  matching: MatchingView;
  memory: {
    groups: { key: string; label: string; items: InsightRow[] }[]; pending: InsightRow[]; rejectedCount: number; removedCount: number;
    consent: ConsentScope; consentGivenAt: string | null;
    permissionHistory: { at: string; title: string; professional: boolean; matching: boolean; previous: Record<string, boolean> | null }[];
    fitProfile: { version: number; changelog: { version: number; at: string; change: string; agent: string }[] } | null;
    handover: { status: string; statusLabel: string } | null;
    stored: { checkIns: number; journal: number; messages: number };
  };
  milestones: Milestone[];
  timeline: TimelineEntry[];
  notifications: Notification[];
  unreadCount: number;
  chat: ChatMessage[];
  guided: GuidedView | null;
  practice: PracticeView;
  progress: { series: SeriesPoint[]; week: WeekSummary };
  demoMessage: string | null;
  requests: { id: string; type: string; title: string; status: string; createdAt: string; handlingNote: string; outcome: string | null }[];
  safety: { lockActive: boolean };
  phaseFlags: { matchingReady: boolean; booked: boolean; therapy: boolean; aftercare: boolean };
  /** Presenter-only: the deterministic matching run behind the phone. */
  backstage: { match: BackstageMatch; modality: BackstageModality };
}

export interface ObservationRow {
  id: string; category: 'wellbeing' | 'safety'; kind: string; title: string; level: number | null; status: string; createdAt: string;
  agent: string; ruleId: string; explanation: { kind: string; text: string; count?: number }[]; suggestedAction: string; reason: string;
  aiSummary: string | null; aiSummarySource?: TextSource | null; reviewedBy: string | null; reviewedAt: string | null;
  reviewOutcome: string | null; reviewNote: string | null; requiresReview: boolean; clientAcknowledgedAt: string | null;
}

/** A made-up profile of the background cohort, shown in a filtered queue to illustrate the group. */
export interface QueueSample {
  bucket: string; name: string; age: number; waitingDays: number; lastCheckIn: string; trend: string; trendArrow: string; trendLabel: string;
  latestObservation: string | null; reviewKey: string; reviewLabel: string; matchingStatus: string; nextAction: string;
}

export interface QueueRow {
  clientId: string; name: string; firstName: string; persona: string; demoPrimary: boolean; journeyState: string; stateLabel: string;
  waitingDays: number | null; lastCheckIn: string | null; trend: string; trendArrow: string; trendLabel: string;
  latestObservation: string | null; latestObservationStatus: string | null; reviewKey: string; reviewLabel: string;
  matchingStatus: string; nextAction: string; urgency: string; mode: string; bucket: string | null;
}

export interface ProfessionalClient {
  id: string; displayName: string; firstName: string; age: number; municipality: string; persona: string; journeyState: string;
  stateLabel: string; phase: string; mode: string; demoPrimary: boolean;
  referral: { referrer: string; assessedBy: string; summary: string; serviceLabel: string; requiredLabels: string[]; soughtHelpAt: string;
    referredAt: string } | null;
  waitingDays: number | null;
  urgency: { value: string; label: string; setBy: string; setAt: string; history: { at: string; from: string | null; to: string; by: string; reason: string }[] } | null;
  consent: ConsentScope; monitoring: boolean;
  observations: ObservationRow[]; openReview: ObservationRow | null;
  trend: { direction: string; label: string; arrow: string; text: string; baseline: number | null; recent: number | null; series: SeriesPoint[];
    signals: { kind: string; text: string }[] };
  checkIns: { id: string; dueDate: string; kind: string; status: string; mood: number | null; anxiety: number | null;
    changes: Record<string, Direction>;
    completedAt: string | null; hasNote: boolean; trackScore: number | null }[];
  checkInSettings: { days: number[]; text: string; next: string | null; paused: boolean };
  insights: { visible: { id: string; category: string; kind: string; title: string; text: string; origin: string; sourceLabel: string;
    matching: boolean; approvedAt: string | null }[]; hiddenCount: number };
  fitProfile: FitProfile | null;
  matching: { decision: { id: string; status: string; shownCount: number; helpRequested: boolean } | null; candidates: Candidate[];
    excluded: { therapistId: string; name: string; failed: { key: string; label: string; reason: string }[] }[];
    input: Record<string, unknown> | null; run: { id: string; trigger: string; createdAt: string; configVersion: string } | null;
    eligibleForRun: boolean; readiness: Criterion[] };
  booking: { start: string; startText: string; therapistName: string; format: string; status: string } | null;
  handover: { status: string; statusLabel: string } | null;
  therapy: { mode: ModeSummary; configured: boolean };
  tasks: { id: string; type: string; title: string; reason: string; status: string; agent: string; suggestedAction: string;
    createdAt: string; outcome: string | null; handlingNote: string; underlyingData: Record<string, unknown>; observationId: string | null }[];
  notes: { id: string; author: string; text: string; createdAt: string; includeInHandover: boolean }[];
  matchFeedback: { id: string; heard: number; goalsUnderstood: number; styleFit: number; wantContinue: string; negative: boolean; note: string }[];
  timeline: TimelineEntry[];
  safetyLockActive: boolean;
  reviewStatus: { key: string; label: string };
}

export interface DirectoryRow extends TherapistPublic {
  active: boolean; inactiveReason: string | null; currentCapacity: number; maxCapacity: number; ageGroups: string[];
  serviceCategories: string[]; exclusionCriteria: string[]; nextAvailableSlot: string | null; freeSlots: number; clients: number;
}

export interface AgentAction {
  id: string; seq: number; agent: string; agentLabel: string; clientId: string | null; clientName: string | null; type: string;
  title: string; detail: string; ruleId: string | null; createdAt: string; aiTask: string | null; aiSource: TextSource | null; visibility: string;
}

export interface ImpactMetric { key: string; label: string; before?: string; after?: string; value?: string; detail: string; demoValue?: string }

export interface ProfessionalView {
  coordinatorName: string;
  overview: { total: number; buckets: { key: string; label: string; value: number; live: number }[]; syntheticNote: string; liveClients: number; note: string;
    samples: QueueSample[]; samplesNote: string };
  queue: QueueRow[];
  details: Record<string, ProfessionalClient>;
  notifications: Notification[];
  directory: DirectoryRow[];
  timeline: AgentAction[];
  audit: { id: string; seq: number; at: string; actor: string; action: string; detail: string; clientName: string | null }[];
  agents: { name: string; label: string; description: string; actions: number }[];
  impact: { label: string; metrics: ImpactMetric[]; liveNote: string };
  openTasks: number;
}

export interface TherapistClientRow {
  clientId: string; clientName: string; firstName: string; age: number; firstSession: string; format: string; bookingStatus: string;
  handoverStatus: string; approvedAt: string | null; sections: HandoverSection[] | null;
  therapy: {
    episodeStatus: 'planned' | 'active' | 'ended' | null; startedAt: string | null; endedAt: string | null; sessionsHeld: number;
    config: (PlanInput & { version: number; createdAt: string }) | null;
    suggestedPlan: PlanInput | null; suggestedAftercare: AftercareInput | null;
    aftercare: (AftercareInput & { id: string; createdAt: string; checkInDays: number[] }) | null;
    mode: ModeSummary;
    sinceStart: { date: string; mood: number | null; anxiety: number | null; trackScore: number | null }[];
    practice: { allowed: boolean; stats: PracticeStats | null; sharedRecords: ThoughtRecordRow[]; ladders: LadderRow[]; homework: PracticeTask[] };
    canHoldFirstSession: boolean;
  };
  milestones: Milestone[];
}

export interface PlanInput {
  primaryGoal: string; allowedActivityIds: string[]; allowedTools: string[]; homeworkTool: string | null; homeworkNote: string;
  checkInsPerWeek: number; track: string; doNotAddress: string;
}

export interface AftercareInput { checkInsPerWeek: number; allowedTools: string[]; maintenance: string; warningSigns: string }

export interface TherapistView {
  therapists: { id: string; name: string; role: string; clientCount: number }[];
  selected: (TherapistPublic & { currentCapacity: number; maxCapacity: number; clients: TherapistClientRow[]; notifications: Notification[] }) | null;
  library: { id: string; title: string }[];
  tools: { id: string; title: string; kind: string }[];
}

export interface ValitukiView {
  meta: Meta;
  demo: DemoInfo;
  client: ClientView | null;
  professional: ProfessionalView;
  therapist: TherapistView;
}
