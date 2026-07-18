"""CMMS service idempotency and the end-to-end approve -> write-back loop."""

import json

from fastapi.testclient import TestClient

import app.main as main_mod
from app.agent.triage import run_triage
from app.models import AuditEvent, Machine, TelemetryReading, TriageCase, utcnow
from app.detector import run_detection


def _make_anomaly(db, machine_id="CMP-01") -> int:
    m = db.get(Machine, machine_id)
    base = {"temperature_c": 70, "vibration_mm_s": 3.0, "pressure_kpa": 720, "rpm": 1500}
    for _ in range(8):
        db.add(TelemetryReading(machine_id=m.id, ts=utcnow().isoformat(),
                                values_json=json.dumps(base)))
    db.commit()
    r = TelemetryReading(machine_id=m.id, ts=utcnow().isoformat(),
                         values_json=json.dumps({**base, "temperature_c": 99}))
    db.add(r)
    db.commit()
    return run_detection(db, m, r)[0]


def test_cmms_create_is_idempotent(db):
    client = TestClient(main_mod.app)
    body = {"equipment_id": "CMP-01", "priority_code": 1, "short_text": "test"}
    r1 = client.post("/cmms/api/workorders", json=body, headers={"Idempotency-Key": "key-x"})
    r2 = client.post("/cmms/api/workorders", json=body, headers={"Idempotency-Key": "key-x"})
    assert r1.status_code == 201 and r2.status_code == 200          # second is a no-op replay
    assert r1.json()["order_id"] == r2.json()["order_id"]           # same work order, not a dup
    assert client.post("/cmms/api/workorders", json=body,
                       headers={"Idempotency-Key": "key-y"}).json()["order_id"] != r1.json()["order_id"]


def test_approval_writes_work_order_to_system_of_record(db):
    client = TestClient(main_mod.app)
    case = run_triage(db, _make_anomaly(db))

    resp = client.post(f"/api/cases/{case.id}/decision",
                       json={"action": "approve", "reviewer": "shikhar"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["cmms_sync_status"] == "synced"
    assert body["cmms_work_order_id"].startswith("4500")

    # The work order is actually in the CMMS, carrying the translated fields.
    orders = client.get("/cmms/api/workorders").json()
    mine = [w for w in orders if w["external_ref"] == f"triage-case-{case.id}"]
    assert len(mine) == 1
    assert mine[0]["equipment_id"] == "CMP-01"
    assert mine[0]["notification_type"] == "M1"
    assert mine[0]["priority_code"] in (1, 2, 3, 4)

    # And the write-back is attributed in the audit trail.
    db.expire_all()
    assert "work_order_created" in [a.event_type for a in db.query(AuditEvent).all()]


def test_rejection_does_not_touch_the_system_of_record(db):
    client = TestClient(main_mod.app)
    case = run_triage(db, _make_anomaly(db))

    resp = client.post(f"/api/cases/{case.id}/decision",
                       json={"action": "reject", "reviewer": "shikhar"})
    body = resp.json()
    assert body["cmms_sync_status"] == "not_applicable"
    assert body["cmms_work_order_id"] == ""
    assert client.get("/cmms/api/workorders").json() == []


def test_outage_defers_sync_and_retry_reports_failure_honestly(db, monkeypatch):
    """An unreachable CMMS marks the case failed (retryable); a retry that still
    fails answers 502, not a deceptive 200; a retry after recovery syncs."""
    import app.routes as routes_mod
    from app.agent.cmms_adapter import CmmsUnavailable

    async def down(payload, idempotency_key, client=None):
        raise CmmsUnavailable("boom")

    client = TestClient(main_mod.app)
    case = run_triage(db, _make_anomaly(db))

    monkeypatch.setattr(routes_mod, "push_work_order", down)
    resp = client.post(f"/api/cases/{case.id}/decision",
                       json={"action": "approve", "reviewer": "shikhar"})
    assert resp.status_code == 200                       # the human decision stands
    assert resp.json()["cmms_sync_status"] == "failed"

    assert client.post(f"/api/cases/{case.id}/sync-cmms").status_code == 502

    monkeypatch.undo()                                   # CMMS back up
    retried = client.post(f"/api/cases/{case.id}/sync-cmms")
    assert retried.status_code == 200
    assert retried.json()["cmms_sync_status"] == "synced"
    assert retried.json()["cmms_work_order_id"].startswith("4500")


def test_cmms_rejection_is_terminal_not_retryable(db, monkeypatch):
    """A 4xx from the CMMS is a translation bug: distinct 'rejected' status,
    audited, and the retry endpoint refuses with 409 instead of looping."""
    import app.routes as routes_mod
    from app.agent.cmms_adapter import CmmsRejected

    async def rejecting(payload, idempotency_key, client=None):
        raise CmmsRejected("CMMS rejected work order: 422 bad payload")

    monkeypatch.setattr(routes_mod, "push_work_order", rejecting)
    client = TestClient(main_mod.app)
    case = run_triage(db, _make_anomaly(db))

    resp = client.post(f"/api/cases/{case.id}/decision",
                       json={"action": "approve", "reviewer": "shikhar"})
    assert resp.json()["cmms_sync_status"] == "rejected"

    assert client.post(f"/api/cases/{case.id}/sync-cmms").status_code == 409

    db.expire_all()
    assert "work_order_rejected" in [a.event_type for a in db.query(AuditEvent).all()]


def test_double_approve_is_refused_and_does_not_double_raise(db):
    client = TestClient(main_mod.app)
    case = run_triage(db, _make_anomaly(db))
    client.post(f"/api/cases/{case.id}/decision", json={"action": "approve", "reviewer": "alice"})
    second = client.post(f"/api/cases/{case.id}/decision", json={"action": "approve", "reviewer": "bob"})
    assert second.status_code == 409                       # decisions are final
    assert len(client.get("/cmms/api/workorders").json()) == 1  # exactly one work order
