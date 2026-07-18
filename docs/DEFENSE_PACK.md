# PM Triage — Defense & Domain Pack

Everything you need to walk in, present this artifact, and defend every line of
it — even with limited maintenance-domain background. Read it top to bottom
once, then re-read Sections 6 (Q&A) and 7 (demo) the night before.

**The one sentence to anchor on:** *"I built the workflow a Forward Deployed
Engineer actually ships — telemetry to a triaged, evidence-backed recommendation,
a mandatory human decision, and a write-back into the maintenance system of
record — and then I measured whether the AI part is actually trustworthy."*

---

## 0. What changed since this pack was first written (READ FIRST)

This pack below is still accurate on **architecture, the failure-handling, the
integration story, and the method** — those are the same. But the system grew,
and a few concrete facts in later sections are now stale. Where the text below
says otherwise, this section wins:

- **Real data now grounds it.** A ninth asset, `PMP-03`, replays **real recorded
  telemetry from the SKAB pump testbed** (Skoltech Anomaly Benchmark, GPL-3.0) —
  physically induced rotor imbalance, cavitation, and valve-restriction faults,
  with the dataset authors' own labels used as eval ground truth. It runs its own
  real signal set (vibration g, motor current, loop pressure, motor/fluid temp,
  flow). So the fleet is **8 simulated + 1 real**, not 8 simulated.
- **Real data forced a real design change** (this is a *strong* FDE story): the
  testbed sits at a different operating point in every recording, so fixed
  thresholds are blind there. Detection gained a second deterministic rule — a
  **robust z-score (median/MAD), |z|>4 sustained over 3 readings**, measured
  against the machine's *own* rolling baseline. Both rules are still non-AI and
  quotable.
- **Persistence is Postgres now** (Supabase), in its own `pm_triage` schema, so
  approved cases and work orders **survive redeploys**. SQLite remains the
  local/test default.
- **Governance is real, not described:** an access gate (`APP_ACCESS_PASSWORD`)
  on every state-changing action, with each reviewer's name signed into the audit
  trail from their session token; a **live/mock LLM toggle in the header**
  (audited) with a **hard daily spend cap** that degrades to the mock policy
  rather than stalling; a live-model call failure falls back to mock mid-case and
  says so in the trace.
- **The CMMS corpus got harder on purpose:** 19 corrective records **plus 12
  routine ones** (PMs, calibrations, inspections, false alarms) carrying a
  `record_type` field (SAP order-type analogue), so retrieval must *rank against
  realistic noise*, not just keyword-match.
- **Test count is 74** (not 68). Live URLs: UI `pm-triage.vercel.app`, API
  `pm-triage-backend.onrender.com`, both auto-deploying from
  `github.com/amarshikhar/pm-triage`, backend kept warm and persistent.

### The numbers, corrected and honest

The **mock scripted baseline is current and measured** on this pipeline:

| | mock baseline — synthetic faults | mock baseline — real SKAB episodes |
|---|---|---|
| detection rate | 100% | 100% (4/4 real fault classes) |
| top-1 root-cause accuracy | 57.5% | 50.0% |
| hit@any | 60.0% | 75.0% |

The **live-model figures quoted later (77.5%, ECE 0.046, the cavitation
25%→100% story, the calibration bands) were measured on the *earlier* pipeline**
— before the noisy corpus and the real episodes. They demonstrate the *method*
(measure → find the real cause → fix the system → re-measure), which is the
point, but the specific accuracy has **not yet been re-measured on the current,
harder pipeline** (the OpenRouter key is out of credit). **Do not present 77.5%
as the current live number.** Say: *"the scripted baseline holds at ~57.5%
synthetic / 50% on real data at 100% detection; the live-model delta was +20pp on
the prior pipeline and I'm re-running it on the current one."* That honesty is
itself the FDE signal.

---

## 1. What the assignment is really testing

They tell you the weighting, so believe it. The center of gravity is **not** the
LLM (7%). It is **architecture (30%)** and **engineering discipline (25%)**,
then **enterprise integration (20%)**. An FDE is "a domain-specialized solution
architect and software engineer" who makes "AI work in the real world … within
real enterprise workflows, constraints, and governance." So the artifact has to
look like production plumbing with a human accountable at the controls — not a
clever demo.

Two hard gates in their doc; miss either and you fail regardless of polish:
1. **A meaningful system integration** — not a standalone script.
2. **Mandatory human accountability** — no fully autonomous action.

This artifact is built around both, on purpose.

---

## 2. Domain primer — every term, in plain English

Skim this until none of these words make you hesitate. If a judge uses one, you
want to answer without translating in your head.

### The business problem
- **Predictive / condition-based maintenance:** fixing a machine *before* it
  breaks, based on its measured condition, instead of on a fixed calendar or
  after it fails. Cheaper than a breakdown, less wasteful than replacing good
  parts early.
- **Unplanned downtime:** the machine stops when you didn't plan for it. This is
  the expensive event — lost production, idle crews, rush parts. The whole
  business case is reducing it.
- **Triage:** deciding what to look at first and how urgently. Same word as a
  hospital ER. A plant generates far more alerts than technicians can chase, so
  triage quality *is* the product.
- **Root cause:** the actual underlying reason (e.g. "suction strainer blocked"),
  as opposed to the symptom you can see ("vibration is high").
- **Floor technician / maintenance planner:** the technician does the physical
  work; the **planner** schedules it and owns the work-order queue. In this app,
  the **planner** is the human who approves/rejects each case.

### The machines and what we measure
- **CNC mill:** a computer-controlled cutting machine (spindle spinning a tool).
- **Compressor:** makes compressed air for the whole plant (utilities).
- **Pump:** moves liquid — coolant, hydraulic oil.
- **Conveyor:** the belt/chain line that moves product.
- **Telemetry:** the stream of sensor readings coming off a machine.
- **Temperature (°C), Vibration (mm/s), Pressure (kPa), RPM:** the four signals
  we read. **Vibration in mm/s** is the standard unit for machine vibration
  velocity; rising vibration is the classic early warning of mechanical wear.
  **kPa** = kilopascals, a pressure unit.

### The four fault signatures (what they physically are)
These are the faults the simulator injects and the agent must recognize. Learn
the one-line physical story for each — judges may ask "what is cavitation?"
- **Bearing wear:** the bearing (the part a shaft spins inside) degrades →
  **vibration rises**, with a little extra heat from friction. On a conveyor the
  same signature is a worn drive chain or a seized roller.
- **Overheat:** cooling is failing (blocked coolant, dead fan, low oil) →
  **temperature climbs** past its limit.
- **Pressure loss:** a leak or a worn valve → **pressure falls** below where it
  should be.
- **Cavitation:** in a pump, if the inlet ("suction") is starved, vapor bubbles
  form and violently collapse → **vibration rises AND pressure swings
  erratically**, with a gravel-like noise. The tricky one: it looks like bearing
  wear on vibration alone; only the erratic pressure separates them. (This
  distinction is the story in Section 5 — remember it.)

### Detection terms
- **Threshold / limit:** a fixed line ("temperature must stay under 92°C"). Cross
  it and you've breached.
- **Rolling window:** the last N readings (here 30). "Rolling" = it moves forward
  as new data arrives.
- **Z-score / sigma (σ):** how unusual a reading is versus recent history,
  measured in standard deviations. "4.1 sigma above the last 30 readings" means
  "far outside normal variation," and it's a number a technician can trust
  because it's arithmetic, not a guess.
- **Drift:** the sustained march of a signal (later-half average minus
  earlier-half average). Separates "creeping upward" from "noisy but flat."
- **Volatility:** how erratic a signal is, as a % of its mean — independent of
  drift. Cavitation is high-volatility pressure; a leak is drifting-but-smooth
  pressure. **Drift vs volatility is the two-axis trick that separates the
  faults.**
- **Severity (low/medium/high):** how far past the limit the breach is.

### The AI terms
- **LLM (large language model):** here, Claude Sonnet 4.5. Used only for the
  judgment step (correlate symptoms to historical causes), never for detection
  or scoring.
- **Tool calling / function calling:** the model doesn't have the data; it asks
  for it. It emits a structured request ("call `search_maintenance_history` with
  these keywords"), our code runs the real function, returns the result, and the
  model continues. This is how you ground an LLM in real systems.
- **Agent / tool loop:** the model calling tools repeatedly until it has enough
  to answer — bounded here to 8 steps so it can't run away.
- **Structured output:** we force the final answer into a fixed JSON shape
  (root_cause, confidence, cited_work_orders, …) so the rest of the system can
  consume it deterministically.
- **Confidence:** the model's own 0–1 self-rating of its answer.
- **Calibration / ECE:** does the confidence mean anything? If it says 75% is it
  right ~75% of the time? **ECE (Expected Calibration Error)** measures the gap.
  Low ECE (ours is 0.046 live) = the confidence is trustworthy, which is what
  lets you set a human-review threshold from data instead of opinion.
- **Top-1 accuracy:** how often the single top answer is correct.
- **hit@any:** how often the correct cause is named *anywhere* in the answer,
  even as a secondary guess — separates "wrong" from "right but hedged."
- **Confusion matrix:** a table of "true fault → what it predicted," so you can
  see *which* mistakes it makes, not just the rate.

### The enterprise / integration terms
- **CMMS (Computerized Maintenance Management System):** the software of record
  for maintenance — work orders, equipment history, schedules. Real ones: **SAP
  PM** (Plant Maintenance), **IBM Maximo**, **Infor EAM**. In this artifact a
  mock CMMS stands in for it.
- **System of record:** the authoritative store for a kind of data. For
  maintenance actions, that's the CMMS. "Writing back to the system of record"
  means the action becomes official, not just a note in our app.
- **Work order:** the CMMS ticket that authorizes and tracks a maintenance job.
- **SAP PM notification:** in SAP, the object that says "something's wrong, please
  look." Types: **M1** = malfunction report (something is failing — what we
  raise), **M2** = maintenance request, **M3** = activity report. A notification
  can become a work **order** (the scheduled job). We raise an **M1** because
  condition monitoring detected a developing malfunction.
- **Functional location (FLOC):** SAP's term for *where* in the plant an asset
  sits (e.g. "Hall 1 / Line A") — distinct from the equipment itself.
- **Equipment:** SAP's term for the physical asset (our "machine").
- **ISO 14224:** the international standard for collecting reliability and
  maintenance data for equipment. It defines a shared vocabulary of **failure
  modes** (VIB = vibration, OHE = overheating, LOO = low output, CAV =
  cavitation…) so data is comparable across plants and vendors. We tag each work
  order with an ISO 14224 **damage code** so it's speaking the CMMS's language.
- **Priority code:** SAP priorities run **1–4 where 1 = very high** — the
  *inverse* of our P1–P4 label direction, which is exactly why translation
  (not renaming) is needed.
- **Anti-corruption layer (ACL):** a design pattern (from Domain-Driven Design).
  When you integrate with a foreign system, you put a translation layer between
  your clean domain model and their schema, so their concepts and quirks never
  leak into yours. Our `cmms_adapter.py` *is* the ACL: it's the only place that
  knows the CMMS's field names.
- **Idempotency:** doing the same operation twice has the same effect as doing it
  once. We key each work-order creation on the case id, so a retry after a
  timeout — or a double-click on Approve — never raises two tickets. The
  **Idempotency-Key** header is how the caller tells the CMMS "this is the same
  request, not a new one."
- **Retry with backoff:** if a call fails transiently, try again, waiting a
  little longer each time (0.2s, 0.4s…). Backoff avoids hammering a struggling
  service.
- **REST / HTTP status codes:** our services talk over HTTP. **2xx** = success,
  **4xx** = the caller's fault (bad request — don't retry), **5xx** = the
  server's fault (maybe transient — safe to retry). The adapter treats them
  differently on purpose.
- **ASGI:** the Python async web-server interface FastAPI speaks. Relevant only
  because our adapter reaches the CMMS in-process over a real HTTP transport
  without needing a second running server.
- **Audit trail:** an append-only log of who did what when — `system` detected,
  `agent` triaged, `human:shikhar` approved, `system` created the work order.
  This is the governance backbone.

### The priority factors
- **P1–P4:** our maintenance priority. **P1 = most urgent.**
- **Criticality (1–5):** how much the business cares about this asset. A main
  conveyor or the plant air compressor is 5 (its failure stops a line); a standby
  unit is 2.
- **Safety flag:** was the closest historical precedent a safety incident? If so,
  it forces P1 and can never be downgraded by the AI.
- **Recurrence:** has this machine+metric raised cases before? Repeat offenders
  get a small bump.
- **Downtime cost ($/hr):** what an idle hour on this asset costs. Turns P1–P4
  into money on the case.

---

## 3. Architecture walkthrough — module by module

Follow the data. For each file: what it does, and the one design decision to be
ready to defend. All backend paths are under `backend/app/`.

**1. `simulator.py` — the IoT feed.** Generates readings for 8 machines on a
tick. Faults ramp a metric away from baseline over several ticks so detection
sees a realistic trend, not a single spike. Faults start randomly (seeded, so
reproducible) or on demand via the "Inject fault" button.
*Defend:* "It's seeded RNG, so demos and the eval are reproducible; faults ramp
so we're testing trend detection, not spike detection."

**2. `detector.py` — rule-based anomaly detection. NOT the LLM.** Checks each
reading against fixed limits and a rolling z-score. When something breaches, it
also computes `signal_context`: for *every* metric, its drift, volatility, and
range over the window.
*Defend — this is a top-3 point:* "Detection is deterministic, cheap, and
quotable to a technician — '96.2°C exceeded the 92°C limit, 4.1 sigma above the
last 30 readings.' I don't spend an LLM call or LLM trust on something arithmetic
does better. The LLM starts where judgment starts."
*Why signal_context matters:* a breach names one metric, but the fault is
identified by the *pattern across all of them.* Rising vibration alone can't tell
bearing wear from cavitation; pressure sitting still vs swinging 9% can. The
detector computes that, deterministically, and hands it to the agent.

**3. `models.py` — the data model (SQLAlchemy ORM).** Machine, TelemetryReading,
Anomaly, MaintenanceLog (the historical CMMS), TriageCase, AuditEvent. Note two
fields on Anomaly: `context_json` (the per-signal stats) and
`ground_truth_fault` (which fault was really injected — **the evaluation label**,
never shown to the agent).
*Defend:* "`ground_truth_fault` is the free labelled data the simulator already
knows. Detection is forbidden from reading it, or the accuracy measurement would
be circular."

**4. `agent/tools.py` — the agent's tools.** Three read-only tools:
`get_machine_info`, `get_recent_telemetry`, `search_maintenance_history` (keyword
search over the historical work orders). Each returns plain data and every call
is logged into the case trace.
*Defend:* "The history search is simple scored keyword overlap — good enough for
a mock CMMS and fully explainable. In production you swap it for embedding search
against the real CMMS; the tool interface doesn't change."

**5. `agent/llm.py` — model access + mock mode.** Live mode calls Claude Sonnet
4.5 via OpenRouter (OpenAI-compatible tool calling). **Mock mode** is a
deterministic scripted policy that follows the *identical* tool-calling protocol,
so the whole pipeline runs offline with no key.
*Defend:* "Mock mode isn't a shortcut — it's demo insurance and it's what makes
the eval's baseline honest: it's a real scripted keyword policy, so the live-vs-
mock delta is 'what does the LLM actually buy me.'"

**6. `priority.py` — the priority formula. NOT the LLM.** A transparent function:
criticality + severity×2 + recurrence + safety → a score → P1–P4. Safety always
forces P1. The agent may propose a **±1 notch** adjustment with a written
justification, clamped, and it can never downgrade a P1.
*Defend — top-3 point:* "Priority is a governance decision, so it's an auditable
formula a planner can read, not vibes from a model. The AI gets exactly one notch
of discretion, in writing, in front of a human."

**7. `agent/triage.py` — the orchestrator.** Given an anomaly: build the prompt
(including the signal-context table), run the bounded tool loop, parse the JSON
answer (robust to the model wrapping it in prose/markdown), combine the LLM's
root-cause hypothesis with the deterministic priority, compute the **dollar
exposure** (worst cited precedent's downtime × the asset's hourly cost — kept
*out* of the score), and persist a `TriageCase` as `pending_review` — never
beyond it.
*Defend:* "The agent produces a hypothesis and evidence; it never changes state
past `pending_review`. Everything after is the human's."

**8. `routes.py` — the API + the human gate + the write-back.** REST endpoints
for machines, telemetry, cases, audit, and the demo fault lever. The critical one
is `POST /cases/{id}/decision`: the *only* way a case leaves `pending_review`. On
approval it calls `_sync_case_to_cmms`, which writes the work order back. On
rejection nothing goes downstream.
*Defend:* "A case is born `pending_review` and only a human decision with a
reviewer name moves it. Decisions are final — a second one gets a 409 — and every
transition is audited with before/after diffs."

**9. `cmms/service.py` + `cmms/models.py` — the CMMS (system of record).** A
*separate* FastAPI app with its *own* schema in the CMMS's vocabulary
(`functional_location`, `equipment_id`, `notification_type`, `priority_code`,
`damage_code`). Create is **idempotent on the Idempotency-Key**. Mounted at
`/cmms` so you can inspect it directly.
*Defend:* "It's a genuinely separate service with a foreign schema. The triage
app never imports its internals — it only speaks HTTP to it. That's the boundary
you'd cut to drop in real SAP PM."

**10. `agent/cmms_adapter.py` — the anti-corruption layer.** The only place the
two vocabularies meet. Translates a triage case into the CMMS schema (P1→priority
code 1, location→functional location, metric→ISO 14224 damage code), POSTs it
over HTTP with the idempotency key, retries transient failures/5xx with backoff,
fails fast on 4xx, and raises `CmmsUnavailable` if the CMMS stays down.
*Defend — the new top point:* "This adapter is the whole integration story. Their
schema never leaks into my domain model; the day the CMMS becomes real SAP PM,
only this file and the transport change. And it's reliable: idempotent so a retry
never double-raises, retried so a blip doesn't lose an approved decision."

**11. `eval/` — the evaluation harness.** Covered in its own section below,
because it's your differentiator.

**Frontend (`frontend/`):** a Next.js dashboard — fleet cards with live
sparklines, the triage queue, the case detail (anomaly, signal-context table,
root cause, evidence work orders, priority formula, dollar exposure, agent trace,
approve/reject/override, and the resulting CMMS work order), a **CMMS tab**
showing the system of record, and an **audit trail** tab.

---

## 4. The evaluation harness — your single biggest differentiator

Almost every candidate will show a working demo. Very few will show they
*measured* whether the AI is trustworthy and then told you honestly what the
number doesn't prove. **Lead with this.** It hits SDLC (25%) and agentic-AI (7%)
and, more importantly, signals seniority.

**The idea in one line:** the simulator already knows which fault it injected, so
**every anomaly it raises is a free labelled example** — a labelled dataset that
was being thrown away. The harness turns that label into a measurement.

**What it does:** drives the *real* pipeline (real simulator, real detector, real
agent tool loop) on a machine with a known fault, then scores the case that comes
out. It never reimplements production logic — if it did, it'd be measuring a copy
of the system.

**The headline numbers** — ⚠️ the *live* column below is from the **earlier
pipeline** (see Section 0); the mock baseline is current, and the live re-run on
the current pipeline is pending OpenRouter credit. Present it that way.

| | mock (scripted keyword baseline) | live (Claude Sonnet 4.5) — *prior pipeline* |
|---|---|---|
| top-1 accuracy | 57.5% | 77.5% *(re-measure pending)* |
| hit@any | 60.0% | 85.0% *(prior)* |
| ECE (calibration error) | 0.191 | 0.046 *(prior)* |

- **+20 points over a scripted baseline** is what the LLM *buys* — measured, not
  asserted.
- **The confidence is trustworthy.** In the 0.70–0.85 band it says 75.5% and is
  right 77.4%. Above 0.85 it says 86% and is right 100% — *under*-confident. So
  the human-review gate isn't a philosophical stance; it's a threshold you can
  argue from data.
- **Two independent scorers cross-check the instrument.** One reads the agent's
  free text, one reads its cited work-order ids through a curated map. They share
  no code, so the harness reports their **agreement (89.7%)** — checking the
  measuring tape, not just the agent. (It earned that twice: two "agent noise"
  findings turned out to be harness bugs the agreement check surfaced.)

**The story that shows judgment — memorize this one.** Live cavitation first
scored **25%** — every case called it bearing wear. It wasn't retrieval failure:
the agent *cited the cavitation work order in all four trials.* It had the
precedent and no way to choose it, because both faults present as rising
vibration and the detector was only reporting the metric that breached. **No
prompt fixes an absent signal.** So I made the detector report drift/volatility/
range for *every* signal — the shapes separate cleanly (cavitation's pressure
swings at 9% volatility vs wear's 1%). **Cavitation went 25% → 100%.** That's the
FDE loop: measure, find the real cause, fix the system, re-measure.

---

## 5. What to volunteer as weaknesses (this is a strength move)

Senior engineers state limits before they're asked. Say these *yourself*:
- **The ground truth is synthetic.** This measures whether the agent recovers a
  fault the simulator seeded and the CMMS already documents — friendlier than a
  real plant, so 77.5% is optimistic. "The harness is the deliverable, not the
  number: point it at real CMMS data and the loop is unchanged."
- **n=40 is small** (per-class n=10). The mock's own score swung 50→57.5% between
  a 16- and 40-trial run with identical code — that's the noise floor; don't
  over-read any single class figure.
- **Fault classes are symptom signatures, not physical causes** — the work-order
  map encoding that is a curated judgement, kept small and auditable in one file.
- **MAX_STEPS=8 looks tight** — one trial in 40 exhausted the budget and produced
  a correctly-low-confidence placeholder. The obvious fix is unmeasured, so I
  don't claim it.

---

## 6. Judge Q&A bank

Grouped by rubric area. Answers are yours to say in first person. Adversarial
ones are marked ⚔.

### Architecture & workflow (30%)
**Q: Why isn't the LLM doing the anomaly detection?**
A: Detection must be deterministic, cheap, and explainable to a floor technician.
Thresholds and z-scores give a number he can trust — "4 sigma over 30 readings."
An LLM there would be slower, costlier, non-reproducible, and un-auditable, for a
job arithmetic does better. The LLM starts where judgment starts: correlating
symptoms to historical causes.

**Q: Why is priority a formula and not the LLM's call?**
A: Priority is a governance decision that drives who gets dispatched. It has to be
an auditable rule a planner can read and contest. The AI gets exactly one notch
of discretion, in writing, and can never downgrade a safety-driven P1.

**⚔ Q: Isn't this just a wrapper around an API call?**
A: The LLM is 7% of the weight and one step of the pipeline. The work is the
seams: deterministic detection, a signal-context computation that makes the hard
faults separable, a transparent priority formula, a structural human gate, a
bidirectional CMMS integration through an anti-corruption layer, and an eval
harness that proves the AI part is calibrated. The LLM is the easy part.

**Q: Walk me through one case end to end.**
A: [Do it live — Section 7. Narrate detector → agent tools → evidence → priority →
approve → work order → audit.]

### Engineering & SDLC (25%)
**Q: How do you know it works?**
A: 66 tests plus an eval harness that drives the real pipeline against ground
truth: 77.5% vs a 57.5% scripted baseline, ECE 0.046. And I can tell you exactly
what that number doesn't prove [Section 5].

**Q: What's your test strategy?**
A: Unit tests for the deterministic pieces (detector rules, priority formula and
its clamps, the adapter's translation and retry/idempotency), end-to-end tests
for the flows (mock agent produces an explainable case; approve writes back and
audits; reject doesn't; a second decision is refused), and the eval harness as a
behavioural/quality gate on the AI. Fast pieces are deterministic; the
non-deterministic piece is measured statistically.

**⚔ Q: Your tests use mock mode — doesn't that prove nothing about the real model?**
A: Correct, and that's why the eval harness exists and runs in *live* mode
separately. Mock mode proves the plumbing (tool loop, parsing, persistence, gate,
write-back) is correct deterministically; the live eval proves the model is
accurate and calibrated. Two different questions, two different tools.

**Q: What happens when the model returns malformed output?**
A: `_extract_json` recovers the answer from prose or markdown fences; if there's
genuinely no object, the case is filed at confidence 0.2 with the raw text, so it
surfaces to a human rather than crashing. If the tool loop exhausts its budget,
it files a confidence-0.1 "escalate to human" placeholder.

### Systems integration (20%)
**Q: What's the meaningful integration here?**
A: It's bidirectional. The agent **reads** the CMMS history as a tool to reason,
and an approved decision is **written back** to the CMMS as a work order. The
CMMS is a separate service with its own schema; the triage side reaches it only
over HTTP through an anti-corruption adapter.

**Q: What is the anti-corruption layer and why?**
A: It's the single translation point between my domain (P1–P4, metrics) and the
CMMS's schema (priority code 1–4, functional location, ISO 14224 damage codes).
It keeps their vocabulary from leaking into my model, so when the CMMS becomes
real SAP PM, only the adapter and the transport change — not my domain logic.

**⚔ Q: The CMMS is in-process — that's not a real integration.**
A: It's a separate ASGI service with its own datastore and a deliberately foreign
schema, reached only over HTTP with real status codes and an idempotency key.
The transport is in-process so the demo has no second server to babysit; set
`CMMS_BASE_URL` and the exact same adapter talks to a networked SAP PM gateway. I
chose to make the *boundary* real and the *transport* swappable, which is the
honest way to slice this in a week.

**Q: What happens if the CMMS is down when a planner approves?**
A: The human decision is already committed and audited — we never lose it. The
push retries with backoff; if it still fails, the case is marked sync-failed and
audited, and a planner retries with one button. Because the write is idempotent
on the case id, that retry (or any double-submit) never raises a duplicate work
order. [Optionally demo it.]
Two failure kinds are kept distinct on purpose: an *outage* (5xx / no answer) is
transient, so the case is `failed` and retryable — and a retry that still can't
reach the CMMS answers **502**, never a deceptive 200. A *4xx rejection* means
the CMMS refused our payload — a translation bug on our side — so the case is
`rejected`, the retry endpoint refuses with **409** (replaying a bad payload can
never succeed), and the CMMS error is in the audit trail for the fix.

**Q: Why idempotency, concretely?**
A: Networks time out after the server already did the work. Without idempotency,
the retry raises a second work order for one fault — a real, expensive failure
mode in maintenance systems. The Idempotency-Key makes the create safe to repeat.

### Domain (15%)
**Q: What's cavitation? Bearing wear?** A: [Section 2 — give the one-line
physical story and the signal signature.]

**Q: Why an M1 notification and priority 1–4?**
A: In SAP PM an M1 is a malfunction report — the right object for "condition
monitoring detected a developing fault." SAP priorities run 1–4 with 1 = very
high, the inverse of my P1–P4 label, which is exactly why the adapter *translates*
rather than renames. The damage codes are ISO 14224 failure modes so the work
order is comparable across the plant's reliability data.

**Q: Where does the dollar figure come from?**
A: The worst cited historical precedent's downtime hours × the asset's hourly
downtime cost from the catalog. It's informational — deliberately *not* in the
priority score, because cost is a business input and the priority is a governance
rule. **If cost drove the rank, an expensive-but-trivial fault could outrank a
safety issue on a cheap asset — exactly backwards.** So safety and criticality set
the queue; cost is shown next to it to make the business case ("this P1 is $14k/hr
of exposure"), not to decide who gets dispatched first.

### Governance (3%) & the hard ones
**Q: Where's the human accountability?**
A: Structural, not optional. No case advances without a named human decision;
nothing reaches the system of record without an approval; every step —
detection, agent run, each tool call, the human decision, the write-back — is in
an append-only audit trail attributed to `system`, `agent`, or `human:<name>`.

**⚔ Q: What if the AI hallucinates a root cause?**
A: Three containments. It must cite historical work orders as evidence, shown to
the planner. Its confidence is *calibrated* (ECE 0.046), so low confidence
genuinely flags "look harder." And it can't act — a human approves before
anything reaches the CMMS, and even then it's a maintenance recommendation, never
machine control.

**⚔ Q: Why not a trained ML classifier instead of an LLM?**
A: For the *detector*, I effectively did — it's deterministic rules, no LLM. For
*root cause*, the value is correlating free-text symptoms to free-text historical
work orders and explaining the link in a technician's language, which is exactly
an LLM's strength and would need a large labelled corpus to train a classifier
for. And I measured it beats the keyword baseline by 20 points. If a plant had
years of labelled failures, a hybrid is the right evolution — the eval harness is
already the yardstick to prove any such change helps.

**⚔ Q: How does this scale to 10,000 machines?**
A: Detection is O(1) per reading and stateless — it shards trivially by machine.
The expensive, rate-limited step is the LLM, and it's already bounded: a cooldown
plus an open case suppresses duplicate anomalies per machine+metric, so an
unreviewed backlog stops spending. At fleet scale you'd move triage onto a queue
(one consumer per shard), cache identical anomaly→precedent lookups, and the DB
goes SQLite→Postgres behind the same ORM. The write-back is already idempotent,
which is what makes at-least-once queue delivery safe.

**⚔ Q: Security / data governance?**
A: The agent's tools are read-only and scoped to maintenance data — no PII, no
control-plane access. The only write is one narrow, validated work-order create
behind a human approval. In production the adapter is where you'd add
authentication, secrets management, and PII redaction — one chokepoint, which is
another reason the ACL pattern earns its place.

**Q: What would you build next, given another week?**
A: Point the harness at a slice of real anonymized CMMS data to get an honest
accuracy read; add embedding search to the history tool and A/B it *through the
harness*; and add auth + a real queue to the write-back. In priority order,
because the harness tells me which change actually moves the number.

**Q (the trap): something you genuinely don't know.**
A: "I haven't validated that — here's how I'd find out." Never bluff. The eval
harness *is* your posture: you measure instead of assert. Use the same line for
any gap: "I'd measure it before claiming it," and gesture at how.

---

## 7. Live demo script (5–7 minutes)

**Warm the backend first** (Render free spins down after ~15 min idle, ~50s cold
start): hit the API `/api/health` a couple of minutes before you present, and
confirm `"simulator_running": true`. Have mock mode ready as the fallback.

1. **Frame it (20s):** "Predictive-maintenance triage: telemetry in, a triaged
   evidence-backed recommendation out, a mandatory human decision, and a
   write-back to the maintenance system of record. No machine control anywhere."
2. **Fleet (20s):** the 8 cards streaming live sparklines. Point out criticality.
3. **Inject a fault (10s):** top bar → e.g. `CMP-01` + `overheat` → *Inject fault*.
   "That's the demo lever; normally the simulator raises these on its own."
4. **Case appears (~15s):** open it. Walk the panels top to bottom:
   - the detected anomaly (the quotable sigma line),
   - the **signal-context table** — "these are the same numbers the agent saw;
     one metric breached but the pattern names the fault,"
   - the root cause + the cited historical work orders (safety flags in red),
   - the **priority formula** shown component-by-component,
   - the **dollar exposure**,
   - the **agent trace** — the actual tool calls it made.
5. **Approve it with your name.** Then: "Watch the loop close." Show the **CMMS
   work order** that appears on the case, then open the **CMMS tab** — "there it
   is in the system of record, with the translated fields: priority code 1, ISO
   14224 damage code, functional location." Then the **audit trail** tab —
   "system detected, agent triaged, human approved, system created the work
   order; every step attributed."
6. **The trust question (the mic-drop):** "How do I know the AI is any good?"
   Open `eval-report.json` / the table: "77.5% vs a 57.5% scripted baseline over
   40 labelled trials, and the confidence is calibrated to within 2 points — so
   the human-review threshold is set from data." Then volunteer one caveat.
7. **If time / if asked — resilience:** the mock-mode pill ("LLM down? identical
   pipeline"); and CMMS-down → sync-failed → *Retry CMMS sync* ("decision never
   lost, retry is idempotent").

**Fallbacks:** live LLM slow/down → say so, switch to mock (identical UI), keep
going. Backend cold → you warmed it; if not, narrate while it wakes. Never let a
network blip read as "the artifact is broken" — the mock/idempotency/retry design
is *there precisely for this*, so name it as a feature.

### Demo gotchas — things that look like bugs but are the design working

Know these cold; each one bit me in testing and each is actually a *feature* to
name out loud if it surfaces.

- **Re-injecting the same fault seems to "do nothing."** By design: the detector
  **suppresses a duplicate anomaly for the same machine+metric while a case is
  open or within a 10-minute cooldown** (`COOLDOWN_MIN`), so it can't spam alerts
  or burn LLM calls on a backlog nobody has reviewed. To get a fresh case on
  demand, use a **different machine**, or a **different fault type** (overheat =
  temperature, bearing/cavitation = vibration, pressure_loss = pressure — faults
  on different metrics don't collide), or clear the fault and wait out the
  cooldown. *Say it as:* "that's the bounded-spend guard — it won't re-alert on
  something already in the queue."
- **The root-cause text may not contain the fault's name.** In live mode the
  root cause is Claude's own prose — it might say "cooling system degradation" for
  an overheat, or "unloader valve sticking" instead of "cavitation." That's not
  wrong: the eval scores the fault **class** and the cited work orders, not
  whether the sentence contains a keyword. *Say it as:* "the model explains in a
  technician's language; the class is what's scored."
- **Cavitation is physically a pump phenomenon.** For a clean cavitation demo use
  **PMP-01 / PMP-02**, not the compressor or a mill — on a pump the pressure
  instability that defines it actually shows up, which is the whole point of the
  signal-context story.
- **A redeploy or a >15-min sleep re-seeds the DB.** Render free is ephemeral, so
  case ids restart at 1 and the queue clears. Do a fresh inject→approve a couple
  of minutes before you present rather than relying on an earlier run.

---

## 8. Presentation strategy — what to keep in mind

- **Open with the workflow and the human gate, not the model.** Mirror their
  rubric: architecture and accountability first. The LLM is 7%; don't spend your
  first 3 minutes there.
- **Lead the "does it work?" moment with the eval harness.** It's the single
  thing that separates you from a demo-only candidate. Then immediately volunteer
  a caveat — stating limits before you're asked is the strongest seniority signal
  in the room.
- **Tie the integration to your background.** You've worked with SAP QM/PM
  notifications and plant telemetry at Baker Hughes. Say so when you hit the
  write-back: "this is the SAP PM notification→order flow I've worked inside;
  the adapter speaks that language." That's a credibility only you have.
- **Every time you claim something, gesture at the evidence.** "Calibrated" →
  the calibration table. "Idempotent" → the test / the retry demo. "Explainable"
  → the signal-context table and citations. Claims backed by artifacts read as
  engineering; claims alone read as slideware.
- **Use their own words back:** "production-grade," "governance," "human
  accountability," "systems integration." You're being scored on fit to a
  definition; speak the definition.
- **When you don't know, say the measuring line.** "I'd measure it before
  claiming it." It's on-brand for this whole artifact and never sounds weak.
- **Time-box the LLM talk.** If they push deep on prompt engineering, answer
  briefly and steer back: "the prompt matters, but the leverage was the *signal*
  I fed it — no prompt fixes an absent signal," and tell the cavitation story.

---

## 9. Tech-stack declaration (copy-paste for the submission)

- **Languages & frameworks:** Python 3.11 (FastAPI, SQLAlchemy 2, Pydantic v2);
  TypeScript with Next.js 14 (App Router); hand-rolled SVG charts, no chart lib.
- **AI/LLM:** Claude Sonnet 4.5 via OpenRouter (OpenAI-compatible tool/function
  calling), model overridable via `OPENROUTER_MODEL`; a deterministic mock-LLM
  mode implementing the identical tool-calling protocol for offline/eval runs.
- **Infrastructure & data (updated):** Postgres (Supabase) in production, own
  `pm_triage` schema, SQLite for local/test — via SQLAlchemy (originally SQLite;
  ORM); an in-process simulated IoT telemetry feed; a mock CMMS exposed as a
  separate ASGI service with its own schema; Render (backend) + Vercel (frontend).
- **Integration:** bidirectional CMMS — read (history search tool) and write
  (approved work-order write-back) — through an anti-corruption adapter over HTTP,
  with idempotency (Idempotency-Key) and retry-with-backoff; `CMMS_BASE_URL`
  repoints it at a networked CMMS (e.g. SAP PM).
- **Evaluation:** in-repo harness scoring the agent against simulator ground truth
  — top-1 accuracy, per-class confusion, confidence calibration + ECE, and a
  live-vs-scripted delta, with two independent cross-checking scorers.
- **Testing/tooling:** pytest (66 tests), reproducible seeded runs.

---

## 10. 90-second cheat sheet (glance before you walk in)

- **Pitch:** telemetry → triaged evidence-backed recommendation → mandatory human
  decision → write-back to the system of record. Measured, not asserted.
- **3 design lines:** detection is rules not LLM; priority is a formula not vibes;
  the loop closes into the CMMS through an anti-corruption layer, with a human in
  the middle.
- **Differentiator:** the eval harness — 77.5% vs 57.5% baseline, ECE 0.046,
  two cross-checking scorers. Then a caveat.
- **Best story:** cavitation 25%→100% by adding a *signal*, not a prompt.
- **Integration one-liner:** "separate CMMS service, foreign schema, reached only
  through an idempotent retried adapter; swap `CMMS_BASE_URL` for real SAP PM."
- **When stuck:** "I'd measure it before claiming it."
- **Warm the backend before you present.**
