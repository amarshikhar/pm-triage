"""Deterministic, transparent maintenance-priority scoring.

Priority is a governance decision, so it is computed by an auditable formula
the planner can read — not free-styled by the LLM. The agent may propose a
±1 notch adjustment with a written justification, and even that lands in
front of a human before anything happens.
"""

SEVERITY_POINTS = {"low": 1, "medium": 2, "high": 3}


def compute_priority(criticality: int, severity: str, recurrence_count: int,
                     safety_related: bool) -> dict:
    crit_pts = criticality            # 1..5
    sev_pts = SEVERITY_POINTS.get(severity, 1) * 2   # 2..6
    rec_pts = min(recurrence_count, 3)               # repeat offender bonus, capped
    safety_pts = 4 if safety_related else 0
    score = crit_pts + sev_pts + rec_pts + safety_pts  # 3..18

    if safety_related or score >= 13:
        prio = "P1"
    elif score >= 10:
        prio = "P2"
    elif score >= 7:
        prio = "P3"
    else:
        prio = "P4"

    return {
        "priority": prio,
        "score": score,
        "components": {
            "machine_criticality": crit_pts,
            "anomaly_severity": sev_pts,
            "recurrence": rec_pts,
            "safety_flag": safety_pts,
        },
        "rule": "P1 if safety-related or score>=13; P2 >=10; P3 >=7; else P4",
    }


def apply_adjustment(base_priority: str, adjustment: int) -> str:
    """Apply the agent's proposed notch adjustment (+1 = more urgent, -1 = less).

    Clamped to one notch and to the P1..P4 range; a P1 produced by the safety
    flag or score can never be downgraded by the agent.
    """
    order = ["P1", "P2", "P3", "P4"]
    adjustment = max(-1, min(1, adjustment))
    if base_priority == "P1" and adjustment < 0:
        return "P1"
    idx = order.index(base_priority) - adjustment  # +1 urgency moves toward P1
    return order[max(0, min(3, idx))]
