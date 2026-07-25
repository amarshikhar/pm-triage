# Language model cost control and model choice, in essay form

## The recommendation

For an intentional live demonstration, use DeepSeek V4 Flash through the
existing OpenRouter integration. Keep GPT-4o mini as the fallback in case the
DeepSeek tool loop fails a smoke test. Do not reach for full GPT-4o merely to
save money — that is not the trade it appears to be.

The OpenRouter catalog prices, checked on the nineteenth of July 2026, run as
follows. DeepSeek V4 Flash, the recommended live default, costs roughly nine
cents per million input tokens and roughly eighteen cents per million output
tokens. GPT-4o mini, the more established fallback, costs fifteen cents per
million input tokens and sixty cents per million output tokens — so a little
under twice the input price and a little over three times the output price of
DeepSeek. Claude Sonnet 4.5, which was the previous expensive default here,
costs three dollars per million input tokens and fifteen dollars per million
output tokens, putting it more than thirty times the input price and more than
eighty times the output price of the recommended model.

Those figures come from the provider and pricing pages for each of the three
models on OpenRouter. Prices change, so re-check them before budgeting anything
against them.

The token-price reduction is large, but architecture is the bigger saving. A
cheap model called continuously can still waste a great deal of money.

## The measured paid run

The fresh real-data workflow on the nineteenth of July 2026 used DeepSeek V4
Flash for all eight SKAB and CWRU cases, with no fallback to mock at any point.
It made thirty-four provider requests. It consumed 143,044 input tokens and
18,541 output tokens, for 161,585 tokens in total. The exact cost returned by
OpenRouter was one point four five cents — $0.014535. Mean case latency was
32.17 seconds.

An earlier twenty-four-case synthetic DeepSeek run predates report-level cost
capture, so its exact spend is not claimed anywhere. That missing number is
precisely why the evaluator now writes a `paid_usage` block into every live
report.

## Why the old spending cap was misleading

The old cap counted completed triage case rows that had been run in live mode.
The problem is that a single case can make four or more paid completion
requests: one asking to call `get_machine_info`, one asking to call
`get_recent_telemetry`, one asking to call `search_maintenance_history`, one
returning the final JSON, and possibly further turns up to the eight-step loop
limit.

So a cap phrased as "forty cases per day" did not mean forty calls per day at
all. Worse, a case that failed outright or switched to mock partway through
could hide paid requests it had already made.

## The paid-request lifecycle now

The sequence is straightforward to describe. Before sending anything, the agent
checks both the request-count cap and the dollar cap against the `llm_calls`
ledger in the database. It then reserves a request row in that ledger before the
request goes out. It sends the chat completion to OpenRouter, and OpenRouter
returns the message along with token counts and an exact cost. The agent marks
the reserved row as succeeded and saves the tokens and the cost against it.

If instead a cap has been reached or the provider errors, the agent marks the
row as a failure or records a budget fallback, and restarts the deterministic
mock tool loop so the case still completes.

The ledger stores, for each call, the timestamp, the model, the status, the
prompt tokens, the completion tokens, the total tokens, the exact cost value
that OpenRouter returned in its usage block, and an error summary where
relevant. Malformed tool-call arguments are never repaired or guessed; the
agent returns a structured error to the model and permits a retry inside the
eight-turn bound.

There is also a secondary in-process counter, which enforces the same limits
across the evaluation harness's intentionally isolated per-trial databases.
Without it, every fresh test database would appear to have used zero calls. The
persistent ledger is the production source of truth; the process counter is an
additional ceiling, and it resets on the UTC day boundary or on process
restart.

## The production controls

A key alone never enables live mode. Render explicitly starts the service in
mock mode. Random simulator faults are disabled in production. Paid mode
requires either an authenticated, audited toggle in the user interface or an
explicit environment change.

The cap on actual provider requests is twelve per UTC day. The cap on returned
cost is twenty-five cents per UTC day. The ceiling on output tokens per response
is seven hundred. If a cap is reached partway through a case, the system
finishes that case with the free deterministic policy rather than losing the
anomaly altogether. The header in the interface shows both the call count and
the actual dollars used today.

One further control matters more than it sounds: a single physical machine
event creates at most one anomaly and one case during its cooldown window, even
when several bearing signals breach together. This prevents one episode from
multiplying paid triage calls by the number of signals that happened to change.

The dollar cap is checked before a call, using the cost already returned by
completed calls. This means one final call can cross the line slightly, because
its exact cost is only known once it has completed. The request-count cap and
the output-token ceiling bound how large that final overshoot can be.

## How to operate without surprise spend

Leave production in mock mode as the normal state. When you want a live
demonstration, manually inject one known fault, turn live mode on immediately
before the expected case, and confirm the header shows the intended cheap model
and the remaining budget. After the case completes, switch back to mock.

Use the manual GitHub evaluation workflow only when you specifically want a paid
comparison. For real replay, one pass is eight episodes across two testbeds;
asking for a larger sample size simply repeats the same physical data. That
workflow asks you for an explicit maximum number of paid calls and an explicit
maximum returned dollar cost for each evaluation process.

### Why production briefly showed twelve out of twelve on the nineteenth of July 2026

One manually cued CWRU episode moved four signals at once, and was incorrectly
emitted as four separate anomalies and four separate cases. The first live cases
each used several provider turns, and the request counter reached twelve, after
which the remaining cases correctly fell back to mock.

The revealing detail is that the ledger showed only $0.003425 spent. It was the
request-count guard, not the twenty-five-cent guard, that stopped the live
calls. Machine-event deduplication now prevents that signal fan-out, and the
header shows live calls already used even while mock mode is active.

## What "GitHub Actions pings Render every ten minutes" actually means

The scheduled workflow sends a small HTTP health request to the Render backend.
It is much like opening the health endpoint in a browser. The goal is to reduce
free-tier sleep and cold-start delays. It does not inject faults, create cases,
run the language model, or spend model tokens. It is best effort only — Render
can still restart or sleep the service under its own platform rules.
