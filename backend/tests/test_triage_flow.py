import json

from app.agent.triage import run_triage
from app.detector import run_detection
from app.models import Anomaly, AuditEvent, Machine, TelemetryReading, TriageCase, utcnow
from app.priority import apply_adjustment, compute_priority


def _make_anomaly(db, machine_id="CNC-01", vib=7.2) -> int:
    m = db.get(Machine, machine_id)
    base = {"temperature_c": 55, "vibration_mm_s": 2.5, "pressure_kpa": 300, "rpm": 8000}
    for _ in range(8):
        db.add(TelemetryReading(machine_id=m.id, ts=utcnow().isoformat(),
                                values_json=json.dumps(base)))
    db.commit()
    r = TelemetryReading(machine_id=m.id, ts=utcnow().isoformat(),
                         values_json=json.dumps({**base, "temperature_c": 62,
                                                 "vibration_mm_s": vib}))
    db.add(r)
    db.commit()
    return run_detection(db, m, r)[0]


def test_mock_agent_produces_explainable_case(db):
    case = run_triage(db, _make_anomaly(db))
    assert case.status == "pending_review"          # never auto-approved
    assert case.root_cause
    assert 0 < case.confidence <= 1
    assert case.priority in ("P1", "P2", "P3", "P4")

    evidence = json.loads(case.evidence_json)
    assert evidence["historical_matches"], "must cite historical work orders"
    assert evidence["signature_analysis"]["ranked"]
    assert "agent_agreement" in evidence["signature_analysis"]
    trace = json.loads(case.trace_json)
    tools_used = [t["tool"] for t in trace if t["step"] == "tool_call"]
    assert "search_maintenance_history" in tools_used

    breakdown = json.loads(case.priority_breakdown_json)
    assert set(breakdown["components"]) == {
        "machine_criticality", "anomaly_severity", "recurrence", "safety_flag"}
    assert set(breakdown["signature_analysis"]) == {
        "predicted", "confidence", "abstain", "agent_agreement", "evidence"}


def test_priority_formula():
    p = compute_priority(criticality=5, severity="high", recurrence_count=2, safety_related=False)
    assert p["priority"] == "P1" and p["score"] == 13
    assert compute_priority(1, "low", 0, False)["priority"] == "P4"
    assert compute_priority(2, "medium", 0, True)["priority"] == "P1"  # safety always P1


def test_priority_adjustment_clamped():
    assert apply_adjustment("P3", +1) == "P2"
    assert apply_adjustment("P3", -1) == "P4"
    assert apply_adjustment("P1", -1) == "P1"   # cannot downgrade P1
    assert apply_adjustment("P4", -5) == "P4"   # over-large adjustments are clamped to one notch
    assert apply_adjustment("P4", +5) == "P3"


def test_human_gate_is_single_decision(db):
    from fastapi.testclient import TestClient
    import app.main as main_mod
    client = TestClient(main_mod.app)

    case = run_triage(db, _make_anomaly(db))
    resp = client.post(f"/api/cases/{case.id}/decision",
                       json={"action": "edit", "reviewer": "shikhar",
                             "note": "bump priority", "priority": "P1"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved_with_edits"
    assert resp.json()["priority"] == "P1"

    # second decision must be refused — decisions are final
    resp2 = client.post(f"/api/cases/{case.id}/decision",
                        json={"action": "approve", "reviewer": "someone-else"})
    assert resp2.status_code == 409

    db.expire_all()
    audit_types = [a.event_type for a in db.query(AuditEvent).all()]
    assert "case_edit" in audit_types and "case_created" in audit_types
