# LLM cost control and model choice

## Recommendation

Use **DeepSeek V4 Flash through the existing OpenRouter integration** for an
intentional live demo. Keep `openai/gpt-4o-mini` as the fallback if the DeepSeek
tool loop fails a smoke test. Do not choose full GPT-4o merely to save money.

Current OpenRouter catalog prices checked 2026-07-19:

| Model | Input / 1M tokens | Output / 1M tokens | Role here |
|---|---:|---:|---|
| DeepSeek V4 Flash | about $0.09 | about $0.18 | Recommended live default |
| GPT-4o mini | $0.15 | $0.60 | More established fallback |
| Claude Sonnet 4.5 | $3.00 | $15.00 | Previous expensive default |

Sources: [DeepSeek V4 Flash on OpenRouter](https://openrouter.ai/deepseek/deepseek-v4-flash/providers),
[GPT-4o mini on OpenRouter](https://openrouter.ai/openai/gpt-4o-mini/pricing),
[Claude Sonnet 4.5 on OpenRouter](https://openrouter.ai/anthropic/claude-sonnet-4.5/pricing).
Prices change; re-check before budgeting.

The token-price reduction is large, but architecture is the bigger saving. A
cheap model called continuously can still waste money.

## Measured paid run

The fresh real-data workflow on 2026-07-19 used DeepSeek V4 Flash for all eight
SKAB+CWRU cases with no mock fallback:

- 34 provider requests;
- 143,044 input tokens and 18,541 output tokens;
- 161,585 total tokens;
- **$0.014535 exact OpenRouter-returned cost**;
- 32.17 seconds mean case latency.

The earlier 24-case synthetic DeepSeek run predates report-level cost capture,
so its exact spend is not claimed. That missing number is why the evaluator now
writes `paid_usage` into every live report.

## Why the old cap was misleading

The old cap counted completed `TriageCase` rows with `llm_mode=live`. One case
can make four or more paid completion requests:

1. ask to call `get_machine_info`;
2. ask to call `get_recent_telemetry`;
3. ask to call `search_maintenance_history`;
4. return the final JSON;
5. possibly make extra turns up to the eight-step loop limit.

So “40 cases/day” did not mean “40 calls/day.” A case that failed or switched
to mock could also hide paid requests.

## New paid-request lifecycle

```mermaid
sequenceDiagram
  participant Agent
  participant DB as llm_calls
  participant OR as OpenRouter
  Agent->>DB: check request and USD caps
  Agent->>DB: reserve request row before sending
  Agent->>OR: chat completion
  OR-->>Agent: message + token counts + exact cost
  Agent->>DB: mark succeeded; save tokens and cost
  alt cap reached or provider error
    Agent->>DB: mark failure or record budget fallback
    Agent->>Agent: restart deterministic mock tool loop
  end
```

The ledger stores timestamp, model, status, prompt tokens, completion tokens,
total tokens, exact OpenRouter `usage.cost`, and an error summary.
Malformed tool-call arguments are not repaired or guessed. The agent returns a
structured error to the model and permits a retry inside the eight-turn bound.

A secondary in-process counter enforces the same limits across the evaluation
harness's intentionally isolated per-trial databases. Otherwise every fresh
test database would appear to have used zero calls. The persistent ledger is
the production source of truth; the process counter is an additional ceiling
and resets on UTC day or process restart.

## Production controls

- A key alone never enables live mode.
- Render explicitly starts with `LLM_MODE=mock`.
- Random simulator faults are disabled in production.
- Paid mode requires an authenticated, audited UI toggle or explicit env change.
- Actual-provider-request cap: 12 per UTC day.
- Returned-cost cap: $0.25 per UTC day.
- Per-response output ceiling: 700 tokens.
- If a cap is reached mid-case, the system finishes the case with the free
  deterministic policy instead of losing the anomaly.
- The header shows call count and actual dollars used today.
- One physical machine event creates at most one anomaly/case during cooldown,
  even when several bearing signals breach together. This prevents one episode
  from multiplying paid triage calls by the number of changed signals.

The dollar cap is checked before a call using cost already returned by completed
calls. One final call can cross the line slightly because its exact cost is only
known after completion. The request-count and output-token caps bound that final
overshoot.

## How to operate without surprise spend

1. Leave production in mock mode normally.
2. Manually inject one known fault.
3. Turn live on immediately before the expected case.
4. Confirm the header shows the intended cheap model and remaining budget.
5. After the case, switch back to mock.
6. Use the manual GitHub eval workflow only when you intentionally want a paid
   comparison. For real replay, one pass is eight episodes across two testbeds; larger n
   repeats the same physical data. The workflow asks for explicit maximum paid
   calls and maximum returned USD cost for each evaluation process.

### Why production briefly showed 12/12 on 2026-07-19

One manually cued CWRU episode moved four signals and was incorrectly emitted as
four anomalies/cases. The first live cases used several provider turns each and
the request counter reached 12, after which remaining cases correctly fell back
to mock. The ledger showed only **$0.003425** spent, so the request-count guard—not
the $0.25 guard—stopped live calls. Machine-event deduplication now prevents that
signal fan-out, and the header shows live calls already used even while mock mode
is active.

## What “GitHub Actions pings Render every 10 minutes” means

The scheduled workflow sends a small HTTP health request to the Render backend.
It is similar to opening `/api/health` in a browser. The goal is to reduce
free-tier sleep/cold-start delays. It does not inject faults, create cases, run
the LLM, or spend model tokens. It is best effort; Render can still restart or
sleep the service under platform rules.
