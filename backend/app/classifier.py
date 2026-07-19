"""Deterministic fault-signature classifier.

This is a small, auditable layer of encoded physics between detection and the
language-model agent.  It does not learn from the evaluation labels.  Instead,
it compares the detector's already-computed window statistics with the failure
signatures documented in the seeded maintenance history.

The thresholds are intentionally few and hand-set.  Once this project has
recordings from more testbeds, they should be cross-validated across assets --
never fitted to these five replay episodes and then reported as general truth.
"""

from __future__ import annotations

import math
import re
from typing import Any

from .ml_classifier import classify_restriction


ROLE_BY_SIGNAL = {
    "vibration_mm_s": "vibration",
    "vibration_g": "vibration",
    "vibration_rms_g": "vibration",
    "flow_lpm": "flow",
    "pressure_kpa": "pressure",
    "pressure_bar": "pressure",
    "current_a": "load",
    "rpm": "load",
    "temperature_c": "temp",
    "temp_motor_c": "temp",
    "temp_fluid_c": "fluid_temp",
}

CLASSES = (
    "bearing_wear",
    "overheat",
    "pressure_loss",
    "cavitation",
    "rotor_imbalance",
    "suction_restriction",
    "discharge_restriction",
)

# A top score below this is not enough evidence to name a class.  Likewise, a
# narrow lead is reported as ambiguity rather than resolved with a tie-break.
SCORE_FLOOR = 0.56
SEPARATION_MARGIN = 0.07


def _number(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return result if math.isfinite(result) else 0.0


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _strength(value: float, starts: float, full: float) -> float:
    """0 below ``starts``, 1 at ``full``; linear only for readability."""
    if full <= starts:
        return float(value >= full)
    return _clamp((value - starts) / (full - starts))


def _features(signal_context: dict, signals: list[dict]) -> dict[str, dict]:
    declared = {str(s.get("key")) for s in (signals or []) if s.get("key")}
    roles: dict[str, dict] = {}
    for key, raw in (signal_context or {}).items():
        if declared and key not in declared:
            continue
        role = ROLE_BY_SIGNAL.get(key)
        if role is None or not isinstance(raw, dict):
            continue
        mean = _number(raw.get("mean"))
        drift = _number(raw.get("drift"))
        span = abs(_number(raw.get("range")))
        # Range, unlike mean, remains meaningful for pressure_bar around zero.
        rel_drift = _clamp(drift / max(0.5 * span, 1e-9), -1.0, 1.0)
        drift_pct = None if abs(mean) < 1e-6 else 100.0 * drift / abs(mean)
        roles[role] = {
            "key": key,
            "mean": mean,
            "drift": drift,
            "drift_pct": drift_pct,
            "rel_drift": rel_drift,
            "volatility_pct": max(0.0, _number(raw.get("volatility_pct"))),
            "range": span,
            "n": int(_number(raw.get("n"))),
        }
    return roles


def _up(feature: dict | None) -> float:
    return _strength((feature or {}).get("rel_drift", 0.0), 0.10, 0.50)


def _down(feature: dict | None) -> float:
    return _strength(-(feature or {}).get("rel_drift", 0.0), 0.10, 0.50)


def _steady(feature: dict | None) -> float:
    if not feature:
        return 0.0
    return 1.0 - _strength(abs(feature["rel_drift"]), 0.25, 0.60)


def _volatile(feature: dict | None, starts: float, full: float) -> float:
    return _strength((feature or {}).get("volatility_pct", 0.0), starts, full)


def _material_up(feature: dict | None, pct_starts: float, pct_full: float) -> float:
    """Direction plus a non-trivial change vs the window operating point."""
    pct = abs((feature or {}).get("drift_pct") or 0.0)
    return _up(feature) * _strength(pct, pct_starts, pct_full)


def _material_down(feature: dict | None, pct_starts: float, pct_full: float) -> float:
    pct = abs((feature or {}).get("drift_pct") or 0.0)
    return _down(feature) * _strength(pct, pct_starts, pct_full)


def _describe(role: str, feature: dict | None) -> str:
    if not feature:
        return f"{role} unavailable"
    rel = feature["rel_drift"]
    if rel > 0.10:
        direction = "rising"
    elif rel < -0.10:
        direction = "falling"
    else:
        direction = "held"
    pct = feature.get("drift_pct")
    change = f"{pct:+.1f}% window drift" if pct is not None else f"relative drift {rel:+.2f}"
    return (
        f"{role} {direction} ({change}, normalized {rel:+.2f}, "
        f"volatility {feature['volatility_pct']:.1f}%)"
    )


def classify_signature(signal_context: dict, signals: list[dict], machine_type: str,
                       source: str) -> dict:
    """Rank committed physical signatures from detector window statistics.

    ``source`` is retained in the public interface because a replay/testbed
    signal roster is materially richer than the synthetic fleet's.  The actual
    disambiguation is still made from observable roles (especially ``flow``),
    not from a hidden dataset label.
    """
    f = _features(signal_context, signals)
    vibration, flow = f.get("vibration"), f.get("flow")
    pressure, load, temp = f.get("pressure"), f.get("load"), f.get("temp")
    has_flow = flow is not None

    vibration_activity = max(
        _material_up(vibration, 1.5, 8.0), _volatile(vibration, 4.0, 16.0))
    pressure_instability = _volatile(pressure, 5.0 if not has_flow else 20.0,
                                     11.0 if not has_flow else 60.0)
    flow_instability = max(
        _material_up(flow, 1.0, 12.0), _volatile(flow, 5.0, 20.0))

    scores = {name: 0.0 for name in CLASSES}

    # A rising vibration signature means imbalance on the instrumented real
    # pump, but bearing/mechanical wear on the synthetic assets with no flow
    # channel. Pressure motion separates synthetic cavitation from wear.
    if has_flow:
        scores["rotor_imbalance"] = (
            0.55 * vibration_activity + 0.225 * _steady(flow) +
            0.225 * _steady(pressure)
        )
    else:
        scores["bearing_wear"] = (
            0.70 * vibration_activity + 0.15 * _material_up(temp, 1.0, 6.0) +
            0.15 * _steady(pressure)
        )

    scores["overheat"] = (
        0.90 * _material_up(temp, 1.0, 6.0) + 0.10 * _steady(vibration)
    )
    scores["pressure_loss"] = 0.88 * _down(pressure) + 0.12 * _steady(vibration)

    if has_flow:
        # A noisy near-zero pressure channel is not enough by itself: require a
        # flow surge/oscillation, then use pressure drop/jitter as corroboration.
        scores["cavitation"] = (
            0.62 * flow_instability +
            0.23 * max(_down(pressure), pressure_instability) +
            0.15 * vibration_activity
        )
    elif machine_type == "pump":
        scores["cavitation"] = (
            0.72 * vibration_activity + 0.28 * pressure_instability
        )

    # Restriction signatures share flow/load fall. Pressure direction is the
    # only short-window separator, so neither class gets a large head start.
    shared_restriction = (
        0.45 * _material_down(flow, 1.0, 8.0) +
        0.20 * _down(load) + 0.10 * _steady(vibration)
    )
    scores["suction_restriction"] = shared_restriction + 0.25 * _down(pressure)
    scores["discharge_restriction"] = shared_restriction + 0.25 * _steady(pressure)

    ranked = sorted(scores.items(), key=lambda item: (-item[1], CLASSES.index(item[0])))
    top_name, top_score = ranked[0]
    runner_up = ranked[1][1]
    below_floor = top_score < SCORE_FLOOR
    ambiguous = top_score - runner_up < SEPARATION_MARGIN
    abstain = below_floor or ambiguous
    predicted = None if abstain else top_name
    confidence = min(top_score, 0.49) if ambiguous else top_score

    evidence: list[str] = []
    if top_name in ("rotor_imbalance", "bearing_wear"):
        evidence.append(_describe("vibration", vibration))
        evidence.append(
            f"flow and pressure {'held' if has_flow and _steady(flow) > 0.5 and _steady(pressure) > 0.5 else 'did not both hold'}"
            if has_flow else _describe("temperature", temp)
        )
    elif top_name == "cavitation":
        evidence.extend([_describe("flow", flow), _describe("pressure", pressure)])
        if vibration:
            evidence.append(_describe("vibration", vibration))
    elif top_name in ("suction_restriction", "discharge_restriction"):
        evidence.extend([
            _describe("flow", flow), _describe("load", load), _describe("pressure", pressure),
        ])
    elif top_name == "overheat":
        evidence.append(_describe("temperature", temp))
    elif top_name == "pressure_loss":
        evidence.append(_describe("pressure", pressure))

    if not f:
        evidence = ["No recognized signal roles were available for signature analysis."]
    elif ambiguous:
        evidence.append(
            f"Top signatures were separated by only {top_score - runner_up:.2f}; "
            "the classifier abstained rather than resolve a weak tie."
        )
    elif below_floor:
        if top_name in ("suction_restriction", "discharge_restriction"):
            evidence.append(
                "Restriction-family evidence is present, but suction vs discharge is "
                "low-separability in this window; the classifier abstained."
            )
        else:
            evidence.append(
                f"Strongest signature scored {top_score:.2f}, below the {SCORE_FLOOR:.2f} "
                "evidence floor; the classifier abstained."
            )

    result = {
        "predicted": predicted,
        "confidence": round(_clamp(confidence), 2),
        "ranked": [(name, round(_clamp(score), 3)) for name, score in ranked],
        "evidence": evidence,
        "abstain": abstain,
        "layer": "deterministic_signature",
        "ml_analysis": None,
    }

    # The trained layer is intentionally narrower than the taxonomy. It may
    # resolve only the suction/discharge pair, and only on the exact real SKAB
    # signal contract it was trained on. Source is a routing guard, never an
    # answer proxy; the model still decides entirely from observed features.
    # On this testbed the hand-built scores can put rotor/cavitation above the
    # restriction pair even when flow is the breached metric. The learned OOD
    # gate is what decides whether the context belongs to its narrow family;
    # requiring the same weak ranking first would prevent the ML layer from
    # ever seeing the hard cases it was built for.
    if source == "replay":
        ml = classify_restriction(signal_context)
        result["ml_analysis"] = ml
        if not abstain:
            # The rules already own a clear non-restriction class. Retain the
            # OOD result as auditable routing evidence without allowing the
            # narrow model to compete outside its job.
            return result
        if ml["abstain"]:
            result["evidence"].append(
                "Trained restriction classifier also abstained: " + ml["ood_reason"]
            )
        else:
            other = ({"suction_restriction", "discharge_restriction"}
                     - {ml["predicted"]}).pop()
            result.update({
                "predicted": ml["predicted"],
                "confidence": round(_clamp(ml["confidence"]), 2),
                "ranked": [
                    (ml["predicted"], round(_clamp(ml["confidence"]), 3)),
                    (other, round(_clamp(1.0 - ml["confidence"]), 3)),
                    *[(name, score) for name, score in result["ranked"]
                      if name not in {"suction_restriction", "discharge_restriction"}],
                ],
                "abstain": False,
                "layer": "trained_restriction_classifier",
                "evidence": [
                    f"Trained grouped SKAB classifier resolved the restriction family as "
                    f"{ml['predicted'].replace('_', ' ')} at {ml['confidence']:.1%}; "
                    f"OOD check: {ml['ood_reason']}.",
                    *result["evidence"][:3],
                ],
            })
    return result


_CLASS_TEXT = {
    "bearing_wear": r"bearing|lubrication|mechanical wear|drive chain|idler roller",
    "overheat": r"overheat|overheating|thermal|cooling fan|coolant flow|coolant filter|cooling system|intercooler|gearbox oil",
    "pressure_loss": r"pressure loss|head loss|mechanical seal|discharge valve|intake filter|unloader|impeller erosion|leak",
    "cavitation": r"cavitation|cavitating|air entrain|air ingress|npsh|suction strainer",
    "rotor_imbalance": r"rotor imbalance|imbalance mass|unbalance|rebalanc|blade fouling",
    "suction_restriction": r"suction restriction|suction line|inlet(?:-side)? valve|partially closed|starving suction|suction starvation",
    "discharge_restriction": r"discharge restriction|outlet valve|throttl|deadhead",
}


def signature_agrees(root_cause: str, predicted: str | None) -> bool | None:
    """Compare a concrete classifier verdict with the agent's stated cause."""
    if not predicted:
        return None
    return bool(re.search(_CLASS_TEXT[predicted], root_cause or "", re.I))
