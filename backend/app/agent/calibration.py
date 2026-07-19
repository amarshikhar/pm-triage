"""Evidence-grounded confidence calibration.

The agent reports its own confidence, but the SKAB evaluation showed that number
does not transfer to real data: on the real pump the live model was ~0.82
confident *while naming the wrong fault* (ECE 0.398 vs 0.043 on synthetic),
because a language model's self-reported certainty tracks fluency, not evidence.
Worse, on the suction-restriction episodes it dodged entirely — "test-loop
operational transient", "instrumentation malfunction" — yet still filed those as
0.65-confidence cases.

This module discounts the raw confidence by how much *evidence* actually backs
the answer and flags weak cases to ABSTAIN — an explicit "not sure, defer to the
planner" rather than a confident guess. Two factors, both auditable:

  precedent   — how strong the closest historical work order match was. The
                agent's whole method is "this looks like WO-xxxx"; with no close
                precedent (the real pump has four, one per fault) that anchor is
                weak and the confidence should reflect it.
  specificity — whether the agent named a concrete cause at all, or retreated to
                a non-diagnostic "transient / noise / operating-condition change /
                instrumentation" that names nothing. That retreat is itself an
                uncertainty signal the raw number hides.

Deterministic and fully reported, like the priority formula: every factor lands
on the case so a planner can audit the calibrated number, not just trust it.
"""

import re
from dataclasses import asdict, dataclass

# Below this calibrated confidence the case is flagged to abstain: the agent is
# not sure enough to stand behind a specific cause, so it says so.
ABSTAIN_THRESHOLD = 0.45

# Confidence is never asserted as certainty and never as zero — even a strong,
# well-precedented answer on real equipment carries residual doubt.
CONF_CEILING = 0.95
CONF_FLOOR = 0.05

# Phrases that mean the agent named no concrete fault — it deferred to noise, a
# transient, an instrument problem, or an explicit non-answer. Matched as whole
# words/phrases, case-insensitive. Erring toward humility (a false positive here
# only lowers confidence) is the safe direction for a triage assistant.
_NON_DIAGNOSTIC = re.compile(
    r"\b("
    r"transient|load cycling|operating condition change|operational transient|"
    r"instrumentation (?:malfunction|error|fault)|instrument(?:ation)? (?:error|drift)|"
    r"control system oscillation|sensor (?:error|fault|malfunction|drift|noise)|"
    r"measurement (?:noise|artifact|error)|signal noise|"
    r"normal variation|within normal|no clear (?:cause|root cause|pattern)|"
    r"unable to determine|cannot determine|could not determine|undetermined|"
    r"inconclusive|unclear|unknown cause|novel anomaly|does not resemble|"
    r"no matching (?:failure|pattern)|insufficient evidence|requires manual"
    r")\b",
    re.I,
)


@dataclass
class Calibration:
    raw: float                # confidence as the model reported it
    precedent_factor: float   # discount from precedent strength (0-1]
    specificity_factor: float # discount for a non-diagnostic answer (0-1]
    signature_factor: float   # conservative deterministic agreement adjustment
    signature_agreement: bool | None  # None when classifier abstained
    signature_abstained: bool # signature layer could not separate a class
    calibrated: float         # the confidence the case actually carries
    abstain: bool             # calibrated below threshold, or non-diagnostic
    reason: str               # one-line, human-readable justification

    def as_dict(self) -> dict:
        return asdict(self)


def is_non_diagnostic(root_cause: str) -> bool:
    """True when the stated cause names no concrete fault — a hedge or non-answer."""
    return bool(_NON_DIAGNOSTIC.search(root_cause or ""))


def _precedent_factor(best_match_score: int) -> float:
    """Map the strongest historical match score to a confidence multiplier.

    Scores come from the CMMS keyword search: term overlap on the work order,
    +2 when it is the *same machine*. So >=3 is a solid, on-asset precedent; 1 is
    a single shared word; 0 is nothing to anchor to.
    """
    if best_match_score >= 3:
        return 1.0
    if best_match_score == 2:
        return 0.85
    if best_match_score == 1:
        return 0.70
    return 0.50


def calibrate(raw_confidence: float, root_cause: str,
              history_matches: list[dict] | None,
              signature_agreement: bool | None = None,
              signature_confidence: float = 0.0,
              signature_abstained: bool = False) -> Calibration:
    """Ground the model's confidence in the evidence behind the answer."""
    raw = max(0.0, min(1.0, float(raw_confidence or 0.0)))
    scores = [int(m.get("match_score") or 0) for m in (history_matches or [])]
    best = max(scores) if scores else 0

    precedent_factor = _precedent_factor(best)
    non_diagnostic = is_non_diagnostic(root_cause)
    specificity_factor = 0.40 if non_diagnostic else 1.0

    # Only a classifier strong enough to publish a concrete verdict affects the
    # number. Agreement is a small corroborating bonus; disagreement is a much
    # stronger warning because two independent reasoning paths conflict. The
    # agent still writes its hypothesis, but the case explicitly defers to the
    # planner on a confident conflict.
    signature_confidence = max(0.0, min(1.0, float(signature_confidence or 0.0)))
    signature_is_confident = signature_agreement is not None and signature_confidence >= 0.56
    if signature_abstained:
        # Retrieval can always find a superficially similar work order. If the
        # observable signal pattern itself cannot separate the candidates, that
        # precedent must not turn ambiguity into confidence.
        signature_factor = 0.75
    elif not signature_is_confident:
        signature_factor = 1.0
    elif signature_agreement:
        signature_factor = 1.05
    else:
        signature_factor = 0.65

    calibrated = round(
        max(CONF_FLOOR, min(
            CONF_CEILING,
            raw * precedent_factor * specificity_factor * signature_factor,
        )), 2)
    if signature_abstained:
        # Keep the numeric field consistent with the decision: a case explicitly
        # routed to the uncertainty path must not still display >50% confidence.
        calibrated = min(calibrated, round(ABSTAIN_THRESHOLD - 0.01, 2))
    signature_conflict = signature_is_confident and signature_agreement is False
    abstain = (non_diagnostic or calibrated < ABSTAIN_THRESHOLD
               or signature_conflict or signature_abstained)

    if non_diagnostic:
        reason = "named no concrete cause — deferring to the planner"
    elif signature_conflict:
        reason = "confident deterministic signature disagrees — deferring to the planner"
    elif signature_abstained:
        reason = "signal signatures overlap — deferring classification to the planner"
    elif best == 0:
        reason = "no historical precedent to anchor the diagnosis"
    elif abstain:
        reason = "weak precedent and low grounded confidence"
    elif signature_is_confident and signature_agreement:
        reason = "matching work order and deterministic signature agree"
    else:
        reason = "diagnosis backed by a matching historical work order"

    return Calibration(
        raw=round(raw, 2),
        precedent_factor=precedent_factor,
        specificity_factor=specificity_factor,
        signature_factor=signature_factor,
        signature_agreement=signature_agreement if signature_is_confident else None,
        signature_abstained=signature_abstained,
        calibrated=calibrated,
        abstain=abstain,
        reason=reason,
    )
