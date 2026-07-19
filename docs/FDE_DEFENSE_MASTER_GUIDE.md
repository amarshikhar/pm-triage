# FDE assessment defense master guide

This is the primary study document for the company assessment. Read it first.
Use `CODE_AND_DATA_FLOW_REFERENCE.md` when an interviewer asks how a particular
screen, endpoint, function, table, or state transition works. Use
`PRODUCTION_CHALLENGE_QA.md` for scale, security, failure, and limitation
questions. The specialist evaluation, ML, cost, and economics documents are
evidence appendices rather than the presentation script.

## What the company asked for

The Manufacturing challenge asks for a working predictive-maintenance triage
assistant that:

1. ingests simulated IoT telemetry;
2. correlates anomalies with historical maintenance logs;
3. suggests a likely root cause and priority;
4. never controls a machine directly;
5. explains recommendations to floor technicians; and
6. contains a meaningful enterprise interaction.

This artifact implements that slice and then adds recorded real-data replay,
a narrow trained classifier, learned OOD rejection, confidence abstention, a
named human gate, CMMS write-back, an audit trail, cost controls, and evaluation.

## Rubric mapping

| Company category | Weight | Evidence to demonstrate | Do not overclaim |
|---|---:|---|---|
| Solution Architecture & Workflow Design | 30% | Clear ownership boundaries; full telemetry-to-CMMS state machine; safe fallback paths | It is a focused working slice, not a complete plant platform |
| Software Engineering & SDLC | 25% | FastAPI/Next.js code, typed contracts, 105 backend tests, production build, deployment, retention, regression fixes | No claim of formal SRE maturity or exhaustive browser E2E testing |
| Systems Integration & Enterprise Architecture | 20% | REST APIs, Supabase Postgres, HTTP CMMS anti-corruption adapter, schema translation, retries, idempotency | Mock CMMS is mounted in the same deployment and shares the database |
| Domain-Embedded Business Architecture | 15% | Machine criticality, engineering limits, signal features, maintenance precedents, priority, downtime exposure, human planner | Thresholds/history/economics are demo inputs, not customer-validated policy |
| Agentic AI / LLM Engineering | 7% | Bounded tool loop, three read-only tools, structured output, mock/live parity, evaluation, provider fallback | LLM does not own detection, authorization, or a concrete classifier verdict |
| Governance, Observability & Control | 3% | OOD/abstention, human approval, audit, trace, call/dollar caps, no direct control | Demo authentication is not enterprise SSO/RBAC |

The highest-scoring story is not “I used an LLM.” It is “I translated the
business workflow into explicit owners and failure boundaries, implemented the
integration, and used AI only where it added value.”

## Thirty-second opening

> This system turns condition-monitoring telemetry into an evidence-backed
> maintenance recommendation without allowing AI to control equipment.
> Deterministic rules detect abnormal behavior; auditable rules plus a narrow
> trained classifier name only supported faults and abstain on OOD inputs; a
> mock or live LLM retrieves precedent and drafts the explanation and actions;
> a named planner must approve before an idempotent CMMS adapter creates a work
> order. The complete path is tested, deployed, audited, cost-capped, and
> evaluated on generated faults plus eight recorded SKAB and CWRU episodes.

## Two-minute architecture answer

```text
telemetry source
  -> TelemetryReading in Postgres
  -> deterministic engineering-limit / robust-z detector
  -> one Anomaly containing the complete signal window
  -> physics signature rules
  -> narrow Extra Trees restriction classifier when eligible
  -> IsolationForest/schema/confidence OOD gates
  -> bounded mock or DeepSeek tool-calling investigation
  -> deterministic confidence calibration and priority
  -> TriageCase(status=pending_review)
  -> named planner approve / edit / reject
  -> approved-only CMMS schema adapter
  -> idempotent work order or preserved retryable sync state
  -> business audit trail
```

The boundaries are deliberate:

- Detection is deterministic because it must be cheap, continuous, and
  explainable.
- Numeric fault classification belongs to features plus a narrow classifier,
  not an LLM reading raw numbers.
- The LLM owns language work: tool selection, precedent synthesis,
  explanation, recommended actions, and drafting.
- Priority is a formula. The LLM can propose only a clamped one-notch change.
- Every case requires human review, including high-confidence cases.
- Approval is committed before downstream CMMS synchronization, so an outage
  cannot erase the human decision.

## What is real, recorded, simulated, mocked, and illustrative

| Element | Exact status |
|---|---|
| Application code and workflow | Real production code running on Vercel/Render |
| Production database | Real Supabase Postgres through SQLAlchemy |
| Synthetic fleet telemetry | Generated Gaussian baselines plus deterministic fault ramps |
| SKAB/CWRU telemetry | Recorded laboratory data curated into replay episodes |
| CWRU transition | Constructed by concatenating real healthy and faulty steady-state frames; not natural run-to-failure |
| Historical maintenance logs | Seeded realistic demo records, not a customer CMMS export |
| CMMS interface | Real HTTP contract, validation, retries, idempotency, and foreign-schema mapping |
| CMMS system | Mock FastAPI app mounted in the same deployment and using the same database |
| Mock agent | Free deterministic policy using the real tool loop and case schema |
| Live agent | DeepSeek V4 Flash through OpenRouter; deliberately enabled and cost-capped |
| Priority and downtime exposure | Executable transparent rules using illustrative business inputs |
| Human decision | Real authenticated user action recorded in the database and audit |

## Presentation preflight

Do this 10–15 minutes before presenting:

1. Open `https://pm-triage-backend.onrender.com/api/health`.
2. Confirm `ok=true`, `simulator_running=true`, and note the seven-character
   `release`.
3. Open the production frontend and wait until machine cards populate.
4. Confirm the header says `MOCK · free`. Do not begin in live mode.
5. Sign in with your own reviewer name so decisions are attributed.
6. Identify an existing pending case as a backup in case a new case is slow.
7. Keep the Evaluation page open in another tab because it uses bundled static
   reports even if Render sleeps.
8. Keep screenshots or a short recording of Fleet -> Case -> CMMS -> Audit as
   the network-failure backup.

Do not clear, delete, reset, or manufacture production history before the
presentation. Existing audit evidence shows the system is actually used.

## Seven-minute golden-path demonstration

### 0:00–0:40 — business problem and safety boundary

Open **Fleet**.

Say:

> The business problem is not merely detecting a high sensor value. It is
> turning an anomaly into an explainable, prioritized maintenance decision,
> connected to the system of record, without autonomous machine control.

Point out:

- simulated versus `real data` badges;
- machine location and criticality;
- live readings and sparklines;
- the free mock/live budget indicator.

Do not say the sparkline detects faults. It is visualization; Python rules
detect faults against database readings.

### 0:40–1:20 — start a controlled scenario

For the most reliable live demonstration, inject a synthetic fault. A synthetic
fault normally crosses a limit in roughly 21–39 seconds. A real replay cue keeps
45 pre-fault rows and can take minutes, so cue real data only when time permits.

Say:

> This button is an assessment/demo lever. Production random fault injection is
> disabled. A real plant would receive readings from a historian, broker, or IoT
> gateway through the same ingestion boundary.

The UI immediately confirms the cue. Navigating away does not cancel it.

### 1:20–2:20 — deterministic detection and signal context

Open the created **Case**. Start with the right-hand Detection card.

Say:

> Detection is not an LLM prompt. An engineering limit or a sustained robust-z
> excursion creates one anomaly. The anomaly stores statistics for every
> signal, not only the breached one, because the cross-signal shape separates
> faults such as bearing wear and cavitation.

Explain the visible numbers:

- value: current reading;
- threshold: engineering limit or rolling median;
- z-score: distance from recent baseline in spread units;
- severity: percentage beyond a fixed limit or robust-z magnitude;
- mean/drift/volatility/range: deterministic window facts;
- one physical event creates one anomaly/case even if several signals move.

### 2:20–3:15 — classifier, OOD, and LLM role

Point to **Signature analysis** and the investigation trace.

Say:

> Clear signatures are scored with auditable physics rules. Only the overlapping
> SKAB suction/discharge pair is routed to Extra Trees. Before accepting that
> narrow model, the system checks the exact sensor schema, IsolationForest
> novelty, and calibrated class confidence. Unsupported data abstains. The LLM
> then uses only three read-only tools: machine information, recent telemetry,
> and historical maintenance search.

Explain mock versus live:

- mock makes the same three tool calls in a fixed order and is free;
- live DeepSeek chooses calls and language dynamically;
- both use the same dispatcher, tools, calibration, priority, schema, human
  gate, and CMMS flow;
- if live fails or reaches a cap, the case restarts through mock and records the
  fallback.

### 3:15–4:10 — confidence, priority, and business context

Point to calibrated confidence and priority.

Say:

> Raw LLM confidence is not trusted. Deterministic calibration discounts weak
> precedent, non-diagnostic language, signature conflict, or signature
> abstention. Below 0.45 the case is visibly uncertain. Priority separately uses
> criticality, severity, recurrence, and safety. Exposure is informational and
> does not secretly change priority.

Priority formula:

```text
score = criticality
      + 2 * severity_points
      + min(recurrence, 3)
      + (4 if safety-related else 0)
P1: safety or >=13; P2: >=10; P3: >=7; otherwise P4
```

### 4:10–5:15 — human decision and CMMS integration

Approve, reject, or approve with edits.

Say:

> Every case is pending review. The session identity, not an arbitrary request
> field, signs the decision. Rejection creates nothing downstream. Approval is
> committed first, translated into the CMMS vocabulary, and posted with
> `Idempotency-Key: triage-case-{case_id}`. A retry returns the same order rather
> than creating a duplicate.

Open **CMMS** and show:

- P1–P4 translated to priority codes 1–4;
- equipment and functional location;
- M1 notification type;
- damage code;
- 40-character short text and detailed long text;
- named human approval.

State clearly that this is a mock CMMS behind a genuine HTTP/domain boundary.

### 5:15–5:50 — auditability

Open **Audit** and narrate:

```text
human cue/injection -> system anomaly -> agent case -> human decision
-> system work-order success/failure
```

The case trace explains one reasoning run. The audit trail explains business
state changes and who caused them. Times display in the browser timezone while
the database stores ISO-8601 UTC.

### 5:50–7:00 — evaluation and honest conclusion

Open **Evaluation**, then **Real testbeds**.

Say:

> Eight recorded episodes were tested: five SKAB pump and three CWRU bearing
> episodes. Detection fired on 8/8. The hybrid classifier named 7/8 and was right
> on all 7 accepted answers. The paid live agent was 7/8 raw, accepted 6/8 after
> its confidence gate, and was right on those 6. This is encouraging development
> evidence, not universal plant accuracy; n is only eight laboratory episodes.

Close with:

> Rules detect; rules plus narrow ML classify; OOD can abstain; the LLM explains
> and retrieves; a named human authorizes; an idempotent adapter integrates the
> approved decision. That division is the production design.

## Numbers you must be able to translate into counts

### Synthetic, 24 generated trials

- Detector: 24/24.
- Hybrid classifier: 18/24 correct overall; names 19/24; 18/19 correct when it
  names a class.
- Mock agent: 20/24 raw text top-1; accepts 19/24 after the gate; 17/19 accepted
  answers correct.
- Paid live agent: 18/24 raw; accepts 18/24; 17/18 accepted answers correct.
- Live ECE 0.319 means an average confidence/accuracy mismatch of about 31.9
  percentage points on this small run; it does not mean 68.1% accuracy.

### Real replay, eight recorded episodes

- Detector: 8/8.
- Hybrid classifier: 7/8 overall; coverage 7/8; selective accuracy 7/7.
- Mock agent: 7/8 raw; coverage 7/8; selective accuracy 7/7.
- Paid DeepSeek: 7/8 raw; coverage 6/8; selective accuracy 6/6; two abstentions.
- In labelled window: 7/8. One anomaly fired before the dataset's labelled
  region; that is a timing/precursor metric, not a missed detection.
- Paid real run: 34 provider turns, 161,585 total tokens, 32.17 seconds mean
  case latency, $0.014535 exact returned cost, zero errors/fallbacks.
- Real live ECE: 0.148, an average confidence/accuracy mismatch of about 14.8
  points on only eight rows.

Never say “100% real accuracy.” Say “7/8 overall and 7/7 among accepted
classifier answers, on eight laboratory episodes.”

## One-sentence explanation of every screen

| Screen | What it proves |
|---|---|
| Fleet | Multiple assets and schemas produce continuously refreshed telemetry; controlled demo injection/replay is available |
| Machine | A single asset's time-series, cases, work orders, and audit history can be traced together |
| Cases | The operational queue exposes priority, confidence, abstention, classifier state, human status, and CMMS outcome |
| Case detail | Every fact, tool call, calibration decision, priority component, recommendation, and human decision is inspectable |
| CMMS | An approved internal case was translated and written to a foreign system-of-record schema |
| Audit | System, agent, human, and downstream transitions are attributed and timestamped |
| Evaluation | Detection, classification, abstention, calibration, scoring quality, latency, cost, and limitations are measured |

## Core design decisions and trade-offs

### Why polling instead of WebSockets?

Polling every 3.5–8 seconds is simple and sufficient for a one-week triage demo.
It is not appropriate for high-frequency historian ingestion. Production would
use event ingestion and server push or subscriptions while keeping the same API
and domain models.

### Why JSON signal values?

Assets have different sensor rosters. `values_json` and catalog-level signal
metadata keep the prototype flexible. At industrial scale, a time-series store
or narrow tag/value table would improve compression, indexing, retention, and
analytics.

### Why not let the LLM classify everything?

The live evaluation showed that overlapping numeric signatures are not the
LLM's strongest job. Deterministic features plus narrow ML are cheaper,
auditable, and easier to reject OOD. The LLM remains useful for language and
retrieval.

### Why mandatory review even at high confidence?

The assessment prohibits direct autonomous action, and maintenance
interventions carry safety and availability consequences. Confidence controls
how uncertainty is presented, not authorization.

### Why a mock CMMS over HTTP?

It proves the integration contract, schema mismatch, status handling,
idempotency, and retry behavior without requiring SAP credentials. A real
deployment replaces transport/authentication and mapping configuration, not the
triage domain.

## Current limitations to volunteer before being challenged

- Eight real laboratory episodes are development evidence, not customer-site
  validation.
- CWRU episodes are constructed transitions and dataset usage rights need
  confirmation for commercial redistribution.
- Maintenance history and economics are seeded illustrative records.
- The trained ML layer solves only suction versus discharge restriction.
- The simulator/replayer cursor, force-detect flag, runtime LLM override, and
  triage queue are process memory. A multi-replica production system needs a
  durable broker and shared state.
- An anomaly is durable, but an anomaly waiting only in the in-process triage
  queue can require recovery scanning after a process crash; that scanner is
  not implemented.
- Database setup uses `create_all`, not versioned Alembic migrations.
- Authentication is a signed crew-password session, not SSO/RBAC.
- The frontend polls; it does not consume an event stream.
- The mock CMMS shares the deployment/database.
- Render free hosting is demonstration infrastructure, not an SLA.

Volunteering these limits demonstrates judgment. Hiding them invites the
interviewer to conclude that you do not understand production.

## If the live demonstration misbehaves

- **Fleet says backend waking:** open health, explain cold start, use the
  Evaluation page or backup case while it wakes.
- **New case is slow:** explain detector lead-in and triage latency; open a
  prepared case rather than repeatedly injecting faults.
- **Live call cap is exhausted:** keep mock mode. Explain that this is the
  designed cost fallback, not a broken AI feature.
- **CMMS sync fails:** this is a valid resilience demonstration—approval remains
  committed and the retry is idempotent.
- **Network is unavailable:** use the backup recording/screenshots, then defend
  the local code and persisted evaluation artifacts.
- **An interviewer asks for an unsupported claim:** state the limitation and
  describe the next validation step.

## Recommended study order

1. Memorize the 30-second opening and two-minute architecture.
2. Rehearse the seven-minute click path twice without notes.
3. Learn the real/synthetic counts and non-claims.
4. Read `CODE_AND_DATA_FLOW_REFERENCE.md` while following the source files.
5. Practice every question in `PRODUCTION_CHALLENGE_QA.md` aloud.
6. Read `EVALUATION_GUIDE.md`, `ML_EXPERIMENT.md`, and `COST_CONTROL.md` for
   specialist follow-ups.

The goal is not verbatim memorization. The goal is to reconstruct the design
from first principles when the interviewer changes the scenario.
