# FDE Assessment — Shared Context & Decision Log

> This file is the saved alignment between Shikhar and Claude. Read it first in
> any new session before touching this app.

## The assignment

Forward Deployed Engineer (FDE) assessment: build a **working, demo-able**
software artifact for one industry challenge in ~1 week, then defend the
architecture live. Artifact-first — slideware fails. Rubric weighting:
architecture/workflow 30%, SDLC discipline 25%, systems integration 20%,
domain business architecture 15%, agentic AI 7%, governance/observability 3%.
Hard requirements: at least one meaningful system integration, appropriate AI
use, and **mandatory human accountability** (no fully autonomous actions).

## Decisions (locked with Shikhar, 2026-07-17)

| Decision | Choice | Why |
|---|---|---|
| Challenge | **8.3 Manufacturing — Predictive Maintenance Triage Assistant** | Direct overlap with Shikhar's Baker Hughes plant-analytics work (SAP QM notifications, telemetry, maintenance data) — real domain story for the 15% domain rubric and the live defense. |
| Demo storyline | **Live triage queue** | Telemetry simulator → anomaly detection → AI triage (root cause + priority + evidence) → human approval gate → audit trail. Hits every rubric line. |
| Stack | **Python FastAPI backend + Next.js UI** | Python matches the data-engineering narrative; Next.js gives an enterprise-credible dashboard. |
| LLM | **Claude Sonnet 4.5 via OpenRouter** (`OPENROUTER_API_KEY`, model overridable via `OPENROUTER_MODEL`) | Best tool-calling; OpenRouter is the key Shikhar has. **Deterministic mock-LLM mode** (`LLM_MODE=mock`) so the demo never dies live. |
| Persistence | **SQLite via SQLAlchemy** | Zero-infra, identical local/deployed; "swap to Postgres in prod" is credible because the ORM layer isolates it. |
| Hosting | **Backend on Render** (service `pm-triage-backend` in root `render.yaml`), **frontend on Vercel** through the repo's centralized deploy router | Deployed URL + one-command local runbook as backup. |
| Human gate | Agent **never** closes a case. Every recommendation requires planner approve / reject / edit; every transition audited. | Challenge constraint: no direct machine control; explainability for floor technicians. |
| Loop closure (added 2026-07-18) | On approval, an **anti-corruption adapter** writes the case back to a **separate CMMS service** as a work order (SAP PM notification fields, ISO 14224 damage codes), **idempotent + retried**. Business exposure ($/hr downtime) shown on each case. | Fills the 20% Systems Integration rubric (the thinnest vs weight): a real, bidirectional enterprise integration — read from + write to the system of record with a human in the middle. Ties to Shikhar's SAP PM/QM background for the defense. |

## Constraints from the challenge (must hold in the artifact)

1. **No direct machine control** — the system only recommends; actions go
   through the human approval gate.
2. **Explainability** — every recommendation carries evidence: the exact
   telemetry that tripped detection, the historical work orders it matched,
   and a technician-readable explanation.
3. Root cause **suggestion** + **maintenance priority ranking** (P1–P4) are
   the required outputs.

## Architecture (agreed)

```
telemetry simulator (8 machines, seeded RNG, injected fault patterns)
        │ readings every tick
        ▼
rule-based anomaly detector (thresholds + rolling z-score — deliberately
        │ explainable, NOT an LLM)          anomalies
        ▼
AI Triage Agent (LLM tool-loop via OpenRouter, or deterministic mock)
  tools: machine info · recent telemetry · historical maintenance log search
        │ TriageCase: root cause, confidence, P1–P4 priority + scoring
        │ rationale, actions, evidence citations, full reasoning trace
        ▼
Human approval gate (planner approves / rejects / edits in the dashboard)
        ▼
Audit trail (every event: detection, agent run, tool calls, human decision)
```

- Integration points (rubric): simulated IoT feed, "legacy" maintenance-history
  store queried by the agent as a tool, REST API consumed by a separate UI.
- Priority ranking is a **transparent scoring function** (safety flag,
  machine criticality, anomaly severity, failure-recurrence) — the LLM
  explains and can adjust one notch with justification, never silently.

## Where things live

- `backend/` — FastAPI app (`app/`), seed data, tests (`pytest`), Dockerfile.
- `frontend/` — Next.js dashboard (fleet view, triage queue, case detail with
  trace + approval actions, audit log). `NEXT_PUBLIC_API_URL` points at the
  backend.
- Root `render.yaml` — Render service for the backend.
- `.github/vercel-projects.json` — frontend registered per repo rules
  (`git.deploymentEnabled=false` in `frontend/vercel.json`).

## Status / next steps

- [x] Decisions locked, scaffold + backend + frontend built (this session)
- [ ] Shikhar: create Render service (root `render.yaml` blueprint) and set
      `OPENROUTER_API_KEY`; create the Vercel project for `frontend/` and put
      its `projectId` in the registry.
- [ ] Dry-run the live demo script in `README.md` before the defense.

---

## Update v2 — 2026-07-18 (post-overhaul; the section above is the original log, kept verbatim)

**Canonical home moved:** github.com/amarshikhar/pm-triage (public). The copy
in Antigravity_Skills `01-revenue/pm-triage` is frozen history — do not
develop there. Backend auto-deploys from pm-triage `main` via Render
(Blueprint, service `pm-triage-backend`); frontend auto-deploys from the same
repo via Vercel (Root Directory `frontend`, domain pm-triage.vercel.app).

**What changed since the original log (all decided with Shikhar):**

| Area | Decision |
|---|---|
| Real data | `PMP-03` replays curated real SKAB pump-testbed episodes (GPL-3.0, committed in `backend/data/episodes/`); dataset labels = eval ground truth; demo lever cues the real recording. Simulated fleet kept alongside for breadth + on-demand demos; UI badges distinguish. |
| Telemetry schema | Signal-generic: `Machine.signals_json` roster + `TelemetryReading.values_json`; per-machine limits. |
| Detection | Second deterministic rule: robust z-score (median/MAD, \|z\|>4 sustained 3 readings) vs the machine's own baseline — real operating-point variance made fixed thresholds insufficient. |
| Persistence | Supabase Postgres via `DATABASE_URL` (Session-pooler DSN; NOT the https:// API URL), own `pm_triage` schema, telemetry retention pruning. SQLite stays for local/tests. |
| Auth | `APP_ACCESS_PASSWORD` crew gate on mutating routes; HMAC session tokens carry the reviewer name, which signs decisions. Reads stay open. |
| LLM control | Mock by default; header toggle (audited) to live; `LLM_DAILY_CALL_CAP` counted from DB; live-call failure falls back to mock mid-case, noted in trace. |
| CMMS corpus | 19 corrective + 12 routine records (`record_type` field, SAP-order-type analogue); retrieval must discriminate. Economics cited in `docs/ECONOMICS.md` (Siemens/Senseye TCOD). |
| Eval | `--data replay` scores against real SKAB labels. Current mock floor: 100% detection both modes, 50% top-1. Live re-run pending on the new pipeline (old live: 77.5%, +20pp, ECE 0.046). |
| UI | Routes: `/` fleet, `/machines/[id]` full-size charts, `/cases`, `/cases/[id]` (investigation as conversation), `/cmms`, `/audit`. Dark control-room theme, validated palette, mobile. |
| Always-on | Keep-warm workflow pings the API every 10 min; Postgres persistence means redeploys keep cases. |

**Known caveats to volunteer, not hide:** keep-warm is best-effort; live-LLM
numbers not yet re-measured on the harder pipeline; SKAB cavitation episode
can fire slightly before the labelled window (reported as out-of-window, not
hidden); `/machines` endpoint batched to 3 queries for remote-Postgres latency.
