# PM Triage — current decision context

Last verified: 2026-07-19.

## Product promise

Turn abnormal machine telemetry into an evidence-backed maintenance triage case
that a named human can approve, reject, or edit before any work order reaches the
maintenance system of record.

## Locked design decisions

| Area | Decision | Reason |
|---|---|---|
| Detection | Fixed limits plus sustained robust median/MAD excursions | Cheap, deterministic, technician-readable |
| Numeric classification | Physics rules plus a narrow trained Extra Trees layer | Rules own clear classes; grouped ML owns only SKAB suction-vs-discharge overlap |
| OOD | IsolationForest score plus exact feature-roster guard | The narrow model abstains on novel same-schema faults and unsupported testbeds |
| LLM role | Explanation, precedent retrieval, recommended actions, work-order draft | Language/synthesis strengths; never detection, priority formula, or control |
| Default LLM mode | Mock, even if a key exists | A credential is not permission to spend |
| Live model | DeepSeek V4 Flash via OpenRouter; GPT-4o mini fallback | Much lower catalog price than previous Sonnet 4.5 default |
| Spend limits | Actual request ledger, 12 calls/day, $0.25/day, 700 output tokens | One case can make several provider calls |
| Fault generation in production | Manual only (`SPONTANEOUS_FAULT_PROB=0`) | Prevent surprise cases and LLM spend |
| Priority | Deterministic criticality/severity/recurrence/safety formula | Governance is auditable; P1 cannot be downgraded by the agent |
| Human gate | Mandatory for every case | No autonomous maintenance order and no direct machine control |
| CMMS | Separate ASGI service boundary, HTTP adapter, idempotency and retry | Demonstrates a replaceable SAP/Maximo-style integration boundary |
| Database | Supabase Postgres production; SQLite local/test; SQLAlchemy | Durable production data with one domain model |
| Real data | Five SKAB pump episodes plus three CWRU bearing episodes | Two laboratory testbeds; CWRU sequences are constructed from real steady states |

## Non-negotiable claims discipline

- A trained classifier is complete only for the narrow restriction pair; it is
  not a universal fault model.
- Eight real replay episodes do not establish production accuracy.
- Existing committed live Sonnet reports are historical and predate current
  calibration/classifier/evaluation changes.
- Current free-mode evidence is in `docs/CURRENT_STATUS.md`.
- The first four-class model was rejected after a high-confidence holdout error.
  The replacement trains 510 windows grouped into 17 physical episodes, tunes
  only on leave-one-episode-out predictions, and passes the frozen 3/3
  restriction holdout. See `docs/ML_EXPERIMENT.md`.
- Changes in the local working tree are not deployed until committed and pushed.

## Next scientific milestone

Acquire customer-owned natural fault-onset recordings with more discharge and
cavitation episodes, confirm CWRU commercial terms or replace it with a clearly
licensed production corpus, and externally validate thresholds without changing
them. Do not random-split windows from the same episode.

For full details see `docs/ARCHITECTURE_AND_INTERVIEW_GUIDE.md` and
`docs/CURRENT_STATUS.md`.
