"""Train the production SKAB restriction classifier and learned OOD gate.

The split is by physical experiment, never by random telemetry row. The five
committed SKAB replays remain a frozen final test. Training uses windows from
the other valve experiments; thresholds are selected only from leave-one-
experiment-out predictions. Same-roster SKAB faults that are outside the
restriction taxonomy are an OOD evaluation set, not classifier training data.

Usage from ``backend/``::

    python data/train_fault_classifier.py --raw /path/to/SKAB/data
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib
import numpy as np
from sklearn.ensemble import ExtraTreesClassifier, IsolationForest, RandomForestClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import balanced_accuracy_score, roc_auc_score

from app.detector import WINDOW, run_detection, signal_context
from app.eval.runner import _fresh_db
from app.ml_classifier import FEATURE_NAMES, feature_vector
from app.models import Anomaly, Machine, TelemetryReading, utcnow
from app.seed import seed_if_empty


MAP = {
    "vibration_g": "Accelerometer1RMS",
    "current_a": "Current",
    "pressure_bar": "Pressure",
    "temp_motor_c": "Temperature",
    "temp_fluid_c": "Thermocouple",
    "flow_lpm": "Volume Flow RateRMS",
}

TRAIN_EPISODES = {
    "suction_restriction": [f"valve1/{i}.csv" for i in range(16) if i != 2],
    "discharge_restriction": ["valve2/2.csv", "valve2/3.csv"],
}
FROZEN_TEST = {
    "suction_restriction": ["valve1/2.csv"],
    "discharge_restriction": ["valve2/0.csv", "valve2/1.csv"],
}
OOD_TEST = [
    "other/1.csv", "other/2.csv", "other/3.csv", "other/4.csv",
    "other/5.csv", "other/6.csv", "other/7.csv", "other/8.csv", "other/9.csv",
    "other/10.csv", "other/11.csv", "other/12.csv", "other/13.csv", "other/14.csv",
]


@dataclass
class Reading:
    values: dict[str, float]


def load_rows(path: Path) -> tuple[list[dict[str, float]], int]:
    raw = list(csv.DictReader(path.open(), delimiter=";"))
    rows = [{key: float(row[source]) for key, source in MAP.items()} for row in raw]
    first = next(i for i, row in enumerate(raw) if float(row["anomaly"]) >= 1)
    return rows, first


def context_at(rows: list[dict[str, float]], end: int) -> dict:
    if end < WINDOW:
        raise ValueError("context needs a complete trailing window")
    history = [Reading(values=row) for row in reversed(rows[end - WINDOW:end])]
    return signal_context(list(MAP), history, Reading(values=rows[end]))


def detection_context(path: Path) -> tuple[dict, int, str]:
    """Replay through the exact production detector and return first context."""
    raw = list(csv.DictReader(path.open(), delimiter=";"))
    first = next(i for i, row in enumerate(raw) if float(row["anomaly"]) >= 1)
    start = max(0, first - (WINDOW + 15))
    db = _fresh_db()
    seed_if_empty(db)
    machine = next(m for m in db.query(Machine).all() if m.id == "PMP-03")
    try:
        for absolute_i, row in enumerate(raw[start:start + 400], start):
            values = {key: float(row[source]) for key, source in MAP.items()}
            reading = TelemetryReading(
                machine_id=machine.id, ts=utcnow().isoformat(),
                values_json=json.dumps(values),
            )
            db.add(reading)
            db.commit()
            if absolute_i - start + 1 <= WINDOW:
                continue
            ids = run_detection(db, machine, reading)
            if ids:
                anomaly = db.get(Anomaly, ids[0])
                return json.loads(anomaly.context_json), absolute_i, anomaly.metric
    finally:
        db.close()
    # Some unrelated OOD experiments do not cross the detector threshold in
    # the bounded replay. They still provide a labelled, full-window OOD point.
    rows, first = load_rows(path)
    end = min(len(rows) - 1, first + WINDOW)
    return context_at(rows, end), end, "labelled_window_fallback"


def training_windows(raw_root: Path):
    X: list[np.ndarray] = []
    y: list[str] = []
    groups: list[str] = []
    trigger_contexts: dict[str, np.ndarray] = {}
    labels: dict[str, str] = {}
    for label, names in TRAIN_EPISODES.items():
        for name in names:
            path = raw_root / name
            rows, first = load_rows(path)
            # Multiple fault-window views improve shape coverage, but every
            # split below holds out the complete physical experiment group.
            stop = min(len(rows) - 1, first + 180)
            for end in range(max(WINDOW, first + 2), stop + 1, 6):
                vector = feature_vector(context_at(rows, end))
                if vector is not None:
                    X.append(vector); y.append(label); groups.append(name)
            trigger, _, _ = detection_context(path)
            trigger_contexts[name] = feature_vector(trigger)
            labels[name] = label
    return np.asarray(X), np.asarray(y), np.asarray(groups), trigger_contexts, labels


def candidates():
    return {
        "extra_trees": ExtraTreesClassifier(
            n_estimators=600, random_state=17, class_weight="balanced",
            max_features=0.65, min_samples_leaf=2, n_jobs=-1,
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=600, random_state=17, class_weight="balanced_subsample",
            max_features=0.7, min_samples_leaf=2, n_jobs=-1,
        ),
    }


def grouped_trigger_oof(model, X, y, groups, trigger_contexts, labels):
    probabilities: dict[str, float] = {}
    predictions: dict[str, str] = {}
    for group in sorted(trigger_contexts):
        keep = groups != group
        fitted = model.__class__(**model.get_params()).fit(X[keep], y[keep])
        vector = trigger_contexts[group].reshape(1, -1)
        proba = fitted.predict_proba(vector)[0]
        discharge = float(proba[list(fitted.classes_).index("discharge_restriction")])
        probabilities[group] = discharge
        predictions[group] = "discharge_restriction" if discharge >= 0.5 else "suction_restriction"
    truth = [labels[group] for group in sorted(trigger_contexts)]
    pred = [predictions[group] for group in sorted(trigger_contexts)]
    return probabilities, predictions, balanced_accuracy_score(truth, pred)


def window_oof_probabilities(model, X, y, groups):
    result = np.zeros(len(y), dtype=float)
    for group in sorted(set(groups)):
        train = groups != group
        test = ~train
        fitted = model.__class__(**model.get_params()).fit(X[train], y[train])
        probs = fitted.predict_proba(X[test])
        result[test] = probs[:, list(fitted.classes_).index("discharge_restriction")]
    return result


def choose_confidence_threshold(probabilities, labels) -> tuple[float, dict]:
    rows = []
    for group in sorted(probabilities):
        prob = probabilities[group]
        pred = "discharge_restriction" if prob >= 0.5 else "suction_restriction"
        rows.append((max(prob, 1 - prob), pred == labels[group]))
    best = None
    for threshold in sorted({0.5, *[round(conf, 6) for conf, _ in rows]}):
        covered = [correct for conf, correct in rows if conf >= threshold]
        if not covered:
            continue
        accuracy = sum(covered) / len(covered)
        candidate = (len(covered), accuracy, -threshold)
        if accuracy >= 0.95 and (best is None or candidate > best[0]):
            best = (candidate, threshold, len(covered), accuracy)
    if best is None:
        return 1.0, {"coverage": 0, "selective_accuracy": None}
    return best[1], {
        "coverage": best[2] / len(rows), "covered_groups": best[2],
        "n_groups": len(rows), "selective_accuracy": best[3],
    }


def ood_threshold_oof(X, groups, trigger_contexts):
    scores: dict[str, float] = {}
    for group in sorted(trigger_contexts):
        keep = groups != group
        model = IsolationForest(
            n_estimators=500, contamination="auto", random_state=29, n_jobs=-1,
        ).fit(X[keep])
        scores[group] = float(model.decision_function(
            trigger_contexts[group].reshape(1, -1))[0])
    # ID-only calibration: target 90% acceptance at the physical-episode level.
    threshold = float(np.quantile(list(scores.values()), 0.10, method="lower"))
    return threshold, scores


def main(raw_root: Path, output: Path, report_path: Path) -> None:
    X, y, groups, trigger_contexts, labels = training_windows(raw_root)
    cv_results = {}
    best_name, best_model, best_score = None, None, -1.0
    for name, model in candidates().items():
        probs, preds, score = grouped_trigger_oof(
            model, X, y, groups, trigger_contexts, labels)
        cv_results[name] = {
            "balanced_accuracy": round(float(score), 4),
            "predictions": {group: {"truth": labels[group], "prediction": preds[group],
                                     "raw_discharge_probability": round(probs[group], 4)}
                            for group in sorted(probs)},
        }
        if score > best_score:
            best_name, best_model, best_score = name, model, score

    raw_window_oof = window_oof_probabilities(best_model, X, y, groups)
    binary_y = (y == "discharge_restriction").astype(int)
    calibrator = IsotonicRegression(out_of_bounds="clip").fit(raw_window_oof, binary_y)
    raw_group_probs, _, _ = grouped_trigger_oof(
        best_model, X, y, groups, trigger_contexts, labels)
    calibrated_group_probs = {
        group: float(calibrator.predict([prob])[0])
        for group, prob in raw_group_probs.items()
    }
    confidence_threshold, confidence_cv = choose_confidence_threshold(
        calibrated_group_probs, labels)
    novelty_threshold, id_scores = ood_threshold_oof(X, groups, trigger_contexts)

    classifier = best_model.fit(X, y)
    ood_model = IsolationForest(
        n_estimators=500, contamination="auto", random_state=29, n_jobs=-1,
    ).fit(X)

    frozen_rows = []
    for truth, names in FROZEN_TEST.items():
        for name in names:
            context, detected_at, metric = detection_context(raw_root / name)
            vector = feature_vector(context).reshape(1, -1)
            raw = float(classifier.predict_proba(vector)[0][
                list(classifier.classes_).index("discharge_restriction")])
            calibrated = float(calibrator.predict([raw])[0])
            candidate = "discharge_restriction" if calibrated >= 0.5 else "suction_restriction"
            novelty = float(ood_model.decision_function(vector)[0])
            accepted = novelty >= novelty_threshold and max(calibrated, 1 - calibrated) >= confidence_threshold
            frozen_rows.append({
                "episode": name, "truth": truth, "candidate": candidate,
                "prediction": candidate if accepted else None, "abstained": not accepted,
                "correct": accepted and candidate == truth,
                "raw_discharge_probability": round(raw, 4),
                "calibrated_discharge_probability": round(calibrated, 4),
                "confidence": round(max(calibrated, 1 - calibrated), 4),
                "ood_score": round(novelty, 4), "ood": novelty < novelty_threshold,
                "detected_row": detected_at, "detected_metric": metric,
            })

    ood_rows = []
    for name in OOD_TEST:
        context, detected_at, metric = detection_context(raw_root / name)
        vector = feature_vector(context).reshape(1, -1)
        novelty = float(ood_model.decision_function(vector)[0])
        ood_rows.append({
            "episode": name, "ood_score": round(novelty, 4),
            "rejected": novelty < novelty_threshold,
            "detected_row": detected_at, "detected_metric": metric,
        })

    # Use leave-one-episode-out ID scores here. Scoring the ID training points
    # with the final fitted novelty model would make AUROC look artificially
    # easy beside genuinely held-out OOD experiments.
    id_eval_scores = [id_scores[group] for group in sorted(trigger_contexts)]
    ood_eval_scores = [row["ood_score"] for row in ood_rows]
    auc = roc_auc_score(
        [1] * len(id_eval_scores) + [0] * len(ood_eval_scores),
        id_eval_scores + ood_eval_scores,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "model_name": f"{best_name}-skab-restriction-v1",
        "training_version": "2026-07-19-grouped-v1",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_names": FEATURE_NAMES,
        "classifier": classifier,
        "probability_calibrator": calibrator,
        "confidence_threshold": confidence_threshold,
        "ood_model": ood_model,
        "ood_threshold": novelty_threshold,
    }
    joblib.dump(bundle, output, compress=3)

    covered = [row for row in frozen_rows if not row["abstained"]]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"dataset": "SKAB v0.9", "source_commit": "b2c0d46c2971dcbfe71e26087b6d231998bb91c2"},
        "split_policy": "physical experiment groups; frozen five replay files never tune model or thresholds",
        "training": {"n_windows": len(X), "n_physical_episodes": len(set(groups)),
                     "class_episode_counts": {label: len(names) for label, names in TRAIN_EPISODES.items()}},
        "model_selection_oof": cv_results,
        "selected_model": best_name,
        "confidence_calibration": {"threshold": confidence_threshold, **confidence_cv},
        "ood_calibration": {
            "method": "IsolationForest; 10th percentile leave-one-episode-out ID score",
            "threshold": round(novelty_threshold, 6),
            "id_group_scores": {key: round(value, 4) for key, value in id_scores.items()},
        },
        "frozen_test": {
            "n": len(frozen_rows), "coverage": len(covered) / len(frozen_rows),
            "selective_accuracy": (sum(row["correct"] for row in covered) / len(covered)) if covered else None,
            "overall_accuracy": sum(row["correct"] for row in frozen_rows) / len(frozen_rows),
            "rows": frozen_rows,
        },
        "same_schema_ood_test": {
            "n": len(ood_rows), "auroc_id_vs_ood": round(float(auc), 4),
            "rejection_rate": sum(row["rejected"] for row in ood_rows) / len(ood_rows),
            "rows": ood_rows,
        },
        "artifact": str(output),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({
        "selected_model": best_name,
        "oof_balanced_accuracy": best_score,
        "confidence_threshold": confidence_threshold,
        "ood_threshold": novelty_threshold,
        "frozen_test": report["frozen_test"],
        "ood_auroc": report["same_schema_ood_test"]["auroc_id_vs_ood"],
        "artifact": str(output),
    }, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).parent / "models" / "skab_restriction.joblib",
    )
    parser.add_argument(
        "--report", type=Path,
        default=Path(__file__).parent / "models" / "skab_restriction_report.json",
    )
    args = parser.parse_args()
    main(args.raw, args.output, args.report)
