"""Triage agent orchestrator.

Given an anomaly, run a bounded tool-calling loop (live LLM or mock policy),
combine the LLM's root-cause hypothesis with the deterministic priority
formula, and persist a TriageCase in `pending_review` — never beyond it.
The human planner owns every state after that.
"""

import json
import re

from sqlalchemy.orm import Session

from ..audit import audit
from ..detector import render_context
from ..models import Anomaly, Machine, TriageCase, utcnow
from ..priority import apply_adjustment, compute_priority
from . import tools as T
from .calibration import calibrate
from .llm import MockLLM, chat, llm_mode, llm_model

SYSTEM_PROMPT = """You are a predictive-maintenance triage assistant for a factory.
An anomaly was detected on a machine. Investigate it with the tools, then output
your final answer as a single JSON object (no markdown) with keys:
root_cause (string), confidence (0-1), explanation (plain language a floor
technician understands, citing the historical work orders you used),
recommended_actions (array of strings), cited_work_orders (array of work order ids),
priority_adjustment (integer -1, 0 or 1 relative to the formula-computed priority),
adjustment_justification (string).
Rules: you only recommend — never instruct direct machine control. Base your
hypothesis on historical evidence; if history has no match, say so and lower
confidence. Always search maintenance history before answering.
The signal context reports what every metric was doing, not just the one that
breached. A failure is identified by the pattern across signals — which are
drifting, which are erratic, which are steady — so weigh all of them against
the symptoms recorded in past work orders before choosing a cause."""

MAX_STEPS = 8

_FENCED_JSON = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json(content: str) -> dict | None:
    """Recover the final answer object from a model reply.

    Models routinely ignore 'no markdown' and wrap the object in a fence, a
    prose preamble ("Based on my investigation..."), or both. The object itself
    is usually valid, so parse around the packaging rather than discard a good
    answer. Returns None only when there is genuinely no object to be had.
    """
    if not content:
        return None
    content = content.strip()

    try:
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    fenced = _FENCED_JSON.search(content)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    # Last resort: decode the first object and ignore any trailing prose.
    start = content.find("{")
    if start != -1:
        try:
            parsed, _ = json.JSONDecoder().raw_decode(content[start:])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return None


def _dispatch_tool(db: Session, name: str, args: dict) -> dict:
    if name == "get_machine_info":
        return T.get_machine_info(db, args["machine_id"])
    if name == "get_recent_telemetry":
        return T.get_recent_telemetry(db, args["machine_id"], int(args.get("n", 20)))
    if name == "search_maintenance_history":
        return T.search_maintenance_history(
            db, args["machine_type"], args["keywords"], args.get("machine_id"))
    return {"error": f"unknown tool {name}"}


def run_triage(db: Session, anomaly_id: int) -> TriageCase:
    from ..llm_budget import live_allowed

    anomaly = db.get(Anomaly, anomaly_id)
    machine = db.get(Machine, anomaly.machine_id)
    mode, model = llm_mode(), llm_model()
    if mode == "live" and not live_allowed(db):
        # Hard daily spend cap: degrade to the deterministic policy rather than
        # stall the queue. The case is honestly marked mock.
        mode = "mock"

    ctx = {
        "machine_id": machine.id, "machine_type": machine.type,
        "metric": anomaly.metric, "severity": anomaly.severity,
    }
    context_block = render_context(
        json.loads(anomaly.context_json or "{}"), anomaly.metric)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"Anomaly on machine {machine.id} ({machine.name}, type {machine.type}, "
            f"criticality {machine.criticality}/5, location {machine.location}):\n"
            f"{anomaly.description}\nSeverity: {anomaly.severity}.\n"
            f"{context_block}\n\nInvestigate and triage."
        )},
    ]
    trace: list[dict] = [{"step": "anomaly", "detail": anomaly.description,
                          "ts": utcnow().isoformat()}]
    mock = MockLLM(ctx) if mode == "mock" else None
    answer: dict | None = None
    cited_history: list[dict] = []

    for _ in range(MAX_STEPS):
        if mock:
            msg = mock.chat(messages, T.TOOL_SCHEMAS)
        else:
            try:
                msg = chat(messages, T.TOOL_SCHEMAS)
            except Exception as exc:
                # A live-model failure (bad key, provider outage, timeout) must
                # not lose the case: fall back to the deterministic policy and
                # say so in the trace. Silently raising here meant no case, no
                # budget movement, and nothing for the planner to review.
                trace.append({"step": "llm_fallback", "ts": utcnow().isoformat(),
                              "detail": f"live LLM call failed ({type(exc).__name__}: "
                                        f"{str(exc)[:120]}) — continuing with the "
                                        f"deterministic mock policy"})
                mode = "mock"
                mock = MockLLM(ctx)
                messages = messages[:2]  # restart cleanly from system+user
                msg = mock.chat(messages, T.TOOL_SCHEMAS)
        messages.append(msg)

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            content = msg.get("content") or ""
            answer = _extract_json(content)
            if answer is None:
                answer = {"root_cause": "Agent returned unstructured output", "confidence": 0.2,
                          "explanation": content, "recommended_actions": [],
                          "cited_work_orders": [], "priority_adjustment": 0,
                          "adjustment_justification": ""}
            break

        for tc in tool_calls:
            name = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"] or "{}")
            result = _dispatch_tool(db, name, args)
            if name == "search_maintenance_history":
                cited_history = result.get("matches", [])
            trace.append({"step": "tool_call", "tool": name, "args": args,
                          "result_summary": _summarize(result), "ts": utcnow().isoformat()})
            messages.append({"role": "tool", "tool_call_id": tc["id"],
                             "name": name, "content": json.dumps(result)})

    if answer is None:
        answer = {"root_cause": "Agent did not converge within step budget", "confidence": 0.1,
                  "explanation": "Escalate to a human planner for manual triage.",
                  "recommended_actions": ["Manual triage required"], "cited_work_orders": [],
                  "priority_adjustment": 0, "adjustment_justification": ""}

    recurrence = T.count_recurrences(db, machine.id, anomaly.metric)
    safety = any(m.get("safety_related") for m in cited_history[:3])
    breakdown = compute_priority(machine.criticality, anomaly.severity, recurrence, safety)
    adj = int(answer.get("priority_adjustment") or 0)
    final_priority = apply_adjustment(breakdown["priority"], adj)
    breakdown["agent_adjustment"] = adj
    breakdown["agent_justification"] = answer.get("adjustment_justification", "")
    breakdown["final_priority"] = final_priority

    # Business exposure, computed alongside the priority but NOT part of its
    # score (the formula stays the four governance factors, unchanged). Worst
    # cited precedent sets the expected downtime; the asset's hourly cost turns
    # it into money. Shown on the case and carried into the CMMS work order.
    cited_downtimes = [m.get("downtime_hours") or 0 for m in cited_history[:3]]
    est_downtime_hours = max(cited_downtimes) if any(cited_downtimes) else 4.0
    breakdown["hourly_downtime_cost"] = machine.hourly_downtime_cost
    breakdown["est_downtime_hours"] = est_downtime_hours
    breakdown["est_cost_exposure"] = round(machine.hourly_downtime_cost * est_downtime_hours, 2)

    # Ground the model's self-reported confidence in the evidence behind it. A
    # language model's raw certainty tracks fluency, not whether a matching
    # precedent exists — the SKAB eval showed it confidently wrong on real data.
    # The calibrated value is what the case (and the eval's ECE) actually carry.
    calibration = calibrate(answer.get("confidence"), str(answer.get("root_cause", "")),
                            cited_history)

    cited_ids = set(answer.get("cited_work_orders") or [])
    evidence = {
        "anomaly": {"metric": anomaly.metric, "value": anomaly.value,
                    "threshold": anomaly.threshold, "zscore": anomaly.zscore,
                    "description": anomaly.description},
        # The statistics the agent was shown, kept with the case so a planner
        # reviewing it later sees the same evidence the agent reasoned from.
        "signal_context": json.loads(anomaly.context_json or "{}"),
        "historical_matches": [m for m in cited_history
                               if not cited_ids or m["work_order"] in cited_ids] or cited_history[:3],
        # The agent's own citation list, in its own order. historical_matches
        # above is ordered by the CMMS search ranking, so it cannot answer
        # "which precedent did the agent lead with" — the agent's ordering is
        # a distinct signal and reconstructing it later is impossible.
        "cited_work_orders": [str(w) for w in (answer.get("cited_work_orders") or [])],
        "recurrence_count": recurrence,
        "confidence_calibration": calibration.as_dict(),
    }
    # Carry a compact calibration summary on the breakdown too, so the case list
    # (which does not ship the full evidence payload) can flag an abstaining case.
    breakdown["confidence_calibration"] = {
        "raw": calibration.raw, "calibrated": calibration.calibrated,
        "abstain": calibration.abstain, "reason": calibration.reason,
    }
    trace.append({"step": "final_answer", "ts": utcnow().isoformat(),
                  "detail": f"root_cause='{answer['root_cause']}' "
                            f"confidence={calibration.calibrated} (raw {calibration.raw}, "
                            f"{'ABSTAIN — ' + calibration.reason if calibration.abstain else calibration.reason})"})

    case = TriageCase(
        anomaly_id=anomaly.id, machine_id=machine.id, created_ts=utcnow().isoformat(),
        status="pending_review",
        root_cause=str(answer.get("root_cause", "")),
        confidence=calibration.calibrated,
        priority=final_priority,
        priority_breakdown_json=json.dumps(breakdown),
        recommended_actions_json=json.dumps(answer.get("recommended_actions") or []),
        explanation=str(answer.get("explanation", "")),
        evidence_json=json.dumps(evidence),
        trace_json=json.dumps(trace),
        llm_mode=mode, llm_model=model if mode == "live" else "deterministic-mock",
    )
    db.add(case)
    anomaly.status = "triaged"
    db.commit()
    audit(db, "agent", "case_created", "case", case.id, {
        "machine_id": machine.id, "priority": final_priority,
        "confidence": case.confidence, "confidence_raw": calibration.raw,
        "abstain": calibration.abstain, "llm_mode": mode,
    })
    return case


def _summarize(result: dict) -> str:
    if "readings" in result:
        return f"{len(result['readings'])} readings returned"
    if "matches" in result:
        return f"{len(result['matches'])} work orders matched: " + \
               ", ".join(m["work_order"] for m in result["matches"])
    return json.dumps(result)[:200]
