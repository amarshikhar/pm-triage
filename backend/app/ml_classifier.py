"""Optional trained classifier for the genuinely overlapping SKAB faults.

The production model has one deliberately narrow job: distinguish suction-
side from discharge-side restriction after the deterministic physics layer has
identified that family but cannot separate the two members.  The checked-in
artifact also contains a learned IsolationForest novelty model and an ID-only
calibrated acceptance threshold. Unknown feature rosters never reach pickle
loading or inference; they are schema-OOD and abstain.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np


MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "models" / "skab_restriction.joblib"

SIGNAL_KEYS = (
    "vibration_g", "current_a", "pressure_bar", "temp_motor_c",
    "temp_fluid_c", "flow_lpm",
)
STATS = (
    "mean", "drift", "volatility_pct", "range", "first_mean", "last_mean",
    "delta", "delta_pct", "slope", "median", "mad", "derivative_std",
)
FEATURE_NAMES = tuple(f"{signal}.{stat}" for signal in SIGNAL_KEYS for stat in STATS)


def feature_vector(context: dict[str, dict[str, Any]]) -> np.ndarray | None:
    """Return the exact ordered training vector, or ``None`` on roster drift."""
    if not all(key in context for key in SIGNAL_KEYS):
        return None
    values: list[float] = []
    try:
        for signal in SIGNAL_KEYS:
            row = context[signal]
            values.extend(float(row[stat]) for stat in STATS)
    except (KeyError, TypeError, ValueError):
        return None
    vector = np.asarray(values, dtype=float)
    return vector if np.isfinite(vector).all() else None


@lru_cache(maxsize=1)
def load_bundle() -> dict | None:
    if not MODEL_PATH.exists():
        return None
    bundle = joblib.load(MODEL_PATH)
    if tuple(bundle.get("feature_names", ())) != FEATURE_NAMES:
        raise RuntimeError("trained classifier feature contract does not match runtime")
    return bundle


def classify_restriction(context: dict[str, dict[str, Any]]) -> dict:
    """Classify the hard restriction pair with calibrated abstention metadata."""
    vector = feature_vector(context)
    if vector is None:
        return {
            "predicted": None, "abstain": True, "confidence": 0.0,
            "ood": True, "ood_reason": "unsupported signal roster or missing ML features",
            "model": "skab-restriction-unavailable",
        }
    bundle = load_bundle()
    if bundle is None:
        return {
            "predicted": None, "abstain": True, "confidence": 0.0,
            "ood": True, "ood_reason": "trained model artifact is not installed",
            "model": "skab-restriction-unavailable",
        }

    X = vector.reshape(1, -1)
    novelty_score = float(bundle["ood_model"].decision_function(X)[0])
    novelty_threshold = float(bundle["ood_threshold"])
    is_ood = novelty_score < novelty_threshold

    raw_probs = bundle["classifier"].predict_proba(X)[0]
    raw_discharge = float(raw_probs[list(bundle["classifier"].classes_).index(
        "discharge_restriction")])
    calibrated_discharge = float(bundle["probability_calibrator"].predict(
        [raw_discharge])[0])
    if calibrated_discharge >= 0.5:
        predicted = "discharge_restriction"
        confidence = calibrated_discharge
    else:
        predicted = "suction_restriction"
        confidence = 1.0 - calibrated_discharge

    confidence_threshold = float(bundle["confidence_threshold"])
    abstain = is_ood or confidence < confidence_threshold
    reasons = []
    if is_ood:
        reasons.append(
            f"learned novelty score {novelty_score:.3f} is below calibrated "
            f"ID threshold {novelty_threshold:.3f}"
        )
    if confidence < confidence_threshold:
        reasons.append(
            f"calibrated class confidence {confidence:.3f} is below acceptance "
            f"threshold {confidence_threshold:.3f}"
        )
    return {
        "predicted": None if abstain else predicted,
        "candidate": predicted,
        "abstain": abstain,
        "confidence": round(confidence if not is_ood else min(confidence, 0.49), 3),
        "raw_discharge_probability": round(raw_discharge, 4),
        "calibrated_discharge_probability": round(calibrated_discharge, 4),
        "ood": is_ood,
        "ood_score": round(novelty_score, 4),
        "ood_threshold": round(novelty_threshold, 4),
        "ood_reason": "; ".join(reasons) if reasons else "within trained distribution",
        "model": bundle["model_name"],
        "training_version": bundle["training_version"],
    }

