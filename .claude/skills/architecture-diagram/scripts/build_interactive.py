"""Fill the architecture-diagram skill template with the PM Triage content."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SRC = Path(__file__).resolve().parents[1] / "assets" / "template.html"
DST = ROOT / "docs" / "diagrams" / "architecture-interactive.html"

t = SRC.read_text()

# ── modes: offline/online → mock/live (keys are generic in the JS) ────────────
for a, b in [("offline", "mock"), ("online", "live"), ("Offline", "Mock"), ("Online", "Live")]:
    t = t.replace(a, b)

# ── header ───────────────────────────────────────────────────────────────────
t = t.replace("{{SYSTEM_NAME}} · Architecture", "PM Triage · Architecture")
t = t.replace("{{PROJECT_LABEL}}", "PM Triage")
t = t.replace("{{SYSTEM_NAME}} <span", "Predictive maintenance triage <span")
t = t.replace("{{TAGLINE}}", "telemetry → work order")
t = t.replace("{{SUBTITLE}}",
              "How one abnormal sensor reading becomes an approved maintenance work order. "
              "Everything before the planner is a proposal; nothing after it happens without a person.")
t = t.replace('{{MODE_A_LABEL}} <span class="pill">{{MODE_A_HINT}}</span>',
              'Mock <span class="pill">free · the deployed default</span>')
t = t.replace('{{MODE_B_LABEL}} <span class="pill">{{MODE_B_HINT}}</span>',
              'Live <span class="pill">OpenRouter · capped</span>')

t = t.replace("    width: 150px;", "    width: 132px;", 1)

lines = t.split("\n")


def find(pred, start=0):
    for i in range(start, len(lines)):
        if pred(lines[i]):
            return i
    raise SystemExit("marker not found")


# ── legend ───────────────────────────────────────────────────────────────────
LEGEND = [
    ("user", "Human authority"),
    ("orch", "Deterministic code"),
    ("compute", "Trained model"),
    ("embed", "Language model"),
    ("vector", "Data &amp; system of record"),
    ("seed", "Telemetry source"),
]
ls = find(lambda l: 'class="swatch" style="background:var(--c-user)' in l)
le = find(lambda l: 'class="swatch" style="background:var(--c-seed)' in l)
lines[ls:le + 1] = [
    f'    <span class="item"><span class="swatch" style="background:var(--c-{r})"></span> {n}</span>'
    for r, n in LEGEND
]

# ── flow tabs ────────────────────────────────────────────────────────────────
TABS = [
    ("triage", "Fault triage"),
    ("decision", "Human decision"),
    ("abstain", "Low confidence"),
    ("spend", "Live model &amp; caps"),
]
fs = find(lambda l: 'data-flow="flow_a"' in l)
fe = find(lambda l: 'data-flow="flow_c"' in l)
lines[fs:fe + 1] = [
    f'  <button class="flowtab" data-flow="{k}" aria-pressed="{"true" if i == 0 else "false"}">'
    f'<span class="num">{i + 1}</span> {n}</button>'
    for i, (k, n) in enumerate(TABS)
]
t = "\n".join(lines)
t = t.replace('<kbd id="kbFlowMax">3</kbd>', '<kbd id="kbFlowMax">4</kbd>')
lines = t.split("\n")

# ── nodes ────────────────────────────────────────────────────────────────────
ICONS = {
    "screen": '<rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>',
    "gauge": '<path d="M12 21a9 9 0 1 1 9-9"/><path d="M12 12l5-3"/><circle cx="12" cy="12" r="1.5"/>',
    "rules": '<path d="M4 5h16"/><path d="M4 12h10"/><path d="M4 19h7"/><circle cx="18" cy="12" r="2"/>',
    "brain": '<path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44A2.5 2.5 0 0 1 4 18a2.5 2.5 0 0 1-1.55-4.45A2.5 2.5 0 0 1 4 9a2.5 2.5 0 0 1 1.55-4.45A2.5 2.5 0 0 1 9.5 2z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44A2.5 2.5 0 0 0 20 18a2.5 2.5 0 0 0 1.55-4.45A2.5 2.5 0 0 0 20 9a2.5 2.5 0 0 0-1.55-4.45A2.5 2.5 0 0 0 14.5 2z"/>',
    "chat": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "cloud": '<path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/>',
    "scale": '<path d="M12 3v18"/><path d="M5 7h14"/><path d="M5 7l-3 6h6z"/><path d="M19 7l3 6h-6z"/>',
    "user": '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "clipboard": '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M9 14l2 2 4-4"/>',
    "db": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/>',
}

NODES = [
    # id, role, left, top, icon, label, tech, port, modes
    ("machines", "seed", 0, 40, "gauge", "Machines", "simulator.py",
     "8 sim · SKAB · CWRU", None),
    ("detector", "orch", 18, 40, "screen", "Detector", "detector.py",
     "limits + median/MAD", None),
    ("rules", "orch", 30, 6, "rules", "Physics rules", "classifier.py",
     "the clear faults", None),
    ("model", "compute", 30, 68, "brain", "Trained model", "ml_classifier.py",
     "Extra Trees + OOD", None),
    ("agent", "embed", 46, 40, "chat", "Triage agent", ("agent/triage.py", "agent/triage.py"),
     ("mock · free", "live · capped"), None),
    ("provider", "embed", 64, 6, "cloud", "OpenRouter", "deepseek-v4-flash",
     "12 calls · $0.25", "live"),
    ("calib", "orch", 64, 40, "scale", "Calibration", "calibration.py",
     "abstains < 0.45", None),
    ("db", "vector", 64, 68, "db", "Postgres", "Supabase",
     "cases · audit", None),
    ("cmms", "vector", 82, 6, "clipboard", "CMMS", "cmms/service.py",
     "idempotent", None),
    ("planner", "user", 82, 40, "user", "Planner", "Next.js · Vercel",
     "approve · edit · reject", None),
]


def node_html(nid, role, left, top, icon, label, tech, port, modes):
    m = f' data-modes="{modes}"' if modes else ""
    if isinstance(tech, tuple):
        techline = (f'<div class="tech" data-tech-mock="{tech[0]}" data-tech-live="{tech[1]}">'
                    f'{tech[0]}</div>')
    else:
        techline = f'<div class="tech">{tech}</div>'
    if isinstance(port, tuple):
        portline = (f'<div class="port" data-port-mock="{port[0]}" data-port-live="{port[1]}">'
                    f'{port[0]}</div>')
    else:
        portline = f'<div class="port">{port}</div>'
    return (
        f'      <div class="node" data-role="{role}" data-id="{nid}"{m} '
        f'style="left: {left}%; top: {top}%;">\n'
        f'        <div class="icon"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="2">{ICONS[icon]}</svg></div>\n'
        f'        <div class="label">{label}</div>\n'
        f'        {techline}\n'
        f'        {portline}\n'
        f'        <span class="step-badge">·</span>\n'
        f'      </div>'
    )


ns = find(lambda l: "<!-- User / client / browser -->" in l)
ne = find(lambda l: "TO ADD MORE NODES:" in l)
while "<!--" not in lines[ne]:
    ne -= 1
lines[ns:ne] = [node_html(*n) for n in NODES] + [""]

# ── flows ────────────────────────────────────────────────────────────────────
FLOWS = r'''const flows = {

  /* ───── 1. Fault triage: telemetry becomes a proposal, never an action ───── */
  triage: {
    name: "Fault triage (telemetry → a case a human can read)",
    note: "Nothing in this flow creates work. It creates a proposal.",
    steps: [
      {
        from:"machines", to:"detector", color:"--c-seed",
        title:"A reading arrives",
        route:"simulator.py / replay.py",
        desc:"Eight simulated assets, plus real SKAB pump and CWRU bearing recordings replayed row by row. <em>Detection runs on every reading.</em>",
        payload:
`TelemetryReading
{
    "machine_id": "pump-03",
    "ts": "2026-07-19T09:14:02Z",
    "vibration_mm_s": 7.9,
    "suction_pressure_bar": 0.41,
    "discharge_pressure_bar": 5.8,
    "temp_c": 61.2
}`,
        chips:["every 3 s","8 assets"]
      },
      {
        from:"detector", to:"rules", color:"--c-orch",
        title:"A sustained excursion raises an anomaly",
        route:"anomalies",
        desc:"Fixed engineering limits and a robust median/MAD excursion that must persist before it raises a case. The same reading always produces the same result, and a technician can read the rule that fired.",
        payload:
`Anomaly
{
    "metric": "vibration_mm_s",
    "value": 7.9,
    "threshold": 6.0,
    "zscore": 5.4,          // robust: median / MAD
    "severity": "high",
    "context": { ... }      // what every OTHER signal was doing
}`,
        chips:["z ≥ 4.0","3 readings","10 min cooldown"]
      },
      {
        from:"rules", to:"model", color:"--c-orch",
        title:"Rules answer, or deliberately defer",
        route:"classify_signature()",
        desc:"Physics rules own every clear fault. They do not separate suction from discharge restriction — the one pair a signature cannot split — so that case is handed on rather than guessed at.",
        payload:
`{
    "top": "bearing_wear",
    "score": 0.71,
    "runner_up": 0.38,
    "separation": 0.33      // floor 0.56, margin 0.07
}
// on the restriction pair: no verdict, defer`,
        chips:["floor 0.56","margin 0.07"]
      },
      {
        from:"model", to:"agent", color:"--c-compute",
        title:"The narrow model answers its one question",
        route:"ml_classifier.classify_restriction()",
        desc:"An Extra Trees classifier trained on one job. An IsolationForest novelty score and an exact feature-roster check make it <em>abstain</em> rather than answer in a domain it was never trained on.",
        payload:
`{
    "predicted": "suction_restriction",
    "proba": 0.81,
    "novelty_ok": true,
    "roster_ok": true       // exact feature roster required
}`,
        chips:["one pair only","abstains on novelty"]
      },
      {
        from:"agent", to:"calib", color:"--c-embed",
        title:"The agent writes the case",
        route:"agent/triage.py · bounded tool loop",
        desc:"Evidence, cited past work orders, recommended actions, a drafted work order. <em>It never sets the fault class, the priority, or whether a work order exists.</em>",
        payloadMock:
`# free deterministic policy — same tool protocol
tools: get_machine_info · get_recent_telemetry
       search_maintenance_history · count_recurrences
-> { explanation, cited_work_orders, actions[] }`,
        payloadLive:
`POST https://openrouter.ai/api/v1/chat/completions
{
    "model": "deepseek/deepseek-v4-flash",
    "tools": [get_machine_info, get_recent_telemetry,
              search_maintenance_history, count_recurrences],
    "max_tokens": 700
}`,
        chipsMock:["free","no provider call"],
        chipsLive:["~32 s mean","≤700 tokens"]
      },
      {
        from:"calib", to:"db", color:"--c-orch",
        title:"Confidence is grounded, then the case is stored",
        route:"triage_cases · status=pending_review",
        desc:"Calibrated against matching precedent and signature agreement — not the model's self-reported certainty. Priority P1–P4 comes from the formula in <code>priority.py</code>, and a P1 can never be downgraded by the agent.",
        payload:
`TriageCase
{
    "status": "pending_review",
    "root_cause": "suction_restriction",
    "confidence": 0.72,     // calibrated, not self-reported
    "priority": "P2",       // criticality + severity + recurrence + safety
    "abstain": false
}`,
        chips:["abstain < 0.45","P1 cannot be downgraded"]
      },
      {
        from:"db", to:"planner", color:"--c-user",
        title:"It reaches a named human",
        route:"GET /cases",
        desc:"The case is a proposal sitting in a queue. Nothing has happened to the machine, and no work order exists yet.",
        payload:
`GET /cases?status=pending_review
[
    { "id": 41, "machine_id": "pump-03",
      "priority": "P2", "confidence": 0.72 }
]`,
        chips:["pending_review"]
      }
    ]
  },

  /* ───── 2. The human gate: the only path from proposal to action ───── */
  decision: {
    name: "Human decision (the only path to a work order)",
    note: "One transition, one endpoint, one named person.",
    steps: [
      {
        from:"planner", to:"db", color:"--c-user",
        title:"A named planner approves, edits, or rejects",
        route:"POST /cases/{id}/decision",
        desc:"Requires a bearer token and a reviewer name. This is the only transition out of <code>pending_review</code>, and it is written by a person, not by the agent.",
        payload:
`POST /cases/41/decision
Authorization: Bearer <token>

{
    "action": "edit",              // approve | reject | edit
    "reviewer": "A. Kowalska",
    "note": "agree, raising priority",
    "priority": "P1",
    "recommended_actions": [ ... ]
}`,
        chips:["bearer token","named reviewer"]
      },
      {
        from:"planner", to:"cmms", color:"--c-vector",
        title:"Only an approval triggers the write-back",
        route:"agent/cmms_adapter.py → POST /cmms/api/workorders",
        desc:"The backend reaches the CMMS over HTTP with an idempotency key and a retry — never by importing it. Point <code>CMMS_BASE_URL</code> at SAP or Maximo and nothing upstream changes. A rejected case produces no work order at all.",
        payload:
`POST /cmms/api/workorders
Idempotency-Key: triage-case-41

{
    "external_ref": "triage-case-41",
    "equipment_id": "pump-03",
    "notification_type": "M1",
    "priority_code": 1,
    "damage_code": "...",
    "short_text": "Suction restriction",
    "reported_by": "PM-Triage-Assistant (AI);
                    approved by A. Kowalska"
}`,
        chips:["Idempotency-Key","retry","rejected → nothing"]
      },
      {
        from:"cmms", to:"db", color:"--c-vector",
        title:"The work-order id lands back on the case",
        route:"triage_cases.cmms_work_order_id",
        desc:"<code>synced</code>, <code>failed</code> (unreachable — retry available) and <code>rejected</code> (payload refused — retry cannot help) are distinct states, each with its own audit event.",
        payload:
`{
    "work_order_id": "WO-10231",
    "cmms_status": "RECEIVED",
    "cmms_sync_status": "synced"
}`,
        chips:["idempotent","no duplicates"]
      },
      {
        from:"db", to:"planner", color:"--c-user",
        title:"The audit trail closes the loop",
        route:"GET /audit",
        desc:"Append-only: every detection, every model call, every decision, with its actor and timestamp.",
        payload:
`[
    { "actor": "system",           "event": "anomaly_detected" },
    { "actor": "agent",            "event": "triage_completed" },
    { "actor": "human:A. Kowalska","event": "case_approved" },
    { "actor": "system",           "event": "cmms_synced" }
]`,
        chips:["append-only"]
      }
    ]
  },

  /* ───── 3. Abstention: the system declining to answer, on purpose ───── */
  abstain: {
    name: "Low confidence (the system declines to answer)",
    note: "Abstention routes to a human. It never drops a case, and it never creates work.",
    steps: [
      {
        from:"model", to:"agent", color:"--c-compute",
        title:"The trained layer abstains",
        route:"novelty + roster guard",
        desc:"A novel signal or an unsupported testbed: the model returns no class rather than a confident answer outside the one job it was trained for.",
        payload:
`{
    "predicted": null,
    "reason": "novelty_score below threshold",
    "roster_ok": false      // unsupported feature set
}`,
        chips:["novelty","roster mismatch"]
      },
      {
        from:"agent", to:"calib", color:"--c-embed",
        title:"A fluent answer is not evidence",
        route:"calibrate()",
        desc:"A language model's own certainty tracks fluency — the SKAB evaluation showed it confidently wrong on real data. The calibrated number is built from matching precedent and signature agreement instead.",
        payload:
`calibrate(raw_confidence=0.88, ...)
-> signature_abstained: true
-> calibrated: 0.44         // capped below the threshold`,
        chips:["raw 0.88 → 0.44"]
      },
      {
        from:"calib", to:"db", color:"--c-orch",
        title:"The case says so, in the case itself",
        route:"triage_cases · abstain=true",
        desc:"Below 0.45 the case is stored flagged: the system is not claiming an answer.",
        payload:
`{
    "confidence": 0.44,
    "abstain": true,
    "reason": "ambiguous signature — routed to human review"
}`,
        chips:["threshold 0.45"]
      },
      {
        from:"db", to:"planner", color:"--c-user",
        title:"It still reaches a planner",
        route:"GET /cases",
        desc:"Marked uncertain, with the same evidence attached. On the real replay set this is the cavitation recording: the system abstains on it and is correct on the seven cases it does accept.",
        payload:
`{ "id": 42, "abstain": true,
  "banner": "agent unsure — evidence attached" }`,
        chips:["human uncertainty review"]
      }
    ]
  },

  /* ───── 4. Live mode: what spending money actually looks like ───── */
  spend: {
    name: "Live model, caps, and the free fallback",
    note: "A credential is not permission to spend.",
    liveMode: "live",
    onlyMode: "live",
    steps: [
      {
        from:"agent", to:"provider", color:"--c-embed",
        title:"The call is reserved before it is made",
        route:"llm_budget.reserve_live_call()",
        desc:"<code>LLM_MODE=mock</code> is the deployed default even when an API key exists. Live mode is opt-in through the authenticated toggle, and the budget is checked before the request leaves.",
        payload:
`reserve_live_call(model="deepseek/deepseek-v4-flash")
# counts actual provider requests, not cases —
# one case can make several calls`,
        chips:["12 calls/day","$0.25/day","700 tokens"]
      },
      {
        from:"provider", to:"agent", color:"--c-embed",
        title:"The exact returned cost is recorded",
        route:"llm_calls",
        desc:"Prompt tokens, output tokens, status and OpenRouter's returned cost, stored per request — not an estimate.",
        payload:
`{
    "usage": { "prompt_tokens": 2143,
               "completion_tokens": 486 },
    "cost": 0.000431          // returned by the provider
}`,
        chips:["exact cost","0 errors"]
      },
      {
        from:"agent", to:"db", color:"--c-vector",
        title:"Spend is a ledger",
        route:"INSERT llm_calls",
        desc:"The whole measured live replay — eight real cases, 34 provider requests — cost $0.014535. That number comes from this table, not from a price list.",
        payload:
`LlmCall
{ "model": "deepseek/deepseek-v4-flash",
  "status": "ok", "cost_usd": 0.000431 }`,
        chips:["34 requests","$0.014535"]
      },
      {
        from:"agent", to:"calib", color:"--c-orch",
        title:"Over cap or provider failure → free and deterministic",
        route:"fallback",
        desc:"The case is never lost. It finishes on the free deterministic policy, which follows the same tool protocol, and the fallback is written into the case's own trace.",
        payload:
`trace += "live call failed (provider timeout);
           continued in deterministic mode"`,
        chips:["no lost case","no silent downgrade"]
      }
    ]
  }
};'''

fls = find(lambda l: l.strip() == "const flows = {")
fle = find(lambda l: l.strip() == "};", fls)
lines[fls:fle + 1] = FLOWS.split("\n")

t = "\n".join(lines)

# default flow fallback in CONFIG should be a real key
t = t.replace('"flow_a"', '"triage"').replace("'flow_a'", "'triage'")
t = t.replace('["triage", "flow_b", "flow_c"]', '["triage", "decision", "abstain", "spend"]')

DST.write_text(t)
left = t.count("{{")
print("wrote", DST, "| leftover placeholders:", left)
if left:
    import re
    print(set(re.findall(r"\{\{[A-Z_]+\}\}", t)))
