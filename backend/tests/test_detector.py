import json

from app.detector import render_context, run_detection, signal_context
from app.models import Anomaly, Machine, TelemetryReading, utcnow


SIM_KEYS = ["temperature_c", "vibration_mm_s", "pressure_kpa", "rpm"]


def _reading(db, machine_id, **overrides):
    vals = {"temperature_c": 55, "vibration_mm_s": 2.5, "pressure_kpa": 300, "rpm": 8000}
    vals.update(overrides)
    r = TelemetryReading(machine_id=machine_id, ts=utcnow().isoformat(),
                         values_json=json.dumps(vals))
    db.add(r)
    db.commit()
    return r


def test_normal_reading_creates_no_anomaly(db):
    m = db.get(Machine, "CNC-01")
    r = _reading(db, m.id)
    assert run_detection(db, m, r) == []


def test_threshold_breach_creates_anomaly_with_explanation(db):
    m = db.get(Machine, "CNC-01")
    for _ in range(10):
        _reading(db, m.id)
    r = _reading(db, m.id, vibration_mm_s=7.2)
    created = run_detection(db, m, r)
    assert len(created) == 1
    a = db.get(Anomaly, created[0])
    assert a.metric == "vibration_mm_s"
    assert a.severity == "high"  # 7.2 vs limit 5.5 is >15% over
    assert "exceeded limit 5.5" in a.description
    assert a.zscore > 3


def test_low_direction_breach(db):
    m = db.get(Machine, "CMP-01")
    r = _reading(db, m.id, temperature_c=70, pressure_kpa=600)
    created = run_detection(db, m, r)
    metrics = {db.get(Anomaly, i).metric for i in created}
    assert "pressure_kpa" in metrics


def test_cooldown_prevents_duplicate_anomalies(db):
    m = db.get(Machine, "CNC-01")
    r1 = _reading(db, m.id, vibration_mm_s=7.0)
    assert len(run_detection(db, m, r1)) == 1
    r2 = _reading(db, m.id, vibration_mm_s=7.5)
    assert run_detection(db, m, r2) == []


# --- signal context ---------------------------------------------------------
#
# A breach names one metric; the fault is identified by the shape across all of
# them. The live eval showed the cost of omitting this: every cavitation case
# was called bearing wear, because both present as rising vibration and nothing
# surfaced the pressure instability that separates them.


def _series(db, machine_id, values):
    return [_reading(db, machine_id, **v) for v in values]


def test_anomaly_stores_context_for_every_metric(db):
    m = db.get(Machine, "PMP-01")
    _series(db, m.id, [{"pressure_kpa": 400 + i} for i in range(8)])
    r = _reading(db, m.id, vibration_mm_s=7.5, pressure_kpa=402)
    created = run_detection(db, m, r)
    ctx = json.loads(db.get(Anomaly, created[0]).context_json)
    assert set(ctx) == {"temperature_c", "vibration_mm_s", "pressure_kpa", "rpm"}
    assert all({"mean", "drift", "volatility_pct", "range"} <= set(v) for v in ctx.values())


def test_volatility_separates_an_erratic_signal_from_a_steady_one(db):
    """The cavitation/bearing-wear discriminator, asserted directly: identical
    rising vibration, but one has pressure swinging underneath it."""
    steady = _series(db, "PMP-01", [{"pressure_kpa": 400 + (i % 2)} for i in range(12)])
    erratic = _series(db, "PMP-02", [{"pressure_kpa": 400 + (40 if i % 2 else -40)}
                                     for i in range(12)])
    last_steady = _reading(db, "PMP-01", pressure_kpa=400)
    last_erratic = _reading(db, "PMP-02", pressure_kpa=440)

    steady_v = signal_context(SIM_KEYS, list(reversed(steady)), last_steady)["pressure_kpa"]
    erratic_v = signal_context(SIM_KEYS, list(reversed(erratic)), last_erratic)["pressure_kpa"]

    assert steady_v["volatility_pct"] < 1.0
    assert erratic_v["volatility_pct"] > 5.0
    assert erratic_v["range"] > steady_v["range"] * 10


def test_drift_separates_a_falling_signal_from_an_erratic_one(db):
    """Volatility alone would confuse a leak with cavitation; drift is what
    tells a one-way march from a swing."""
    falling = _series(db, "PMP-01", [{"pressure_kpa": 420 - 8 * i} for i in range(12)])
    swinging = _series(db, "PMP-02", [{"pressure_kpa": 400 + (40 if i % 2 else -40)}
                                      for i in range(12)])
    f = signal_context(SIM_KEYS, list(reversed(falling)), _reading(db, "PMP-01", pressure_kpa=320))
    s = signal_context(SIM_KEYS, list(reversed(swinging)), _reading(db, "PMP-02", pressure_kpa=400))

    assert f["pressure_kpa"]["drift"] < -20      # a sustained march downward
    assert abs(s["pressure_kpa"]["drift"]) < 20  # swings cancel, no net march


def test_context_reports_facts_not_verdicts(db):
    """The detector must not name faults. It reports what the signals did; the
    agent (and the eval) own the judgement. A leaked verdict here would make
    accuracy self-fulfilling."""
    m = db.get(Machine, "PMP-01")
    _series(db, m.id, [{"pressure_kpa": 400} for _ in range(8)])
    r = _reading(db, m.id, vibration_mm_s=7.5)
    created = run_detection(db, m, r, ground_truth_fault="cavitation")
    blob = db.get(Anomaly, created[0]).context_json
    for fault in ("cavitation", "bearing_wear", "overheat", "pressure_loss"):
        assert fault not in blob


def test_render_context_marks_the_breached_metric(db):
    m = db.get(Machine, "PMP-01")
    _series(db, m.id, [{"pressure_kpa": 400} for _ in range(8)])
    r = _reading(db, m.id, vibration_mm_s=7.5)
    ctx = json.loads(db.get(Anomaly, run_detection(db, m, r)[0]).context_json)
    out = render_context(ctx, "vibration_mm_s")
    assert "vibration_mm_s" in out and "<-- breached" in out
    assert "pressure_kpa" in out, "context must show the non-breaching signals too"
    assert render_context({}, "x") == ""


def test_context_needs_enough_history_to_mean_anything(db):
    """Two points have no meaningful drift or volatility; better to report
    nothing than a number computed from noise."""
    r = _reading(db, "PMP-01")
    assert signal_context(SIM_KEYS, [], r) == {}
