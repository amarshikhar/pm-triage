"""Rule-based anomaly detection.

Deliberately NOT an LLM: detection must be deterministic, cheap, and
explainable to a floor technician ("temperature 96.2C exceeded the 92C limit,
4.1 sigma above the last 30 readings"). The LLM's job starts *after* detection.

Two independent trigger rules, both quotable:

1. **Absolute limit** — an engineering bound from the asset catalog
   (Machine.limits_json): "flow fell below 300 L/min".
2. **Relative excursion** — a robust z-score (median/MAD over the trailing
   window) sustained for several consecutive readings: "flow 4.6 sigma below
   its own recent baseline for 3 readings running". Real equipment runs at
   different operating points day to day (the SKAB pump's healthy flow is
   125 L/min in one run and 32 L/min in another), so a fixed threshold cannot
   see a fault that a departure-from-own-baseline rule catches. Median/MAD
   rather than mean/stdev so the baseline is not dragged by the excursion
   itself.
"""

import json
import statistics
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .audit import audit
from .models import Anomaly, Machine, TelemetryReading, TriageCase, utcnow

WINDOW = 30          # readings used for the rolling baseline
COOLDOWN_MIN = 10    # no duplicate anomaly for same machine+metric within this

# Machines whose next detection bypasses the dedup/cooldown, so a *manually*
# cued fault always surfaces a fresh case in a demo even if one is already open.
# Cleared once a new anomaly is actually raised for that machine.
FORCE_DETECT: set[str] = set()


def force_detect(machine_id: str) -> None:
    FORCE_DETECT.add(machine_id)
Z_LIMIT = 4.0        # robust z magnitude that counts as an excursion
Z_SUSTAIN = 3        # consecutive readings the excursion must persist
MAD_SCALE = 1.4826   # MAD -> sigma-equivalent for a normal distribution


def _severity(value: float, limit: float, direction: int) -> str:
    margin = (value - limit) / abs(limit) * direction if limit else 0.0
    if margin > 0.15:
        return "high"
    if margin > 0.05:
        return "medium"
    return "low"


def _severity_z(z: float) -> str:
    if abs(z) > 8:
        return "high"
    if abs(z) > 6:
        return "medium"
    return "low"


def robust_z(series: list[float], value: float) -> float:
    """(value - median) / (1.4826 * MAD). 0 when the baseline has no spread."""
    if len(series) < 5:
        return 0.0
    med = statistics.median(series)
    mad = statistics.median(abs(x - med) for x in series)
    if mad <= 0:
        # a flat baseline: fall back to stdev, else no spread information
        stdev = statistics.pstdev(series)
        if stdev <= 0:
            return 0.0
        return (value - med) / stdev
    return (value - med) / (MAD_SCALE * mad)


def signal_context(signal_keys: list[str], history: list[TelemetryReading],
                   reading: TelemetryReading) -> dict:
    """What every signal was doing over the window, as plain statistics.

    A threshold breach names a single metric, which is not enough to name a
    fault: rising vibration alone reads as bearing wear whether or not pressure
    is swinging underneath it. The discriminating information is already in the
    telemetry — it just needs computing, which is the detector's job, not the
    model's. An LLM asked to eyeball variance across thirty rows will not.

    Per signal:
      drift      — later-half mean minus earlier-half mean; a sustained march.
      volatility — stdev as a % of mean; how erratic, independent of drift.
      range      — peak-to-peak, the number a technician actually pictures.

    Those two axes separate the failure shapes: pressure drifting down is a
    leak, pressure erratic but not drifting is cavitation, pressure flat while
    vibration climbs is wear. No thresholds and no verdicts here — facts only,
    with the judgement left to the agent.
    """
    series_by_metric = {}
    ordered = list(reversed(history)) + [reading]  # history is newest-first
    rows = [r.values for r in ordered]
    for metric in signal_keys:
        series = [v[metric] for v in rows if metric in v]
        if len(series) < 4:
            continue
        mean = statistics.fmean(series)
        half = len(series) // 2
        drift = statistics.fmean(series[half:]) - statistics.fmean(series[:half])
        stdev = statistics.pstdev(series)
        series_by_metric[metric] = {
            "mean": round(mean, 3),
            "drift": round(drift, 3),
            "volatility_pct": round(100 * stdev / abs(mean), 1) if mean else 0.0,
            "range": round(max(series) - min(series), 3),
            "n": len(series),
        }
    return series_by_metric


def render_context(context: dict, breached_metric: str) -> str:
    """Fixed-width rendering for the agent prompt and the case trace."""
    if not context:
        return ""
    lines = ["Signal context over the detection window "
             "(computed from telemetry, not inferred):"]
    for metric, s in context.items():
        flag = "  <-- breached" if metric == breached_metric else ""
        lines.append(
            f"  {metric:<15} mean {s['mean']:<10} drift {s['drift']:+<9} "
            f"volatility {s['volatility_pct']}%  range {s['range']}{flag}"
        )
    return "\n".join(lines)


def _blocked_metrics(db: Session, machine_id: str) -> set[str]:
    """Metrics under cooldown or with an open case — two queries per machine
    per reading, instead of two per *signal* (which, against a remote Postgres,
    was the dominant cost of a detection tick)."""
    if machine_id in FORCE_DETECT:
        return set()  # manual cue: let the fault through even if a case is open
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=COOLDOWN_MIN)).isoformat()
    recent = {
        m for (m,) in db.query(Anomaly.metric)
        .filter(Anomaly.machine_id == machine_id, Anomaly.ts >= cutoff).all()
    }
    open_cases = {
        m for (m,) in db.query(Anomaly.metric)
        .join(TriageCase, TriageCase.anomaly_id == Anomaly.id)
        .filter(TriageCase.machine_id == machine_id,
                TriageCase.status == "pending_review").all()
    }
    return recent | open_cases


def _raise_anomaly(db: Session, machine: Machine, metric: str, value: float,
                   threshold: float, zscore: float, severity: str, description: str,
                   ground_truth_fault: str | None,
                   history: list[TelemetryReading], reading: TelemetryReading) -> int:
    signal_keys = [s["key"] for s in machine.signals]
    anomaly = Anomaly(
        machine_id=machine.id,
        ts=utcnow().isoformat(),
        metric=metric,
        value=value,
        threshold=threshold,
        zscore=round(zscore, 2),
        severity=severity,
        description=description,
        ground_truth_fault=ground_truth_fault,
        context_json=json.dumps(signal_context(signal_keys, history, reading)),
    )
    db.add(anomaly)
    db.commit()
    audit(db, "system", "anomaly_detected", "anomaly", anomaly.id, {
        "machine_id": machine.id, "metric": metric, "value": value,
        "threshold": threshold, "zscore": anomaly.zscore, "severity": severity,
    })
    return anomaly.id


def run_detection(db: Session, machine: Machine, reading: TelemetryReading,
                  ground_truth_fault: str | None = None) -> list[int]:
    """Check one reading against both rules. Returns new anomaly ids.

    `ground_truth_fault` is the fault label active on this machine (injected
    fault for simulated machines, dataset markup for replayed ones), recorded
    for evaluation only. Detection never reads it — it must stay a pure
    function of the telemetry, or the accuracy measurement is circular.
    """
    created = []
    limits = machine.limits
    values = reading.values
    history = (
        db.query(TelemetryReading)
        .filter(TelemetryReading.machine_id == machine.id)
        .order_by(TelemetryReading.id.desc())
        .limit(WINDOW + 1)
        .all()
    )[1:]  # exclude the reading itself

    past_values = [r.values for r in history]
    blocked = _blocked_metrics(db, machine.id)

    for metric, value in values.items():
        if metric in blocked:
            continue
        past = [v[metric] for v in past_values if metric in v]

        # Rule 1: absolute engineering limit from the asset catalog.
        if metric in limits:
            limit, direction = limits[metric]
            if (value - limit) * direction > 0:
                zscore = 0.0
                if len(past) >= 5:
                    mean = statistics.fmean(past)
                    stdev = statistics.pstdev(past) or 1e-9
                    zscore = (value - mean) / stdev
                created.append(_raise_anomaly(
                    db, machine, metric, value, limit, zscore,
                    _severity(value, limit, direction),
                    f"{metric} = {value} {'exceeded' if direction > 0 else 'fell below'} "
                    f"limit {limit} ({abs(zscore):.1f} sigma vs last {len(past)} readings)",
                    ground_truth_fault, history, reading))
                continue

        # Rule 2: sustained robust excursion from the machine's own baseline.
        if len(past) >= WINDOW // 2:
            baseline = past[Z_SUSTAIN:]  # exclude the freshest readings so the
            z = robust_z(baseline, value)  # excursion can't vouch for itself
            if abs(z) > Z_LIMIT:
                recent = past[:Z_SUSTAIN - 1]  # newest-first
                sustained = all(
                    abs(robust_z(baseline, prev)) > Z_LIMIT for prev in recent
                ) and len(recent) == Z_SUSTAIN - 1
                if sustained:
                    med = statistics.median(baseline)
                    created.append(_raise_anomaly(
                        db, machine, metric, value, round(med, 3), z,
                        _severity_z(z),
                        f"{metric} = {value} sustained {abs(z):.1f} sigma "
                        f"{'above' if z > 0 else 'below'} its rolling baseline "
                        f"(median {med:.3g}, {Z_SUSTAIN} consecutive readings)",
                        ground_truth_fault, history, reading))
    if created:
        FORCE_DETECT.discard(machine.id)  # the cue produced its case; resume dedup
    return created
