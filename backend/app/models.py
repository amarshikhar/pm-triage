import json
from datetime import datetime, timezone

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Machine(Base):
    __tablename__ = "machines"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)  # cnc_mill | compressor | pump | conveyor
    location: Mapped[str] = mapped_column(String)
    criticality: Mapped[int] = mapped_column(Integer)  # 1 (low) .. 5 (line-down)

    # Where this machine's telemetry comes from: "simulated" (synthetic feed)
    # or "replay" (recorded real-world dataset episodes).
    source: Mapped[str] = mapped_column(String, default="simulated")

    # The machine's signal set — ordered [{key, label, unit}]. Different assets
    # expose different tags (a historian does not have four fixed columns), so
    # the signal roster is data on the asset, and every consumer (detector,
    # agent tools, UI) reads it from here.
    signals_json: Mapped[str] = mapped_column(Text, default="[]")

    # Absolute alarm limits {signal: [limit, direction]} (+1 breach above,
    # -1 breach below). Simulated machines get engineering limits; replay
    # machines may have none — the relative (z-score) rule covers them.
    limits_json: Mapped[str] = mapped_column(Text, default="{}")

    # Dataset provenance for replay machines ({dataset, url, license, ...});
    # empty for simulated ones. Surfaces as the "real data" badge in the UI.
    dataset_json: Mapped[str] = mapped_column(Text, default="{}")

    @property
    def signals(self) -> list[dict]:
        return json.loads(self.signals_json or "[]")

    @property
    def limits(self) -> dict:
        return json.loads(self.limits_json or "{}")

    # What an hour of unplanned downtime on this asset costs the business (USD).
    # Turns the P1..P4 label into money: a P1 on a line-down asset is not just
    # "urgent", it is $X/hr of lost output. Feeds the triage case's exposure
    # estimate and the work order raised in the CMMS. It is a business input, so
    # it lives in the asset catalog, not in code.
    hourly_downtime_cost: Mapped[float] = mapped_column(Float, default=0.0)


class TelemetryReading(Base):
    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey("machines.id"), index=True)
    ts: Mapped[str] = mapped_column(String, index=True)  # ISO-8601 UTC
    # {signal_key: value} for the machine's signal set at this instant. Signal
    # rosters differ per machine (see Machine.signals_json), so readings are a
    # mapping, not fixed columns.
    values_json: Mapped[str] = mapped_column(Text, default="{}")

    @property
    def values(self) -> dict[str, float]:
        return json.loads(self.values_json or "{}")


class Anomaly(Base):
    __tablename__ = "anomalies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey("machines.id"), index=True)
    ts: Mapped[str] = mapped_column(String)
    metric: Mapped[str] = mapped_column(String)
    value: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    zscore: Mapped[float] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String)  # low | medium | high
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="new")  # new | triaged

    # Deterministic per-metric statistics over the detection window: what every
    # OTHER signal was doing when this one breached. Computed from telemetry
    # only. A breach names one metric, but the fault is identified by the shape
    # across all of them — pressure swinging wildly while vibration climbs is
    # cavitation; pressure steady while vibration climbs is wear.
    context_json: Mapped[str] = mapped_column(Text, default="{}")

    # Which simulated fault was active when this excursion was detected, or NULL
    # for organic readings. This is the evaluation label: the simulator already
    # knows the answer, so every anomaly it produces is a free labelled example.
    # NEVER expose this through app.agent.tools — the agent would be reading the
    # answer key, and the accuracy numbers would be meaningless.
    ground_truth_fault: Mapped[str | None] = mapped_column(String, nullable=True)


class LlmCall(Base):
    """One paid provider request, including tool-call turns within a case.

    A triage case can require several completions.  Keeping this ledger separate
    from ``triage_cases`` makes the spend cap count what OpenRouter bills rather
    than pretending one case always equals one request.
    """

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String, index=True)
    model: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, default="started")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str] = mapped_column(Text, default="")


class MaintenanceLog(Base):
    """Historical work orders — the 'legacy CMMS' the agent searches."""

    __tablename__ = "maintenance_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # WO-1042
    machine_id: Mapped[str] = mapped_column(String, index=True)
    machine_type: Mapped[str] = mapped_column(String, index=True)
    date: Mapped[str] = mapped_column(String)
    # "corrective" = a failure event with forensics; "routine" = PM routes,
    # inspections, calibrations, false alarms. Real CMMSes carry this as the
    # order type (SAP PM01/PM02); keyword search alone cannot tell a false
    # vibration alarm from a vibration failure, but this field can.
    record_type: Mapped[str] = mapped_column(String, default="corrective")
    failure_mode: Mapped[str] = mapped_column(String)
    symptoms: Mapped[str] = mapped_column(Text)
    root_cause: Mapped[str] = mapped_column(Text)
    action_taken: Mapped[str] = mapped_column(Text)
    downtime_hours: Mapped[float] = mapped_column(Float)
    safety_related: Mapped[int] = mapped_column(Integer, default=0)


class TriageCase(Base):
    __tablename__ = "triage_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anomaly_id: Mapped[int] = mapped_column(ForeignKey("anomalies.id"))
    machine_id: Mapped[str] = mapped_column(ForeignKey("machines.id"), index=True)
    created_ts: Mapped[str] = mapped_column(String)
    # pending_review | approved | rejected | approved_with_edits
    status: Mapped[str] = mapped_column(String, default="pending_review", index=True)

    root_cause: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    priority: Mapped[str] = mapped_column(String, default="P4")  # P1..P4
    priority_breakdown_json: Mapped[str] = mapped_column(Text, default="{}")
    recommended_actions_json: Mapped[str] = mapped_column(Text, default="[]")
    explanation: Mapped[str] = mapped_column(Text, default="")
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    trace_json: Mapped[str] = mapped_column(Text, default="[]")
    llm_mode: Mapped[str] = mapped_column(String, default="mock")
    llm_model: Mapped[str] = mapped_column(String, default="")

    reviewer: Mapped[str] = mapped_column(String, default="")
    review_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_ts: Mapped[str] = mapped_column(String, default="")

    # Write-back to the system of record. A case only ever earns a work order
    # AFTER a human approves it, so these stay empty until the decision, then
    # record where the action landed in the CMMS.
    #   cmms_sync_status: "" (undecided) | not_applicable (case rejected) |
    #                     synced | failed (CMMS unreachable — retry available) |
    #                     rejected (CMMS refused the payload — retry cannot help)
    cmms_work_order_id: Mapped[str] = mapped_column(String, default="")
    cmms_status: Mapped[str] = mapped_column(String, default="")  # CMMS-side status code
    cmms_sync_status: Mapped[str] = mapped_column(String, default="")

    def as_dict(self, full: bool = False) -> dict:
        d = {
            "id": self.id,
            "anomaly_id": self.anomaly_id,
            "machine_id": self.machine_id,
            "created_ts": self.created_ts,
            "status": self.status,
            "root_cause": self.root_cause,
            "confidence": self.confidence,
            "priority": self.priority,
            "priority_breakdown": json.loads(self.priority_breakdown_json or "{}"),
            "recommended_actions": json.loads(self.recommended_actions_json or "[]"),
            "explanation": self.explanation,
            "llm_mode": self.llm_mode,
            "llm_model": self.llm_model,
            "reviewer": self.reviewer,
            "review_note": self.review_note,
            "reviewed_ts": self.reviewed_ts,
            "cmms_work_order_id": self.cmms_work_order_id,
            "cmms_status": self.cmms_status,
            "cmms_sync_status": self.cmms_sync_status,
        }
        if full:
            d["evidence"] = json.loads(self.evidence_json or "{}")
            d["trace"] = json.loads(self.trace_json or "[]")
        return d


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String, index=True)
    actor: Mapped[str] = mapped_column(String)  # system | agent | human:<name>
    event_type: Mapped[str] = mapped_column(String)
    entity: Mapped[str] = mapped_column(String)
    entity_id: Mapped[str] = mapped_column(String)
    detail: Mapped[str] = mapped_column(Text, default="")
