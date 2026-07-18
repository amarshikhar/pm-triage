"""Anti-corruption layer between triage and the CMMS system of record.

The triage domain speaks in P1..P4, metrics, and root-cause text. The CMMS
speaks in priority codes 1..4, functional locations, and ISO 14224 damage
codes. This module is the ONLY place those two vocabularies meet: it translates
a triage decision into the CMMS's schema and pushes it over HTTP. Nothing about
the CMMS's field names leaks back into the triage models, so the day the CMMS
becomes real SAP PM, only this file and the transport change.

Transport: by default the adapter talks to the in-process CMMS app over httpx's
ASGI transport — genuine HTTP request/response (headers, status codes, the
Idempotency-Key), but no second server to run during a demo. Set CMMS_BASE_URL
to point the same adapter at a networked CMMS instead.

Reliability: the push is idempotent (one work order per case, keyed on the case
id) and retried with backoff on transport failures and 5xx. A 4xx is our
mistake, not the CMMS's, so it fails fast instead of hammering. If every attempt
fails the caller gets CmmsUnavailable and records the case as sync-failed — the
human decision still stands; only the downstream sync is deferred and retryable.
"""

import asyncio
import os

import httpx

# Imported for the default in-process transport only. The triage side never
# calls the CMMS through this object — always over HTTP through this adapter.
from ..cmms.service import cmms_app

MAX_RETRIES = 3
BACKOFF_BASE_S = float(os.getenv("CMMS_RETRY_BACKOFF_S", "0.2"))
TIMEOUT_S = float(os.getenv("CMMS_TIMEOUT_S", "10"))

# Our P1..P4 label -> the CMMS's priority code (note the direction is preserved
# but the encoding is the CMMS's: 1 = very high). This is a translation, not a
# rename, which is the whole reason the adapter exists.
PRIORITY_MAP = {
    "P1": (1, "1-Very high"),
    "P2": (2, "2-High"),
    "P3": (3, "3-Medium"),
    "P4": (4, "4-Low"),
}


class CmmsUnavailable(RuntimeError):
    """The CMMS could not be reached after all retries — sync is deferrable."""


class CmmsRejected(RuntimeError):
    """The CMMS rejected the payload (4xx) — a translation bug, not a transient."""


def failure_mode(breached_metric: str, root_cause: str) -> tuple[str, str]:
    """Map the observed excursion to an ISO 14224 failure-mode code.

    ISO 14224 classifies failures by their observed *mode* (what was seen), not
    the underlying cause, which is exactly what the detector gives us: the metric
    that breached. Cavitation and vibration both show as rising vibration, so the
    root-cause text disambiguates that one pair. Codes are illustrative of the
    ISO 14224 vocabulary a real CMMS carries, kept in one auditable place.
    """
    rc = (root_cause or "").lower()
    metric = (breached_metric or "").lower()
    if "cavit" in rc:
        return "CAV", "Cavitation"
    # Signal keys differ per machine (temperature_c on the simulated fleet,
    # temp_motor_c on the SKAB pump), so match the family, not the exact tag.
    if metric.startswith(("temp", "therm")):
        return "OHE", "Overheating"
    if metric.startswith(("pressure", "press", "flow")):
        return "LOO", "Low output / insufficient pressure or flow"
    if metric.startswith(("vibration", "vib")):
        return "VIB", "Vibration / abnormal noise"
    return "OTH", "Other / unspecified"


def build_payload(
    *,
    case_id: int,
    equipment_id: str,
    functional_location: str,
    priority: str,
    breached_metric: str,
    root_cause: str,
    explanation: str,
    cited_work_orders: list[str],
    est_downtime_hours: float,
    est_cost_exposure: float,
    reviewer: str,
) -> dict:
    """Translate a triage case into the CMMS work-order schema (the ACL core)."""
    prio_code, prio_text = PRIORITY_MAP.get(priority, (4, "4-Low"))
    dmg_code, dmg_text = failure_mode(breached_metric, root_cause)
    cites = ", ".join(cited_work_orders) if cited_work_orders else "none"
    long_text = (
        f"{explanation}\n\n"
        f"Historical precedent cited by triage: {cites}.\n"
        f"Estimated downtime if unaddressed: {est_downtime_hours:.1f} h "
        f"(~${est_cost_exposure:,.0f} exposure).\n"
        f"Raised by condition-monitoring triage (AI); approved by {reviewer}."
    )
    return {
        "external_ref": f"triage-case-{case_id}",
        "equipment_id": equipment_id,
        "functional_location": functional_location,
        "notification_type": "M1",  # malfunction report
        "priority_code": prio_code,
        "priority_text": prio_text,
        "damage_code": dmg_code,
        "damage_text": dmg_text,
        "short_text": (root_cause or "Investigate detected anomaly")[:40],
        "long_text": long_text,
        "reported_by": f"PM-Triage-Assistant (AI); approved by {reviewer}",
        "est_downtime_hours": round(est_downtime_hours, 1),
        "est_cost_exposure": round(est_cost_exposure, 2),
    }


def _make_client() -> httpx.AsyncClient:
    base = os.getenv("CMMS_BASE_URL")
    if base:  # networked CMMS (e.g. a real SAP PM gateway)
        return httpx.AsyncClient(base_url=base, timeout=TIMEOUT_S)
    # In-process CMMS over a real HTTP transport — no socket, no second server.
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=cmms_app),
        base_url="http://cmms.internal",
        timeout=TIMEOUT_S,
    )


async def push_work_order(payload: dict, idempotency_key: str,
                          client: httpx.AsyncClient | None = None) -> dict:
    """POST the work order with retry/backoff. Returns the CMMS work order dict.

    Retries transport errors and 5xx; a 4xx fails immediately as CmmsRejected.
    Raises CmmsUnavailable if the CMMS stays unreachable across all attempts.
    """
    owns_client = client is None
    client = client or _make_client()
    headers = {"Idempotency-Key": idempotency_key}
    last_err: Exception | None = None
    try:
        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.post("/api/workorders", json=payload, headers=headers)
                if resp.status_code >= 500:
                    last_err = httpx.HTTPStatusError(
                        f"CMMS {resp.status_code}", request=resp.request, response=resp)
                    raise last_err
                if resp.status_code >= 400:
                    raise CmmsRejected(f"CMMS rejected work order: {resp.status_code} {resp.text}")
                return resp.json()
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                last_err = e
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(BACKOFF_BASE_S * (2 ** attempt))
        raise CmmsUnavailable(f"CMMS unreachable after {MAX_RETRIES} attempts: {last_err}")
    finally:
        if owns_client:
            await client.aclose()
