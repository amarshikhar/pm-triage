# Product shipping state

## Identity

- Product: PM Triage
- Repository: https://github.com/amarshikhar/pm-triage
- Released version: unversioned assessment artifact
- Last verified: 2026-07-19
- Release stage: design-partner ready on a published review branch; merge/redeploy pending

## Shared understanding

- Primary buyer: plant maintenance/reliability manager evaluating AI-assisted triage.
- Painful job: turn condition-monitoring anomalies into prioritized, evidenced,
  CMMS-ready maintenance recommendations without removing human accountability.
- Input → processing → output: telemetry → deterministic detection/signature,
  optional LLM investigation, calibration → pending-review case → approved CMMS
  work order and audit trail.
- Paid promise: faster, consistent triage with visible evidence and mandatory
  planner control; accuracy claims must be revalidated on customer labels.
- Non-goals: machine control, autonomous work-order approval, universal fault
  diagnosis, or claims beyond the narrow trained restriction model.
- Product model: assisted design-partner/demo; not yet a commercial self-serve product.
- Customer owns/pays: telemetry/CMMS access, Postgres, hosting, model credits,
  labels, security and retention policy.
- Seller provides: application, adapter boundary, deployment/runbook, tests,
  evaluation harness, and onboarding/support during validation.

## Facts and evidence

- Observed capabilities: full telemetry→case→human→CMMS→audit flow; SKAB and
  CWRU replay; trained restriction classifier; learned OOD gate; persistent
  request/cost cap.
- Tests/demos: 102 backend tests pass; Next.js production build passes; free-mode
  synthetic n=24 and real n=8 plus paid DeepSeek real n=8 reproduced 2026-07-19.
- Demand signals: challenge artifact and interview/demo need; no paid customer
  demand signal recorded.
- Known limitations: real n=8 remains tiny; trained ML covers one fault pair;
  CWRU transitions are constructed and its commercial rights need confirmation;
  mock CMMS shares deployment/database; deployment of the review branch is pending.

## Open alignment questions

1. Is the next release target the assessment demo or a customer design-partner pilot?
2. Which customer site can supply a locked external validation set?

## Decisions

| Date | Decision | Reason/evidence |
|---|---|---|
| 2026-07-19 | Production defaults to free mock even with a key | Credentials are not spending authorization. |
| 2026-07-19 | DeepSeek V4 Flash is live default; GPT-4o mini fallback | Paid real run: 7/8 raw, 6/6 selective at 75% coverage, $0.014535. |
| 2026-07-19 | Count provider requests and exact returned cost | One case makes several completion calls. |
| 2026-07-19 | Signature abstention forces the human uncertainty path | Five-episode replay exposed overconfidence when retrieval found a precedent for overlapping signals. |
| 2026-07-19 | Do not claim universal trained ML | Production ML is complete only for the narrow suction/discharge restriction pair. |
| 2026-07-19 | Reject the tested random-forest classifier | 22 independent training runs / 5 heldout produced 3/5 and a ~0.95-confidence wrong restriction class. |
| 2026-07-19 | Ship a narrow Extra Trees restriction classifier | 17 physical training episodes, grouped OOF tuning, and 3/3 frozen restriction holdout. |
| 2026-07-19 | Require learned novelty and schema-OOD gates | Same-schema non-restriction SKAB: AUROC 1.0, 14/14 rejected; CWRU roster rejected before narrow inference. |
| 2026-07-19 | Add CWRU only as research/eval evidence | Official source has no explicit dataset license; constructed real steady-state transition is not a natural failure evolution. |

## Shipping gates

| Gate | Status | Evidence | Blocking item |
|---|---|---|---|
| Alignment and demand | partial | Product promise/non-goals are documented. | No external paid/design-partner demand recorded. |
| Core outcome and reliability | partial-pass | 102 tests, frontend build, full mock E2E, grouped ML evidence, fixed eval sets, paid DeepSeek replay. | External customer labels. |
| Safety, privacy, cost, and compliance | partial-pass | Mandatory human gate, no control tool, auth, request/USD caps, SKAB license documented. | Customer retention/privacy policy and independent security review. |
| Installation and operations | partial | `.env.example`, Render/Vercel/Supabase paths documented. | Commit/push/redeploy and verify current production state; backup/restore runbook. |
| Onboarding and documentation | pass for assisted demo | Current status, architecture, eval, cost, defense, and economics guides. | Stranger-install usability not independently tested. |
| Proof and demo | partial-pass | Reproducible synthetic n=24, real n=8, and paid DeepSeek n=8; full workflow. | Real n is tiny and not a customer-site validation. |
| Offer and delivery | not ready | Assisted model hypothesized. | No price, terms, support SLA, or delivery agreement. |
| Launch and learning | not ready | Public repo/app exists. | Commercial funnel, feedback loop, success metric, review date. |

## Offer hypothesis

- DIY: not ready.
- Assisted: design-partner pilot with customer-owned data/infrastructure.
- Commercial/custom: integration and validation engagement, not accuracy-guaranteed SaaS.
- Update period: to be agreed.
- Support boundary: application/adapter/eval support; customer owns plant safety
  decisions, labels, CMMS permissions, and infrastructure billing.
- Refund boundary: not defined.

## Risks

| Risk | Likelihood/impact | Mitigation | Owner |
|---|---|---|---|
| Overclaiming 7/7 selective real accuracy | high/high | Always quote 7/8 overall, 7/8 coverage, and n=8. | Product owner |
| Surprise LLM spend | low/medium after fix | Mock default, manual faults, 12-call and $0.25 caps, ledger. | Application owner |
| Unsafe coverage gain in future ML | high/high | Group by asset/episode; untouched test set; reject high-confidence holdout errors. | ML owner |
| CMMS integration differs from SAP/Maximo | high/medium | Keep anti-corruption adapter; validate against customer sandbox. | Integration owner |
| Local fixes assumed deployed | medium/high | Commit/push before workflow/redeploy; verify health/config/UI. | Release owner |

## Next action

- Action: review and merge PR #1, redeploy, then verify the published SHA and
  one manual mock case before any intentional live demo.
- Completion evidence: production health reports mock mode + DeepSeek model;
  UI budget shows provider calls/USD; spontaneous faults do not appear; one
  manual mock case completes; deployed commit SHA is recorded.
- Blocking question: user authorization to merge/redeploy the review branch.

## Work log

| Date | Milestone | Verification | Next action |
|---|---|---|---|
| 2026-07-19 | Cost controls, eval honesty, replay episode coverage, and docs implemented | 94 pytest pass; Next.js build pass; synthetic n=24 and SKAB n=5 mock eval | Train narrow classifier and add OOD/second testbed |
| 2026-07-19 | Narrow ML, learned OOD, and CWRU development replay implemented | 99 pytest pass; Next build; synthetic n=24; real n=8; restriction holdout 3/3 | Publish, then run capped live DeepSeek eval |
| 2026-07-19 | Paid DeepSeek real replay and provider hardening completed | 102 pytest pass; 8/8 live rows; 0 errors; 34 calls; $0.014535; run 29692423022 | Review PR, merge, redeploy, verify |
