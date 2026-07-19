# PM Triage defense pack — current

## 30-second pitch

“This system turns machine telemetry into a maintenance recommendation without
letting an AI control equipment. Deterministic rules detect anomalies, an
auditable signature layer classifies only when signals are separable, the LLM
retrieves precedent and explains what to do, confidence can abstain, and a named
planner must approve before an idempotent adapter creates a CMMS work order.
The eval reports accuracy, coverage, calibration, OOD behavior, and scorer
coverage on simulated faults plus eight real episodes across SKAB and CWRU.”

## The architecture answer

```text
telemetry
  → deterministic detection
  → cross-signal statistics
  → physics rules + narrow trained restriction classifier
  → learned OOD / calibrated abstention
  → mock/live tool-calling investigation
  → evidence-grounded confidence and abstention
  → pending-review case
  → named human decision
  → approved-only CMMS work order
  → audit trail
```

The component boundaries are the point:

- Detection does not depend on the LLM.
- Classification of numeric signatures does not belong solely to the LLM.
- Priority is a formula, not generated prose.
- The LLM does explanation, history synthesis, and action drafting.
- A human owns every operational decision.

## Numbers to quote

Fresh deterministic runs after the 2026-07-19 fixes:

| Evidence | Synthetic n=24 | Real n=8, SKAB + CWRU |
|---|---:|---:|
| Detection | 100% | 100% |
| Hybrid classifier overall top-1 | 75.0% | 87.5% (7/8) |
| Hybrid classifier coverage | 79.2% | 87.5% (7/8) |
| Hybrid classifier selective accuracy | 94.7% | 100% (7/7) |
| Full-system coverage | 79.2% | 87.5% |
| Full-system selective accuracy | 89.5% | 100% (7/7) |
| ECE | 0.207 | 0.239 |

Always say “7/7 accepted real cases, 7/8 overall, n=8,” never “100% real-data
accuracy.” The sample is far too small for a plant-wide claim.

Do not quote the older Sonnet live results as current; the pipeline changed and
a new live DeepSeek run has not been purchased.

## Likely interview questions

### Is the ML classifier finished?

Yes for one narrow job: Extra Trees separates SKAB suction from discharge
restriction. It trains on 17 physical experiments, calibrates only on grouped
out-of-fold predictions, and passes a frozen 3/3 restriction test. Rules still
own all other classes. It is not a universal classifier.

### Does the LLM work better than the classifier?

They should not own the same job. On synthetic numeric classification the
hybrid classifier is the owner and is 7/8 overall on the current real suite.
The LLM's job is explanation, precedent use, recommended action, and work-order
drafting. A guard prevents it from replacing a concrete classifier class.

### Why so much abstention?

Because the model should only answer inside its supported distribution. The
narrow ML layer now resolves the restriction pair but rejects same-roster novel
faults and unsupported sensor rosters. The remaining real cavitation recording
is routed to the planner instead of being forced into a valve class.

### How is confidence calibrated?

It starts with the model's raw confidence, then deterministically discounts it
for weak precedent, non-diagnostic language, signature conflict, or signature
abstention. If the signature layer cannot separate the classes, confidence is
capped at 0.44 and the case enters the uncertainty path.

### Is the human gate selective?

Operational authorization is mandatory for every case. The abstention path is
selective uncertainty escalation inside that mandatory review. The system does
not auto-approve high-confidence maintenance orders; that would weaken the
challenge's accountability requirement.

### What tools can the agent call?

Only three read-only tools: machine catalog, recent telemetry, and maintenance
history search. No tool can control a machine or read the evaluation label.

### What happens if the LLM fails or gets expensive?

Production is mock by default. Live mode is an authenticated toggle. Random
production faults are off. Every provider request is reserved and logged, with
12-request and $0.25 daily limits plus a 700-output-token ceiling. Failure or
cap exhaustion continues in deterministic mode and leaves a trace.

### Why DeepSeek instead of GPT-4o?

DeepSeek V4 Flash is the recommended cost-first tool-use model through the
existing OpenRouter endpoint. GPT-4o mini is the fallback if its tool calls fail
the smoke test. Full GPT-4o is not the cheap option. The architecture keeps the
model name configurable so the eval—not preference—decides.

### What is the meaningful integration?

The agent reads maintenance history and an approved case writes back a CMMS work
order through a foreign-schema adapter. P1–P4 becomes CMMS priority 1–4;
temperature becomes OHE, pressure/flow LOO, vibration VIB, cavitation CAV;
the case id becomes the idempotency key. Retries cannot duplicate work orders.

### Is the CMMS a truly separate production system?

It is a separate FastAPI application and HTTP/domain boundary but is mounted in
the same deployment and uses the same configured SQL database for the demo. The
boundary, status codes, schema translation, retries, and idempotency are real;
independent deployment/authentication against SAP PM or Maximo is future work.

### What does the Render keep-warm workflow do?

It sends a health HTTP request every ten minutes to reduce cold starts. It does
not inject a fault, run triage, call an LLM, or spend tokens.

### What would you build next?

Collect natural customer fault-onset recordings, especially discharge and
cavitation; lock an external site-level validation set; confirm production data
rights; then monitor acceptance, selective accuracy, drift, and human
corrections. Run a capped DeepSeek-vs-GPT-4o-mini comparison only after the
pipeline is published.

## Five-minute demo

1. Start in mock mode and show the free-mode pill and zero/limited paid budget.
2. Open a machine and explain that sparklines display readings; Python rules do
   detection.
3. Inject a synthetic fault. Expect roughly 7–13 ticks, or about 21–39 seconds
   at a three-second interval, depending on the fault.
4. Open the case. Show anomaly evidence, all-signal context, signature decision
   or abstention, citations, priority components, cost exposure, and tool trace.
5. Approve or edit as a named planner. Show the created CMMS order and mapping.
6. Open Audit and narrate system detection → agent case → human decision → system
   work order.
7. Open Evaluation. Explain overall accuracy, coverage, selective accuracy, and
   why 7/7 accepted cases in an eight-episode lab suite is not a production claim.

For live mode, turn it on only immediately before a deliberate test, verify the
model name and budget, and turn it off afterward.

## Non-claims

- Not a universal or cross-plant classifier; trained ML covers one hard pair.
- Not validated across plants or 10,000 assets.
- Not a real SAP PM connector yet.
- Not an autonomous maintenance controller.
- Not current live-model accuracy until the paid eval is rerun.
- Not externally certified OOD performance; current learned OOD evidence is
  SKAB-based plus a schema-OOD check on CWRU.
