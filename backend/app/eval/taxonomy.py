"""Fault taxonomy and the two independent scorers.

WHAT THE LABELS ACTUALLY MEAN — read this before quoting any accuracy number.

The simulator's "faults" name *which metric drifts and how*, not a physical
cause. `bearing_wear` is really "progressive mechanical wear -> rising vibration
(+ mild heat)". On a conveyor that physically presents as a worn drive chain or
a seized idler; on a spindle it presents as a worn bearing. So these are
symptom-signature classes, and WORK_ORDER_CLASS maps each historical work order
to the signature it exhibits, not to a shared root cause.

That mapping is a curated judgement call. It is deliberately small, in one
place, and auditable — if you disagree with a row, change it and re-run.

Two scorers, deliberately independent:

  * `classify_text`   — reads the agent's free-text root_cause, which is what a
                        planner actually reads. It is a weighted phrase matcher.
  * `classify_citations` — reads the agent's cited work-order ids, a structured
                        field, through WORK_ORDER_CLASS. No text handling.

They share no logic. If a scorer were silently broken, the two would drift
apart, so the harness reports their agreement rate as a check on the *measuring
instrument itself* — not just on the agent.
"""

import re

FAULT_CLASSES = ("bearing_wear", "overheat", "pressure_loss", "cavitation",
                 "rotor_imbalance", "suction_restriction", "discharge_restriction")

# Human-readable signature of each class, for reports. The last three are the
# SKAB testbed's physically induced faults (real data), which is why their
# signatures speak of flow: the real pump measures flow, the simulated fleet
# does not.
CLASS_SIGNATURE = {
    "bearing_wear": "progressive mechanical wear -> vibration rising, mild heat rise",
    "overheat": "thermal fault -> temperature climbing past limit",
    "pressure_loss": "loss of pressure/head -> pressure falling below limit",
    "cavitation": "suction-side fault -> vibration plus erratic pressure/flow swings",
    "rotor_imbalance": "mass imbalance -> vibration climbing, flow and pressure steady",
    "suction_restriction": "inlet-side starvation -> flow sagging, motor load easing",
    "discharge_restriction": "outlet throttled -> flow stepping down while pressure holds",
}

# Seeded work order -> the signature it exhibits. None = no clean signature
# match (a sudden one-off rather than a progressive drift), so citing it alone
# yields no citation-based prediction rather than a wrong one.
WORK_ORDER_CLASS: dict[str, str | None] = {
    "WO-1001": "bearing_wear",    # spindle bearing wear, vibration 2.8 -> 6.5
    "WO-1002": "overheat",        # coolant flow restriction, spindle temp > 78C
    "WO-1003": None,              # tool holder imbalance: sudden spike, not a drift
    "WO-1004": "pressure_loss",   # discharge valve leak, 750 -> 640 kPa
    "WO-1005": "overheat",        # cooling fan failure, head temp > 95C
    "WO-1006": "pressure_loss",   # intake filter clogging, gradual pressure drop
    "WO-1007": "cavitation",      # suction strainer blocked -> cavitation
    "WO-1008": "pressure_loss",   # mechanical seal failure -> leak, pressure loss
    "WO-1009": "bearing_wear",    # bearing lubrication starvation, vibration up
    "WO-1010": "bearing_wear",    # idler roller seized -> vibration (a bearing seizure)
    "WO-1011": "overheat",        # gearbox overheating, > 90C
    "WO-1012": "bearing_wear",    # drive chain wear -> vibration/noise at drive end
    "WO-1013": "bearing_wear",    # early-stage spindle bearing wear
    "WO-1014": "pressure_loss",   # unloader valve sticking, pressure oscillating
    "WO-1015": "pressure_loss",   # impeller erosion -> gradual head loss
    # PMP-03 (SKAB testbed pump, real data)
    "WO-1016": "suction_restriction",    # inlet valve partially closed, flow sagging
    "WO-1017": "discharge_restriction",  # outlet valve throttled, flow stepped down
    "WO-1018": "rotor_imbalance",        # imbalance mass, vibration ~3x baseline
    "WO-1019": "cavitation",             # air entrained at inlet, flow oscillating
    # Corpus noise: PMs, calibrations, inspections, false alarms. None by
    # construction — citing one of these as the analogue for a live fault
    # yields no citation prediction rather than an accidental hit.
    "WO-1020": None,  # quarterly PM, no defect
    "WO-1021": None,  # pressure transmitter recalibration (instrument, not process)
    "WO-1022": None,  # false vibration alarm — loose sensor mount
    "WO-1023": None,  # safety interlock replacement
    "WO-1024": None,  # scheduled valve inspection, nothing found
    "WO-1025": None,  # motor insulation test, passed
    "WO-1026": None,  # way lube service
    "WO-1027": None,  # planned belt replacement (wear-out, not failure event)
    "WO-1028": None,  # coupling alignment check after motor swap
    "WO-1029": None,  # condensate drain trap rebuild
    "WO-1030": None,  # spindle chiller refrigerant leak (support system)
    "WO-1031": None,  # packing gland adjustment
    "WO-1032": "bearing_wear",  # independent bearing-rig rolling-element defect
}

# (weight, phrase). Multi-word phrases outrank bare words because bare words
# collide across classes: "bearing" appears in WO-1005's *overheat* root cause
# ("seized cooling fan motor bearing"), so "cooling fan" (3) must beat
# "bearing" (2) there. Bare "coolant" is deliberately absent — PMP-01 is named
# "Coolant Pump 01" and would drag every pump verdict toward overheat.
CLASS_MARKERS: dict[str, list[tuple[int, str]]] = {
    "bearing_wear": [
        (3, "bearing lubrication"), (3, "lubrication starvation"), (3, "auto-luber"),
        (3, "lubrication issue"), (3, "chain wear"), (3, "idler roller"),
        (3, "drive chain"), (3, "bearing wear"), (3, "bearing failure"),
        (2, "bearing"), (2, "grease"), (2, "luber"), (2, "lubrication"),
        (1, "wear"), (1, "misalignment"),
    ],
    "overheat": [
        # "gearbox oil" outranks the generic pressure markers on purpose: a low
        # gearbox oil level presents as heat, and WO-1011's root cause reads
        # "low gearbox oil due to slow leak at output seal" — leak+seal would
        # otherwise steal a correct thermal answer.
        (4, "gearbox oil"),
        (3, "cooling fan"), (3, "coolant flow"), (3, "coolant filter"),
        (3, "cooling system"), (3, "intercooler"),
        (3, "coolant restriction"), (3, "heat dissipation"),
        (2, "overheat"), (2, "overheating"), (2, "thermal"), (2, "cooling"),
        (1, "clogged filter"),
    ],
    "pressure_loss": [
        (3, "pressure loss"), (3, "discharge valve"), (3, "intake filter"),
        (3, "air filter"), (3, "unloader"), (3, "mechanical seal"),
        (3, "impeller erosion"), (3, "head loss"), (3, "valve leak"),
        (2, "leak"), (2, "valve"), (2, "impeller"), (2, "blowby"),
        # Bare "seal" stays weak: gearboxes and shafts have seals that fail
        # thermally, so on its own it is not evidence of a pressure fault.
        (1, "seal"), (1, "restriction"),
    ],
    "cavitation": [
        (3, "cavitation"), (3, "suction strainer"),
        (3, "npsh"), (3, "strainer"), (3, "two-phase"), (3, "air entrained"),
        (3, "air ingress"),
        (2, "suction"), (2, "cavitating"),
    ],
    "rotor_imbalance": [
        (3, "rotor imbalance"), (3, "imbalance mass"), (3, "unbalance"),
        (3, "blade fouling"), (3, "rebalance"), (3, "rebalanced"),
        (2, "imbalance"), (2, "runout"),
    ],
    "suction_restriction": [
        (3, "suction restriction"), (3, "suction line"), (3, "inlet valve"),
        (3, "starving suction"), (3, "suction starvation"),
        (2, "partially closed"), (2, "inlet-side"),
    ],
    "discharge_restriction": [
        (4, "discharge-side"), (3, "discharge restriction"),
        (3, "outlet valve"), (3, "throttled"),
        (3, "back on its curve"), (3, "deadhead"),
        (2, "throttling"),
    ],
}

_MARKER_RE = {
    cls: [(w, re.compile(rf"\b{re.escape(p)}\b", re.I)) for w, p in markers]
    for cls, markers in CLASS_MARKERS.items()
}

# A marker at this weight is distinctive enough to mean the agent actually named
# that cause, rather than brushing past a word the class happens to share.
STRONG_WEIGHT = 3


def score_text(text: str) -> dict[str, int]:
    """Weighted marker score per class. Exposed so reports can show the working."""
    if not text:
        return {c: 0 for c in FAULT_CLASSES}
    return {
        cls: sum(w for w, rx in markers if rx.search(text))
        for cls, markers in _MARKER_RE.items()
    }


def named_classes(text: str) -> list[str]:
    """Classes the agent distinctively named (a marker at STRONG_WEIGHT+).

    Scores alone can't answer this: markers accumulate, so "bearing lubrication
    issue or suction strainer blockage" scores 10 vs 8 — two genuinely named
    causes that no closeness threshold would catch.
    """
    return [
        cls for cls, markers in _MARKER_RE.items()
        if any(w >= STRONG_WEIGHT and rx.search(text or "") for w, rx in markers)
    ]


def classify_text(text: str) -> tuple[str | None, bool]:
    """Best-guess class from free text.

    Returns (class or None, hedged). `hedged` means the agent distinctively
    named two or more different causes, e.g. "bearing lubrication issue or
    suction strainer blockage". The top scorer is still taken as the top-1
    prediction (ties broken by whichever marker reads first), but hedging is
    reported separately so top-1 accuracy is not quietly flattered by answers
    that covered several bases at once.
    """
    scores = score_text(text)
    best = max(scores.values())
    if best == 0:
        return None, False

    leaders = [c for c, s in scores.items() if s == best]
    if len(leaders) > 1:
        leaders.sort(key=lambda c: _earliest_marker_pos(text, c))
    return leaders[0], len(named_classes(text)) > 1


def _earliest_marker_pos(text: str, cls: str) -> int:
    positions = [m.start() for _, rx in _MARKER_RE[cls] if (m := rx.search(text))]
    return min(positions) if positions else len(text)


def classify_citations(work_orders: list[str]) -> str | None:
    """Class implied by the work orders the agent cited, in its own order.

    The first cited order carrying a known signature wins: agents list their
    primary analogue first. Unmapped ids are skipped rather than guessed at.
    """
    for wo in work_orders or []:
        cls = WORK_ORDER_CLASS.get(str(wo).strip().upper())
        if cls:
            return cls
    return None


def mentions_class(text: str, cls: str) -> bool:
    """Did the agent name this class anywhere, even as a secondary hypothesis?

    Feeds the hit@any metric, which separates 'wrong' from 'right but hedged'.
    """
    return any(rx.search(text or "") for _, rx in _MARKER_RE[cls])


# An abstaining answer names no fault at all — it retreats to noise, a transient,
# an instrument problem, or a non-answer. The scorer recognises this on its own
# (no shared code with the agent's calibrator) so the confusion matrix can show
# "abstained" distinctly from "unclassified": the SKAB run had the live model
# dodge every suction-restriction episode with "test-loop operational transient",
# and reporting that as a plain miss hid *how* it failed.
_ABSTENTION_RE = re.compile(
    r"\b("
    r"transient|load cycling|operating condition change|operational transient|"
    r"instrumentation (?:malfunction|error|fault)|control system oscillation|"
    r"sensor (?:error|fault|malfunction|drift)|measurement (?:noise|artifact|error)|"
    r"normal variation|within normal|no clear (?:cause|root cause|pattern)|"
    r"unable to determine|cannot determine|could not determine|undetermined|"
    r"inconclusive|unknown cause|novel anomaly|does not resemble|"
    r"no matching (?:failure|pattern)|insufficient evidence"
    r")\b",
    re.I,
)


def is_abstention(text: str) -> bool:
    """True when the agent's stated cause names no concrete fault — a hedge."""
    return bool(_ABSTENTION_RE.search(text or ""))
