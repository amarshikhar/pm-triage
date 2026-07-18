import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .agent.cmms_adapter import (
    CmmsRejected, CmmsUnavailable, build_payload, push_work_order)
from .agent.llm import llm_mode, llm_model, runtime_mode, set_runtime_mode
from .agent.triage import run_triage
from .audit import audit
from .auth import auth_enabled, current_reviewer, issue_token
from .db import get_db
from .llm_budget import budget
from .models import Anomaly, AuditEvent, Machine, TelemetryReading, TriageCase
from .replay import replayer
from .simulator import FAULTS, simulator

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    return {"ok": True, "llm_mode": llm_mode(), "llm_model": llm_model(),
            "simulator_running": simulator.running, "auth_enabled": auth_enabled()}


class Login(BaseModel):
    password: str
    reviewer: str = Field(min_length=2, max_length=60)


@router.post("/auth/login")
def login(body: Login, db: Session = Depends(get_db)):
    """Crew password in, per-reviewer session token out. The reviewer name in
    the token is what every subsequent decision is attributed to."""
    import os

    if not auth_enabled():
        return {"token": "", "reviewer": body.reviewer, "auth_enabled": False}
    if body.password != os.getenv("APP_ACCESS_PASSWORD", ""):
        raise HTTPException(401, "wrong password")
    audit(db, f"human:{body.reviewer}", "login", "session", body.reviewer, {})
    return {"token": issue_token(body.reviewer), "reviewer": body.reviewer,
            "auth_enabled": True}


@router.get("/llm")
def llm_status(db: Session = Depends(get_db)):
    import os

    return {"mode": llm_mode(), "model": llm_model(),
            "runtime_override": runtime_mode(),
            # Without a key, a "live" toggle silently resolves to mock — the UI
            # needs to say WHY, not just show mock.
            "key_configured": bool(os.getenv("OPENROUTER_API_KEY")),
            "budget": budget(db)}


class LlmMode(BaseModel):
    mode: str = Field(pattern="^(live|mock|auto)$")


@router.post("/llm/mode")
def set_llm_mode(body: LlmMode, db: Session = Depends(get_db),
                 reviewer: str = Depends(current_reviewer)):
    """Demo toggle. `live` spends real tokens (within the daily cap); `mock`
    is free; `auto` follows the deployment's environment default."""
    set_runtime_mode(None if body.mode == "auto" else body.mode)
    audit(db, f"human:{reviewer or 'anonymous'}", "llm_mode_set", "llm", body.mode,
          {"effective_mode": llm_mode(), "budget": budget(db)})
    return {"mode": llm_mode(), "runtime_override": runtime_mode(), "budget": budget(db)}


@router.get("/machines")
def list_machines(db: Session = Depends(get_db)):
    """Fleet snapshot in three queries, not 2N+1.

    Against a remote Postgres every query is a network round trip; the per-
    machine latest-reading + pending-count pattern made this endpoint ~20
    round trips and it is polled every few seconds by the dashboard."""
    from sqlalchemy import func

    machines = db.query(Machine).order_by(Machine.id).all()
    latest_ids = (
        db.query(func.max(TelemetryReading.id))
        .group_by(TelemetryReading.machine_id)
        .subquery()
    )
    latest_by_machine = {
        r.machine_id: r
        for r in db.query(TelemetryReading).filter(TelemetryReading.id.in_(latest_ids)).all()
    }
    pending_by_machine = dict(
        db.query(TriageCase.machine_id, func.count())
        .filter(TriageCase.status == "pending_review")
        .group_by(TriageCase.machine_id)
        .all()
    )

    out = []
    for m in machines:
        latest = latest_by_machine.get(m.id)
        pending = pending_by_machine.get(m.id, 0)
        if m.source == "replay":
            fault_active = replayer.active_fault(m.id) is not None
        else:
            fault_active = m.id in simulator.active_faults
        dataset = json.loads(m.dataset_json or "{}")
        out.append({
            "id": m.id, "name": m.name, "type": m.type, "location": m.location,
            "criticality": m.criticality,
            "source": m.source,
            "signals": m.signals,
            "dataset": {k: dataset[k] for k in ("dataset", "url", "license")
                        if k in dataset},
            "fault_active": fault_active,
            "pending_cases": pending,
            "latest": None if not latest else {"ts": latest.ts, **latest.values},
        })
    return out


@router.get("/machines/{machine_id}/telemetry")
def machine_telemetry(machine_id: str, n: int = 60, db: Session = Depends(get_db)):
    rows = (
        db.query(TelemetryReading)
        .filter(TelemetryReading.machine_id == machine_id)
        .order_by(TelemetryReading.id.desc())
        .limit(min(n, 500))
        .all()
    )
    rows.reverse()
    return [{"ts": r.ts, **r.values} for r in rows]


@router.get("/cases")
def list_cases(status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(TriageCase)
    if status:
        q = q.filter(TriageCase.status == status)
    cases = q.order_by(TriageCase.priority, TriageCase.id.desc()).limit(100).all()
    return [c.as_dict() for c in cases]


@router.get("/cases/{case_id}")
def get_case(case_id: int, db: Session = Depends(get_db)):
    case = db.get(TriageCase, case_id)
    if not case:
        raise HTTPException(404, "case not found")
    d = case.as_dict(full=True)
    anomaly = db.get(Anomaly, case.anomaly_id)
    if anomaly:
        d["anomaly"] = {"metric": anomaly.metric, "value": anomaly.value,
                        "threshold": anomaly.threshold, "zscore": anomaly.zscore,
                        "severity": anomaly.severity, "ts": anomaly.ts,
                        "description": anomaly.description}
    return d


class Decision(BaseModel):
    action: str = Field(pattern="^(approve|reject|edit)$")
    reviewer: str = Field(min_length=2)
    note: str = ""
    priority: str | None = Field(default=None, pattern="^P[1-4]$")
    recommended_actions: list[str] | None = None


@router.post("/cases/{case_id}/decision")
async def decide_case(case_id: int, decision: Decision, db: Session = Depends(get_db),
                      session_reviewer: str = Depends(current_reviewer)):
    """The mandatory human checkpoint. A case leaves pending_review only here.

    On approval, the decision is written back to the CMMS as a work order — the
    action only ever leaves this system AFTER a human has signed it. Rejection
    raises nothing downstream. With auth enabled, the reviewer identity comes
    from the session token, not the request body — a decision cannot be signed
    with someone else's name.
    """
    if session_reviewer:
        decision.reviewer = session_reviewer
    case = db.get(TriageCase, case_id)
    if not case:
        raise HTTPException(404, "case not found")
    if case.status != "pending_review":
        raise HTTPException(409, f"case already decided ({case.status}) — decisions are final and audited")

    from .models import utcnow
    before = {"priority": case.priority,
              "recommended_actions": json.loads(case.recommended_actions_json)}

    if decision.action == "approve":
        case.status = "approved"
    elif decision.action == "reject":
        case.status = "rejected"
    else:  # edit
        case.status = "approved_with_edits"
        if decision.priority:
            case.priority = decision.priority
        if decision.recommended_actions is not None:
            case.recommended_actions_json = json.dumps(decision.recommended_actions)

    case.reviewer = decision.reviewer
    case.review_note = decision.note
    case.reviewed_ts = utcnow().isoformat()
    db.commit()

    audit(db, f"human:{decision.reviewer}", f"case_{decision.action}", "case", case.id, {
        "note": decision.note, "before": before,
        "after": {"priority": case.priority,
                  "recommended_actions": json.loads(case.recommended_actions_json)},
    })

    if case.status in ("approved", "approved_with_edits"):
        await _sync_case_to_cmms(db, case)
    else:  # rejected — nothing goes to the system of record
        case.cmms_sync_status = "not_applicable"
        db.commit()

    return case.as_dict()


async def _sync_case_to_cmms(db: Session, case: TriageCase) -> None:
    """Translate an approved case and push it to the CMMS.

    A CMMS outage must not lose an approved decision: the human sign-off already
    committed above, so a failed push only marks the case sync-failed and audits
    it — a planner can retry via POST /api/cases/{id}/sync-cmms. Idempotency on
    the case id makes that retry (and any double-submit) safe.
    """
    machine = db.get(Machine, case.machine_id)
    anomaly = db.get(Anomaly, case.anomaly_id)
    breakdown = json.loads(case.priority_breakdown_json or "{}")
    evidence = json.loads(case.evidence_json or "{}")
    cited = evidence.get("cited_work_orders") or [
        m["work_order"] for m in evidence.get("historical_matches", [])[:3]]

    payload = build_payload(
        case_id=case.id,
        equipment_id=case.machine_id,
        functional_location=machine.location if machine else "",
        priority=case.priority,
        breached_metric=anomaly.metric if anomaly else "",
        root_cause=case.root_cause,
        explanation=case.explanation,
        cited_work_orders=[str(w) for w in cited],
        est_downtime_hours=breakdown.get("est_downtime_hours", 4.0),
        est_cost_exposure=breakdown.get("est_cost_exposure", 0.0),
        reviewer=case.reviewer,
    )
    try:
        wo = await push_work_order(payload, idempotency_key=f"triage-case-{case.id}")
    except CmmsUnavailable as e:
        # Outage: transient by definition — retryable, and the UI offers Retry.
        case.cmms_sync_status = "failed"
        db.commit()
        audit(db, "system", "work_order_sync_failed", "case", case.id, {"error": str(e)[:200]})
        return
    except CmmsRejected as e:
        # 4xx: the CMMS refused the payload — a translation bug on our side.
        # Retrying the same payload can never succeed, so this is a distinct
        # terminal status, not "failed", and the retry endpoint refuses it.
        case.cmms_sync_status = "rejected"
        db.commit()
        audit(db, "system", "work_order_rejected", "case", case.id, {"error": str(e)[:200]})
        return

    case.cmms_work_order_id = wo["order_id"]
    case.cmms_status = wo["system_status"]
    case.cmms_sync_status = "synced"
    db.commit()
    audit(db, "system", "work_order_created", "case", case.id, {
        "order_id": wo["order_id"], "equipment_id": wo["equipment_id"],
        "priority_code": wo["priority_code"], "damage_code": wo["damage_code"],
        "est_cost_exposure": wo["est_cost_exposure"],
    })


@router.post("/cases/{case_id}/sync-cmms")
async def retry_cmms_sync(case_id: int, db: Session = Depends(get_db),
                          _reviewer: str = Depends(current_reviewer)):
    """Retry a deferred CMMS write-back for an approved case."""
    case = db.get(TriageCase, case_id)
    if not case:
        raise HTTPException(404, "case not found")
    if case.status not in ("approved", "approved_with_edits"):
        raise HTTPException(409, "only an approved case has a work order to sync")
    if case.cmms_sync_status == "synced":
        return case.as_dict()  # idempotent: already in the system of record
    if case.cmms_sync_status == "rejected":
        raise HTTPException(409, "CMMS rejected this payload (translation error) — "
                                 "a retry cannot succeed; see the audit trail")
    await _sync_case_to_cmms(db, case)
    if case.cmms_sync_status != "synced":
        raise HTTPException(502, "CMMS still unreachable — decision preserved, retry again later")
    return case.as_dict()


@router.get("/audit")
def list_audit(limit: int = 100, machine: str | None = None, db: Session = Depends(get_db)):
    q = db.query(AuditEvent)
    if machine:
        # Scope to one asset: events on the machine itself, on its anomalies, or
        # on cases raised from it. Resolve the id sets, then filter.
        anomaly_ids = {str(a.id) for a in db.query(Anomaly.id).filter(Anomaly.machine_id == machine)}
        case_ids = {str(c.id) for c in db.query(TriageCase.id).filter(TriageCase.machine_id == machine)}
        rows = []
        for r in q.order_by(AuditEvent.id.desc()).limit(1500).all():
            hit = ((r.entity == "machine" and r.entity_id == machine)
                   or (r.entity == "anomaly" and r.entity_id in anomaly_ids)
                   or (r.entity == "case" and r.entity_id in case_ids))
            if hit:
                rows.append(r)
            if len(rows) >= min(limit, 500):
                break
    else:
        rows = q.order_by(AuditEvent.id.desc()).limit(min(limit, 500)).all()
    return [{"id": r.id, "ts": r.ts, "actor": r.actor, "event_type": r.event_type,
             "entity": r.entity, "entity_id": r.entity_id,
             "detail": json.loads(r.detail or "{}")} for r in rows]


@router.get("/eval-report")
def eval_report():
    """Serve the committed evaluation reports so the app can render the harness
    result (confusion matrix, calibration, accuracy) — the differentiator, made
    visible. trials_detail is stripped to keep the payload light."""
    import os

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # backend/
    out: dict = {}
    for key, fname in (("synthetic", "eval-report.json"), ("real", "eval-report-real.json")):
        path = os.path.join(here, fname)
        if not os.path.exists(path):
            continue
        with open(path) as fh:
            data = json.load(fh)
        for report in data.get("reports", {}).values():
            report.pop("trials_detail", None)
        out[key] = data
    return out


class Inject(BaseModel):
    machine_id: str
    fault: str


@router.post("/simulate/inject")
def inject_fault(body: Inject, db: Session = Depends(get_db),
                 reviewer: str = Depends(current_reviewer)):
    """Demo lever. Simulated machine: force a synthetic fault pattern onto its
    stream. Replay machine: cue the real recording of that fault class just
    before its labelled window — nothing is synthesized, only skipped to."""
    machine = db.get(Machine, body.machine_id)
    if not machine:
        raise HTTPException(404, "unknown machine")
    try:
        from .detector import force_detect
        force_detect(machine.id)  # a manual cue always surfaces a case (no dedup)
        if machine.source == "replay":
            episode = replayer.jump_to_fault(machine, body.fault)
            audit(db, f"human:{reviewer or 'demo'}", "episode_cued", "machine", machine.id,
                  {"fault": body.fault, "episode": episode})
            return {"ok": True, "episode": episode}
        simulator.inject_fault(body.machine_id, body.fault)
    except ValueError as e:
        raise HTTPException(422, str(e))
    audit(db, f"human:{reviewer or 'demo'}", "fault_injected", "machine", body.machine_id,
          {"fault": body.fault})
    return {"ok": True, "faults": {k: v["fault"] for k, v in simulator.active_faults.items()}}


@router.post("/simulate/clear/{machine_id}")
def clear_fault(machine_id: str, db: Session = Depends(get_db),
                reviewer: str = Depends(current_reviewer)):
    simulator.clear_fault(machine_id)
    audit(db, f"human:{reviewer or 'demo'}", "fault_cleared", "machine", machine_id, {})
    return {"ok": True}


@router.get("/simulate/faults")
def list_faults(db: Session = Depends(get_db)):
    replay_machines = db.query(Machine).filter(Machine.source == "replay").all()
    active = {k: v["fault"] for k, v in simulator.active_faults.items()}
    for m in replay_machines:
        fault = replayer.active_fault(m.id)
        if fault:
            active[m.id] = fault
    return {
        "available": sorted(FAULTS),
        "replay": {m.id: replayer.available_faults(m) for m in replay_machines},
        "active": active,
    }


async def triage_anomaly_async(anomaly_id: int):
    """Run the agent off the event loop; the simulator callback awaits this."""
    from .db import SessionLocal

    def _run():
        db = SessionLocal()
        try:
            run_triage(db, anomaly_id)
        finally:
            db.close()

    await asyncio.to_thread(_run)
