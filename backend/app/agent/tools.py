"""Tools the triage agent can call. Every call is logged into the case trace."""

from sqlalchemy.orm import Session

from ..models import Machine, MaintenanceLog, TelemetryReading, TriageCase


def get_machine_info(db: Session, machine_id: str) -> dict:
    m = db.get(Machine, machine_id)
    if not m:
        return {"error": f"unknown machine {machine_id}"}
    return {"id": m.id, "name": m.name, "type": m.type,
            "location": m.location, "criticality": m.criticality,
            "signals": m.signals}


def get_recent_telemetry(db: Session, machine_id: str, n: int = 20) -> dict:
    rows = (
        db.query(TelemetryReading)
        .filter(TelemetryReading.machine_id == machine_id)
        .order_by(TelemetryReading.id.desc())
        .limit(n)
        .all()
    )
    rows.reverse()
    m = db.get(Machine, machine_id)
    return {
        "machine_id": machine_id,
        "signal_units": {s["key"]: s["unit"] for s in (m.signals if m else [])},
        "readings": [{"ts": r.ts, **r.values} for r in rows],
    }


def search_maintenance_history(db: Session, machine_type: str, keywords: str,
                               machine_id: str | None = None, limit: int = 5) -> dict:
    """Keyword-overlap search over the legacy CMMS work orders.

    Simple scored retrieval (term overlap on failure mode / symptoms /
    root cause, boosted for same machine) — good enough for a mock CMMS and
    fully explainable; swap for embedding search against the real system.
    """
    terms = {t.strip().lower() for t in keywords.replace(",", " ").split() if len(t.strip()) > 2}
    results = []
    for log in db.query(MaintenanceLog).filter(MaintenanceLog.machine_type == machine_type).all():
        haystack = f"{log.failure_mode} {log.symptoms} {log.root_cause}".lower()
        score = sum(1 for t in terms if t in haystack)
        if machine_id and log.machine_id == machine_id:
            score += 2
        if score > 0:
            results.append((score, log))
    results.sort(key=lambda x: (-x[0], x[1].date))
    return {
        "query": keywords,
        "matches": [
            {"work_order": log.id, "machine_id": log.machine_id, "date": log.date,
             "record_type": log.record_type,
             "failure_mode": log.failure_mode, "symptoms": log.symptoms,
             "root_cause": log.root_cause, "action_taken": log.action_taken,
             "downtime_hours": log.downtime_hours, "safety_related": bool(log.safety_related),
             "match_score": score}
            for score, log in results[:limit]
        ],
    }


def count_recurrences(db: Session, machine_id: str, metric: str) -> int:
    """Prior triage cases on the same machine+metric — the repeat-offender signal."""
    from ..models import Anomaly
    return (
        db.query(TriageCase)
        .join(Anomaly, TriageCase.anomaly_id == Anomaly.id)
        .filter(TriageCase.machine_id == machine_id, Anomaly.metric == metric)
        .count()
    )


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_machine_info",
            "description": "Get catalog data for a machine: type, location, business criticality (1-5).",
            "parameters": {"type": "object", "properties": {
                "machine_id": {"type": "string"}}, "required": ["machine_id"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_telemetry",
            "description": "Get the last N telemetry readings (the machine's own signal set, with units) to see the trend shape.",
            "parameters": {"type": "object", "properties": {
                "machine_id": {"type": "string"},
                "n": {"type": "integer", "default": 20}}, "required": ["machine_id"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_maintenance_history",
            "description": "Search historical work orders (legacy CMMS) for similar failures on this machine type. Use symptom keywords like 'vibration rising temperature'.",
            "parameters": {"type": "object", "properties": {
                "machine_type": {"type": "string"},
                "keywords": {"type": "string"},
                "machine_id": {"type": "string"}}, "required": ["machine_type", "keywords"]},
        },
    },
]
