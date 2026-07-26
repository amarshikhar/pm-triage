# Presentation script — what to say, sentence by sentence

A spoken script for the live presentation: the five-slide deck
([`PRESENTATION.html`](PRESENTATION.html)), the click-through architecture
([`diagrams/architecture-interactive.html`](diagrams/architecture-interactive.html)),
and the app demo.

Every line in a `>` block is meant to be **said out loud as written**. They are
short on purpose: short sentences survive nerves, long ones do not. Everything
outside a `>` block is a stage direction — do not read it.

Numbers here match [`CURRENT_STATUS.md`](CURRENT_STATUS.md) and the committed
eval reports. If a number is not in this script, do not invent it on stage —
say "I'd have to check the report" and move on.

---

## Running order (12 minutes + questions)

| Time | What | Where |
|---|---|---|
| 0:00–0:45 | Slide 1 — what it is, and what is real | Deck |
| 0:45–2:00 | Slide 2 — the flow, and who decides what | Deck |
| 2:00–3:00 | Architecture, clicked through | Interactive page, fullscreen |
| 3:00–9:30 | The app, live | Browser |
| 9:30–10:30 | Slide 4 — measured results | Deck |
| 10:30–12:00 | Slide 5 — how this is judged, and limits | Deck |

Slide 3 (*what runs where*) is your **reserve slide**. Use it if the demo fails,
or if an engineer asks where something lives. Otherwise skip it — the
interactive page covers the same ground better.

**Ten minutes before you start:** open `/api/health`, confirm `ok=true` and
`simulator_running=true`, load the frontend until machine cards populate,
confirm the header says `MOCK · free`, sign in with your own name, and note one
existing pending case as a backup. Do not clear history.

---

## Slide 1 — "Telemetry goes in. A person signs the work order."

The spine of this slide: **four owners, and a human at the end.**

> Predictive maintenance fails in practice for a boring reason. Not because
> nobody notices the vibration — because nobody turns the vibration into a
> decision somebody is willing to sign.
>
> This system does that. Telemetry goes in. An evidence-backed maintenance case
> comes out. A named planner signs it before anything reaches the maintenance
> system of record.
>
> There are four owners on this slide, and none of them can quietly take
> another's job.
>
> Deterministic code decides whether a reading is abnormal, and how urgent it
> is. A trained model has exactly one job: suction versus discharge restriction
> on one pump. A language model retrieves precedent, explains the evidence, and
> drafts the work order. A named human decides whether any work actually
> happens — every case, every time.
>
> No AI step can move a machine, set a priority, or authorize work. That
> boundary is structural, not a policy note.

Now point at the right-hand column, then at the two tables:

> It is deployed and tested: a hundred and five backend tests, a production
> frontend build, running on Vercel, Render and Supabase. A run costs zero
> dollars by default, because mock mode stays on even when an API key exists.
>
> And before anyone asks me — here is what is not real. The CMMS is a mock
> service behind a real HTTP boundary. The fleet telemetry is simulated. The
> maintenance history is seeded. The real recordings are two laboratory
> testbeds, replayed.

**Beat. Then move on.** Volunteering the "not real" column early is the single
highest-value thing you do all presentation. It buys you credibility for
everything after it.

*If asked "so what is actually real?"*
> The code, the workflow, the database, the integration contract, and the
> laboratory recordings. Everything else is honestly labelled on this slide.

---

## Slide 2 — "One abnormal reading, left to right"

The spine: **everything left of the dashed line is a proposal.**

Trace the diagram with your finger while you say this:

> One abnormal reading, left to right.
>
> Telemetry arrives. Deterministic code detects: a fixed engineering limit, or
> a robust median-and-MAD excursion that has to persist before it raises
> anything. The same reading always gives the same result, and a technician can
> read the rule that fired.
>
> Physics rules classify. They own every clear fault. When the evidence is weak
> or two signatures are tied, they abstain instead of guessing — and only then
> does the trained model get a turn, on the one pair it was built for.
>
> The language model explains. It writes the case: the evidence, the cited past
> work orders, the recommended actions, a drafted work order. It never sets the
> fault class, the priority, or whether a work order exists.
>
> Then this line. Everything left of it is a proposal. A named planner
> approves, edits or rejects. Only an approval reaches the CMMS, over HTTP,
> with an idempotency key, so a retry returns the same work order instead of
> creating a second one.

Point at the "why the boundaries sit there" column:

> Three reasons the lines sit where they do.
>
> Detection is deterministic because it has to be cheap, continuous, and
> readable by a technician.
>
> The trained model is deliberately narrow. A novelty score and an exact
> sensor-roster check make it abstain outside its job, rather than answer
> confidently about a machine it has never seen.
>
> And the language model never decides. So a fluent wrong answer costs an
> explanation — not a maintenance action.

If you have the time, add the priority line. It lands well:

> Priority is arithmetic, not prose. Criticality, plus twice severity, plus
> recurrence capped at three, plus four if it is safety-related. P1 if it is
> safety-related or scores thirteen. The agent may move it one notch with a
> written reason, and can never downgrade a P1.

*If asked "why not just let the LLM classify?"*
> Because a language model's confidence tracks fluency, not correctness. On the
> real recordings it was confidently wrong. Numbers are classified from
> features; language work goes to the language model.

---

## Architecture, clicked through (2:00–3:00)

Open `architecture-interactive.html`. Press **F** for fullscreen. The mode
toggle, the legend and the four flow tabs stay visible at the top of the
screen, so you can switch scenario mid-sentence. Press **Space** to autoplay a
flow, **→** to step manually, **Esc** to come back out.

Say the frame first:

> This is the same architecture, but you can step through it. Four scenarios.
> Every box is a real file or a real service, and the arrows are the only paths
> between them.

**Tab 1 — Fault triage.** Step it. One sentence per step is enough:

> A reading arrives, every three seconds. A sustained excursion raises one
> anomaly — one physical event, one case, not one alert per signal. The rules
> score the signatures, and here they abstain: the top two are three
> hundredths apart, which a short window cannot separate. That, and only that,
> is when the trained model answers. The agent writes the case. Confidence is
> calibrated against precedent, not self-reported. And the case lands in a
> queue as a proposal — nothing has happened to the machine.

**Tab 2 — Human decision.** This is the one that matters:

> One transition, one endpoint, one named person. Approval is committed first,
> then translated into the CMMS vocabulary and posted with an idempotency key.
> A rejected case produces nothing downstream. And synced, failed and rejected
> are three different states, each with its own audit event — because "we could
> not reach the CMMS" and "the CMMS refused this payload" need different
> answers.

**Tab 3 — Low confidence.** The credibility flow:

> This is the system declining to answer. The trained layer abstains on novelty
> or an unsupported sensor roster. Calibration takes a raw confidence of
> zero point eight eight down to zero point four four, because the precedent
> and the signature did not back it up. Below zero point four five the case is
> stored flagged as uncertain — and it still reaches a planner, with the same
> evidence attached. On the real replay set this is the cavitation recording.
> Abstention routes to a human. It never drops a case, and it never creates
> work.

**Tab 4 — Live model and caps.** (The page switches to live mode by itself.)

> A credential is not permission to spend. Mock is the deployed default even
> with an API key in the environment. Live is opt-in, behind the authenticated
> toggle. The budget is checked before the request leaves: twelve calls a day,
> twenty-five cents a day, seven hundred output tokens. Every request is costed
> into a table from the provider's returned number, not a price list. Over cap,
> or on a provider failure, the case finishes free and deterministic — and says
> so in its own trace.

---

## The app, live (3:00–9:30)

Follow the seven-minute path in
[`FDE_DEFENSE_MASTER_GUIDE.md`](FDE_DEFENSE_MASTER_GUIDE.md). The five lines
you must not improvise:

**Fleet:**
> The problem is not spotting a high sensor value. It is turning it into an
> explainable, prioritized decision connected to the system of record, without
> autonomous machine control.

**Injecting the fault:**
> This button is a demo lever. Random fault injection is disabled in
> production. A real plant feeds the same ingestion boundary from a historian
> or an IoT gateway.

**The case, detection card:**
> Detection is not a prompt. A limit or a sustained robust-z excursion creates
> one anomaly, and the anomaly stores statistics for every signal — not just
> the breached one — because the cross-signal shape is what separates bearing
> wear from cavitation.

**Approving:**
> The session identity signs this decision, not a field in the request. Approval
> is committed before the CMMS call, so an outage cannot erase the human
> decision.

**Audit:**
> System detected. Agent triaged. A named human decided. System synced. Every
> row has an actor and a timestamp, and it is append-only.

If the backend is asleep, say so plainly and open the Evaluation page — it uses
bundled static reports:
> That is a cold start on a free instance. While it wakes, let me show you the
> evaluation, which is served from committed reports.

---

## Slide 4 — "Every number in counts"

The spine: **n is eight. Say it before they ask.**

> Four numbers, and they are not interchangeable.
>
> Detection rate: did it notice at all. Overall top-one: was it right, over
> everything, where an abstention counts as not correct. Coverage: how often it
> was willing to answer. Selective accuracy: was it right when it did answer.
>
> The honest headline is this. On eight recorded episodes — five SKAB pump,
> three CWRU bearing — detection fired on eight out of eight. The classifier
> named seven of the eight and was right on all seven it accepted. The paid
> live run was seven out of eight raw, accepted six after its own confidence
> gate, and was right on those six.
>
> The one real abstention is the cavitation recording. It was routed to a
> planner rather than forced into a valve class. That is the gate working, not
> a miss.
>
> The whole paid run cost one and a half cents. Thirty-four provider requests,
> eight cases, zero errors, and that cost is the number the provider returned,
> not an estimate.
>
> And I will say the important part myself: n is eight. This is development
> evidence, not customer-site validation.

*If asked about calibration error:*
> ECE of zero point one four eight means the confidence is off from the
> accuracy by about fifteen points on average. It does not mean eighty-five
> percent accurate.

*Never say* "a hundred percent accuracy on real data." Say seven out of eight
overall, and seven out of seven among accepted classifier answers.

---

## Slide 5 — "How this is judged"

The spine: **the division of labour is the design, not a shortcut.**

> Six categories. The heaviest is architecture and workflow design, at thirty
> percent — which is why I spent most of this talk on who owns which decision
> rather than on the model.
>
> Engineering: typed contracts on both sides, a hundred and five backend tests,
> a production build, a live deployment, and data retention. Integration: an
> HTTP anti-corruption adapter with schema translation, retries and
> idempotency. Domain: criticality, engineering limits, precedent, a published
> priority formula, and a human planner. Agentic AI is seven percent, and it is
> last for a reason — the language model owns no detection, no authorization,
> and cannot overrule a classifier verdict.

Then the limitations, before anyone reaches for them:

> The limits I would raise myself. Eight laboratory episodes are development
> evidence. The trained layer solves one pair — everything else is a rule or an
> abstention. The CWRU episodes are constructed transitions, not natural
> run-to-failure. The replay cursor and the triage queue live in one process,
> so multiple replicas would need a durable broker. Schema setup uses
> create-all, not migrations. And the frontend polls; it does not consume an
> event stream.

Close on this. Slow down, and stop talking afterwards:

> Rules detect. Rules plus narrow ML classify. The gate can abstain. The
> language model explains and retrieves. A named human authorizes. An
> idempotent adapter integrates the approved decision.
>
> That division is the production design — not a limitation of the prototype.
>
> What I would do next is get customer-owned recordings of natural fault onset,
> especially discharge and cavitation, and an external validation set that
> tests these thresholds without changing them.

---

## Practice notes

- **Rehearse slides 1, 4 and 5 out loud twice.** They carry the claims. Slides
  2 and 3 you can talk through from the picture.
- **Three deliberate pauses**: after "structural, not a policy note"; after "n
  is eight"; after "not a limitation of the prototype."
- **Speak the numbers as words** — "zero point four five", "seven out of
  eight". Reading digits aloud is where scripts fall apart.
- If you lose your place, the recovery sentence is always the same:
  > The rule is that nothing acts without a named human. Let me show you where
  > that is enforced.

## Questions you will get

| Question | The line |
|---|---|
| Does this scale to ten thousand assets? | Detection is O(one) per reading and already runs on every reading. The queue and the replay cursor are the single-process parts, and they would move to a durable broker. |
| Why DeepSeek? | Cost. The role is explanation and retrieval, and the tool protocol is identical in mock mode, so the provider is replaceable. |
| What if the LLM hallucinates a work order? | It drafts; it does not create. A work order exists only after a named human approval, in one endpoint. |
| Is the OOD gate validated? | On SKAB, plus a schema check on CWRU. It is not externally certified, and I would not claim that. |
| Why not SAP directly? | The adapter is the point — one HTTP boundary with schema translation and idempotency. Point the base URL at SAP or Maximo and nothing upstream changes. |
| How do you know the human gate holds? | There is exactly one state transition out of pending review, it needs a bearer token, and with auth on the reviewer name comes from the session token rather than the request body. |

---

## Architecture accuracy check — 2026-07-26

The interactive diagram was re-read against the source before this
presentation. Verified correct against code: the detector's `Z_LIMIT = 4.0`,
`Z_SUSTAIN = 3` and ten-minute cooldown; the signature layer's `SCORE_FLOOR =
0.56` and `SEPARATION_MARGIN = 0.07`; `ABSTAIN_THRESHOLD = 0.45` and the
`0.45 - 0.01 = 0.44` cap; the priority formula and the P1 downgrade clamp; the
caps of 12 calls a day, $0.25 a day and 700 output tokens; the default model
`deepseek/deepseek-v4-flash` with `LLM_MODE=mock` as the default; the
`Idempotency-Key: triage-case-{id}` contract and the CMMS payload fields; the
three-second simulator tick; 24-hour telemetry retention; eight simulated
assets plus `PMP-03` and `BRG-01`; and the `human:<name>` audit actor format.

Four payload examples in the triage flow did not match the real schema and were
corrected: the reading now uses the actual SKAB signal roster
(`flow_lpm`, `pressure_bar`, `vibration_g`, `current_a`, `temp_motor_c`,
`temp_fluid_c`) on machine `PMP-03` instead of invented field names; the
anomaly's threshold is the baseline median, because that asset has no fixed
limit; the signature step now shows a genuine floor-and-margin abstention
rather than a resolved `bearing_wear` verdict that would never have reached the
trained model; and the trained-model step uses the keys `classify_restriction`
actually returns.

One nuance worth knowing on stage: the trained model is reached only when the
signature layer abstains **and** the machine is a replay-source asset. It is a
routing guard, not an answer proxy — the model still decides entirely from
observed features.
