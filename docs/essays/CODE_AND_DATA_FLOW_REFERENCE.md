# Code and data-flow reference, in essay form

This is the deep technical companion to the FDE defense master guide. It maps
the running application from user-interface actions through HTTP endpoints,
Python and TypeScript functions, database rows, model and tool decisions, and
rendered components. It is intentionally detailed, and it is not meant to be
presented linearly — listen to the section you need.

On scope: this catalog covers every application function that owns runtime
behaviour, data movement, training, evaluation, or a presentation-visible
interface decision. It deliberately excludes CSS declarations, TypeScript
type-only definitions, constants already described beside whatever consumes
them, third-party framework internals, and test helper functions. None of those
change a business state or explain an architectural decision, and the test files
themselves remain the exact reference whenever a reviewer asks about a specific
assertion.

## The repository and runtime map

The frontend splits three ways. The `frontend/app` directory holds the Next.js
pages and navigation-level interface, running in the browser on Vercel.
`frontend/components` holds the reusable charts, machine cards, and global
chrome, also in the browser. And `frontend/lib/api.ts` is the typed REST client
and session storage, running in the browser.

The backend is larger. `backend/app/main.py` handles FastAPI creation,
startup and shutdown, CORS, and the mounted CMMS, running under Uvicorn on
Render. `backend/app/routes.py` is the triage REST API together with the human
and CMMS workflow. `backend/app/simulator.py` produces synthetic telemetry and
owns the asynchronous triage queue, and `backend/app/replay.py` plays back the
recorded SKAB and CWRU episodes — both live in the Render process.

`backend/app/detector.py` holds the deterministic limits, the robust-z
detection, and the window context, and it runs on a worker thread.
`backend/app/classifier.py` is the auditable physical-signature classifier and
`backend/app/ml_classifier.py` is the Extra Trees, calibration, and
IsolationForest inference; both run on the triage thread. The `backend/app/agent`
package holds the tool schemas, the mock and live model loop, the confidence
calibration, and the CMMS adapter, split between the triage thread and
asynchronous HTTP. `backend/app/priority.py` is the deterministic priority
formula, on the triage thread.

`backend/app/models.py` holds the triage SQLAlchemy models, which map onto SQLite
or Postgres. `backend/app/cmms` is the mock system-of-record application and its
foreign schema, mounted as a separate FastAPI app. `backend/app/eval` is the
trial runner, the independent scorers, and the metrics and report rendering,
running from the command line or GitHub Actions. And `backend/data` holds the
episodes, the trained artifact, the curation and training scripts, and the
provenance records, read at build, evaluation, and runtime.

Finally, `render.yaml` carries the Render build, start, and environment
defaults, and `.github/workflows` carries the keep-warm and evaluation
workflows.

## Startup and shutdown

The lifespan function in `backend/app/main.py` is the entry sequence, and it runs
in a fixed order. It calls `init_db()` to create the Postgres schema and any
currently missing tables. It opens a session. It calls `seed_if_empty()`, which
additively inserts missing machines and historical records — existing
operational data is never overwritten. If the simulator is enabled, it starts
`simulator_loop()` as an asyncio task, and it starts `retention_loop()` as
another. FastAPI then serves the triage router alongside the mounted CMMS
application. On shutdown, the simulator's running flag becomes false and the
background tasks are cancelled.

The CORS middleware currently accepts whatever origins are configured, and the
production configuration uses a wildcard for demonstration convenience. That is
not the final enterprise policy.

## The complete HTTP endpoint reference

All main endpoints sit under `/api`, and the mock CMMS endpoints under
`/cmms/api`. GET endpoints are open for demonstration purposes. The
state-changing main endpoints depend on `current_reviewer`, so they require a
valid bearer token whenever an access password is configured.

Starting with the unauthenticated reads. `GET /api/health` calls `routes.health`,
reads the effective language model mode and the simulator state, writes nothing,
and returns 200 along with the release id. `GET /api/llm` calls
`routes.llm_status`, reads the environment, the runtime override, and the
`llm_calls` ledger, and returns the mode, model, key status, and budget.

`GET /api/machines` calls `routes.list_machines` and reads machines, latest
telemetry, pending cases, and replay and simulator state, returning a batched
three-query fleet snapshot. `GET /api/machines/{id}/telemetry` with an `n`
parameter calls `routes.machine_telemetry`, returning readings oldest to newest,
capped at five hundred. `GET /api/cases` with an optional status filter calls
`routes.list_cases`, returning at most a hundred cases ordered by priority and
id. `GET /api/cases/{id}` calls `routes.get_case` and returns the full evidence
and trace, or a 404.

`GET /api/audit`, with machine and limit parameters, calls `routes.list_audit`
and returns at most five hundred filtered rows. `GET /api/eval-report` calls
`routes.eval_report`, reading the committed JSON files and stripping per-trial
detail to reduce the payload. `GET /api/simulate/faults` calls
`routes.list_faults`, reading machines and source state to return the available
options and the currently active faults.

Now the authenticated and state-changing endpoints. `POST /api/auth/login` calls
`routes.login`, taking a password in the body, checking it against the configured
password, writing a login audit event, and returning a signed token — or a 401.
`POST /api/llm/mode` calls `routes.set_llm_mode`, requires authentication, reads
the budget, and writes a process-local override plus an audit event; Pydantic
permits only live, mock, or auto.

`POST /api/cases/{id}/decision` calls `routes.decide_case`, requires
authentication, reads the case, and writes the final human decision, an audit
event, and possibly a CMMS synchronisation. It returns the decided case, or a 404
if the case does not exist, or a 409 if it was already decided. `POST
/api/cases/{id}/sync-cmms` calls `routes.retry_cmms_sync`, requires
authentication, reads an approved case, and retries a deferred synchronisation;
it returns 409 for an invalid or terminal state and 502 if the CMMS is still
down.

`POST /api/simulate/inject` calls `routes.inject_fault`, requires
authentication, reads machine and replay metadata, and either injects synthetic
state or moves the replay cursor, setting the force flag and writing an audit
event; it returns a cue confirmation, or a 404 or 422. `POST
/api/simulate/clear/{id}` calls `routes.clear_fault`, requires authentication,
clears the machine's synthetic active fault, audits it, and returns 200.

The mock CMMS exposes four endpoints. `GET /cmms/api/health` returns its health.
`POST /cmms/api/workorders` requires an idempotency header, checks for an
existing key, inserts one work order, and returns 201 the first time and 200 on
a repeat. `GET /cmms/api/workorders` returns the latest hundred, and
`GET /cmms/api/workorders/{id}` returns one order or a 404.

There are five Pydantic request models. `Login` takes a password and a reviewer
name of between two and sixty characters. `LlmMode` takes a mode matching the
regular expression for live, mock, or auto. `Decision` takes an action of
approve, reject, or edit, plus a reviewer, a note, and optionally a P1-through-P4
priority and an action list. `Inject` takes a machine id and a fault string,
with the domain code validating availability. And `WorkOrderIn` takes the foreign
CMMS schema, with the priority code constrained to between one and four.

On the frontend side, the `j<T>()` helper attaches the JSON headers and the
stored bearer token, uses a no-store cache policy, raises a browser event on a
401 so that the login modal opens, and throws the API's detail string on any
non-2xx response.

## The full state transition

A reading arrives from a simulator or replayer tick, and normally nothing
happens — reading follows reading. When the detector fires, the reading produces
a new anomaly. When triage completes, that anomaly becomes a pending case.

From pending, a human can take the case in one of three directions: rejected,
approved, or approved-with-edits. Rejection ends the story with no CMMS write at
all. Both approval paths attempt synchronisation, and each can land in one of
three places: synced, when the CMMS accepts; sync-failed, when an outage or
exhausted 5xx retries stop it; or sync-rejected, when the CMMS returns a 4xx
mapping error. A sync-failed case can move to synced later through an
authenticated retry.

Case decisions are final: a second decision is rejected with a 409. And CMMS
synchronisation is deliberately not part of the decision transaction — the human
decision is committed first, and the sync fields record only what happened
downstream.

## Synthetic telemetry, function by function

The configuration lives in four structures. `BASELINES` gives mean and noise
pairs for the four simulated machine types. `SIM_SIGNALS` defines temperature,
vibration velocity, pressure, and RPM. `SIM_LIMITS` defines the fixed limits and
directions per type. And `FAULTS` maps each fault onto its primary metric and
its per-tick drift.

The `FleetSimulator` class itself has seven pieces worth knowing. Its
constructor creates a seeded random number generator and a process-local set of
active faults, and the seed is what makes runs repeatable. `inject_fault`
validates the fault name and stores a record of the fault and a tick count of
zero for one machine, while `clear_fault` removes that machine's active
synthetic fault.

`_reading_for` draws Gaussian healthy values, then applies any active drift, the
cavitation oscillation, and friction heating, caps the fault age at twenty-five
ticks, and rounds the values. `tick` loads the simulated machines, possibly
injects a random fault, inserts each reading, runs detection, and returns the
anomaly ids.

`simulator_loop` is the outer loop: every interval it runs the synthetic and
replay ticks in threads and puts the resulting anomaly ids onto a queue, without
waiting for any language model work. The nested `triage_worker` consumes those
anomaly ids serially, awaits the asynchronous triage, logs the duration or the
failure, and marks the queue task done.

Production sets the random-fault probability to zero. A manual injection calls
`force_detect`, so that an already-open demonstration case does not suppress the
new operator-requested event. Even then, the detector emits only one anomaly for
a multi-signal event.

## Recorded replay, function by function

The `Episode` constructor reads a curated CSV, removes the label and the time
offset from the visible signal dictionary, converts the signals to floats,
retains the label only as evaluation ground truth, and records where the first
labelled row sits.

The `DatasetReplayer` has nine members. Its constructor holds the episode-set
cache and the per-machine, process-local cursor state. `_load_set` loads the
descriptor JSON and its episode CSVs exactly once. `_state_for` initialises a
replay machine at episode zero and row zero with a thirty-row warm-up.

`active_fault` returns the label under the latest cursor, used only for the
interface's fault badge. `available_faults` returns the distinct cueable fault
families, and `available_episodes` returns the exact physical episode name and
fault pairs used by the evaluation harness.

`jump_to_episode` selects an exact recording, positions the cursor forty-five
rows before that recording's first label, and resets the warm-up.
`jump_to_fault` selects the first episode matching a requested fault and
delegates to `jump_to_episode`. And `tick` inserts one row for every replay
machine, advances or rolls the cursor, suppresses detection during the warm-up,
and then calls `run_detection` with the hidden label attached purely for
evaluation storage.

The jump lead is the window size plus fifteen, which is forty-five rows. At the
three-second production interval, that is roughly 135 seconds of pre-fault lead.
The evaluation runner calls exactly the same replay logic, without the real-time
sleeping.

## The detector, every function

`force_detect(machine_id)` takes an id and adds an entry to a process-local set;
it exists so that exactly one fresh, manually requested event can get through
despite the open-case cooldown.

`_severity(value, limit, direction)` turns a fixed-limit margin into low,
medium, or high, giving a transparent engineering-limit severity. `_severity_z(z)`
turns a robust-z magnitude into a severity, for the relative rule where no fixed
limit exists.

`robust_z(series, value)` takes the recent values and returns the value minus the
median, divided by 1.4826 times the median absolute deviation. It exists because
that formulation is robust to an excursion pulling its own baseline along, and it
falls back to standard deviation when the MAD is flat.

`signal_context(keys, history, reading)` turns a complete window into per-signal
statistics, giving both the classifier and the agent auditable cross-signal
facts. `render_context(context, breached_metric)` turns those statistics into
compact prompt text, which exists specifically so nobody has to ask the language
model to calculate trends from raw rows.

`_machine_blocked(db, id)` turns database state into a boolean, implementing the
machine-level ten-minute and open-case deduplication — the mechanism that keeps
one physical event from becoming one case per signal. `_raise_anomaly` turns
evidence into an anomaly id, inserting the anomaly, committing, and writing a
system audit event. And `run_detection(db, machine, reading, label)` turns one
reading into zero or one anomaly ids, running the fixed-limit rule and then the
sustained robust-z rule, with the hidden label stored only for evaluation.

On the rules themselves: the fixed-limit rule fires when the value minus the
limit, multiplied by the direction, is greater than zero. Severity is low up to
five percent beyond the limit, medium above five percent, and high above fifteen
percent.

The relative rule requires that at least half a window exists. It excludes the
three freshest values from the baseline, requires the absolute z-score to exceed
four, and requires the current reading plus two fresh previous readings all to
exceed the threshold — which is what suppresses single-spike alerts. A break
after insertion is what enforces one anomaly, and therefore one case, per reading
event.

The context stored for every signal comprises the mean; the later-minus-earlier
drift; the volatility as a percentage of the mean; the range; the first-quarter
and last-quarter means; the absolute and percentage deltas; the least-squares
slope; the median; the median absolute deviation; the standard deviation of the
derivative; and the sample count.

## The classifier, every function

### The physical-signature layer

In `classifier.py`, `_number` safely converts arbitrary values into finite
floats, and `_clamp` bounds a score. `_strength` produces a linear membership
value between a start threshold and a full-strength threshold. `_features` maps
machine-specific tags onto physical roles and normalises the window statistics.

The trend membership functions `_up`, `_down`, `_steady`, and `_volatile` are
reusable across signatures, and `_material_up` and `_material_down` are the
percentage-delta membership functions. `_describe` produces human-readable
evidence for a role's feature values.

`classify_signature` is the main entry point: it scores seven fault families,
applies the separability thresholds, optionally routes to the narrow machine
learning model, and returns the ranking, the evidence, the layer that answered,
and the out-of-distribution metadata. `signature_agrees` maps root-cause language
onto the predicted family and returns true, false, or unknown.

The clear signatures remain deterministic: bearing wear, overheat, pressure loss,
cavitation, rotor imbalance, suction restriction, and discharge restriction. The
rules publish an answer only when the top score is at least 0.56 and leads the
runner-up by at least 0.07. Otherwise they abstain, or try the narrow
restriction model when the source and schema make it eligible.

### The narrow trained layer

In `ml_classifier.py`, `feature_vector` orders twelve statistics for each of the
exact six SKAB signal keys into seventy-two values, and returns nothing at all on
a schema or data mismatch. `load_bundle` is a cached joblib artifact load,
returning nothing if the artifact is absent. And `classify_restriction` runs the
schema gate, then the IsolationForest score against its threshold, then the
calibrated Extra Trees probability against the confidence threshold, before
returning either suction, discharge, or an abstention, always with evidence.

The artifact is not a universal fault classifier. It is a narrow resolver for the
overlapping restriction pair. CWRU's different sensor roster is rejected before
inference ever runs, which is schema-level out-of-distribution rejection rather
than a fabricated cross-domain class.

### The training and curation functions

On the curation side, `curate_cwru.sha256` verifies the identity of the raw
downloads. `matlab_vector` extracts the drive-end accelerometer vector and the
RPM from the MATLAB files. `frames` converts raw vibration into
tenth-of-a-second RMS, kurtosis, crest factor, and RPM feature rows. And
`curate` creates the checked healthy-plus-fault episode CSVs together with their
descriptor metadata.

On the training side, in `train_fault_classifier`: `load_rows` reads the raw SKAB
CSV values and the label index. `context_at` builds a detector-compatible context
at one window end, and `detection_context` finds the same first detectable
context that production logic would find. `training_windows` builds multiple
labelled windows while preserving the physical experiment group ids.

`candidates` defines the candidate Extra Trees hyperparameters.
`grouped_trigger_oof` evaluates trigger contexts with entire experiments held
out. `window_oof_probabilities` produces the grouped out-of-fold probabilities
used for calibration. `choose_confidence_threshold` targets selective safety on
those out-of-fold predictions, and `ood_threshold_oof` derives the novelty
threshold from held-out in-distribution experiments. Finally, `main` fits the
final model, calibrator, and out-of-distribution bundle, and writes the artifact
and the report.

## The agent and case creation, in exact call order

`routes.triage_anomaly_async` opens a fresh database session inside a thread and
calls `run_triage`. That keeps the synchronous SQLAlchemy and model HTTP work off
the event loop. The simulator's triage worker awaits this, but the telemetry
ticks never await the worker.

Within `triage.py`, `_extract_json` accepts direct JSON, fenced JSON, or the
first embedded object, and returns nothing only when no object parses at all.
`_dispatch_tool` whitelists the three tool names and calls their Python
functions. `run_triage` is the full orchestration, inserting one pending case and
marking the anomaly triaged. And `_summarize` stores compact tool-result text in
the human-readable trace rather than duplicating the full payloads.

`run_triage` performs nineteen steps in order. It loads the anomaly and the
machine. It freezes the effective mock-or-live mode and the configured model for
this case. It parses the deterministic signal context. It calls
`classify_signature` and adds the prediction into the context given to the mock
or live model. It renders the system and user messages, carrying the anomaly, the
asset, the cross-signal facts, and either the concrete classifier verdict or the
abstention. It initialises the trace with the anomaly and signature entries.

It then runs at most eight model turns. Before each paid turn it calls
`reserve_live_call`, and if the reservation is unavailable it resets to mock. On
a provider error it finishes the ledger row as failed, records the fallback,
resets to clean mock messages, and continues — rather than losing the anomaly. It
parses tool arguments strictly, so malformed JSON becomes a structured tool
error and is never guessed at or silently repaired. It dispatches the allowed
read-only tools and appends the results, messages, and trace entries.

It parses the final structured answer, producing a safe low-confidence answer if
the output is unstructured or if the eight-turn loop fails to converge. If a
concrete classifier verdict conflicts with the language model's answer, it
retains the classifier class, removes the unsupported citations, sets safe
actions, records a classification guard event, and defers verification to the
planner.

It counts recurrence and inspects the cited history for safety flags. It computes
the formula priority and clamps the model's proposed adjustment. It estimates
downtime from the worst leading cited precedent, falling back to four hours, and
multiplies that by the machine's illustrative hourly cost. It calibrates
confidence from the precedent, the specificity, and the signature evidence. It
constructs the evidence object and the compact list-level breakdown. And finally
it inserts the triage case in the pending-review state, marks the anomaly
triaged, commits, and writes a case-created audit event.

### The agent tools

There are four functions in `agent/tools.py`, three of which are exposed to the
model. `get_machine_info` reads the machines table and returns identity, type,
location, criticality, and the signal schema. `get_recent_telemetry` reads
telemetry and machines and returns the latest N rows chronologically, plus the
units. `search_maintenance_history` reads same-type maintenance logs, scores them
by term overlap with a plus-two boost for the same machine, and returns the
latest five ordered by score and date.

The fourth, `count_recurrences`, is internal: it joins cases to anomalies and
returns the count of prior cases on the same machine and the same metric, which
feeds the priority formula.

`TOOL_SCHEMAS` is the JSON-schema contract exposed to both the mock and the live
model. No tool controls equipment, decides a case, writes a work order, switches
the mode, or reads the ground-truth fault.

### The language model functions

In `agent/llm.py`, `set_runtime_mode` sets a process-local override, and a
restart returns the system to the safe environment default. `runtime_mode`
returns that override for the interface and the audit trail. `llm_mode` resolves
the override against the environment and the key — and a key alone never
authorises live spending. `llm_model` reads the configurable OpenRouter model,
defaulting to DeepSeek V4 Flash.

`chat` sends one OpenRouter completion turn at temperature 0.2, with the tool
schemas, a sixty-second timeout, and the output cap, and returns the exact usage.
On the mock side, `MockLLM.__init__` stores the anomaly context and the scripted
step state, while `MockLLM.chat` calls machine, then telemetry, then history, in
that order, prefers corrective records, and returns a structured evidence-based
answer. `_tool_call` builds an OpenAI-compatible function-call message so that
mock and live stay at parity.

### Calibration

In `agent/calibration.py`, `Calibration.as_dict` serialises every confidence
factor into the evidence object. `is_non_diagnostic` finds noise, transient, and
inconclusive language. `_precedent_factor` maps the best history score onto a
multiplier: a score of three or more gives 1.0, two gives 0.85, one gives 0.70,
and zero gives 0.50.

`calibrate` clamps the raw confidence, applies the precedent, specificity, and
signature factors, caps the result into the range 0.05 to 0.95, forces a
signature abstention to at most 0.44, and returns the abstain decision along with
its reason.

The specificity factor is 0.40 for a non-diagnostic answer. On the signature
side, a concrete agreeing signature contributes 1.05, a conflict contributes
0.65, and a signature abstention contributes 0.75. Operational abstention occurs
below 0.45, or for non-diagnostic text, or on conflict, or on signature
abstention.

### Priority

In `priority.py`, `compute_priority` returns the score, the components, the base
priority, and a readable statement of the rule. `apply_adjustment` clamps the
agent's proposal to minus one, zero, or plus one, keeps the result within P1
through P4, and refuses to downgrade a formula-derived P1.

## The paid request ledger, every function

`daily_cap` and `daily_usd_cap` read the twelve-request and twenty-five-cent
defaults from the environment. `_midnight` computes the UTC start-of-day
boundary used by the persistent queries. `_reset_process_day_if_needed` resets the
secondary evaluation and process counters when the UTC date changes, and
`reset_process_budget` is the reset hook used by tests and the evaluation
harness. `process_budget_snapshot` reports the process-level calls, cost, and
tokens.

`live_calls_today` and `live_cost_today` query the persistent `llm_calls` rows
since UTC midnight. `budget` combines the caps, the usage, the remaining
amounts, and a reached flag, for the API and the interface. `live_allowed` tests
both the persistent call ceiling and the dollar ceiling.

`reserve_live_call` checks the process and persistent limits, increments the
process count, and inserts a row with status started *before* the provider call
goes out. `finish_live_call` then saves the succeeded or failed status, the exact
tokens, cost, and any error, and updates the process counters.

The production ledger counts provider turns, not cases, and a single case
normally uses several calls. The current reservation scheme is sufficient for one
triage worker; multiple workers would require a database lock or an advisory lock
to prevent a race.

## Authentication, every function

`_password` reads the configured access password. `auth_enabled` is true only
when a password is configured. `_key` derives the HMAC key from that password.
`issue_token` creates a signed token carrying the reviewer and an expiry, and
`verify_token` checks the format, the HMAC, the expiry, and the reviewer.
`current_reviewer` is the FastAPI dependency: it accepts a bearer token, and it
permits demonstration mutations only when authentication is disabled entirely.

With authentication enabled, `decide_case` replaces whatever reviewer name is in
the request body with the reviewer from the signed session. That is what
prevents anyone from signing a decision as another person. It is still
demonstration authentication: production would need identity-provider
single-sign-on, role-based access control, short-lived tokens, revocation, a
CSRF and threat review, and least-privilege roles.

## The CMMS path, every function

In `agent/cmms_adapter.py`, `failure_mode` maps the signal and root-cause family
onto the illustrative CAV, OHE, LOO, VIB, or OTH code. `build_payload` translates
the triage vocabulary into the foreign work-order schema and formats the
narrative. `_make_client` uses the configured network base URL when one is set,
and otherwise preserves genuine HTTP semantics through an ASGI transport. And
`push_work_order` POSTs with the idempotency key, retrying transport errors and
5xx responses three times with exponential backoff, while failing fast on a 4xx.

On the route side, `decide_case` enforces that only a pending case may be
decided, applies any optional human edits, commits and audits the identity, and
invokes the CMMS only for approvals. `_sync_case_to_cmms` loads the case,
machine, anomaly, and evidence, builds the payload, and writes the sync result
and audit event without ever undoing the approval. `retry_cmms_sync` permits
retries on approved retryable cases, returns idempotently when the case is
already synced, and rejects a terminal mapping error.

Inside the mock CMMS service, `_next_order_id` generates SAP-like ids beginning
with 4500 for this single-writer mock. `health` returns a service health
response. `create_work_order` returns the existing order when it sees a known
idempotency key, and otherwise inserts one validated order. `list_work_orders`
returns the latest hundred, `get_work_order` returns one order or a 404, and
`CmmsWorkOrder.as_dict` handles the foreign model serialisation.

The field mapping runs as follows. The case id becomes the external reference in
the form `triage-case-{id}`. The machine id becomes the equipment id directly,
and the location becomes the functional location directly. The internal P1, P2,
P3, and P4 become codes one, two, three, and four, in an inverse-number
vocabulary that also carries text. A constant supplies the notification type,
always M1 for a malfunction report.

The anomaly and root cause together produce the damage code: cavitation gives
CAV, a thermal fault gives OHE, a pressure or flow fault gives LOO, a vibration
fault gives VIB, and anything else gives OTH. The root cause also supplies the
short text, truncated to forty characters, while the explanation, citations,
exposure, and reviewer are formatted into the long text. The reviewer field
records the AI draft plus the named approval. And the case id serves as the HTTP
idempotency key, guaranteeing exactly one order per case.

## Database and model reference

In `db.py`, the URL normalisation logic rejects a Supabase HTTPS API URL and
rewrites the Postgres driver URL. The `engine` is SQLite locally and in tests,
and a Postgres pool in production with pre-ping enabled, a pool size of five, an
overflow of five, and a thirty-minute recycle. `SessionLocal` is a non-expiring
SQLAlchemy session factory. `init_db` creates the `pm_triage` schema and any
missing tables via `create_all`. And `get_db` is the request-scoped session
dependency, with a guaranteed close.

There are eight models. `Machine`, backed by the machines table, holds the
catalog entry, criticality, source, dynamic signal, limit, and dataset JSON, and
the hourly cost; it is consumed by the feed, the tools, the interface, and the
priority formula. `TelemetryReading`, backed by telemetry, holds the machine, a
UTC string timestamp, and dynamic values JSON, consumed by the detector, the
tools, and the charts.

`Anomaly`, backed by anomalies, holds the metric, value, threshold, z-score,
severity, description, status, and context, and drives case creation; it also
carries the hidden evaluation label. `MaintenanceLog`, backed by
maintenance_logs, holds the demonstration legacy work orders with their record
type, symptoms, root cause, action, downtime, and safety flag, and feeds both
retrieval and priority.

`TriageCase`, backed by triage_cases, holds the agent output, evidence, trace,
status, reviewer, and CMMS state — it is the link between the human queue and the
system record. `LlmCall`, backed by llm_calls, holds one provider turn with its
tokens, cost, and any error, and serves as both budget source and evidence.
`AuditEvent`, backed by audit_events, holds the actor, event, entity, and detail
that make up the accountability timeline. And `CmmsWorkOrder`, backed by
cmms_work_orders, holds the foreign CMMS vocabulary and the unique idempotency
key.

A few helpers matter. `utcnow` returns a timezone-aware UTC value. The signals
and limits on a machine, and the values on a telemetry reading, parse their JSON
fields. `TriageCase.as_dict` returns list-safe fields by default, and returns the
evidence and trace as well when asked for the full form. And `audit()` inserts
and commits one attributed business event.

## Retention and seeding

In the seed module, `_skab_machine` builds the PMP-03 catalog row from the
episode descriptor, and `_cwru_machine` builds the BRG-01 catalog row along with
its provenance. `seed_if_empty` additively inserts the missing eight simulated
machines, the replay machines, and the history rows, without overwriting existing
data.

On retention, `prune_telemetry` deletes only telemetry older than the configured
default of twenty-four hours, and `retention_loop` runs that prune in a thread
every nine hundred seconds, logging errors without killing the service.

Cases, anomalies, audit events, work orders, and the language model ledger are
never pruned. A real retention policy would have to account for customer
regulation and for partitioning and archiving volume, rather than keeping every
non-telemetry row forever.

## The frontend, page and function reference

### The shared API and session layer

In `frontend/lib/api.ts`, `API` is the build-time backend base URL. `getSession`
safely parses the reviewer and token out of localStorage, and `setSession` stores
or removes the session and dispatches an auth-changed event. The private `j<T>`
helper performs the authenticated, no-cache JSON fetch, raises the 401 event, and
returns a typed result or throws a typed error.

The exported calls group by purpose. `getHealth`, `getLlm`, `setLlmMode`, and
`login` are the global status and authentication controls. `getMachines` and
`getTelemetry` supply the fleet and machine data. `getCases`, `getCase`,
`decideCase`, and `retryCmmsSync` cover the triage and human workflow.
`getFaults` and `injectFault` are the demonstration scenario controls. And
`getAudit`, `getEvalReport`, and `getWorkOrders` serve the accountability,
evidence, and system-of-record views.

The TypeScript types mirror the dynamic signal schema, the cases, the work
orders, the signature evidence, the evaluation reports, and the budget. These are
compile-time checks only, not runtime validation of server responses; the
backend's Pydantic models remain the runtime authority.

### The global shell and shared components

`RootLayout` makes no API calls and renders the HTML shell, the global CSS, the
chrome, and the page content. `Chrome` polls health and the language model status
every eight seconds and listens for session events, rendering the navigation, the
wake status, the free-versus-live call and cost pill, and the sign-in control.
`toggleLlm` calls `setLlmMode` after a paid-mode confirmation, providing the
authenticated mock-live switch. `LoginModal` and its submit handler call `login`
and `setSession`, rendering the reviewer and password form along with any error
state.

`MachineCard` polls telemetry every four seconds and renders the latest rounded
values, the real-data, fault, and case badges, and the sparklines. `Sparkline`
makes no API calls and renders a small SVG line normalised to the local minimum
and maximum — it is purely visual. `AxisChart`, also API-free, renders a larger
chart with axes, units, and a hover and last-value tooltip.

### The pages

`FleetPage` polls machines and cases every three and a half seconds and loads the
fault list once, rendering the fleet grid, the cold-start retry, and the
injection or cue message. Its nested `inject` function calls `injectFault` and
refreshes, sending the authenticated scenario request and reporting the server's
timing and status.

`MachinePage` polls machines, telemetry, cases, work orders, and audit every five
seconds, and provides the asset-centred join across all the operational records.
`CaseRow` makes no API calls and renders the compact case link on that page.

`CasesInner` polls cases every five seconds, filters client-side by machine,
status, and priority, and renders the queue cards; `CasesPage` is the Suspense
wrapper that makes search parameters safe.

`CasePage` loads one case and refreshes after any state change, rendering the
complete evidence and decision screen. Several API-free components make up that
screen: `TraceBubble` maps trace steps onto detector, tool, warning, and system
bubbles; `FinalBubble` shows the root cause, explanation, actions, and calibrated
confidence or abstention; `DecisionBubble` shows the final human identity, time,
and note along with the work order; `SignalTable` shows the deterministic context
that was given to the classifier and agent; and `SignaturePanel` shows the
prediction, ranking, confidence, out-of-distribution evidence, and agent
agreement. `CmmsPanel` and its retry handler call `retryCmmsSync` and render the
synced, failed, or rejected downstream state with a safe retry. `DecisionBox` and
its decide handler call `decideCase`, rendering the approve, edit, and reject
form and refreshing the case.

`CmmsInner` polls work orders every six seconds and renders the foreign-schema
work orders with a machine filter, wrapped by `CmmsPage` for search-parameter
safety. `AuditInner` polls audit every six seconds and renders local-time
attributed state transitions with a machine filter, helped by `actorClass` and
`localTimestamp` for colour classification and timezone display, and wrapped by
`AuditPage`.

`EvalPage` renders the static reports immediately and then applies a backend
override once, showing dataset tabs, summaries, comparisons, matrices,
calibration, and cost. `hasReports` turns a report object into a boolean,
preventing an empty live response from replacing the bundled evidence.
`reportTimestamp` turns an ISO string into unambiguous UTC text. `Stat`, `Panel`,
and `Explain` are the presentation components. `PlainResult` converts abstract
percentages into integer counts, so the page can say eighteen of twenty-four,
seven of eight, six of six. `Row` compares mock and live values with delta and
good-or-warning styling, using percentage points where the underlying values are
percentages. And `Confusion` renders the nested count map as truth rows and
predicted columns with diagonal and off-diagonal heat cells.

## Evaluation, function by function

In `eval/runner.py`, `TrialResult.as_dict` serialises one trial along with the
derived scorer fields. `_fresh_db` creates an isolated SQLite database and seed
per trial, which is what prevents state leaking between trials.
`eligible_machines` chooses the machine types that support a given synthetic
fault. `_record_classifier` captures the case's signature prediction, layer, and
out-of-distribution evidence into the result.

`run_trial` executes a synthetic case through the actual simulator reading, the
actual detector, and the actual `run_triage`, then applies independent text and
citation scoring. `run_replay_trial` replays an exact recorded episode through the
actual replayer, detector, and triage, and records the label-window timing.
`replay_faults` lists the replay fault labels and `replay_episodes` lists the
physical machine, episode, and fault tuples. `run_replay_suite` runs a
deterministic plan over the physical episodes — and a larger sample size simply
repeats the same evidence. `build_plan` produces a balanced, seeded synthetic
machine and fault plan, and `run_suite` executes that plan with a progress
callback.

In `eval/metrics.py`, `_pct` is a safe rounded percentage. `summarize` builds all
the detection, accuracy, coverage, abstention, per-class, confusion, calibration,
and latency fields. `_calibration` groups cases into confidence buckets and
compares stated against actual accuracy. `_ece` computes the weighted mean
absolute confidence-versus-accuracy gap. And `format_report` produces the plain
console report used in workflow logs and pull requests.

In `eval/taxonomy.py`, which is the independent scorer, `score_text` weights the
known fault markers found in free text. `named_classes` finds distinctively named
families, which is how hedging is exposed. `classify_text` chooses the top class,
resolving ties by earliest marker, and returns a hedging flag;
`_earliest_marker_pos` is that tie-break helper. `classify_citations`
independently maps the first recognised cited work order onto a class.
`mentions_class` implements the hit-anywhere check for the true class. And
`is_abstention` independently detects explicit noise, transient, or unknown
non-answer language.

In the command-line wrapper `eval/__main__.py`, `_run` selects the mock or live
mode, validates the paid key, snapshots the paid usage, runs the synthetic or
replay suite, summarises the results, attaches the per-trial evidence, and
calculates the replay detection timing. Its nested `progress` function prints a
dot for a correct text classification, an x for a scored miss, and an
exclamation mark for a trial error, unless quiet mode is on. And `main` parses
the command-line options, runs mock or live or both, prints the comparison,
optionally merges untouched modes from an existing report, stamps the pipeline
metadata, and writes the JSON.

Running with mode "both" uses the same seeded synthetic plan, which is what makes
the scripted-versus-live comparison fair. Running with data "replay" uses the
recorded episode plan. And the merge-existing option does not blend trials: it
preserves report modes that were not rerun and replaces the selected mode as a
complete unit.

The evaluator uses the production detector, classifier, agent, tools,
calibration, priority, and case persistence. Ground truth is never exposed to
the agent tools, and the text and citation scorers share no decision code with
the agent or the classifier.

## The test-suite map: 105 backend tests

The tests split across eleven files. `test_answer_parsing.py` has nine tests
covering direct, fenced, and prose JSON along with malformed outputs.
`test_auth_and_budget.py` has nine covering signed identity, authentication
enforcement, and the request and cost ledger and caps. `test_calibration.py` has
nine covering the evidence factors, the threshold, conflict, and abstention.
`test_classifier.py` has five covering the physical signatures and ambiguity.

`test_cmms_adapter.py` has five covering field translation, retry, and idempotent
HTTP behaviour, while `test_cmms_flow.py` has six covering the path from human
decision through sync, failure, retry, and rejection. `test_detector.py` has
twelve covering the fixed and relative rules, the context, the cooldown, and the
one-event deduplication.

`test_eval_runner.py` is the largest at twenty, covering plans, replay,
isolation, labels, and report integration. `test_eval_taxonomy.py` has fourteen
covering text and citation classification, hedging, and the scorer regressions.
`test_simulator_loop.py` has a single test, asserting that slow triage cannot
pause the telemetry ticks. And `test_triage_flow.py` has eight covering the
tools, case persistence, the classifier guard, and the live fallback.

The Next.js production build performs the TypeScript checking and the static and
dynamic route compilation. There is not yet a committed browser end-to-end suite,
and that is an honest software-development-lifecycle gap.

## A worked example: a synthetic CNC vibration event

Assume CNC-01 has criticality five, a vibration limit of 5.5 millimetres per
second, a current vibration of 7.2, no recurrence, no safety precedent, and a
specific matching diagnosis available in history.

The simulator's `_reading_for` produces the row and `tick` commits it. Then
`run_detection` checks the fixed limit: 7.2 minus 5.5, times a direction of plus
one, is greater than zero, so the rule fires. The margin is 1.7 over 5.5, which
is 30.9 percent, so `_severity` returns high. `_raise_anomaly` inserts one anomaly
plus an anomaly-detected audit event.

The triage queue then calls the asynchronous triage, which calls `run_triage`.
`classify_signature` sees rising vibration alongside the other roles and returns
either a class or an explicit ambiguity, with evidence either way. The mock or
live agent calls the three read-only tools and cites the matching history.

Priority computes as criticality five, plus high severity worth six, plus
recurrence zero, plus safety zero, totalling eleven — which is base P2.

Suppose the raw confidence is 0.75, the best precedent score is three or higher,
the language is specific, and the signature agrees confidently. Then the
calibration is 0.75 times 1.0 times 1.0 times 1.05, which is 0.7875, displayed as
0.79 — comfortably above the 0.45 abstention threshold.

The case is inserted pending review. No work order exists yet. On human approval,
P2 maps to CMMS code two, "high"; vibration maps to the VIB damage code; and the
case id becomes both the external reference and the idempotency key. The CMMS
returns one order id beginning 4500, and the audit trail records a
work-order-created event.

This example is worth rehearsing because it separates three numbers that
interviewers routinely conflate: the anomaly severity, the calibrated diagnosis
confidence, and the business priority.

## A worked example: a CWRU bearing replay

BRG-01 has four recorded features: drive-end RMS in g, a kurtosis ratio, a
crest-factor ratio, and RPM. Healthy display values such as 0.074 g, 2.78, 3.36,
and 1,796 RPM are rounded only in the interface; the stored and detector values
retain their full precision.

First, `jump_to_fault` selects a CWRU episode and positions the cursor
forty-five healthy frames before its labelled faulty section. Then `tick` commits
one frame every three seconds, and the first thirty refill the detector baseline
after the artificial jump between recordings.

A sustained excursion, or a large relative change, creates one anomaly. During
the production incident that was investigated, an RMS event reached about 0.292 g
against a rolling baseline of roughly 0.072, giving a z-score of about 115.87.

The context contains all four signals. The fixed version of the code stops after
the first event, so kurtosis, crest factor, and RPM remain evidence attached to
that one case rather than becoming three extra cases.

CWRU's schema does not match the narrow six-signal SKAB model, so that model does
not pretend to generalise to it. The physical rules can still identify the coarse
bearing-wear family; failing that, the system abstains. And the ground-truth
inner-race, ball, and outer-race labels remain evaluation-only, mapping onto the
application's coarser bearing-wear taxonomy.

The event demonstrates real recorded signal ingestion and schema-level
out-of-distribution behaviour. It does not prove natural run-to-failure
prediction.

## A file path for every presentation claim

If you claim there is no machine control, point to the tool schemas in
`agent/tools.py` and the system prompt in `triage.py`. If you claim detection is
deterministic, point to `detector.py`. If you claim one event produces one case,
point to `detector._machine_blocked`, the loop break, and the detector tests. If
you claim telemetry continues during a model call, point to
`simulator.simulator_loop`, the triage worker, and the loop test.

If you claim narrow machine learning with out-of-distribution rejection, point to
`ml_classifier.py`, the model artifact and its report, and the machine learning
experiment document. If you claim the language model cannot override the
classifier, point to the classification guard inside `run_triage`. If you claim
confidence can abstain, point to `agent/calibration.py`. If you claim priority is
transparent, point to `priority.py`.

If you claim the human step is mandatory, point to `routes.decide_case` and to
the fact that all new cases are created pending review. If you claim a real CMMS
integration, point to `agent/cmms_adapter.py`, `cmms/service.py`, and the flow
tests. If you claim a cost guard, point to `llm_budget.py`, `agent/llm.py`, and
the authentication and budget tests. If you claim auditability, point to
`audit.py` and the decision, sync, and injection call sites in the routes.

If you claim the evaluation uses the production pipeline, point to
`eval/runner.py`. And if you quote current numbers, point to the committed JSON
reports and the evaluation guide.

When challenged, start from the business invariant, name the owning function,
describe its database effect, and then state the production limitation. That is a
far stronger defense than reciting implementation syntax.
