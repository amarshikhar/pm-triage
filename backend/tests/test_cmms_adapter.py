"""Anti-corruption layer: translation, and retry/idempotency behaviour."""

import asyncio

import httpx
import pytest

from app.agent.cmms_adapter import (
    CmmsRejected, CmmsUnavailable, build_payload, failure_mode, push_work_order)


def test_failure_mode_maps_to_iso14224_codes():
    assert failure_mode("temperature_c", "seized fan bearing")[0] == "OHE"
    assert failure_mode("pressure_kpa", "discharge valve leak")[0] == "LOO"
    assert failure_mode("vibration_mm_s", "worn spindle bearing")[0] == "VIB"
    # cavitation and bearing wear both breach vibration — the text disambiguates
    assert failure_mode("vibration_mm_s", "suction strainer cavitation")[0] == "CAV"


def test_build_payload_is_a_translation_not_a_rename():
    p = build_payload(
        case_id=7, equipment_id="CMP-01", functional_location="Utility Room",
        priority="P1", breached_metric="temperature_c",
        root_cause="seized cooling fan motor bearing on the discharge head assembly",
        explanation="head temperature climbing past limit",
        cited_work_orders=["WO-1005"], est_downtime_hours=4.0,
        est_cost_exposure=14000.0, reviewer="shikhar")
    assert p["priority_code"] == 1 and p["priority_text"].startswith("1")  # P1 -> 1
    assert p["functional_location"] == "Utility Room"                       # location -> FLOC
    assert p["notification_type"] == "M1"                                   # malfunction report
    assert p["damage_code"] == "OHE"
    assert len(p["short_text"]) <= 40                                       # SAP short-text limit
    assert p["external_ref"] == "triage-case-7"
    assert "WO-1005" in p["long_text"] and "14,000" in p["long_text"]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_push_retries_transient_failure_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(503)  # transient
        assert request.headers["Idempotency-Key"] == "k1"
        return httpx.Response(201, json={
            "order_id": "4500000001", "system_status": "OSNO",
            "equipment_id": "CMP-01", "priority_code": 1, "damage_code": "OHE",
            "est_cost_exposure": 14000.0})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                     base_url="http://cmms.test") as c:
            return await push_work_order({"equipment_id": "CMP-01"}, "k1", client=c)

    wo = _run(run())
    assert wo["order_id"] == "4500000001"
    assert calls["n"] == 2  # one retry, then success


def test_push_gives_up_and_raises_unavailable():
    def handler(request):
        return httpx.Response(500)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                     base_url="http://cmms.test") as c:
            return await push_work_order({}, "k2", client=c)

    with pytest.raises(CmmsUnavailable):
        _run(run())


def test_push_fails_fast_on_client_error():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(422, text="bad payload")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                     base_url="http://cmms.test") as c:
            return await push_work_order({}, "k3", client=c)

    with pytest.raises(CmmsRejected):
        _run(run())
    assert calls["n"] == 1  # a 4xx is our bug — do NOT retry it
