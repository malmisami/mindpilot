import { post, put, request } from '../lib/http';
import type { AftercareInput, AICheck, AIStatus, ConsentScope, FeelingProposal, Mutation, PlanInput, ValitukiView } from './types';

/** Which client / therapist the returned view should be built for. */
export interface ViewScope { clientId: string | null; therapistId: string | null }

const BASE = '/api/valituki';

function qs(scope: ViewScope): string {
  const params = new URLSearchParams();
  if (scope.clientId) params.set('clientId', scope.clientId);
  if (scope.therapistId) params.set('therapistId', scope.therapistId);
  const text = params.toString();
  return text ? `?${text}` : '';
}

const del = <T>(path: string) => request<T>(path, { method: 'DELETE' });

export const api = {
  view: (scope: ViewScope) => request<ValitukiView>(`${BASE}/view${qs(scope)}`),

  // client – conversational intake
  // No separate intake conversation: the starting profile comes from the referral and the assessment visit, with consent.
  intakeStart: (s: ViewScope, id: string, consent: ConsentScope) =>
    post<Mutation>(`${BASE}/clients/${id}/intake/start${qs(s)}`, { ...consent, fromRecords: true }),
  intakeAnswer: (s: ViewScope, id: string, text: string) =>
    post<Mutation<{ safety?: { level: number } }>>(`${BASE}/clients/${id}/intake/answer${qs(s)}`, { text }),
  intakeSkip: (s: ViewScope, id: string) => post<Mutation>(`${BASE}/clients/${id}/intake/skip${qs(s)}`),
  intakeFinish: (s: ViewScope, id: string) => post<Mutation>(`${BASE}/clients/${id}/intake/finish${qs(s)}`),
  updateProposal: (s: ViewScope, id: string, proposalId: string, changes: { text?: string; included?: boolean; structured?: Record<string, unknown> }) =>
    put<Mutation>(`${BASE}/clients/${id}/intake/proposals/${proposalId}${qs(s)}`, changes),
  intakeConfirm: (s: ViewScope, id: string) => post<Mutation>(`${BASE}/clients/${id}/intake/confirm${qs(s)}`),
  intakeComplete: (s: ViewScope, id: string, body: { checkInDays: number[]; communicationStyle: 'brief' | 'warm'; mood?: number; anxiety?: number | null;
    contactChannel?: 'app' | 'phone'; callTime?: string }) =>
    post<Mutation>(`${BASE}/clients/${id}/intake/complete${qs(s)}`, body),
  /** "Miten voit tänään?" on the home screen right after the intake – the first point of the client's own baseline. */
  recordBaseline: (s: ViewScope, id: string, body: { mood: number; anxiety: number | null }) =>
    post<Mutation>(`${BASE}/clients/${id}/baseline${qs(s)}`, body),
  /** A wellbeing call: the client's own words → a proposed 1–5 level that they confirm or correct. */
  callFeeling: (s: ViewScope, id: string, scale: 'mood' | 'anxiety', text: string) =>
    post<Mutation<FeelingProposal>>(`${BASE}/clients/${id}/call/feeling${qs(s)}`, { scale, text }),

  // client – support
  setConsent: (s: ViewScope, id: string, changes: Partial<ConsentScope>) => put<Mutation>(`${BASE}/clients/${id}/consent${qs(s)}`, changes),
  checkIn: (s: ViewScope, id: string, body: { mood: number; anxiety?: number | null; changes: Record<string, string>; noChange: boolean; note: string; trackScore?: number | null }) =>
    post<Mutation<{ safetyLevel: number }>>(`${BASE}/clients/${id}/checkins${qs(s)}`, body),
  completeActivity: (s: ViewScope, id: string, activityId: string, rating: number | null) =>
    post<Mutation>(`${BASE}/clients/${id}/activities/${activityId}/complete${qs(s)}`, { rating, note: '' }),
  skipActivity: (s: ViewScope, id: string, activityId: string) => post<Mutation>(`${BASE}/clients/${id}/activities/${activityId}/skip${qs(s)}`),
  decideInsight: (s: ViewScope, id: string, insightId: string, decision: 'approve' | 'reject') =>
    post<Mutation>(`${BASE}/clients/${id}/insights/${insightId}/decision${qs(s)}`, { decision }),
  editInsight: (s: ViewScope, id: string, insightId: string, text: string) => put<Mutation>(`${BASE}/clients/${id}/insights/${insightId}${qs(s)}`, { text }),
  setSharing: (s: ViewScope, id: string, insightId: string, sharing: { professional: boolean; matching: boolean }) =>
    put<Mutation>(`${BASE}/clients/${id}/insights/${insightId}/sharing${qs(s)}`, sharing),
  removeInsight: (s: ViewScope, id: string, insightId: string) => del<Mutation>(`${BASE}/clients/${id}/insights/${insightId}${qs(s)}`),
  sendMessage: (s: ViewScope, id: string, text: string) =>
    post<Mutation<{ safety: { level: number } }>>(`${BASE}/clients/${id}/messages${qs(s)}`, { text }),
  // client – guided practice in the chat (check-in and CBT tools) and agreed tasks
  startPractice: (s: ViewScope, id: string, tool: string, prefill: Record<string, unknown> = {}, startedFrom = 'chat') =>
    post<Mutation<{ sessionId: string; tool: string }>>(`${BASE}/clients/${id}/practice/start${qs(s)}`, { tool, prefill, startedFrom }),
  answerPractice: (s: ViewScope, id: string, body: { sessionId: string | null; stepKey: string | null; value?: unknown; skip?: boolean }) =>
    post<Mutation<{ safety: { level: number } }>>(`${BASE}/clients/${id}/practice/answer${qs(s)}`, body),
  stopPractice: (s: ViewScope, id: string, sessionId: string | null) => post<Mutation>(`${BASE}/clients/${id}/practice/stop${qs(s)}`, { sessionId }),
  chooseOffer: (s: ViewScope, id: string, messageId: string, option: string) =>
    post<Mutation<Record<string, unknown>>>(`${BASE}/clients/${id}/chat/offer${qs(s)}`, { messageId, option }),
  clientTaskAction: (s: ViewScope, id: string, taskId: string, action: 'done' | 'later' | 'skip') =>
    post<Mutation<Record<string, unknown>>>(`${BASE}/clients/${id}/tasks/${taskId}${qs(s)}`, { action }),
  setPracticeSharing: (s: ViewScope, id: string, kind: string, itemId: string, shared: boolean) =>
    put<Mutation>(`${BASE}/clients/${id}/practice/${kind}/${itemId}/sharing${qs(s)}`, { shared }),
  removePracticeItem: (s: ViewScope, id: string, kind: string, itemId: string) => del<Mutation>(`${BASE}/clients/${id}/practice/${kind}/${itemId}${qs(s)}`),
  requestHuman: (s: ViewScope, id: string, reason: string, message: string) =>
    post<Mutation<{ safety: { level: number } }>>(`${BASE}/clients/${id}/request-human${qs(s)}`, { reason, message }),
  helpNow: (s: ViewScope, id: string) => post<Mutation>(`${BASE}/clients/${id}/help-now${qs(s)}`),
  dismissSafety: (s: ViewScope, id: string) => post<Mutation>(`${BASE}/clients/${id}/safety/dismiss${qs(s)}`),
  selectCandidate: (s: ViewScope, id: string, candidateId: string) => post<Mutation>(`${BASE}/clients/${id}/matches/select${qs(s)}`, { candidateId }),
  moreCandidates: (s: ViewScope, id: string) => post<Mutation<{ added: number }>>(`${BASE}/clients/${id}/matches/more${qs(s)}`),
  matchingHelp: (s: ViewScope, id: string, note: string) => post<Mutation>(`${BASE}/clients/${id}/matches/help${qs(s)}`, { note }),
  toggleChecklist: (s: ViewScope, id: string, itemId: string, done: boolean) =>
    post<Mutation>(`${BASE}/clients/${id}/checklist${qs(s)}`, { itemId, done }),
  updateHandover: (s: ViewScope, id: string, change: { action: 'remove' | 'restore' | 'edit'; section: string; text?: string; questions?: string[] }) =>
    put<Mutation>(`${BASE}/clients/${id}/handover${qs(s)}`, change),
  approveHandover: (s: ViewScope, id: string) => post<Mutation>(`${BASE}/clients/${id}/handover/approve${qs(s)}`),
  withdrawHandover: (s: ViewScope, id: string) => post<Mutation>(`${BASE}/clients/${id}/handover/withdraw${qs(s)}`),
  matchFeedback: (s: ViewScope, id: string, body: { heard: number; goalsUnderstood: number; styleFit: number; wantContinue: string; wantDiscussAlternative: boolean; note: string }) =>
    post<Mutation<boolean>>(`${BASE}/clients/${id}/match-feedback${qs(s)}`, body),
  markNotificationsRead: (s: ViewScope, id: string) => post<Mutation>(`${BASE}/clients/${id}/notifications/read${qs(s)}`),

  // professional
  reviewObservation: (s: ViewScope, observationId: string, action: 'mark_reviewed' | 'contact' | 'no_action' | 'frequency', note = '', perWeek?: number) =>
    post<Mutation<{ reviewCompleted: boolean; outcome: string }>>(`${BASE}/observations/${observationId}/review${qs(s)}`, { action, note, perWeek }),
  taskAction: (s: ViewScope, taskId: string, action: 'contact' | 'complete' | 'close', note = '') =>
    post<Mutation>(`${BASE}/tasks/${taskId}/action${qs(s)}`, { action, note }),
  setFrequency: (s: ViewScope, id: string, perWeek: number) => post<Mutation>(`${BASE}/clients/${id}/checkin-frequency${qs(s)}`, { perWeek }),
  setUrgency: (s: ViewScope, id: string, urgency: 'non_urgent' | 'urgent', reason: string) =>
    post<Mutation>(`${BASE}/clients/${id}/urgency${qs(s)}`, { urgency, reason }),
  addNote: (s: ViewScope, id: string, text: string, includeInHandover: boolean) =>
    post<Mutation>(`${BASE}/clients/${id}/notes${qs(s)}`, { text, includeInHandover }),
  runMatching: (s: ViewScope, id: string) => post<Mutation>(`${BASE}/clients/${id}/matching/run${qs(s)}`),

  // therapist
  savePlan: (s: ViewScope, therapistId: string, clientId: string, plan: PlanInput) =>
    put<Mutation>(`${BASE}/therapists/${therapistId}/clients/${clientId}/plan${qs(s)}`, plan),
  holdFirstSession: (s: ViewScope, therapistId: string, clientId: string) =>
    post<Mutation<{ days: number }>>(`${BASE}/therapists/${therapistId}/clients/${clientId}/first-session${qs(s)}`),
  endTherapy: (s: ViewScope, therapistId: string, clientId: string, plan: AftercareInput) =>
    post<Mutation>(`${BASE}/therapists/${therapistId}/clients/${clientId}/end-therapy${qs(s)}`, plan),

  // demo controls
  advance: (s: ViewScope, days: number) => post<Mutation<{ days: number; agentActions: number }>>(`${BASE}/demo/advance${qs(s)}`, { days }),
  openSlot: (s: ViewScope) => post<Mutation<{ therapistName: string; reason: string; matchedClients: string[] }>>(`${BASE}/demo/open-slot${qs(s)}`),
  deteriorate: (s: ViewScope, clientId: string) =>
    post<Mutation<{ days: number; trendChanged: boolean; currentDate: string }>>(`${BASE}/demo/deteriorate${qs(s)}`, { clientId }),
  stabilize: (s: ViewScope, clientId: string) => post<Mutation<{ days: number; checkIns: number }>>(`${BASE}/demo/stabilize${qs(s)}`, { clientId }),
  firstSession: (s: ViewScope, clientId: string) => post<Mutation<{ days: number }>>(`${BASE}/demo/first-session${qs(s)}`, { clientId }),
  crisis: (s: ViewScope) => post<Mutation>(`${BASE}/demo/crisis${qs(s)}`),
  demoEndTherapy: (s: ViewScope, clientId: string) =>
    post<Mutation<{ days: number; sessions: number }>>(`${BASE}/demo/end-therapy${qs(s)}`, { clientId }),
  reset: (s: ViewScope) => post<Mutation>(`${BASE}/demo/reset${qs(s)}`),
  aiMode: (s: ViewScope, mode: AIStatus['configuredMode']) =>
    put<Mutation<AIStatus & { check: AICheck | null }>>(`${BASE}/ai/mode${qs(s)}`, { mode }),
  aiCheck: (s: ViewScope) => post<Mutation<AIStatus & { check: AICheck }>>(`${BASE}/ai/check${qs(s)}`),
  scene: (s: ViewScope, scene: string) => post<Mutation<{ scene: string }>>(`${BASE}/demo/scene${qs(s)}`, { scene }),
};
