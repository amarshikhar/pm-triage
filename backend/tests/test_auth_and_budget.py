"""Access gate, reviewer attribution, and the live-LLM spend cap."""

import json

from fastapi.testclient import TestClient

import app.main as main_mod
from app.auth import issue_token, verify_token
from app.agent.llm import llm_mode, set_runtime_mode
from app.llm_budget import budget, finish_live_call, live_allowed, reserve_live_call
from app.models import LlmCall, Machine, TelemetryReading, utcnow
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


def test_key_alone_does_not_enable_paid_mode(monkeypatch):
    set_runtime_mode(None)
    monkeypatch.setenv("OPENROUTER_API_KEY", "configured-but-not-authorized")
    monkeypatch.delenv("LLM_MODE", raising=False)
    assert llm_mode() == "mock"
    monkeypatch.setenv("LLM_MODE", "live")
    assert llm_mode() == "live"


def test_llm_budget_counts_provider_requests_and_cost(db, monkeypatch):
    monkeypatch.setenv("LLM_DAILY_CALL_CAP", "2")
    monkeypatch.setenv("LLM_DAILY_USD_CAP", "0.01")
    assert budget(db)["remaining"] == 2
    old = LlmCall(ts="2020-01-01T00:00:00+00:00", model="old", status="succeeded")
    db.add(old)
    db.commit()
    row = reserve_live_call(db, "cheap/model")
    assert row is not None
    finish_live_call(db, row, {"prompt_tokens": 100, "completion_tokens": 20,
                               "total_tokens": 120, "cost": 0.004})
    b = budget(db)
    assert b["unit"] == "provider_requests"
    assert b["used_today"] == 1 and b["remaining"] == 1
    assert b["cost_usd_today"] == 0.004
    assert live_allowed(db)
    assert reserve_live_call(db, "cheap/model") is not None
    assert not live_allowed(db)


def test_dollar_cap_blocks_even_before_request_cap(db, monkeypatch):
    monkeypatch.setenv("LLM_DAILY_CALL_CAP", "10")
    monkeypatch.setenv("LLM_DAILY_USD_CAP", "0.005")
    row = reserve_live_call(db, "cheap/model")
    assert row is not None
    finish_live_call(db, row, {"cost": 0.006})
    assert budget(db)["cap_reached"]
    assert reserve_live_call(db, "cheap/model") is None


def test_process_guard_survives_an_empty_per_trial_ledger(db, monkeypatch):
    monkeypatch.setenv("LLM_DAILY_CALL_CAP", "1")
    monkeypatch.setenv("LLM_DAILY_USD_CAP", "1")
    row = reserve_live_call(db, "cheap/model")
    assert row is not None
    # The eval harness replaces the whole DB each trial. Deleting the persistent
    # row reproduces the dangerous "new trial sees zero usage" condition.
    db.delete(row)
    db.commit()
    assert reserve_live_call(db, "cheap/model") is None
