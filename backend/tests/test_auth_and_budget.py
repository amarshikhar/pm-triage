"""Access gate, reviewer attribution, and the live-LLM spend cap."""

import json

from fastapi.testclient import TestClient

import app.main as main_mod
from app.auth import issue_token, verify_token
from app.llm_budget import budget, live_allowed
from app.models import Machine, TelemetryReading, TriageCase, utcnow
from app.detector import run_detection
from app.agent.triage import run_triage


def _make_case(db, machine_id="CNC-01"):
    m = db.get(Machine, machine_id)
    base = {"temperature_c": 55, "vibration_mm_s": 2.5, "pressure_kpa": 300, "rpm": 8000}
    for _ in range(8):
        db.add(TelemetryReading(machine_id=m.id, ts=utcnow().isoformat(),
                                values_json=json.dumps(base)))
    db.commit()
    r = TelemetryReading(machine_id=m.id, ts=utcnow().isoformat(),
                         values_json=json.dumps({**base, "vibration_mm_s": 7.2}))
    db.add(r)
    db.commit()
    return run_triage(db, run_detection(db, m, r)[0])


def test_gate_disabled_without_password(db, monkeypatch):
    monkeypatch.delenv("APP_ACCESS_PASSWORD", raising=False)
    client = TestClient(main_mod.app)
    case = _make_case(db)
    r = client.post(f"/api/cases/{case.id}/decision",
                    json={"action": "reject", "reviewer": "Open Access"})
    assert r.status_code == 200
    assert r.json()["reviewer"] == "Open Access"


def test_gate_blocks_unauthenticated_decisions(db, monkeypatch):
    monkeypatch.setenv("APP_ACCESS_PASSWORD", "crew-secret")
    client = TestClient(main_mod.app)
    case = _make_case(db)
    r = client.post(f"/api/cases/{case.id}/decision",
                    json={"action": "reject", "reviewer": "Nobody"})
    assert r.status_code == 401
    # reads stay open: a shared link shows the dashboard
    assert client.get("/api/cases").status_code == 200
    assert client.get("/api/machines").status_code == 200


def test_login_and_token_signs_the_decision(db, monkeypatch):
    monkeypatch.setenv("APP_ACCESS_PASSWORD", "crew-secret")
    client = TestClient(main_mod.app)

    assert client.post("/api/auth/login",
                       json={"password": "wrong", "reviewer": "Ana"}).status_code == 401
    token = client.post("/api/auth/login",
                        json={"password": "crew-secret", "reviewer": "Ana"}).json()["token"]

    case = _make_case(db)
    r = client.post(f"/api/cases/{case.id}/decision",
                    json={"action": "approve", "reviewer": "Somebody Else"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    # the token identity wins — you cannot sign with another name
    assert r.json()["reviewer"] == "Ana"


def test_token_tampering_and_password_rotation_invalidate(monkeypatch):
    monkeypatch.setenv("APP_ACCESS_PASSWORD", "crew-secret")
    token = issue_token("Ana")
    assert verify_token(token) == "Ana"
    assert verify_token(token[:-1] + ("0" if token[-1] != "0" else "1")) is None
    monkeypatch.setenv("APP_ACCESS_PASSWORD", "rotated")
    assert verify_token(token) is None


def test_llm_toggle_requires_auth_and_is_audited(db, monkeypatch):
    monkeypatch.setenv("APP_ACCESS_PASSWORD", "crew-secret")
    client = TestClient(main_mod.app)
    assert client.post("/api/llm/mode", json={"mode": "mock"}).status_code == 401

    token = client.post("/api/auth/login",
                        json={"password": "crew-secret", "reviewer": "Ana"}).json()["token"]
    r = client.post("/api/llm/mode", json={"mode": "mock"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["mode"] == "mock"
    # back to environment default so other tests are unaffected
    client.post("/api/llm/mode", json={"mode": "auto"},
                headers={"Authorization": f"Bearer {token}"})


def test_llm_budget_counts_only_todays_live_cases(db, monkeypatch):
    monkeypatch.setenv("LLM_DAILY_CALL_CAP", "2")
    assert budget(db)["remaining"] == 2
    db.add(TriageCase(anomaly_id=1, machine_id="CNC-01",
                      created_ts=utcnow().isoformat(), llm_mode="live"))
    db.add(TriageCase(anomaly_id=1, machine_id="CNC-01",
                      created_ts=utcnow().isoformat(), llm_mode="mock"))
    db.add(TriageCase(anomaly_id=1, machine_id="CNC-01",
                      created_ts="2020-01-01T00:00:00+00:00", llm_mode="live"))
    db.commit()
    b = budget(db)
    assert b["used_today"] == 1 and b["remaining"] == 1
    assert live_allowed(db)
    db.add(TriageCase(anomaly_id=1, machine_id="CNC-01",
                      created_ts=utcnow().isoformat(), llm_mode="live"))
    db.commit()
    assert not live_allowed(db)
