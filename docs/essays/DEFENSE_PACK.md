# The PM Triage defense pack, current, in essay form

This is the concise revision sheet. For the company-specific presentation, the
rubric mapping, the complete code trace, and the adversarial questions, start
instead with the FDE defense master guide, then use the code and data-flow
reference and the production challenge questions.

## The thirty-second pitch

This system turns machine telemetry into a maintenance recommendation without
letting an AI control equipment. Deterministic rules detect anomalies. An
auditable signature layer classifies only when the signals are actually
separable. The language model retrieves precedent and explains what to do.
Confidence can abstain. And a named planner must approve before an idempotent
adapter creates a work order in the maintenance system. The evaluation reports
accuracy, coverage, calibration, out-of-distribution behaviour, and scorer
coverage, on simulated faults plus eight real episodes drawn from SKAB and CWRU.

## The architecture answer

The path runs in a single line. Telemetry arrives. Deterministic detection fires
on it. Cross-signal statistics are computed. Physics rules, plus a narrow
trained restriction classifier, attempt a class. A learned
out-of-distribution check and a calibrated abstention gate decide whether that
answer is allowed to stand. A tool-calling investigation runs, in either mock or
live mode. Evidence-grounded confidence is computed, with abstention still
possible. A case is created in the pending-review state. A named human makes a
decision. Only on approval does a CMMS work order come into existence. And the
whole sequence lands in an audit trail.

The component boundaries are the entire point. Detection does not depend on the
language model. Classification of numeric signatures does not belong solely to
the language model. Priority is a formula, not generated prose. The language
model does explanation, history synthesis, and action drafting. And a human owns
every operational decision.

## The numbers to quote

Three evaluation reports are currently committed: synthetic mock at
twenty-four trials, real mock at eight, and real DeepSeek at eight.

Detection is 100 percent across all three.

The hybrid classifier's overall top-one accuracy is 75.0 percent on synthetic
mock, and 87.5 percent — seven of eight — on both real runs. Its coverage is
79.2 percent on synthetic mock and 87.5 percent, seven of eight, on both real
runs. Its selective accuracy is 94.7 percent on synthetic mock and 100 percent,
seven for seven, on both real runs.

The full system's raw top-one accuracy is 83.3 percent on synthetic mock and
87.5 percent on both real runs. Its coverage is 79.2 percent on synthetic mock,
87.5 percent on real mock, and 75.0 percent — six of eight — on real DeepSeek.
Its selective accuracy is 89.5 percent on synthetic mock, 100 percent seven for
seven on real mock, and 100 percent six for six on real DeepSeek.

Expected calibration error is 0.207 on synthetic mock, 0.239 on real mock, and
0.148 on real DeepSeek.

Always phrase the real result as "seven out of seven accepted real cases, seven
out of eight overall, with n equals eight". Never say "100 percent real-data
accuracy" — the sample is far too small to support a plant-wide claim.

The real DeepSeek run used thirty-four requests and cost $0.014535, at a mean
latency of 32.17 seconds, with zero errors and zero fallbacks. Do not quote the
older Sonnet results.

## The likely interview questions

**Is the machine learning classifier finished?** Yes, for one narrow job: an
Extra Trees model separates SKAB suction restriction from discharge restriction.
It trains on seventeen physical experiments, calibrates only on grouped
out-of-fold predictions, and passes a frozen test three for three. Rules still
own every other class. It is not a universal classifier.

**Does the language model work better than the classifier?** They should not own
the same job. On numeric classification the hybrid classifier is the owner, and
it is seven of eight overall on the current real suite. The language model's job
is explanation, precedent use, recommended action, and work-order drafting. In
the paid real run it matched seven of eight raw top-one, but covered only six of
eight after calibration, against the classifier's seven of eight coverage. A
guard prevents it from replacing a concrete classifier class.

**Why so much abstention?** Because the model should only answer inside its
supported distribution. The narrow machine learning layer now resolves the
restriction pair, but it rejects same-roster novel faults and unsupported sensor
rosters outright. The remaining real cavitation recording is routed to the
planner rather than forced into a valve class.

**How is confidence calibrated?** It begins with the model's raw confidence,
then deterministically discounts it for weak precedent, non-diagnostic language,
signature conflict, or signature abstention. If the signature layer cannot
separate the classes at all, confidence is capped at 0.44 and the case enters
the uncertainty path.

**Is the human gate selective?** Operational authorisation is mandatory for
every case. The abstention path is a selective uncertainty escalation *inside*
that mandatory review. The system does not auto-approve high-confidence
maintenance orders, because that would weaken the accountability requirement the
challenge sets.

**What tools can the agent call?** Only three, all read-only: the machine
catalog, recent telemetry, and maintenance history search. No tool can control a
machine, and no tool can read the evaluation label.

**What happens if the language model fails or gets expensive?** Production runs
in mock mode by default. Live mode is an authenticated toggle. Random production
faults are off. Every provider request is reserved and logged, under a
twelve-request and twenty-five-cent daily limit plus a seven-hundred-output-token
ceiling. A failure or an exhausted cap continues in deterministic mode and
leaves a trace behind. Malformed tool arguments are rejected without guessing,
and the model gets a bounded retry.

**Why DeepSeek instead of GPT-4o?** DeepSeek V4 Flash is the recommended
cost-first tool-use model through the existing OpenRouter endpoint, with GPT-4o
mini as the fallback if its tool calls fail the smoke test. It cost 1.45 cents
for the eight-case real run. Full GPT-4o is not the cheap option. The
architecture keeps the model name configurable, so the evaluation decides rather
than preference.

**What is the meaningful integration?** The agent reads maintenance history, and
an approved case writes back a CMMS work order through a foreign-schema adapter.
The internal P1-through-P4 scale becomes CMMS priority one through four;
temperature faults become the OHE code, pressure and flow faults become LOO,
vibration becomes VIB, and cavitation becomes CAV; and the case id becomes the
idempotency key, so retries cannot duplicate work orders.

**Is the CMMS a truly separate production system?** It is a separate FastAPI
application with a real HTTP and domain boundary, but for the demonstration it
is mounted in the same deployment and uses the same configured SQL database. The
boundary, the status codes, the schema translation, the retries, and the
idempotency are all real; independent deployment and authentication against SAP
PM or Maximo is future work.

**What does the Render keep-warm workflow do?** It sends a health HTTP request
every ten minutes to reduce cold starts. It does not inject a fault, run triage,
call a language model, or spend tokens.

**What would you build next?** Collect natural customer fault-onset recordings,
especially for discharge restriction and cavitation. Lock an external
site-level validation set. Confirm production data rights. Then monitor
acceptance rate, selective accuracy, drift, and human corrections. Run a capped
DeepSeek-versus-GPT-4o-mini comparison only after the pipeline is published.

## The five-minute demonstration

Start in mock mode, showing the free-mode pill and the zero or limited paid
budget. Open a machine and explain that the sparklines display readings while
Python rules do the detection. Inject a synthetic fault, and expect roughly
seven to thirteen ticks — about twenty-one to thirty-nine seconds at a
three-second interval — depending on which fault it is.

Open the resulting case and show the anomaly evidence, the all-signal context,
the signature decision or abstention, the citations, the priority components,
the cost exposure, and the tool trace. Then approve or edit it as a named
planner, and show the created CMMS order and its field mapping.

Open the Audit view and narrate the four actors in order: system detection,
agent case, human decision, system work order. Finally open the Evaluation page
and explain overall accuracy, coverage, and selective accuracy — and why seven
accepted cases out of seven in an eight-episode laboratory suite is not a
production claim.

If you are demonstrating live mode, turn it on only immediately before a
deliberate test, verify the model name and the remaining budget, and turn it off
again afterwards.

## The non-claims

This is not a universal or cross-plant classifier; the trained machine learning
layer covers exactly one hard pair. It has not been validated across plants or
across ten thousand assets. It is not a real SAP PM connector yet. It is not an
autonomous maintenance controller. It is not proof that DeepSeek generalises
beyond these eight laboratory episodes. And its out-of-distribution performance
is not externally certified — the current learned evidence is SKAB-based, plus a
schema-level out-of-distribution check on CWRU.
