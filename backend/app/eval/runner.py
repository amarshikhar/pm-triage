"""Trial execution.

A trial drives the *real* pipeline — real simulator, real detector, real agent
tool loop — on a machine with a known injected fault, then scores the case the
agent filed. Nothing here reimplements production logic; if it did, the harness
would measure a copy of the system rather than the system.

Each trial gets its own in-memory database. Trials must not see each other:
`count_recurrences` reads prior cases, and the detector's cooldown suppresses
repeat anomalies, so a shared database would make trial N depend on trial N-1.
"""

import json
import time
from dataclasses import asdict, dataclass, field

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from .. import db as db_module
from ..agent.triage import run_triage
from ..classifier import classify_signature
from ..db import Base
from ..models import Anomaly, Machine
from ..seed import seed_if_empty
from ..simulator import FAULTS, FleetSimulator
from .taxonomy import classify_citations, classify_text, is_abstention, mentions_class

# A fault is only usable on a machine whose type the detector can see it through.
# LIMITS gives cnc_mill and conveyor no pressure threshold at all, so a
# pressure_loss there would drift for ever and never raise an anomaly. Cavitation
# is confined to pumps because that is where it physically occurs — and the only
# cavitation precedent in the CMMS (WO-1007) is a pump.
FAULT_MACHINE_TYPES: dict[str, tuple[str, ...]] = {
    "bearing_wear": ("cnc_mill", "compressor", "pump", "conveyor"),
    "overheat": ("cnc_mill", "compressor", "pump", "conveyor"),
    "pressure_loss": ("compressor", "pump"),
    "cavitation": ("pump",),
}

MAX_TICKS = 60  # a fault ramps into breach in ~10-15 ticks; this is a stop, not a target


@dataclass
class TrialResult:
    machine_id: str
    machine_type: str
    fault: str                      # ground truth
    detected: bool = False
    detected_metric: str = ""
    severity: str = ""
    ticks_to_detect: int = 0
    case_id: int | None = None
    root_cause: str = ""
    confidence: float = 0.0
    priority: str = ""
    cited_work_orders: list[str] = field(default_factory=list)
    predicted_text: str | None = None      # scorer 1: free text
    predicted_citation: str | None = None  # scorer 2: cited work orders
    hedged: bool = False
    abstained: bool = False         # named no concrete fault (a hedge/non-answer)
    hit_any: bool = False           # ground truth named anywhere, even secondarily
    correct_text: bool = False
    correct_citation: bool = False
    classifier_pred: str | None = None
    classifier_correct: bool = False
    classifier_abstained: bool = True
    classifier_layer: str = ""
    classifier_ood: bool = False
    llm_mode: str = ""
    llm_model: str = ""
    latency_s: float = 0.0
    error: str = ""
    data_source: str = "simulated"  # simulated | replay (real dataset episode)
    dataset: str = ""              # named source corpus/testbed
    episode_name: str = ""          # exact physical recording used for replay
    in_labelled_window: bool = True  # replay only: anomaly inside dataset markup
    textual_abstained: bool = False  # root-cause wording explicitly declined a class

    def as_dict(self) -> dict:
        return asdict(self)


def _fresh_db():
    """Isolated in-memory database, wired the way the app expects.

    The simulator and audit trail reach for the module-level SessionLocal rather
    than taking a session argument, so it has to be rebound per trial.
    """
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db_module.SessionLocal.configure(bind=engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def eligible_machines(db, fault: str) -> list[Machine]:
    # Simulated machines only: a replay machine's telemetry comes from a
    # recording, so a synthetic fault injected on it would never appear.
    types = FAULT_MACHINE_TYPES[fault]
    return [m for m in db.query(Machine).all()
            if m.type in types and m.source == "simulated"]


def _record_classifier(result: TrialResult, anomaly: Anomaly, machine: Machine) -> None:
    """Run the production classifier without exposing the trial label to it."""
    analysis = classify_signature(
        json.loads(anomaly.context_json or "{}"),
        machine.signals,
        machine.type,
        machine.source,
    )
    result.classifier_pred = analysis["predicted"]
    result.classifier_abstained = analysis["abstain"]
    result.classifier_correct = analysis["predicted"] == result.fault
    result.classifier_layer = analysis.get("layer", "")
    result.classifier_ood = bool((analysis.get("ml_analysis") or {}).get("ood", False))


def run_trial(machine_id: str, fault: str, seed: int) -> TrialResult:
    """Inject one known fault, let the real pipeline react, score the outcome."""
    if fault not in FAULTS:
        raise ValueError(f"unknown fault {fault!r}; known: {sorted(FAULTS)}")

    db = _fresh_db()
    try:
        seed_if_empty(db)
        machine = db.get(Machine, machine_id)
        result = TrialResult(machine_id=machine_id, machine_type=machine.type, fault=fault)

        # No spontaneous faults: a second, unrelated fault appearing mid-trial
        # would make the ground-truth label ambiguous.
        sim = FleetSimulator(seed=seed, spontaneous_fault_prob=0.0)
        sim.inject_fault(machine_id, fault)

        anomaly_id = None
        for tick in range(1, MAX_TICKS + 1):
            for aid in sim.tick():
                if db.get(Anomaly, aid).machine_id == machine_id:
                    anomaly_id = aid
                    break
            if anomaly_id:
                result.ticks_to_detect = tick
                break

        if anomaly_id is None:
            result.error = f"no anomaly raised within {MAX_TICKS} ticks"
            return result

        anomaly = db.get(Anomaly, anomaly_id)
        result.detected = True
        result.detected_metric = anomaly.metric
        result.severity = anomaly.severity
        _record_classifier(result, anomaly, machine)

        started = time.monotonic()
        try:
            case = run_triage(db, anomaly_id)
        except Exception as exc:  # a live API failure is a real result, not a crash
            result.error = f"{type(exc).__name__}: {exc}"[:200]
            result.latency_s = round(time.monotonic() - started, 2)
            return result
        result.latency_s = round(time.monotonic() - started, 2)

        evidence = case.as_dict(full=True)["evidence"]
        # The agent's own ordering, not the CMMS search ranking. Reading
        # historical_matches here scored the retrieval engine instead of the
        # agent: it is sorted by match_score, so a reply naming an idler roller
        # (WO-1010) was scored against WO-1011 merely because search ranked it
        # first. Fall back only for cases written before this was persisted.
        cited = evidence.get("cited_work_orders") or [
            m["work_order"] for m in evidence.get("historical_matches", [])
        ]

        result.case_id = case.id
        result.root_cause = case.root_cause
        result.confidence = case.confidence
        result.priority = case.priority
        result.cited_work_orders = cited
        result.llm_mode = case.llm_mode
        result.llm_model = case.llm_model

        # Score the root cause the planner reads, not the whole explanation:
        # a long explanation mentions many things, and crediting that would
        # inflate accuracy for free.
        result.predicted_text, result.hedged = classify_text(case.root_cause)
        result.textual_abstained = is_abstention(case.root_cause)
        result.abstained = bool(
            evidence.get("confidence_calibration", {}).get("abstain", False))
        result.predicted_citation = classify_citations(cited)
        result.hit_any = mentions_class(case.root_cause, fault)
        result.correct_text = result.predicted_text == fault
        result.correct_citation = result.predicted_citation == fault
        return result
    finally:
        db.close()


REPLAY_MAX_TICKS = 400  # an episode is ~1100 rows; the jump leaves ~45 + window


def run_replay_trial(fault: str, episode_name: str | None = None,
                     machine_id: str | None = None) -> TrialResult:
    """Cue a real recorded fault episode, let the pipeline react, score it.

    Ground truth is the dataset authors' markup, not our simulator: the trial's
    fault class comes from the physically induced experiment, and
    `in_labelled_window` records whether the anomaly fired inside the marked
    rows (an early fire on real precursor behaviour scores as detected but
    out-of-window — reported, not hidden).
    """
    from ..replay import DatasetReplayer

    db = _fresh_db()
    try:
        seed_if_empty(db)
        replay_machines = [m for m in db.query(Machine).all() if m.source == "replay"]
        machine = (
            next(m for m in replay_machines if m.id == machine_id)
            if machine_id else next(m for m in replay_machines if m.id == "PMP-03")
        )
        dataset = json.loads(machine.dataset_json or "{}").get("dataset", "")
        result = TrialResult(machine_id=machine.id, machine_type=machine.type,
                             fault=fault, data_source="replay",
                             episode_name=episode_name or "", dataset=dataset)

        replayer = DatasetReplayer()
        result.episode_name = (
            replayer.jump_to_episode(machine, episode_name)
            if episode_name else replayer.jump_to_fault(machine, fault)
        )

        anomaly_id = None
        for tick in range(1, REPLAY_MAX_TICKS + 1):
            for aid in replayer.tick():
                if db.get(Anomaly, aid).machine_id == machine.id:
                    anomaly_id = aid
                    break
            if anomaly_id:
                result.ticks_to_detect = tick
                break

        if anomaly_id is None:
            result.error = f"no anomaly raised within {REPLAY_MAX_TICKS} ticks"
            return result

        anomaly = db.get(Anomaly, anomaly_id)
        result.detected = True
        result.detected_metric = anomaly.metric
        result.severity = anomaly.severity
        result.in_labelled_window = anomaly.ground_truth_fault == fault
        _record_classifier(result, anomaly, machine)

        started = time.monotonic()
        try:
            case = run_triage(db, anomaly_id)
        except Exception as exc:
            result.error = f"{type(exc).__name__}: {exc}"[:200]
            result.latency_s = round(time.monotonic() - started, 2)
            return result
        result.latency_s = round(time.monotonic() - started, 2)

        evidence = case.as_dict(full=True)["evidence"]
        cited = evidence.get("cited_work_orders") or [
            m["work_order"] for m in evidence.get("historical_matches", [])
        ]
        result.case_id = case.id
        result.root_cause = case.root_cause
        result.confidence = case.confidence
        result.priority = case.priority
        result.cited_work_orders = cited
        result.llm_mode = case.llm_mode
        result.llm_model = case.llm_model

        result.predicted_text, result.hedged = classify_text(case.root_cause)
        result.textual_abstained = is_abstention(case.root_cause)
        result.abstained = bool(
            evidence.get("confidence_calibration", {}).get("abstain", False))
        result.predicted_citation = classify_citations(cited)
        result.hit_any = mentions_class(case.root_cause, fault)
        result.correct_text = result.predicted_text == fault
        result.correct_citation = result.predicted_citation == fault
        return result
    finally:
        db.close()


def replay_faults() -> list[str]:
    """Fault classes available across every configured replay testbed."""
    from ..replay import DatasetReplayer

    db = _fresh_db()
    try:
        seed_if_empty(db)
        replayer = DatasetReplayer()
        return sorted({fault for machine in db.query(Machine).all()
                       if machine.source == "replay"
                       for fault in replayer.available_faults(machine)})
    finally:
        db.close()


def replay_episodes() -> list[tuple[str, str, str]]:
    """(machine id, fault, episode name) for every distinct recording."""
    from ..replay import DatasetReplayer

    db = _fresh_db()
    try:
        seed_if_empty(db)
        replayer = DatasetReplayer()
        return [
            (machine.id, item["fault"], item["name"])
            for machine in db.query(Machine).all() if machine.source == "replay"
            for item in replayer.available_episodes(machine)
        ]
    finally:
        db.close()


def run_replay_suite(trials: int | None = None, on_result=None) -> list[TrialResult]:
    """Replay exact recordings, not only the first episode of each class.

    With no count, each physical episode runs once. A larger requested count
    cycles the complete episode list; repeated rows are explicit in each
    result's ``episode_name`` rather than silently pretending to be new data.
    """
    episodes = replay_episodes()
    if not episodes:
        return []
    n = len(episodes) if trials is None else max(0, trials)
    results = []
    for i in range(n):
        machine_id, fault, episode_name = episodes[i % len(episodes)]
        result = run_replay_trial(fault, episode_name, machine_id)
        results.append(result)
        if on_result:
            on_result(result)
    return results


def build_plan(trials: int, seed: int) -> list[tuple[str, str, int]]:
    """(machine_id, fault, seed) triples, balanced across fault classes.

    Round-robins the classes and rotates machines within each so a run is not
    dominated by whichever fault has the most eligible machines.
    """
    import random

    rng = random.Random(seed)
    db = _fresh_db()
    try:
        seed_if_empty(db)
        by_fault = {f: [m.id for m in eligible_machines(db, f)] for f in FAULT_MACHINE_TYPES}
    finally:
        db.close()

    for ids in by_fault.values():
        rng.shuffle(ids)

    faults = list(FAULT_MACHINE_TYPES)
    plan = []
    for i in range(trials):
        fault = faults[i % len(faults)]
        machines = by_fault[fault]
        plan.append((machines[(i // len(faults)) % len(machines)], fault, seed + i))
    return plan


def run_suite(trials: int, seed: int, on_result=None) -> list[TrialResult]:
    """Run the plan sequentially.

    Sequential is a constraint, not a preference: SessionLocal is a single
    module-level sessionmaker, so concurrent trials would fight over its bind.
    Live runs therefore cost roughly (trials x agent latency).
    """
    results = []
    for machine_id, fault, trial_seed in build_plan(trials, seed):
        result = run_trial(machine_id, fault, trial_seed)
        results.append(result)
        if on_result:
            on_result(result)
    return results
