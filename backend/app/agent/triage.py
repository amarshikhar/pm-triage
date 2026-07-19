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
from ..classifier import classify_signature, signature_agrees
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
the symptoms recorded in past work orders before choosing a cause.
You may also receive a classifier verdict. A concrete verdict owns fault
classification; your job is to retrieve the matching precedent, explain the
evidence, and recommend actions. Do not replace it with another class merely
because keyword retrieval ranked a different work order. If the classifier
abstains, do not turn its weak ranking into certainty."""

MAX_STEPS = 8

_CLASSIFIER_ACTIONS = {
    "suction_restriction": [
        "Inspect inlet valve position and suction-side blockage",
        "Verify available NPSH and flow with an independent measurement",
        "Have the planner confirm findings before changing the valve lineup",
    ],
    "discharge_restriction": [
        "Inspect outlet valve position and discharge-side blockage",
        "Verify flow and pressure with an independent measurement",
        "Have the planner confirm findings before changing the valve lineup",
    ],
}

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
    from ..llm_budget import finish_live_call, reserve_live_call

    anomaly = db.get(Anomaly, anomaly_id)
    machine = db.get(Machine, anomaly.machine_id)
    mode, model = llm_mode(), llm_model()

    ctx = {
        "machine_id": machine.id, "machine_type": machine.type,
        "metric": anomaly.metric, "severity": anomaly.severity,
    }
    signal_stats = json.loads(anomaly.context_json or "{}")
    signature_analysis = classify_signature(
        signal_stats, machine.signals, machine.type, machine.source)
    ctx["signature_prediction"] = signature_analysis["predicted"]
    context_block = render_context(signal_stats, anomaly.metric)
    if signature_analysis["abstain"]:
        leaders = ", ".join(name.replace("_", " ")
                            for name, _ in signature_analysis["ranked"][:2])
        signature_prior = (
            "Signature analysis (deterministic) abstained: no separable class "
            f"({leaders} were closest). Evidence: " +
            " ".join(signature_analysis["evidence"])
        )
    else:
        signature_prior = (
            "Signature analysis (deterministic) suggests: "
            f"{signature_analysis['predicted'].replace('_', ' ')} "
            f"({signature_analysis['confidence']:.0%}) because " +
            " ".join(signature_analysis["evidence"])
        )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"Anomaly on machine {machine.id} ({machine.name}, type {machine.type}, "
            f"criticality {machine.criticality}/5, location {machine.location}):\n"
            f"{anomaly.description}\nSeverity: {anomaly.severity}.\n"
            f"{context_block}\n\n{signature_prior}\n\nInvestigate and triage."
        )},
    ]
    trace: list[dict] = [{"step": "anomaly", "detail": anomaly.description,
                          "ts": utcnow().isoformat()},
                         {"step": "signature_analysis", "detail": signature_prior,
                          "ts": utcnow().isoformat()}]
    mock = MockLLM(ctx) if mode == "mock" else None
    answer: dict | None = None
    cited_history: list[dict] = []

    for _ in range(MAX_STEPS):
        if mock:
            msg = mock.chat(messages, T.TOOL_SCHEMAS)
        else:
            call_row = reserve_live_call(db, model)
            if call_row is None:
                trace.append({"step": "llm_budget_fallback", "ts": utcnow().isoformat(),
                              "detail": "paid request or dollar cap reached — continuing "
                                        "with the deterministic mock policy"})
                mode = "mock"
                mock = MockLLM(ctx)
                messages = messages[:2]
                msg = mock.chat(messages, T.TOOL_SCHEMAS)
            else:
                try:
                    msg, usage = chat(messages, T.TOOL_SCHEMAS)
                    finish_live_call(db, call_row, usage)
                except Exception as exc:
                    finish_live_call(db, call_row, error=f"{type(exc).__name__}: {exc}")
                    # A live-model failure (bad key, provider outage, timeout)
                    # must not lose the case: fall back to the deterministic
                    # policy and say so in the trace.
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
            raw_args = tc["function"].get("arguments") or "{}"
            try:
                args = json.loads(raw_args)
                if not isinstance(args, dict):
                    raise ValueError("tool arguments must be a JSON object")
            except (json.JSONDecodeError, ValueError) as exc:
                # Providers occasionally stream/truncate an otherwise valid
                # tool call. Do not lose the case and do not guess at the
                # intended arguments: return a structured tool error so the
                # model can retry on its next bounded turn.
                detail = f"invalid JSON arguments for {name}: {type(exc).__name__}"
                trace.append({"step": "invalid_tool_arguments", "tool": name,
                              "detail": detail, "ts": utcnow().isoformat()})
                messages.append({"role": "tool", "tool_call_id": tc["id"],
                                 "name": name,
                                 "content": json.dumps({
                                     "error": detail,
                                     "instruction": "Retry this tool call with one valid JSON object.",
                                 })})
                continue
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

    # Classification is owned by the dedicated rules/ML layer when it has a
    # concrete, in-distribution verdict. The LLM still owns retrieval,
    # explanation and suggested work, but it cannot silently replace the class
    # with a superficially similar work order. Preserve any violation in the
    # trace and route it safely if the supporting citations are inconsistent.
    draft_root_cause = str(answer.get("root_cause", ""))
    draft_cited_work_orders = [
        str(work_order) for work_order in (answer.get("cited_work_orders") or [])
    ]
    draft_agreement = signature_agrees(
        draft_root_cause, signature_analysis["predicted"])
    if signature_analysis["predicted"] and draft_agreement is False:
        fault = signature_analysis["predicted"]
        display = fault.replace("_", " ")
        trace.append({
            "step": "classification_guard", "ts": utcnow().isoformat(),
            "detail": (
                f"LLM draft '{draft_root_cause}' conflicted with the concrete "
                f"{signature_analysis['layer']} verdict '{display}'; classifier verdict retained"
            ),
        })
        answer["root_cause"] = f"{display} (classifier verdict)"
        answer["confidence"] = signature_analysis["confidence"]
        answer["explanation"] = (
            f"The dedicated classifier identified {display} from the signal window. "
            "The language-model draft disagreed, so its diagnosis and citations were not "
            "used; a planner should verify the class before intervention."
        )
        answer["recommended_actions"] = _CLASSIFIER_ACTIONS.get(
            fault, ["Inspect the named fault family and verify with an independent measurement"])
        answer["cited_work_orders"] = []
        cited_history = []

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
    agreement = signature_agrees(
        str(answer.get("root_cause", "")), signature_analysis["predicted"])
    calibration = calibrate(
        answer.get("confidence"), str(answer.get("root_cause", "")), cited_history,
        signature_agreement=agreement,
        signature_confidence=signature_analysis["confidence"],
        signature_abstained=signature_analysis["abstain"],
    )

    signature_for_case = {
        **signature_analysis,
        "agent_agreement": agreement,
        "agent_draft_root_cause": draft_root_cause,
        "agent_draft_agreement": draft_agreement,
        "operational_agreement": agreement,
    }

    cited_ids = set(answer.get("cited_work_orders") or [])
    evidence = {
        "anomaly": {"metric": anomaly.metric, "value": anomaly.value,
                    "threshold": anomaly.threshold, "zscore": anomaly.zscore,
                    "description": anomaly.description},
        # The statistics the agent was shown, kept with the case so a planner
        # reviewing it later sees the same evidence the agent reasoned from.
        "signal_context": signal_stats,
        "signature_analysis": signature_for_case,
        "historical_matches": [m for m in cited_history
                               if not cited_ids or m["work_order"] in cited_ids] or cited_history[:3],
        # The agent's own citation list, in its own order. historical_matches
        # above is ordered by the CMMS search ranking, so it cannot answer
        # "which precedent did the agent lead with" — the agent's ordering is
        # a distinct signal and reconstructing it later is impossible.
        "cited_work_orders": [str(w) for w in (answer.get("cited_work_orders") or [])],
        "agent_draft_cited_work_orders": draft_cited_work_orders,
        "recurrence_count": recurrence,
        "confidence_calibration": calibration.as_dict(),
    }
    # Carry a compact calibration summary on the breakdown too, so the case list
    # (which does not ship the full evidence payload) can flag an abstaining case.
    breakdown["confidence_calibration"] = {
        "raw": calibration.raw, "calibrated": calibration.calibrated,
        "abstain": calibration.abstain, "reason": calibration.reason,
    }
    breakdown["signature_analysis"] = {
        "predicted": signature_analysis["predicted"],
        "confidence": signature_analysis["confidence"],
        "abstain": signature_analysis["abstain"],
        "agent_agreement": agreement,
        "evidence": signature_analysis["evidence"][:2],
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
