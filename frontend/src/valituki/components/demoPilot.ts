import { useCallback, useEffect, useRef, useState } from 'react';
import { asPilotStep } from '../../lib/http';
import { api } from '../api';
import type { ViewScope } from '../api';
import { useValituki } from '../context';
import type { ClientTab } from '../context';
import type { GuidedView, IntakeView, Mutation, ValitukiView } from '../types';
import { chatRevealing, hurryChat } from '../client/chatPace';

/* DEMO-OHJAIN – the presenter presses "Seuraava" (or →) and the demo takes the next step of the concept's story: it
   types the demo text, presses the right button and opens the right view. Every step goes through the same API as a
   click in the app. The stages follow the Konsepti page: avun haku → käyttöönotto esitiedoilla → Mieliluotsi (KKT, seuranta
   ja muutosten tunnistus, Therapy Fit Profile) → terapeutti ja handover → terapia → seuranta terapian jälkeen. */

const AINO = 'cl-aino';
const ANNA = 'th-anna';
const SCOPE: ViewScope = { clientId: AINO, therapistId: ANNA };
const STORAGE_KEY = 'vt-demo-pilot';
const FALLBACK_MESSAGE = 'On Tuesday I have to present the project status to the whole team, and I\'m already terribly nervous about it.';
// The item the client takes out of the first-session summary before approving it (the same in scenes.py).
const DROPPED_SECTION = 'tried';

export type StageKey = 'intro' | 'haku' | 'alku' | 'seuranta' | 'kkt' | 'tfp' | 'terapeutti' | 'terapia' | 'jalkeen';

/** One part of a stage's narration: shown from step `from` (1-based) until the next part of the stage begins. */
export interface TellPart { from: number; heading?: string; text: string }

/** The concept's stages in the order of the Konsepti page; `group` marks the four inside the "Mieliluotsi" box. `tell` is
    the stage's narration beside the panel – the presenter's pitch, spoken as the client – split into the parts
    that belong to what is on the screen, so the column shows the part to read now. */
export const STAGES: { key: StageKey; label: string; group?: 'valituki'; tell: TellPart[] }[] = [
  { key: 'haku', label: 'Seeking help', tell: [
    { from: 1, text: 'Here is a typical situation: the wait before treatment starts is 20–25 weeks. Now, with Mieliluotsi, '
      + 'support starts right away. First, I decide myself which of my information is used and what the care team and the '
      + 'therapist can see.' },
  ] },
  { key: 'alku', label: 'Getting started from records', tell: [
    { from: 2, text: 'There is no new initial assessment. I already described my situation in the referral and at the '
      + 'assessment visit, so I am not asked the same things again. With my permission, Mieliluotsi uses this information: '
      + 'my goals, the way I would like to work, my hardest moments and what has helped before. I can check and edit it on '
      + 'the My data page.' },
    { from: 3, text: 'I choose how Mieliluotsi keeps in touch with me: either I reply in writing in the app, or Mieliluotsi '
      + 'calls me on agreed days, asks how I am doing and does a short thinking exercise with me by talking it through.' },
    { from: 4, text: 'To the right of the phone is a backstage view that the client does not see. My answers and what I do '
      + 'in the app keep updating how well each therapist and therapy approach fits me. This matters, because the therapy '
      + 'approach, the way of working and the working relationship have the biggest effect on treatment outcomes. It is a '
      + 'big change from today, where the therapist is chosen by availability, not by fit. At the same time, my '
      + 'conversations and my other information build a profile that my future therapist will see: my goals, what helps '
      + 'me and how my wellbeing develops while I wait.' },
  ] },
  { key: 'kkt', label: 'Guided CBT practice in the chat', group: 'valituki', tell: [
    { from: 5, text: 'I open the chat and say that Tuesday\'s presentation to the team is already making me nervous. '
      + 'Mieliluotsi does not start giving advice. It asks whether I would like to explore the thought together. I say yes.' },
    { from: 6, text: 'The exercise is cognitive behavioural therapy. It suits the waiting time because it focuses on changing '
      + 'harmful patterns of thinking and behaviour. So it does not go into the root causes of problems, such as childhood '
      + 'trauma. The conversation stays within safety limits and does not get in the way of future treatment. The key is to '
      + 'bring the conversations people have with general AI services onto a supervised platform: conversations without '
      + 'safety limits, where people open up about difficult topics too quickly, are harmful to recovery.' },
    { from: 7, text: 'By the end of the exercise my nervousness has dropped from eight to five. Then we build an exposure '
      + 'ladder: I approach the presentation in small steps, from the easiest to the hardest.' },
  ] },
  { key: 'seuranta', label: 'Tracking mood and anxiety', group: 'valituki', tell: [
    { from: 8, heading: 'Wellbeing check-in', text: 'On the home screen I answer a short wellbeing check-in at the agreed '
      + 'pace: mood and anxiety on a scale from one to five. This way my wellbeing is followed throughout the waiting time. '
      + 'It gives professionals visibility across the whole waiting list.' },
    { from: 9, text: 'In the Progress view I can see how my mood and anxiety have developed. It is a self-assessment, not a '
      + 'diagnosis. My conversations build up into a thought diary that only I can see. I can share a single entry from it '
      + 'with my therapist. The weeks go by. In three check-ins in a row, my wellbeing is at least one point below my own '
      + 'baseline. Mieliluotsi notices the change and tells me about it. It does not change the urgency of my care; '
      + 'instead, it asks a professional to review the situation.' },
    { from: 11, heading: 'Care coordinator\'s view', text: 'I switch to the care coordinator\'s view. There are a thousand '
      + 'synthetic demo clients on the waiting list. Mieliluotsi raises changes for review, and a professional decides. '
      + 'Wellbeing is always compared with the client\'s own baseline, never with other people.' },
    { from: 12, heading: 'Care coordinator\'s view', text: 'I came up on the list because my wellbeing was below my baseline '
      + 'in three check-ins in a row. The coordinator sees the rule the request is based on, and only the information I '
      + 'have given permission to share.' },
    { from: 13, heading: 'Care coordinator\'s view', text: 'I mark the situation as reviewed and change the urgency to '
      + 'urgent. This decision is always made by a professional, not by AI.' },
  ] },
  { key: 'tfp', label: 'An observation refines the therapist profile', group: 'valituki', tell: [
    { from: 14, text: 'I go back to the client\'s app. I approve Mieliluotsi\'s observation: my anxiety is higher on the '
      + 'evenings before working days. It refines the profile that my future therapist will see.' },
  ] },
  { key: 'terapeutti', label: 'The best-fitting available therapist', tell: [
    { from: 15, text: 'When a place opens up with the therapist who fits me best, I get three suggestions with the reasons. '
      + 'Besides the referral, the choice draws on what came up in my conversations while I waited, which I have allowed '
      + 'to be used. The choice is no longer decided by who has free appointments. I can see why Anna is recommended, and I '
      + 'choose her.' },
    { from: 18, heading: 'Summary for the first session', text: 'A summary is put together for Anna for our first '
      + 'meeting. It is a draft. Nothing is shared before I approve it, and the chat history is not shared at all. I remove '
      + 'one item and approve the rest. The first session starts from a ready base.' },
  ] },
  { key: 'terapia', label: 'Therapy + between-session tasks in Mieliluotsi', tell: [
    { from: 20, heading: 'Therapist\'s view', text: 'I switch to the therapist\'s view. Anna sees the summary I approved '
      + 'before our first meeting. For every piece of information she can see whether the client said it in their own '
      + 'words, whether it was measured, or whether AI summarised it. These are never mixed up.' },
    { from: 21, heading: 'Therapist\'s view', text: 'During therapy, Anna decides what Mieliluotsi may offer between '
      + 'sessions. Mieliluotsi works only within the limits she sets.' },
  ] },
  { key: 'jalkeen', label: 'Follow-up after therapy', tell: [
    { from: 24, text: 'Therapy has ended. Mieliluotsi stays on as aftercare, following the maintenance plan Anna drew up. '
      + 'The exercises stay available to me: exploring a thought, the behavioural experiment and the exposure ladder, '
      + 'where five of the six steps are already done.' },
  ] },
];

/** The narration before the first press – the presenter's opening line, shown in the demo control beside the panel. */
export const DEMO_INTRO = 'When someone is referred to therapy, treatment does not begin. Months of passive waiting begin.';

type Where = { role: 'pitch' } | { role: 'client'; tab: ClientTab } | { role: 'professional'; client: string | null } | { role: 'therapist' };

interface PilotCtx {
  /** The newest view: the last mutation's result, or the rendered one. */
  view: () => ValitukiView;
  /** Run one API call for Sami/Anna; resolves to the new view, or null when it failed. */
  mutate: <T>(call: (s: ViewScope) => Promise<Mutation<T>>) => Promise<ValitukiView | null>;
  go: (where: Where) => void;
  /** Scroll the first matching element into view and pulse it; resolves to the element. */
  spot: (selectors: string | string[], block?: 'start' | 'center') => Promise<HTMLElement | null>;
  /** Pauses between replayed answers – skipped when a jump rebuilds a step in the background. */
  pause: (ms: number) => Promise<void>;
  /** Wait until the chat has shown Mieliluotsi's whole reply, bubble by bubble (at once when hurried or rebuilt). */
  settle: () => Promise<void>;
}

export interface Beat {
  stage: StageKey;
  /** What is on the screen after this step – the presenter's cue and the audience's subtitle. */
  title: string;
  say: string;
  /** The state change (same API as the app's buttons). Returns false when it did not succeed. */
  act?: (p: PilotCtx) => Promise<boolean>;
  /** Where to look: role, tab, scroll position and the highlighted element. */
  show: (p: PilotCtx) => Promise<void>;
}

const ok = (view: ValitukiView | null) => view !== null;

/** The intake conversation: the rest of the scripted answers, one at a time. */
async function playIntake(p: PilotCtx): Promise<boolean> {
  let view: ValitukiView | null = p.view();
  for (let i = 0; i < 12; i += 1) {
    const intake: IntakeView | undefined = view?.client?.intake;
    if (!intake || intake.status !== 'conversation') break;
    const question: IntakeView['pendingQuestion'] = intake.pendingQuestion;
    const answer: string | null = question ? intake.demoAnswers?.[question.key] ?? question.demoAnswer : null;
    if (!answer) break;
    await p.pause(i === 0 ? 250 : 900);
    view = await p.mutate((s): Promise<Mutation> => api.intakeAnswer(s, AINO, answer));
  }
  if (view?.client?.intake.status === 'conversation' && view.client.intake.canFinish) {
    view = await p.mutate((s) => api.intakeFinish(s, AINO));
  }
  return ok(view);
}

/** A guided CBT exercise in the chat: the rest of the scripted answers, one at a time – each once Mieliluotsi's reply and
    question are on the screen and there has been a moment to read them. */
async function playGuided(p: PilotCtx): Promise<boolean> {
  let view: ValitukiView | null = p.view();
  for (let i = 0; i < 30; i += 1) {
    const guided: GuidedView | null | undefined = view?.client?.guided;
    if (!guided || guided.demoAnswer === null || guided.demoAnswer === undefined) break;
    await p.settle();
    await p.pause(i === 0 ? 400 : 900);
    view = await p.mutate((s): Promise<Mutation> => api.answerPractice(s, AINO,
      { sessionId: guided.id, stepKey: guided.stepKey, value: guided.demoAnswer }));
  }
  await p.settle();
  return ok(view);
}

export const BEATS: Beat[] = [
  // 1 · Avun haku – the demo starts here, from the prepared start state
  { stage: 'haku', title: 'Sami has sought help and is on the therapy waiting list',
    say: 'Work-related anxiety, short-term therapy, estimated wait 20–25 weeks. Normally this is where the waiting would begin – with Mieliluotsi, support starts right away.',
    act: async (p) => ok(await p.mutate((s) => api.scene(s, 'start'))),
    show: async (p) => { p.go({ role: 'client', tab: 'koti' }); await p.spot('.wait-card'); } },

  // 2 · Käyttöönotto esitiedoilla – no separate intake conversation
  { stage: 'alku', title: 'No new assessment – the existing records are used',
    say: 'Sami has already described the situation in the referral and at the assessment visit. With Sami\'s permission, Mieliluotsi uses this information – the same things are not asked again.',
    act: async (p) => ok(await p.mutate((s) => api.intakeStart(s, AINO, p.view().client?.intake.consentDefaults ?? {
      proactiveCheckins: true, storeHistory: true, professionalMonitoring: true, sharePractice: true }))),
    show: async (p) => { p.go({ role: 'client', tab: 'koti' }); } },
  { stage: 'alku', title: 'In the app or by phone?',
    say: 'Sami chooses how Mieliluotsi keeps in touch: in writing in the app, or Mieliluotsi calls, asks how Sami is doing and does a short thinking exercise.',
    show: async (p) => { p.go({ role: 'client', tab: 'koti' }); await p.spot('.rhythm-screen .radio-cards'); } },
  { stage: 'alku', title: 'A Therapy Fit Profile from the records – Sami can edit it',
    say: 'The goal, the way of working and what has helped are in the therapist profile and in matching (on the right). Sami can edit them on the My data page.',
    act: async (p) => {
      // A conversation left open in an older saved state is played to the end first.
      if (p.view().client?.intake.status === 'conversation' && !(await playIntake(p))) return false;
      if (p.view().client?.intake.status === 'review' && !ok(await p.mutate((s) => api.intakeConfirm(s, AINO)))) return false;
      // The rhythm closes the intake; today's wellbeing is asked on the home screen after the first conversation.
      const intake = p.view().client?.intake;
      const rhythm = intake?.demoRhythm;
      return intake?.status !== 'rhythm' || ok(await p.mutate((s) => api.intakeComplete(s, AINO, {
        checkInDays: rhythm?.checkInDays ?? [0, 2, 5], communicationStyle: rhythm?.communicationStyle ?? 'brief' })));
    },
    show: async (p) => { p.go({ role: 'client', tab: 'koti' }); await p.spot('.bp-doc'); } },

  // 3 · Mieliluotsi: ohjattu KKT-harjoittelu chatissa
  { stage: 'kkt', title: 'Sami talks about a nerve-racking situation',
    say: '“On Tuesday I have to present the project to the whole team…” Mieliluotsi recognises the situation and suggests exploring it together.',
    act: async (p) => {
      const text = p.view().client?.demoMessage ?? FALLBACK_MESSAGE;
      p.go({ role: 'client', tab: 'keskustelu' });
      await p.pause(500);
      const sent = ok(await p.mutate((s) => api.sendMessage(s, AINO, text)));
      await p.settle();
      return sent;
    },
    show: async (p) => { p.go({ role: 'client', tab: 'keskustelu' }); } },
  { stage: 'kkt', title: '“Yes, let\'s explore it” – the guided exercise begins',
    say: 'Exploring a thought, one question at a time. Every question can be skipped, and the exercise can be stopped at any time.',
    act: async (p) => {
      const offer = [...(p.view().client?.chat ?? [])].reverse()
        .find((m) => m.kind === 'offer' && m.actionable && m.widget?.options.some((o) => o.value.startsWith('start:')));
      const option = offer?.widget?.options.find((o) => o.value.startsWith('start:'))?.value;
      const started = offer && option
        ? ok(await p.mutate((s) => api.chooseOffer(s, AINO, offer.id, option)))
        : ok(await p.mutate((s) => api.startPractice(s, AINO, 'thought_record', {}, 'chat')));
      await p.settle();
      return started;
    },
    show: async (p) => { p.go({ role: 'client', tab: 'keskustelu' }); } },
  { stage: 'kkt', title: 'Situation → thought → feeling → thinking trap → more balanced thought → step',
    say: 'Rules decide the steps; the language model only phrases them. At the end a concrete step is agreed: the first step of the exposure ladder, tomorrow.',
    act: playGuided,
    show: async (p) => { p.go({ role: 'client', tab: 'keskustelu' }); } },

  // 4 · Mieliluotsi: mielialan ja ahdistuksen seuranta – vointikysely ja oma lähtötaso, sitten kun dataa on kertynyt
  { stage: 'seuranta', title: 'Wellbeing check-in: mood and anxiety 1–5 – own baseline',
    say: 'Mood and anxiety 1–5, three times a week. Wellbeing is compared with Sami\'s own baseline, not with other people.',
    act: async (p) => {
      if (!p.view().client?.checkIn.needsBaseline) return true;
      // "Miten voit tänään?" on the home screen: the card is on screen for a moment, then Sami answers.
      p.go({ role: 'client', tab: 'koti' });
      await p.spot('.cx-baseline', 'center');
      await p.pause(1600);
      return ok(await p.mutate((s) => api.recordBaseline(s, AINO, { mood: p.view().client?.intake.demoMood ?? 3, anxiety: 3 })));
    },
    show: async (p) => { p.go({ role: 'client', tab: 'koti' }); await p.spot('.cx-teaser', 'center'); } },
  { stage: 'seuranta', title: 'Two weeks later: mood and anxiety on the chart – wellbeing drops below own baseline',
    say: 'Check-ins three times a week and practice build up, and every check-in is compared with Sami\'s own baseline. Then '
      + 'a check-in is missed and sleep gets worse: the observation agent detects the change and asks a professional to take a look.',
    act: async (p) => {
      const view = p.view();
      if (daysBetween(view.meta.demoStartDate, view.meta.currentDate) < 14) {
        if (!ok(await p.mutate((s) => api.advance(s, 14)))) return false;
        // The two weeks on the chart first, then the decline.
        p.go({ role: 'client', tab: 'edistyminen' });
        await p.spot('.ma-chart');
        await p.pause(1800);
      }
      return ok(await p.mutate((s) => api.deteriorate(s, AINO)));
    },
    show: async (p) => { p.go({ role: 'client', tab: 'edistyminen' }); await p.spot('.ma-chart'); } },
  { stage: 'seuranta', title: '“We noticed something” – the observation is only a suggestion',
    say: 'Anxiety has been higher on the evenings before working days. Sami decides whether the observation is saved.',
    show: async (p) => { p.go({ role: 'client', tab: 'koti' }); await p.spot(['.cx-insight', '.bp-doc']); } },
  { stage: 'seuranta', title: 'The care team\'s waiting list: Sami comes up for review',
    say: 'Open review requests first. Mieliluotsi does not prioritise clients or change the urgency of care.',
    show: async (p) => { p.go({ role: 'professional', client: null }); await p.spot('.queue-table tr.row-primary', 'center'); } },
  { stage: 'seuranta', title: '“Why did Sami come up for review?”',
    say: 'The reasons, the rule and the self-reported data are visible – no diagnosis and no black box.',
    show: async (p) => { p.go({ role: 'professional', client: AINO }); await p.spot('.why-card'); } },
  { stage: 'seuranta', title: 'The professional marks it reviewed and changes the urgency – a human decides',
    say: 'The situation is marked as reviewed and the urgency is set to urgent. The decision is always made by a professional, not by AI.',
    act: async (p) => {
      const review = p.view().professional.details[AINO]?.openReview;
      if (review && !ok(await p.mutate((s) => api.reviewObservation(s, review.id, 'mark_reviewed')))) return false;
      // The professional's own decision, as in the pitch: the urgency becomes urgent (the select on the review page).
      if (p.view().professional.details[AINO]?.urgency?.value === 'urgent') return true;
      return ok(await p.mutate((s) => api.setUrgency(s, AINO, 'urgent', 'Wellbeing below own baseline three times')));
    },
    show: async (p) => { p.go({ role: 'professional', client: AINO }); await p.spot(['.urgency-box', '.reviewed-card', '.review-main']); } },

  // 6 · Mieliluotsi: Therapy Fit Profile
  { stage: 'tfp', title: 'Sami approves – the Therapy Fit Profile is updated',
    say: 'The profile for the therapist is built only from approved information, and every item has its own permission.',
    act: async (p) => {
      const pattern = p.view().client?.memory.pending.find((i) => i.kind === 'pattern');
      if (!pattern) return true;
      // The observation stays on the home screen until Sami presses "Tämä tuntuu oikealta": first a moment to read it.
      p.go({ role: 'client', tab: 'koti' });
      await p.spot(['.cx-insight .cx-btn-dark', '.cx-insight'], 'center');
      await p.pause(3200);
      return ok(await p.mutate((s) => api.decideInsight(s, AINO, pattern.id, 'approve')));
    },
    show: async (p) => { p.go({ role: 'client', tab: 'koti' }); await p.spot('.bp-doc'); } },

  // 7 · Sopivin saatavilla oleva terapeutti
  { stage: 'terapeutti', title: 'A therapist has a place free – matching runs at once',
    say: 'Hard requirements first, then transparent scoring. Sami sees the three therapists who best fit the situation.',
    act: async (p) => ok(await p.mutate((s) => api.openSlot(s))),
    show: async (p) => {
      p.go({ role: 'client', tab: 'polku' });
      // Scrolled to, without the golden pulse: the whole section is new on the screen anyway.
      (await p.spot('.matching'))?.classList.remove('pilot-spot');
    } },
  { stage: 'terapeutti', title: '“Why Anna?” – the reasons, the free appointment and the wishes not met',
    say: 'No probabilities: Sami sees what the recommendation is based on and which wishes could not be met.',
    show: async (p) => {
      p.go({ role: 'client', tab: 'polku' });
      const card = await p.spot('.cand');
      card?.querySelector('details.unmet')?.setAttribute('open', '');
    } },
  { stage: 'terapeutti', title: 'Sami chooses Anna – the first appointment is booked',
    say: 'A remote session on a Tuesday evening, as Sami wished. At the same time a draft summary is created for the first session.',
    act: async (p) => {
      const candidates = p.view().client?.matching.candidates ?? [];
      const anna = candidates.find((c) => c.therapist.id === ANNA) ?? candidates[0];
      return anna ? ok(await p.mutate((s) => api.selectCandidate(s, AINO, anna.id))) : false;
    },
    show: async (p) => { p.go({ role: 'client', tab: 'polku' }); await p.spot('.booking-card'); } },

  // (terapeutti jatkuu: asiakkaan hyväksymä yhteenveto ensimmäistä tapaamista varten)
  { stage: 'terapeutti', title: 'A summary for the first session',
    say: 'Every item is labelled: in the client\'s own words, measured, or an AI summary. Sami can edit and remove items.',
    show: async (p) => { p.go({ role: 'client', tab: 'polku' }); await p.spot('.handover-card'); } },
  { stage: 'terapeutti', title: 'Sami removes one item and approves the rest for sharing',
    say: 'Nothing is shared before approval, and the chat history is never shared.',
    act: async (p) => {
      // One item out before approving, as in the pitch – unless the presenter already removed one by hand.
      const sections = p.view().client?.matching.handover?.sections ?? [];
      const drop = sections.some((x) => x.removed) ? null : sections.find((x) => x.key === DROPPED_SECTION && x.available && x.removable);
      if (drop && !ok(await p.mutate((s) => api.updateHandover(s, AINO, { action: 'remove', section: drop.key })))) return false;
      return ok(await p.mutate((s) => api.approveHandover(s, AINO)));
    },
    show: async (p) => { p.go({ role: 'client', tab: 'polku' }); await p.spot(['.handover-card .banner-ok', '.handover-card']); } },

  // 9 · Terapia + välitehtävät Mieliluotsissa
  { stage: 'terapia', title: 'Therapy starts – Anna sees only the approved summary',
    say: 'The first session does not start from scratch: the goals, the direction of wellbeing and the practice are ready. Anna sees '
      + 'the practice with Sami\'s permission, and thought diary entries only if Sami shares them.',
    act: async (p) => ok(await p.mutate((s) => api.firstSession(s, AINO))),
    show: async (p) => { p.go({ role: 'therapist' }); await p.spot('.doc-card'); } },
  { stage: 'terapia', title: 'The therapist sets the support and the task between sessions',
    say: 'Main goal, allowed CBT exercises, a weekly between-session task and check-in frequency – the AI works only within these limits.',
    show: async (p) => { p.go({ role: 'therapist' }); await p.spot('.plan-card'); } },
  { stage: 'terapia', title: 'Save and activate',
    say: 'Mieliluotsi moves from the waiting-time protocol to between-session support guided by the therapist, and Sami gets a notification about it.',
    act: async (p) => {
      const row = p.view().therapist.selected?.clients.find((c) => c.clientId === AINO);
      const plan = row?.therapy.suggestedPlan;
      return plan ? ok(await p.mutate((s) => api.savePlan(s, ANNA, AINO, plan))) : false;
    },
    show: async (p) => { p.go({ role: 'therapist' }); await p.spot('.plan-card'); } },
  { stage: 'terapia', title: 'Sami sees the between-session support the therapist set',
    say: 'The between-session task and exercises between sessions – within the limits the therapist set.',
    show: async (p) => { p.go({ role: 'client', tab: 'polku' }); await p.spot('.cx-modecard'); } },

  // 10 · Seuranta terapian jälkeen
  { stage: 'jalkeen', title: 'Therapy ends – follow-up continues',
    say: 'A maintenance plan and the signs to act on. Mood and anxiety once a week, and a change goes back to the care team.',
    act: async (p) => ok(await p.mutate((s) => api.demoEndTherapy(s, AINO))),
    show: async (p) => { p.go({ role: 'client', tab: 'polku' }); await p.spot('.cx-modecard'); } },
];

/** The first step of each stage – where a click on the stage takes the demo. */
export function stageStart(stage: StageKey): number {
  return Math.max(0, BEATS.findIndex((b) => b.stage === stage));
}

/** The index of a stage's last step. */
export function stageEnd(stage: StageKey): number {
  return BEATS.reduce((last, beat, i) => (beat.stage === stage ? i : last), -1);
}

/* How far Sami's story has come, as the index of the last step whose change is in the state. It lets a step notice that
   it was already done by hand (skip it) and that the state is behind (rebuild it first). */
function progress(view: ValitukiView): number {
  const client = view.client;
  if (!client || client.id !== AINO) return -1;
  const intake = client.intake.status;
  if (intake === 'not_started' || intake === 'consent') return 0;
  if (intake === 'conversation') return 1;
  if (intake === 'review' || intake === 'rhythm') return 2;
  const row = view.therapist.selected?.clients.find((c) => c.clientId === AINO);
  const stage = client.matching.stage;
  if (stage === 'aftercare' || client.modeKey === 'aftercare_support') return 23;
  if (row?.therapy.config) return 21;
  if (row?.therapy.episodeStatus === 'active') return 19;
  if (client.matching.handover?.status === 'approved') return 18;
  if (stage === 'booked' || stage === 'therapy') return 16;
  if (stage === 'choose') return 14;
  const pro = view.professional.details[AINO];
  if (pro?.observations.some((o) => o.kind === 'trend_decline')) {
    if (pro.openReview) return 8;
    return client.memory.pending.some((i) => i.kind === 'pattern') ? 12 : 13;
  }
  if (daysBetween(view.meta.demoStartDate, view.meta.currentDate) >= 14) return 7;  // the decline is still to come
  // The wellbeing check-in comes after the first conversation (step 8); answered early by hand, the conversation still plays.
  if (client.practice.thoughtRecords.length > 0) return client.checkIn.needsBaseline ? 6 : 7;
  if (client.guided?.tool === 'thought_record') return 5;
  if (client.chat.some((m) => m.role === 'client')) return 4;
  return 3;
}

function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(to.slice(0, 10)) - Date.parse(from.slice(0, 10))) / 86_400_000);
}

/** The prepared scenes and the step whose state each one equals – a jump rebuilds the nearest one and replays the rest.
    ('reviewed' leaves the observation for step 14, where Sami approves it on the home screen.) */
const SCENE_AFTER: [scene: string, beat: number][] = [
  ['start', 0], ['intake', 3], ['cbt', 6], ['reviewed', 12], ['matches', 14], ['handover', 18], ['therapy', 21],
  ['aftercare', 23],
];

const lastActBefore = (index: number) => {
  for (let i = index - 1; i >= 0; i -= 1) if (BEATS[i].act) return i;
  return -1;
};

const frame = () => new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
const sleep = (ms: number) => new Promise<void>((resolve) => window.setTimeout(resolve, ms));

function scrollParent(el: HTMLElement): HTMLElement | null {
  for (let node = el.parentElement; node; node = node.parentElement) {
    const overflow = getComputedStyle(node).overflowY;
    if ((overflow === 'auto' || overflow === 'scroll') && node.scrollHeight > node.clientHeight + 2) return node;
  }
  return null;
}

async function findVisible(selectors: string[], timeout = 2500): Promise<HTMLElement | null> {
  const until = Date.now() + timeout;
  while (Date.now() < until) {
    for (const selector of selectors) {
      const el = Array.from(document.querySelectorAll<HTMLElement>(selector)).find((e) => e.getClientRects().length > 0);
      if (el) return el;
    }
    await frame();
  }
  return null;
}

function scrollToElement(el: HTMLElement, block: 'start' | 'center') {
  const container = scrollParent(el);
  const rect = el.getBoundingClientRect();
  if (container) {
    const box = container.getBoundingClientRect();
    // The phone is scaled with CSS zoom: screen pixels → the container's own pixels.
    const scale = box.height / (container.offsetHeight || box.height) || 1;
    const height = rect.height / scale;
    const offset = (rect.top - box.top) / scale + container.scrollTop;
    const top = block === 'center' ? offset - (container.clientHeight - height) / 2 : offset - 12;
    container.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
    return;
  }
  // The page itself scrolls: keep the element below the sticky top bar and demo dock (beside the panel it covers nothing).
  const covered = document.querySelector('.dock:not(.is-side)')?.getBoundingClientRect().bottom ?? 0;
  const offset = rect.top + window.scrollY;
  const top = block === 'center' ? offset - (window.innerHeight - covered - rect.height) / 2 - covered : offset - covered - 16;
  window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
}

function readPointer(): number {
  try {
    const value = Number(window.sessionStorage.getItem(STORAGE_KEY));
    return Number.isInteger(value) && value >= 0 && value <= BEATS.length ? value : 0;
  } catch {
    return 0;
  }
}

export interface DemoPilot {
  /** How many steps are done – BEATS[pointer] is the next one. */
  pointer: number;
  running: boolean;
  failed: boolean;
  next: () => Promise<void>;
  prev: () => Promise<void>;
  /** Go to step `index`: rebuild the demo to just before it and take it. */
  enter: (index: number) => Promise<void>;
  /** The rest of the stage the next step belongs to, at once: no presses or pauses in between (Shift+→). */
  finishStage: () => Promise<void>;
  restart: () => void;
  replay: () => Promise<void>;
}

export function useDemoPilot(): DemoPilot {
  const ctx = useValituki();
  const [stored, setPointerState] = useState(readPointer);
  // Clicking ahead in the app by hand moves the demo along too: once the demo has started, the pointer never trails the state.
  // It only follows steps that change the state, so a step that just shows something is never skipped or pulled back.
  const pointer = stored > 0 ? Math.max(stored, lastActBefore(progress(ctx.view) + 1) + 1) : 0;
  const [running, setRunning] = useState(false);
  const [failed, setFailed] = useState(false);
  const latest = useRef(ctx.view);
  const ctxRef = useRef(ctx);
  const runningRef = useRef(false);
  // → while a step plays (a conversation) finishes it at once, like skipping an animation in a slide show.
  const hurryRef = useRef(false);
  // The steps run in event handlers: they read the newest view and context through refs, synced after every render.
  useEffect(() => {
    latest.current = ctx.view;
    ctxRef.current = ctx;
  });

  const setPointer = useCallback((value: number) => {
    setPointerState(value);
    try { window.sessionStorage.setItem(STORAGE_KEY, String(value)); } catch { /* the pointer just is not remembered */ }
  }, []);

  const pilot = useCallback((fast: boolean): PilotCtx => ({
    view: () => latest.current,
    mutate: async (call) => {
      let fresh: ValitukiView | null = null;
      await ctxRef.current.run(async () => {
        const response = await asPilotStep(() => call(SCOPE));
        fresh = response.view;
        return response;
      });
      if (!fresh) return null;  // the app already shows the error
      latest.current = fresh;
      return fresh;
    },
    go: (where) => {
      if (fast) return;
      const c = ctxRef.current;
      c.setClientId(AINO);
      c.setTherapistId(ANNA);
      if (where.role === 'client') c.setClientTab(where.tab);
      if (where.role === 'professional') { c.setProTab('jono'); c.setProClientId(where.client); }
      if (c.role !== where.role) c.setRole(where.role);
    },
    spot: async (selectors, block = 'start') => {
      if (fast) return null;
      await frame();
      await frame();
      const el = await findVisible(Array.isArray(selectors) ? selectors : [selectors]);
      if (!el) return null;
      scrollToElement(el, block);
      el.classList.remove('pilot-spot');
      void el.offsetWidth;  // restart the pulse
      el.classList.add('pilot-spot');
      window.setTimeout(() => el.classList.remove('pilot-spot'), 2600);
      return el;
    },
    pause: (ms) => (fast || hurryRef.current ? Promise.resolve() : sleep(ms)),
    settle: async () => {
      if (fast) return;
      await sleep(60);  // the new view renders and the chat starts showing the reply
      await frame();
      const until = Date.now() + 20000;
      while (chatRevealing() && Date.now() < until) await sleep(100);
    },
  }), []);

  /** Bring the state to "after step index − 1": the nearest prepared scene, then the remaining steps without pauses. */
  const rebuild = useCallback(async (index: number): Promise<boolean> => {
    const target = index - 1;
    const [scene, after] = [...SCENE_AFTER].reverse().find(([, beat]) => beat <= target) ?? SCENE_AFTER[0];
    const quiet = pilot(true);
    hurryChat(true);  // a rebuilt conversation appears at once
    try {
      if (!(await quiet.mutate((s) => api.scene(s, scene)))) return false;
      for (let i = after + 1; i <= target; i += 1) {
        const act = BEATS[i].act;
        if (act && !(await act(quiet))) return false;
      }
      return true;
    } finally {
      await sleep(60);  // the last rebuilt view renders while the chat is still hurried
      hurryChat(hurryRef.current);
    }
  }, [pilot]);

  const guard = useCallback(async (task: () => Promise<boolean>) => {
    if (runningRef.current) return;
    runningRef.current = true;
    setRunning(true);
    setFailed(false);
    try {
      if (!(await task())) setFailed(true);
    } finally {
      if (hurryRef.current) await sleep(60);  // a hurried step's last reply renders at once too
      runningRef.current = false;
      hurryRef.current = false;
      hurryChat(false);
      setRunning(false);
    }
  }, []);

  /** The steps judge progress from Sami's and Anna's view – another demo client or therapist may be on screen. */
  const ensureScope = useCallback(async () => {
    const view = latest.current;
    if (view.client?.id === AINO && view.therapist.selected?.id === ANNA) return;
    try { latest.current = await api.view(SCOPE); } catch { /* judged from the view on screen */ }
  }, []);

  /** Take step `index` from the state it needs: the change (unless already made) and then the view. */
  const perform = useCallback(async (index: number) => {
    const beat = BEATS[index];
    if (!beat) return true;
    const live = pilot(false);
    await ensureScope();
    // The cue changes at once: the presenter talks while the step plays (a replayed conversation takes a few seconds).
    setPointer(index + 1);
    const done = (index === 0 || !(progress(latest.current) < lastActBefore(index)) || await rebuild(index))
      && (!beat.act || (index > 0 && progress(latest.current) >= index) || await beat.act(live));
    if (!done) {
      setPointer(index);
      return false;
    }
    await beat.show(live);
    return true;
  }, [ensureScope, pilot, rebuild, setPointer]);

  const next = useCallback(async () => {
    if (runningRef.current) {
      hurryRef.current = true;
      hurryChat(true);
      return;
    }
    await guard(() => perform(pointer));
  }, [guard, perform, pointer]);

  // A stage on the rail: rebuild the demo to just before the stage's first step and take that step, so the stage is on
  // the screen at once.
  const enter = useCallback((index: number) => guard(async () => {
    const target = Math.max(0, Math.min(BEATS.length - 1, index));
    if (target > 0 && !(await rebuild(target))) return false;
    return perform(target);
  }), [guard, perform, rebuild]);

  // "Vaihe loppuun": every remaining step of the stage in a row without pauses – the chat shows each reply whole – and then
  // the view of the stage's last step. While a step plays, it finishes that step at once like Seuraava.
  const finishStage = useCallback(async () => {
    if (runningRef.current) {
      hurryRef.current = true;
      hurryChat(true);
      return;
    }
    await guard(async () => {
      const start = pointer;
      if (!BEATS[start]) return true;
      const end = stageEnd(BEATS[start].stage);
      await ensureScope();
      hurryRef.current = true;
      hurryChat(true);
      setPointer(end + 1);
      if (start > 0 && progress(latest.current) < lastActBefore(start) && !(await rebuild(start))) {
        setPointer(start);
        return false;
      }
      const quiet = pilot(true);
      for (let i = start; i <= end; i += 1) {
        const act = BEATS[i].act;
        if (act && !(i > 0 && progress(latest.current) >= i) && !(await act(quiet))) {
          setPointer(i);
          return false;
        }
      }
      await BEATS[end].show(pilot(false));
      return true;
    });
  }, [ensureScope, guard, pilot, pointer, rebuild, setPointer]);

  const back = useCallback((index: number) => guard(async () => {
    const target = Math.max(1, Math.min(BEATS.length, index));
    if (!(await rebuild(target))) return false;
    setPointer(target);
    await BEATS[target - 1].show(pilot(false));
    return true;
  }), [guard, pilot, rebuild, setPointer]);

  const prev = useCallback(async () => {
    if (pointer <= 1 || runningRef.current) return;
    // A step that only showed something is undone by showing the one before it; a step that changed the state is rebuilt.
    if (!BEATS[pointer - 1].act) {
      await guard(async () => {
        setPointer(pointer - 1);
        await BEATS[pointer - 2].show(pilot(false));
        return true;
      });
      return;
    }
    await back(pointer - 1);
  }, [back, guard, pilot, pointer, setPointer]);

  const restart = useCallback(() => setPointer(0), [setPointer]);

  /** "Toista demokeskustelu": plays the rest of the intake or of the guided exercise that is open now. */
  const replay = useCallback(() => guard(async () => {
    await ensureScope();
    const client = latest.current.client;
    if (client?.intake.status === 'conversation') return playIntake(pilot(false));
    if (client?.guided) return playGuided(pilot(false));
    return true;
  }), [ensureScope, guard, pilot]);

  // Keyboard and presentation clickers: → / PageDown = next, ← / PageUp = back, Shift+→ = the rest of the stage. Typing
  // in a field is never hijacked.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest('input, textarea, select, [contenteditable="true"], [role="radiogroup"], [role="tablist"]')) return;
      if (event.shiftKey) {
        if (event.key === 'ArrowRight') {
          event.preventDefault();
          void finishStage();
        }
        return;
      }
      if (event.key === 'ArrowRight' || event.key === 'PageDown') {
        event.preventDefault();
        void next();
      } else if (event.key === 'ArrowLeft' || event.key === 'PageUp') {
        event.preventDefault();
        void prev();
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [finishStage, next, prev]);

  return { pointer, running, failed, next, prev, enter, finishStage, restart, replay };
}
