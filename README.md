# Mieliluotsi

AMD Developer Hackathon: ACT III

> **Tuki alkaa heti, vaikka terapia ei vielä ala.** – Support starts now, even if therapy does not start yet.

Mieliluotsi turns the waiting time before psychotherapy into an active part of the care pathway. From the moment a person
is placed on a therapy waiting list, a set of rule-driven agents checks in with them, notices changes against their own
baseline, offers only professionally approved self-care activities, raises changes for **human** review, finds the best
available therapist with transparent criteria, and prepares a first-session summary that the client approves. When
therapy starts, the therapist decides how Mieliluotsi supports the client between sessions; when it ends, Mieliluotsi follows
mood and anxiety and brings a change back to the care team.

**v3: chat-first, Limbic/Wysa-style.** The client app is built around a conversation. Mieliluotsi asks how you are (mood
and anxiety, 1–5), recognises a situation worth looking at ("Tiistaina pitää pitää esitys ja jännittää…") and offers
**guided cognitive behavioural (CBT) exercises** one question at a time – *Ajatusten tutkiminen* (situation → thought →
feeling 0–10 → behaviour → thinking trap → evidence → a balanced thought → re-rating → an agreed next step),
*Käyttäytymiskoe* and *Altistusporras* (graded exposure). The results become agreed tasks, a private thought journal and
a mood/anxiety progress view. Rules decide every step; a language model may only phrase the questions.

**Hackathon prototype.** Mieliluotsi is **not clinically validated, not a medical device and not production ready.** It
does not diagnose, does not change treatment or clinical urgency, is not an emergency service and is not monitored in
real time. **Kaikki demon henkilöt ja terveystiedot ovat täysin kuvitteellisia** – all people and health data in the
demo are entirely fictional, and every dashboard figure is a labelled synthetic example.

The app is a pivot of the existing repository (FastAPI + React/Vite/TypeScript). The earlier OmaGenomi DNA features are
kept but hidden behind feature flags – see [Hidden legacy features](#hidden-legacy-features). Plan: [PLAN.md](PLAN.md).

---

## Quick start

Requirements: Python 3.12 and Node.js 20+ (`start-macos.sh` also looks for Node in `~/.local/node20/bin`).

```bash
# once
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt
npm --prefix frontend install

# development: backend :8020 + Vite :5195 (Vite proxies /api to the backend)
./start-macos.sh
```

Open **http://127.0.0.1:5195**. Ports can be changed: `BACKEND_PORT=8031 FRONTEND_PORT=5197 ./start-macos.sh`.

**Single-port presentation mode** (no Node process during the pitch) – the backend serves the production build:

```bash
npm --prefix frontend run build
backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --port 8020   # → http://127.0.0.1:8020
```

**AI mode (Claude in the conversation).** The app starts in `LIVE_AI_MODE`: with your own key in `.env` (project root;
`ANTHROPIC_API_KEY`, or `ANTHROPIC_AUTH_TOKEN`), Claude phrases the chat replies, the guided CBT questions (reflection,
thinking-trap proposals, alternative thoughts, exposure steps) and the other bounded texts. Without a key – or with
`VALITUKI_AI_MODE=DEMO_AI_MODE` – it uses deterministic, pre-approved texts, **no API key needed**. The **Tekoäly**
switch (Demo / Claude) changes the mode at runtime: "Claude" re-reads the key from `.env` – no restart needed – and makes
a small test call that shows the model and reply time, or the reason for a failure (e.g. "API-avain ei kelpaa (401)");
the switch stays green while Claude answers and turns amber when it does not. The switch lasts until the server restarts; `.env` decides the mode at start-up. If the key is missing
or a call fails or is rejected by the output guard, the demo text is used automatically (the chat marks it "Valmis
tekstipohja – tekoälyn vastausta ei käytetty"; live texts are marked "Tekoälyn muotoilema"). Never commit a real key.

**Quality checks**

```bash
cd backend && .venv/bin/python -m pytest              # 301 tests: 63 Mieliluotsi + 238 kept legacy tests
cd backend && .venv/bin/ruff check .
cd frontend && npm run typecheck && npm run lint && npm run build
```

**Shareable web address (Render)**

`Dockerfile` builds the frontend and serves it from the FastAPI backend, so one web service is enough; `render.yaml`
describes it. On render.com: **New → Blueprint →** this GitHub repository **→ Apply**. The address is
`https://<service-name>.onrender.com`, and every push to `main` deploys again. The service starts in `LIVE_AI_MODE`; the
API key is set in Render's dashboard (`ANTHROPIC_API_KEY`), never in the repository – without it the demo texts are used. Everyone who opens the address shares one demo state, which starts over when the service restarts
(the free plan sleeps when idle; the first request then takes about half a minute).

---

## PRODUCT

Three demo roles, switched from the view selector in the demo dock's extra controls (the chevron) – the demo steps switch views by themselves (no login in the demo):

| Role | What it is |
|---|---|
| **Asiakas** (client, mobile-first) | A phone-sized, chat-first app: conversational intake, then five tabs – **Koti** ("Hei Sami, miten voit tänään?", the day's plan, a guided exercise), **Keskustelu** (the AI chat with guided CBT exercises and check-ins), **Harjoitukset** (agreed tasks, CBT tools, exposure ladders, the approved self-care library), **Edistyminen** (mood and anxiety over time, the week in review, completed practice, the private thought journal) and **Hoitopolku** (waiting → therapist → therapy → follow-up, matching, handover, milestones). **Tietoni** (my data and consents) opens from the avatar and **Viestit** from the bell. **Apua nyt** is always visible. On wide screens a live **"Mieliluotsi taustalla"** panel shows the agents' steps as they happen. |
| **Ammattilainen** (care coordinator, desktop) | **Terapiajono** (synthetic cohort KPIs + sortable queue), client review ("Miksi Sami nousi tarkistettavaksi?"), **Mitä Mieliluotsi teki?** (all agent actions + audit log), **Terapeutit** (directory, capacity, matching weights, integration points) and **Vaikuttavuus** (synthetic impact). |
| **Terapeutti** (therapist, desktop) | Only the summary the client approved, the first session, the configuration of **Mieliluotsi tapaamisten välillä** (allowed activities and CBT tools, a weekly between-session task), a between-session practice summary (with the client's permission; journal entries only if the client shares them) and **ending therapy** with a maintenance plan. |

A fourth view, **Konsepti**, is the pitch screen: *Passiivisesta jonosta aktiiviseksi hoitopoluksi*.

## WHY

Waiting for psychotherapy is usually passive: a person gets a referral and then nothing happens until the first
appointment. During that time wellbeing can change without anyone noticing, what the person learns about themselves is
lost, the choice of therapist depends on who happens to be free, and the therapist starts the first session from zero.
Coordinators have long queues but little information about who needs a closer look – and giving that job to an opaque
"AI prioritiser" is not acceptable in health care.

## SOLUTION

```
ENNEN                                   MIELILUOTSILLA
Avun haku → Jono → Odotus → Odotus →   Avun haku → AI-alkukeskustelu → [ Mieliluotsi: mieliala + ahdistus · KKT-harjoittelu
Terapia                                 chatissa · muutosten tunnistus · Therapy Fit Profile ] → sopivin saatavilla oleva
                                        terapeutti → valmis, asiakkaan hyväksymä handover → terapia + välitehtävät →
                                        seuranta terapian jälkeen
```

Mieliluotsi is an **orchestration layer, not a new mental-health chatbot**:

1. **Support starts immediately** – a short conversational intake instead of forms; check-ins in the chat (mood and
   anxiety 1–5 + "what changed") in the rhythm the client chooses; one approved activity per check-in day, always
   skippable.
2. **Guided CBT in the chat** – when the client describes a situation, Mieliluotsi offers to look at it together. The
   exercise asks one question at a time, proposes thinking traps and example thoughts (never pre-selected), and ends in
   an agreed next step: a behavioural experiment, a graded exposure step or an approved activity – each a task with a
   day and a reminder.
3. **Agentic, not just chat** – agents act on events (a missed check-in, a third below-baseline check-in, a therapist's
   slot opening) and every step is shown in *Mitä Mieliluotsi teki?* with the agent's name and the rule behind it.
4. **Continuity** – what is learned while waiting builds a **Therapy Fit Profile** and a first-session summary; practice
   continues between sessions (the therapist's tools and homework) and after therapy (follow-up with a maintenance plan).
5. **Transparent matching** – hard filters first, then an explainable weighted fit; the client sees reasons, unmet
   wishes and the first free time, never a probability.
6. **The client decides** – AI interpretations stay *proposed* until approved; every stored item has its own
   permission (🔒 *Vain minä* / 👩‍⚕️ *Saa näkyä ammattilaiselle* / 🧩 *Saa käyttää terapeutin matchingissa*); the
   handover is shared only after *Hyväksy jaettavaksi*.
7. **Humans decide care** – Mieliluotsi raises changes for review; only a professional can change clinical urgency, and the
   therapist defines the between-session support once therapy starts.

---

## ARCHITECTURE

```
backend/app/valituki/                         frontend/src/valituki/
  router.py        /api/valituki/* (every      ValitukiApp.tsx   role switcher, demo dock, hash routing
                   mutation = one transaction)  context.tsx, api.ts   run(): mutation → fresh view (UI never calls an LLM)
  models.py        entities (pydantic)          client/   phone frame: Intake, HomeTab, ChatTab + ChatWidgets, ToolsTab,
  store.py         JSON repository + demo clock           ProgressTab, PathTab (+ MatchingTab), DataTab, NoticesPage,
  practice.py      guided CBT engine: steps,              sheets, Backstage
                   answers, safety, results
  journey.py       deterministic state machine  pro/      Queue, ClientReview, AgentLog, Directory, Impact
  agents/          orchestrator + 6 agents      therapist/TherapistApp (summary + between-session plan)
  intake.py        conversational intake        pitch/    PitchScreen
  interpret.py     rule-based interpretation    components/ charts (line, sparkline, meter), timeline,
  insights.py      insights + permissions                   milestones, handover document, safety screens
  fit_profile.py   Therapy Fit Profile          styles/app.css   design tokens + components (scoped under .vt)
  trends.py        own-baseline trends, patterns
  activities.py    approved library selection   data/valituki/   activities, cbt (tools, thinking traps, flows,
  matching.py      pure matching engine                          ladder templates), therapists, clients, rules,
                                                                 safety_rules, matching_config, modalities,
  modality.py      therapy approach suggestion                   cohort (all JSON)
  matching_flow.py runs, decisions, booking
  handover.py      first-session summary
  therapy.py       therapist configuration
  safety.py        deterministic safety engine
  ai.py, guard.py  AIProvider (DEMO/LIVE) + output guard
  adapters.py      integration interfaces + mocks
  simulation.py    demo time machine
  seed.py, scenes.py  synthetic history + demo jump points
  professional.py, client_actions.py, view.py, impact.py
```

**What was reused, replaced and hidden.** Reused: the FastAPI/pydantic backend, the JSON repository with lock +
transaction, the Claude call pattern, the React/Vite/TypeScript toolchain and the `run()` mutation pattern. Replaced:
the v1 form onboarding and PHQ/GAD-style questionnaires (now conversational intake + light 1–5 check-ins), the single
agent module (now named agents behind an orchestrator) and the UI (new mobile-first client and desktop professional
views). Hidden, not deleted: the OmaGenomi DNA/genetic-risk/care-plan/Apple Health features.

**Principles.** Rules decide, the language model only phrases. Every autonomous step is an `AgentAction` with the
agent's name and rule ID. AI inferences stay *proposed* until the client approves them. Only approved insights with the
matching permission reach the matcher. There is no code path by which an agent changes clinical urgency
(`professional.set_clinical_urgency` raises `PermissionDenied` for anyone but a professional).

### Journey state machine

`INVITED → INTAKE → WAITING_ACTIVE ⇄ HUMAN_REVIEW_NEEDED → MATCHING_READY → MATCH_PROPOSED → MATCH_ACCEPTED →
THERAPY_ACTIVE → AFTERCARE → SERVICE_ENDED`. `journey.TRANSITIONS` defines which event is allowed in which state (others → HTTP
409); `HUMAN_REVIEW_NEEDED` returns to the previous state after review. Every event is stored with the state before and
after, and every change is written to the audit log.

### Multi-agent orchestration

`agents/orchestrator.py` routes each event to named agents; the **SafetyAgent** can interrupt everything else
(`INTERRUPTIBLE_EVENTS`). A daily tick at 09:00 (demo clock) marks missed check-ins, reminds of agreed tasks due today
(`TASK-DUE-001`), sends due check-ins and re-evaluates readiness.

| Event | Agents | What happens (rule IDs) |
|---|---|---|
| `CLIENT_ENROLLED` | Navigation | Invitation right after joining the waiting list (`NAV-001`) |
| `INSIGHTS_APPROVED`, `BASELINE_COMPLETED` | Navigation, CheckIn, Support | Fit profile from approved data (`FIT-001`), support plan + check-in rhythm (`PLAN-001`), first step (`ACT-SEL-001`) |
| `CHECKIN_DUE` | CheckIn, Support | The check-in opens as a conversation in the chat (`CHK-DUE-001`), extra check-in after two low ones (`CHK-EXTRA-001`), today's approved step |
| `CHECKIN_MISSED` | CheckIn | "Mieliluotsi huomasi, että check-in puuttuu" + gentle reminder (`CHK-MISS-001`); 3 in a row → low-priority engagement task (`CHK-MISS-002`). A missed check-in is never read as worsening. |
| `CHECKIN_COMPLETED` | Observation, Support | Comparison with the client's own baseline (`TREND-L1`, `TREND-L2`), pattern search (`PATTERN-WORKDAY-EVE-001`), acknowledgement in the chat (`CHK-ACK-001`) and, when anxiety is high, an offer to look at the situation |
| `WELLBEING_TREND_CHANGED` | Observation | Explainable human-review request – never a diagnosis or an urgency change |
| `PATTERN_DETECTED` | Observation | "Huomasimme jotain" – stays proposed until the client approves |
| `ACTIVITY_COMPLETED` / `_SKIPPED` | Support | Helpful activities recorded to the profile (`ACT-HELP-001`, `ACT-SKIP-001`) |
| `USER_REQUESTED_HUMAN` | Navigation | Coordinator task immediately (`HUMAN-REQ-001`) |
| `SAFETY_SIGNAL` | Safety | Level 3: interrupt, safety screen, synthetic professional alert |
| `HUMAN_REVIEW_COMPLETED`, `MATCHING_READINESS_MET` | Navigation | Resume support (`NAV-REVIEW-001`), readiness for matching (`MATCH-READY-001`) |
| `THERAPIST_SLOT_OPENED`, `MATCHES_GENERATED` | Matching, Navigation | Matching run for eligible clients (`MATCH-RUN-001`), candidates to the client |
| `MATCH_SELECTED`, `FIRST_SESSION_BOOKED` | Navigation | Booking via AppointmentAdapter (`NAV-MATCH-001`, `NAV-BOOK-001`), handover draft (`HANDOVER-001`) |
| `THERAPY_STARTED`, `THERAPIST_PLAN_CONFIGURED` | Navigation, CheckIn, Support | Therapy mode (`THERAPY-001`), therapist's rhythm and allowed activities (`THERAPY-CHK-001`, `THERAPY-002`) |
| `MATCH_FEEDBACK_RECEIVED` | Matching | Negative feedback → "Matching review requested" task, never an automatic rematch (`MATCH-FEEDBACK-001`) |
| `THOUGHT_RECORD_COMPLETED`, `EXPERIMENT_*`, `EXPOSURE_*`, `PRACTICE_TASK_COMPLETED` | Support | The client's own practice is recorded **privately** (never on a professional timeline, `PRACTICE-001`); weekly homework is renewed (`THERAPY-HW-001`) |
| `THERAPY_ENDED` | Navigation, CheckIn | Follow-up after therapy (`AFTERCARE-001`), weekly mood and anxiety check-ins (`AFTERCARE-CHK-001`); a later decline goes back to human review |

Thresholds live in `data/valituki/rules.json`: the baseline is the mean of the first three check-ins; *below* means at
least one point under it; two below in a row → extra check-in, three completed below in a row → review request.

### Data and persistence

`models.py` includes User, ClientProfile, Referral, WaitingListEpisode, IntakeSession/Proposal/Message, ClientInsight,
InsightPermission (append-only), Goal, TherapyFitProfile (versioned changelog), CheckIn, WellbeingMetric,
WellbeingObservation, SafetyObservation, ProfessionalReviewTask, ApprovedActivity, ActivityCompletion, AgentEvent,
AgentAction, Therapist, TherapistAvailability, MatchRun, MatchCandidate, MatchDecision, Booking, MatchFeedback,
TherapyEpisode, TherapistAgentConfiguration, AftercarePlan, HandoverSummary, ProfessionalNote, Notification, AuditEvent,
ChatMessage (with a structured `widget` for guided answers and offers), GuidedSession, ThoughtRecord, Experiment,
ExposureLadder (steps and attempts) and PracticeTask. Records carry `createdAt, updatedAt, createdBy, source` and status/consent where relevant. Storage is
`ValitukiRepository` (`runtime/valituki/state.json`, lock + transaction); production would swap in a database behind the
same interface.

### AI (Claude)

`AIProvider` (in `ai.py`): `generate_intake_follow_up`, `summarise_client_statement`, `generate_support_response`,
`personalise_approved_activity`, `summarise_checkin`, `generate_observation_explanation`, `generate_match_explanation`,
`generate_handover_draft` and `generate_guided_turn` (one step of a guided CBT exercise: a short reflection of the
previous answer and the next question, plus proposed thinking traps, example thoughts or ladder steps – validated and
never pre-selected). The support response may also offer a guided tool (`suggestedTool`, only among the tools allowed
for the client). `DemoAIProvider` is deterministic. `ClaudeAIProvider` uses `claude-opus-5`
(`VALITUKI_AI_MODEL`) with adaptive thinking at low effort and JSON-schema output, checks refusals and truncation, and
passes every text through `guard.py` (diagnoses, medication, treatment changes, clinical claims, urgency decisions,
claims about reviews that do not exist, human-like feelings, dependency, more than one question…). The system prompt is
`ai.VALITUKI_SYSTEM_PROMPT`. A chat reply gets the conversation so far (today's messages, and earlier ones only with the
storeHistory consent; at most 12), the approved goals, the latest check-in and the allowed activities and tools. Only
interactive client actions may call the live model; simulations and the synthetic history always use demo texts. The UI
never calls a model. `PUT /api/valituki/ai/mode` and `POST /api/valituki/ai/check` back the demo dock's AI switch;
`ai.status()` (in every view's `meta.ai`) reports the mode, whether a key is present and the last call (task, ok,
failure, ms, answering model).

### Guided CBT practice (`practice.py`, `data/valituki/cbt.json`)

| Tool | Steps (one question at a time) | Result |
|---|---|---|
| Check-in | mood 1–5 → anxiety 1–5 → what got worse → (therapist's tracked item) → note | CheckIn; high anxiety → offer to look at the situation |
| **Ajatusten tutkiminen** | situation → thought → emotions → intensity 0–10 → behaviour → thinking traps (proposed by phrase rules) → what supports the thought → what would you tell a friend → balanced thought (examples) → re-rating 0–10 → agreed next step | ThoughtRecord (private journal) + chains to an experiment, a ladder or an activity task |
| **Käyttäytymiskoe** | prediction → belief 0–10 → a small safe experiment (examples) → day | Experiment + task; later *outcome → belief → what I learned* |
| **Altistusporras** | what you avoid → anxiety 0–10 → the ladder (template steps, editable) → first step → day | ExposureLadder + task; each attempt records anxiety *before / peak / after* |

- **Rules decide**: the steps, their order, what counts as an answer, which tools are allowed (waiting-list protocol,
  the therapist's `allowedTools`, the aftercare plan) and what is stored. Exposure is not offered when distress is
  elevated. A model only phrases the reflection and the question, and every text passes the output guard (incl. new
  rules against invalidating a thought or a feeling).
- **Safety first**: every free-text answer passes the deterministic Safety Engine before anything else; a level-3 signal
  stops the exercise, clears its answers and shows the safety screen – no model is called. A model's hint can only raise
  the level.
- **Private by default**: the thought journal is the client's own. Practice events are `private` agent actions (never on
  a professional timeline). The therapist sees a summary (counts, thinking traps, 0–10 changes, ladder progress) only
  with the `sharePractice` consent, and individual entries only when the client shares them. The handover gets an
  aggregated *Mitä olen harjoitellut* section, removable like every other section.

### Matching

1. **Hard filters:** active, service type, professional role, age group, required competence, language, format and
   location, exclusions (incl. the client's own), real capacity and availability.
2. **Weighted fit** (`data/valituki/matching_config.json`): goals & competence 30, working style 20, own preferences
   15, language & accessibility 15, availability & continuity 15, logistics 5.

Clients see *Vahva / Hyvä / Mahdollinen yhteensopivuus* with reasons, unmet wishes, the first free time and the data
used – never a numeric probability. The professional sees the component meters and the excluded therapists with reasons.

**Sopivin terapiamuoto ja työtapa** (next to the phone, under **Sopivin terapeutti**): the therapy approaches the pool offers,
written out in full – kognitiivinen käyttäytymisterapia, hyväksymis- ja omistautumisterapia, ratkaisukeskeinen
lyhytterapia, interpersoonallinen terapia, psykodynaaminen psykoterapia (`modality.py`, `data/valituki/modalities.json`)
– with only their fit 0–100; the breakdown is in the tooltip. Goals 55 (the approach's fit to the approved goal topics,
the referral's until then) and working style 45 (the approved wishes against the approach's typical way of working, on
the therapists' 1–5 levels); unknown = neutral. Practice during the wait is not counted: only cognitive behavioural
therapy has guided exercises in the app, so it would always gain. Only data allowed in matching is used, no language
model takes part, and it is a suggestion for the professional's decision. For Sami, cognitive behavioural therapy leads.

### Handover

"Yhteenveto ensimmäistä tapaamista varten": what I hope for, goals, wellbeing while waiting (chart), what I have tried,
what helped / did not help, working-style and practical preferences, approved observations, questions to start with,
professional notes, an AI summary, sources and sharing permissions. Every section is typed – **Asiakkaan sanoin /
Mitattu / Tekoälyn tiivistelmä / Ammattilaisen merkintä** – and can be edited or removed. The chat history is not
included by default. The therapist sees nothing until the client approves, and withdrawal removes it.

### Integration points (mocks in `adapters.py`)

| Interface | Demo | Production |
|---|---|---|
| `WaitingListAdapter` | referral and queue data from the seed | wellbeing-services-county referrals and queues |
| `TherapistDirectoryAdapter` | synthetic directory + calendar sync | provider/voucher directory and calendars |
| `AppointmentAdapter` | booking in the demo state | appointment system |
| `NotificationAdapter` | in-app notifications | push, SMS or e-mail |
| `HealthRecordAdapter` | sends nothing (audit only) | approved summary to the patient record |
| `ProfessionalTaskAdapter` | tasks in the demo state | coordinator work queue |

---

## DEMO

### Synthetic people

| Client | Situation at the start (Fri 16.10.2026) |
|---|---|
| **Sami Lehtinen** (31, Espoo) | Main demo client: anxiety and work stress, eligible for short-term therapy, just joined the waiting list, prefers a structured and practical approach, Finnish, remote, Tuesday/Thursday evenings |
| Mikko Salonen | Stable waiting client – matching possible |
| Sara Nieminen | Check-ins repeatedly missed → low-priority engagement task |
| Demo-kriisikäyttäjä | Used only for the safety path |
| Juha Mäkinen, Maria Korhonen | In therapy; Maria gave negative match feedback → "Matching review requested" |
| Pekka Rantanen | Therapist suggestions waiting for his choice |
| Leena Järvinen | Asked to talk to a professional |
| Noora Salo | Invited, not started |

Eleven fictional therapists ("Demon kuvitteellinen terapeutti."), including a full one, an inactive one, one without the
anxiety competence, Swedish/English-speaking and in-person-only ones. About 30 days of history are produced by running
the same engine day by day (`seed.py`), so every observation and timeline row comes from the same rules.

### Demo dock (dark strip – not part of the product)

Shown on every view as the only (sticky) bar. **Seuraava** (or → / PageDown; ← / PageUp
goes back) drives the whole demo in 24 steps that follow the concept: avun haku → AI-alkukeskustelu → Mieliluotsi
(KKT, seuranta ja muutosten tunnistus, Therapy Fit Profile) → sopivin terapeutti ja handover → terapia + välitehtävät →
seuranta terapian jälkeen. Each step types the demo text, presses the right button through the same API, opens the right
view and highlights what to look at; the step number (e.g. 5/24) sits next to Seuraava, with what is on the screen in its
tooltip. Clicking a stage opens it
directly: the demo is rebuilt from the prepared scenes and the stage's first step is taken (`components/demoPilot.ts`). Script: [docs/DEMO_5MIN.md](docs/DEMO_5MIN.md).
**Lisää** holds the date controls (+1 / +7 / +14 pv), **Vointi heikkenee**, **Vakaa tilanne**, **Kriisipolku**, the demo
client and **Alkutilaan** (reset). In the chat, **Demovastaus** answers the current question with the scripted answer and
**Toista demokeskustelu** plays the rest of the exercise. **Ohjaus paneelin viereen** moves the demo control out of the
top bar into a column on the right – beside the backstage panel in the client's view, beside the page in the others – so
the phone and the panel get the screen's whole height; **Ohjaus yläpalkkiin** brings it back. The column shows the
stage's narration for the pitch video (`STAGES[].tell` in `components/demoPilot.ts`: one text per stage, about 270
words in all for a 3-minute demo; see [docs/DEMO_5MIN.md](docs/DEMO_5MIN.md)). It applies in a window at least 900 px
wide and is remembered in the browser (`components/dockPlace.ts`; the control's state stays put – only its markup
moves, through a portal).

### The 3-minute demo

Press **Aloita demo** – the demo starts in Sami's home view (the Konsepti page is not part of the demo).

1. **Sami on the waiting list (0:15–0:30).** *Asiakas* → "Hei Sami – Olet terapian jonossa." Consents → **Aloita
   keskustelu**.
2. **Conversational intake (0:30–0:55).** "Kerro omin sanoin, miksi hait apua." → **Toista demokeskustelu** (six
   focused follow-ups, one at a time). "**Ymmärsinkö tilanteesi oikein?**" – TAVOITE, TYÖSKENTELYTAPA, KÄYTÄNNÖN
   TOIVEET; nothing is saved yet → **Kyllä, tämä kuvaa tilannettani** → rhythm, message tone, today's mood → **Aloita
   Mieliluotsi**. Point at *Mieliluotsi taustalla*: plan, first step, Therapy Fit Profile v1.
3. **The chat and CBT (0:55–1:25).** *Koti* → write the demo message ("Tiistaina minun pitää esitellä projektin tilanne
   koko tiimille, ja jännittää jo nyt ihan hirveästi."; the demo control's → sends it for you) → Mieliluotsi offers to look at it → **Kyllä, tutkitaan** → answer a few
   questions (emotions, 0–10, thinking traps proposed by the rules) → **Toista demokeskustelu** → *Ajatuspäiväkirja* card
   (8/10 → 5/10) → an exposure ladder with the first step tomorrow.
4. **Two weeks of support (1:25–1:40).** **Simuloi 14 päivää**. *Edistyminen*: mood and anxiety lines, 3 thought records,
   5 exposure steps, 1 experiment, *Viikkosi* with "Sanat muistiin". *Koti*: today's exposure step and "**Huomasimme
   jotain** – perustuu 6 check-iniin, ei diagnoosi" → **Tämä tuntuu oikealta**.
5. **A change → human review (1:40–2:05).** **Simuloi voinnin heikkeneminen**. Timeline: *09.00 check-in puuttuu ·
   09.01 muistutus · 14.40 check-in · 14.41 kolmatta kertaa oman lähtötason alapuolella · 14.41 tarkistuspyyntö*.
   **Ammattilainen**: TERAPIAJONO 1 000 / 647 / 164 / 31 / 118 / 40 (synthetic) → Sami → "**MIKSI AINO NOUSI
   TARKISTETTAVAKSI?**" → "Mieliluotsi ei ole muuttanut hoidon kiireellisyyttä." → **Merkitse tarkistetuksi** and set
   the urgency to *Kiireellinen* (the demo control's step 13 does both).
6. **A slot opens → matching (2:05–2:25).** **Avaa terapeutin vapaa aika** (Anna Laine). *Asiakas → Hoitopolku*:
   "Löysimme kolme tilanteeseesi sopivaa terapeuttia." – "Miksi Anna?", "Ti 17.11. klo 18.00", "Mitä toiveita ei
   pystytty täyttämään?".
7. **Choice and handover (2:25–2:40).** **Valitse** → first session booked → "Yhteenveto ensimmäistä tapaamista
   varten" (typed sections incl. *Mitä olen harjoitellut*, *Muokkaa* / *Poista kohta*) → remove *Mitä olen kokeillut* →
   **Hyväksy jaettavaksi** (the demo control's step 19 does both). The therapist sees nothing before the approval.
8. **Therapist (2:40–2:50).** **Terapeutti** → "Ensimmäinen tapaaminen 17.11. klo 18.00" and "Samin hyväksymä
   yhteenveto" → **Merkitse ensimmäinen tapaaminen pidetyksi (demo)**.
9. **Therapist-guided support (2:50–3:00).** Päätavoite, KKT-harjoitukset, välitehtävä (*Ajatusten tutkiminen*), sallitut
   omahoitoharjoitukset, check-in-tiheys, seurataan, älä käsittele → **Tallenna ja ota käyttöön**. *Harjoittelu
   tapaamisten välillä* shows the ladder's progress. Sami's *Hoitopolku*: "Terapeutti Anna on määrittänyt tämän
   suunnitelman."
10. **After therapy (optional).** **Terapia päättyy** (or *Terapeutti → Laadi ylläpitosuunnitelma → Päätä terapia*):
    *Hoitopolku* → *Seuranta terapian jälkeen* with the maintenance plan; mood and anxiety weekly. Close: "Mieliluotsi ei
    korvaa terapeuttia. Se tekee ajasta ennen terapiaa, tapaamisten välillä ja niiden jälkeen jatkuvan osan
    hoitopolkua."

Optional: **Kriisipolku** (safety screen for the crisis demo client, alert in the queue), **Matkani** (milestones),
**Tietoni** (per-item permissions), **Vaikuttavuus**. If something goes wrong on stage, **Hyppää vaiheeseen…** rebuilds
any step in well under a second.

Deep links: `#/konsepti`, `#/asiakas/cl-aino/koti` (also `keskustelu`, `harjoitukset`, `edistyminen`, `polku`),
`#/ammattilainen/cl-aino`, `#/terapeutti/th-anna`.

---

## SAFETY

- **Separate deterministic safety engine** (`safety.py`, `data/valituki/safety_rules.json`): Finnish phrase rules (with
  Swedish/English basics), a mood-floor rule (1/5 → level 1) and the explicit *Tarvitsen apua nyt* button. Levels:
  **0** normal support · **1** extra check-in suggested · **2** professional review requested · **3** immediate safety
  guidance.
- The final level is `max(deterministic, model hint)` – **a language model can never downgrade it**. A level-3 phrase
  in chat interrupts the conversation before any model is called.
- Level 3 shows fixed text (no AI): "**Tarvitsetko apua juuri nyt?**", "Mieliluotsi ei ole päivystyspalvelu eikä tätä
  keskustelua seurata jatkuvasti.", **112**, **Päivystysapu 116117**, **MIELI Kriisipuhelin 09 2525 0111**. It creates a
  synthetic professional alert and states that Mieliluotsi has **not** contacted emergency services.
- The safety screen interrupts the other agents until the client acknowledges it; *Apua nyt* is always available.
- Guided exercises: every free-text answer is checked before anything else; level 3 stops the exercise (answers cleared,
  nothing saved) before any model is called, and exposure is not offered while distress is elevated.
- No diagnoses, no medication or treatment advice, no urgency changes, no claims of reviews that did not happen – enforced
  by rules and by the output guard for every model text.
- Interpretations and patterns are never stored as facts without the client's approval; permissions are per item and
  logged.

## Tests

`backend/tests/valituki/` – 58 tests, including:

| Requirement | Test |
|---|---|
| Intake does not auto-approve inferred information | `test_intake.py::test_conversational_intake_does_not_automatically_approve_inferred_information` |
| Unapproved insight cannot be used for matching | `test_matching.py::test_unapproved_insight_cannot_be_used_for_matching` |
| Revoked permission / revoked data excluded from matching | `test_matching.py::test_user_can_revoke_matching_permission`, `test_revoked_information_is_excluded_from_future_matching` |
| No capacity → excluded | `test_matching.py::test_therapist_with_no_capacity_is_excluded` |
| Failing a hard criterion → excluded | `test_matching.py::test_therapist_failing_a_hard_eligibility_criterion_is_excluded` |
| Deterministic ranking | `test_matching.py::test_matching_ranking_is_deterministic` |
| Labels, not probabilities | `test_matching.py::test_client_sees_labels_not_numeric_probabilities` |
| Worsening wellbeing → explainable human review task | `test_agent.py::test_worsening_wellbeing_generates_an_explainable_human_review_task` |
| One missed check-in → no clinical conclusion | `test_agent.py::test_one_missed_checkin_alone_does_not_produce_a_clinical_conclusion` |
| AI cannot alter waiting-list priority / urgency | `test_agent.py::test_ai_cannot_independently_alter_waiting_list_priority` |
| Safety trigger interrupts the normal agent flow | `test_safety.py::test_safety_trigger_interrupts_normal_agent_flow` |
| LLM output cannot downgrade safety | `test_safety.py::test_llm_output_cannot_downgrade_a_deterministic_safety_level` |
| Handover excludes the full chat by default | `test_handover.py::test_handover_excludes_full_chat_history_by_default` |
| Therapist sees only approved handover data | `test_handover.py::test_only_user_approved_handover_data_is_shown_to_the_therapist` |
| Therapist configuration changes agent behaviour | `test_agent.py::test_therapist_configuration_changes_agent_behaviour` |
| Negative match feedback → review, no rematch | `test_agent.py::test_negative_match_feedback_requests_review_without_rematch` |
| DEMO_AI_MODE works without an API key | `test_ai.py::test_demo_mode_works_without_api_key` |
| The chat offers a tool; nothing starts before the client chooses | `test_practice.py::test_the_chat_offers_a_guided_tool_and_the_client_decides` |
| Thought record follows the rules, one question at a time, stays private | `test_practice.py::test_thought_record_follows_the_rules_and_stays_private` |
| Level-3 phrase in an exercise interrupts before any model call | `test_practice.py::test_a_level_three_phrase_in_an_exercise_interrupts_before_any_model_call` |
| A model turn is validated and falls back to the approved question | `test_practice.py::test_a_model_turn_is_validated_and_falls_back_to_the_approved_question` |
| Check-in in the chat records mood and anxiety | `test_practice.py::test_the_check_in_runs_as_a_conversation_with_mood_and_anxiety` |
| Exposure ladder → task → attempt | `test_practice.py::test_exposure_ladder_task_and_attempt` |
| The therapist decides tools and weekly homework | `test_practice.py::test_the_therapist_decides_the_tools_and_the_weekly_homework` |
| Therapist sees practice only with permission, entries only when shared | `test_practice.py::test_the_therapist_sees_a_summary_only_with_permission_and_entries_only_when_shared` |
| Aftercare follows mood and anxiety; a decline returns to human review | `test_practice.py::test_therapy_ends_and_aftercare_follows_mood_and_anxiety` |
| Whole journey through the API | `test_api_flow.py::test_full_demo_journey` |

---

## PRODUCTION REQUIREMENTS

Before any real use, at minimum:

- **Clinical validation and governance:** the safety phrases and levels (sensitivity/specificity, Swedish and English
  too), the level 2–3 handling process and on-call responsibility (Mieliluotsi is not monitored in real time), trend
  thresholds, the activity library content, cautions and approval process, matching criteria and weights and their
  equity effects, the system prompt and guard rules, and the handover content – all reviewed and owned by clinicians.
- **Regulation and data protection:** MDR and EU AI Act classification, GDPR/health-data legal basis, consent wording,
  retention and deletion, DPIA, and processing agreements (including for any LLM provider).
- **Integrations:** referrals and waiting lists, provider directory and calendars, appointments, messaging channels,
  patient record / Kanta, the coordinator work queue.
- **Security and operations:** strong authentication (Suomi.fi) and role-based access control (the demo returns all
  roles' views), a database with encryption at rest, logging and monitoring, availability and incident processes.
- **Quality:** accessibility audit (WCAG 2.1 AA), usability testing with real users and professionals, and evaluation of
  outcomes – the impact figures in the demo are synthetic.

## Assumptions and limitations

- The demo clock starts on Friday 16.10.2026 and moves only with the demo controls; there is no background process.
- Wellbeing is a 1–5 self-report (mood, and anxiety on the same 1–5 scale so both share one chart axis) with "what
  changed" domains, compared with the client's own baseline (the trend rules use mood). Situational feelings in the CBT
  exercises are rated 0–10. No questionnaires, scores or diagnoses.
- The CBT content (questions, thinking traps and their phrase rules, example thoughts, ladder templates) is placeholder
  demo content in `data/valituki/cbt.json` and needs clinical validation, like the activity library.
- Waiting-time check-ins default to Mon/Wed/Sat; the therapist sets the rhythm in therapy mode.
- The professional dashboard numbers are synthetic and labelled; the demo clients add to them live.
- The UI is in Finnish; language preferences only affect matching.
- Storage is one JSON file (single user at a time); live AI calls run synchronously inside the request.
- The phrase rules do not interpret negation (precaution: an unnecessary safety prompt is preferred to a missed one).
- Matching weights are not learned from feedback and have no validated predictive accuracy.

## Hidden legacy features

The DNA analysis, genetic-risk rule engine, blood-pressure care plans and Apple Health data are still in the repository
(`backend/app/loop`, `support`, `wellbeing`, `services`, `app/legacy_api.py`; `frontend/src/App.tsx`, `loop/`,
`support/`, `wellbeing/`) but are not in the navigation or the API. Restore with `LEGACY_FEATURES_ENABLED=1` (backend) and
`VITE_ENABLE_LEGACY_APP=true` (frontend). Their tests still run (`backend/tests/legacy`) and their documentation is in
[docs/legacy](docs/legacy).
