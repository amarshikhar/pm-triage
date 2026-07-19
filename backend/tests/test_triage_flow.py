import json

from app.agent.triage import run_triage
from app.detector import run_detection
from app.models import (Anomaly, AuditEvent, LlmCall, Machine, MaintenanceLog,
                        TelemetryReading, TriageCase, utcnow)
from app.priority import apply_adjustment, compute_priority
from app.seed import seed_if_empty


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


def test_live_usage_ledger_counts_every_provider_turn(db, monkeypatch):
    import app.agent.triage as triage_mod
    from app.agent.llm import MockLLM, set_runtime_mode

    anomaly_id = _make_anomaly(db)
    scripted_provider = MockLLM({
        "machine_id": "CNC-01", "machine_type": "cnc_mill",
        "metric": "vibration_mm_s", "severity": "high",
    })
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("LLM_DAILY_CALL_CAP", "10")
    monkeypatch.setenv("LLM_DAILY_USD_CAP", "1")
    set_runtime_mode(None)

    def fake_chat(messages, tools):
        return scripted_provider.chat(messages, tools), {
            "prompt_tokens": 100, "completion_tokens": 20,
            "total_tokens": 120, "cost": 0.001,
        }

    monkeypatch.setattr(triage_mod, "chat", fake_chat)
    case = run_triage(db, anomaly_id)
    calls = db.query(LlmCall).order_by(LlmCall.id).all()
    assert case.llm_mode == "live"
    assert len(calls) == 4, "three tool turns plus one final answer"
    assert all(c.status == "succeeded" for c in calls)
    assert round(sum(c.cost_usd for c in calls), 3) == 0.004


def test_live_cap_falls_back_mid_case_without_losing_case(db, monkeypatch):
    import app.agent.triage as triage_mod
    from app.agent.llm import MockLLM, set_runtime_mode

    anomaly_id = _make_anomaly(db)
    scripted_provider = MockLLM({
        "machine_id": "CNC-01", "machine_type": "cnc_mill",
        "metric": "vibration_mm_s", "severity": "high",
    })
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("LLM_DAILY_CALL_CAP", "2")
    monkeypatch.setenv("LLM_DAILY_USD_CAP", "1")
    set_runtime_mode(None)
    monkeypatch.setattr(
        triage_mod, "chat",
        lambda messages, tools: (scripted_provider.chat(messages, tools), {"cost": 0.001}),
    )

    case = run_triage(db, anomaly_id)
    assert case.llm_mode == "mock"
    assert db.query(LlmCall).count() == 2
    assert any(t["step"] == "llm_budget_fallback"
               for t in json.loads(case.trace_json))


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


def test_reference_seed_adds_new_testbed_without_overwriting_existing_rows(db):
    user_name = "Locally renamed by customer"
    db.get(Machine, "CNC-01").name = user_name
    db.delete(db.get(MaintenanceLog, "WO-1032"))
    db.delete(db.get(Machine, "BRG-01"))
    db.commit()

    assert seed_if_empty(db) is True
    assert db.get(Machine, "BRG-01") is not None
    assert db.get(MaintenanceLog, "WO-1032") is not None
    assert db.get(Machine, "CNC-01").name == user_name
    assert seed_if_empty(db) is False
