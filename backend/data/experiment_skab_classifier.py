"""Episode-separated SKAB classifier experiment (not production code).

The committed five replay recordings are a frozen holdout. Twenty-two other
physical SKAB runs train four small classical models on the exact detector
context available when the first anomaly fires. The experiment was rejected
for production because its best raw model was 3/5 on holdout and included a
high-confidence suction/discharge confusion.

Usage from backend/:
  pip install -r data/requirements-ml-experiment.txt
  python data/experiment_skab_classifier.py --raw /path/to/SKAB/data
"""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.detector import WINDOW, run_detection
from app.eval.runner import _fresh_db
from app.models import Anomaly, Machine, TelemetryReading, utcnow
from app.seed import seed_if_empty
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

parser = argparse.ArgumentParser()
parser.add_argument("--raw", required=True, type=Path,
                    help="SKAB data directory containing other/, valve1/, valve2/")
args = parser.parse_args()
RAW = args.raw
TRAIN = {
    "rotor_imbalance": [RAW / "other" / f"{i}.csv" for i in [5, 7, 8, 9]],
    "cavitation": [RAW / "other" / "12.csv"],
    "suction_restriction": [RAW / "valve1" / f"{i}.csv" for i in range(16) if i != 2],
    "discharge_restriction": [RAW / "valve2" / f"{i}.csv" for i in [2, 3]],
}
TEST = {
    "rotor_imbalance": [RAW / "other" / "6.csv"],
    "cavitation": [RAW / "other" / "13.csv"],
    "suction_restriction": [RAW / "valve1" / "2.csv"],
    "discharge_restriction": [RAW / "valve2" / f"{i}.csv" for i in [0, 1]],
}
MAP = {
    "vibration_g": "Accelerometer1RMS", "current_a": "Current",
    "pressure_bar": "Pressure", "temp_motor_c": "Temperature",
    "temp_fluid_c": "Thermocouple", "flow_lpm": "Volume Flow RateRMS",
}


def vector(context):
    return [context.get(key, {}).get(stat, 0.0)
            for key in MAP for stat in ("drift", "volatility_pct", "range")]


def extract(path, fault):
    rows = list(csv.DictReader(path.open(), delimiter=";"))
    first = next(i for i, row in enumerate(rows) if float(row["anomaly"]) >= 1)
    start = max(0, first - (WINDOW + 15))
    db = _fresh_db()
    seed_if_empty(db)
    machine = next(m for m in db.query(Machine).all() if m.source == "replay")
    try:
        for tick, row in enumerate(rows[start:start + 400], 1):
            values = {key: float(row[source]) for key, source in MAP.items()}
            reading = TelemetryReading(machine_id=machine.id, ts=utcnow().isoformat(),
                                       values_json=json.dumps(values))
            db.add(reading)
            db.commit()
            if tick <= WINDOW:
                continue
            ids = run_detection(db, machine, reading, ground_truth_fault=fault)
            if ids:
                anomaly = db.get(Anomaly, ids[0])
                return vector(json.loads(anomaly.context_json)), tick, anomaly.metric
    finally:
        db.close()
    return None


def make(group):
    X, y, names = [], [], []
    for fault, paths in group.items():
        for path in paths:
            result = extract(path, fault)
            print(fault, path.relative_to(RAW), None if result is None else result[1:])
            if result:
                X.append(result[0]); y.append(fault); names.append(str(path.relative_to(RAW)))
    return X, y, names


X, y, _ = make(TRAIN)
Xt, yt, names = make(TEST)
print("train samples", len(X), "test samples", len(Xt))
models = [
    ("rf", RandomForestClassifier(n_estimators=500, class_weight="balanced",
                                   random_state=7, max_features=0.7)),
    ("extra", ExtraTreesClassifier(n_estimators=500, class_weight="balanced",
                                    random_state=7, max_features=0.8)),
    ("log", make_pipeline(StandardScaler(), LogisticRegression(
        class_weight="balanced", max_iter=5000, C=0.3))),
    ("svc", make_pipeline(StandardScaler(), SVC(
        class_weight="balanced", probability=True, C=0.5, random_state=7))),
]
for name, model in models:
    model.fit(X, y)
    print("\n", name)
    correct = 0
    for source, truth, prediction, probabilities in zip(
            names, yt, model.predict(Xt), model.predict_proba(Xt)):
        correct += prediction == truth
        print(source, truth, prediction, round(max(probabilities), 3),
              {c: round(float(p), 2) for c, p in zip(model.classes_, probabilities)})
    print(f"holdout top-1: {correct}/{len(yt)} = {100 * correct / len(yt):.1f}%")
