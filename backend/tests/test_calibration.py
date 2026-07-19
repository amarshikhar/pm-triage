"""Confidence calibration: the agent's raw certainty, grounded in evidence.

The SKAB run showed the live model ~0.82 confident while naming the wrong fault
and dodging others as "transient". These check the discount actually fires on
weak evidence and non-diagnostic answers, and leaves well-precedented ones alone.
"""

from app.agent.calibration import ABSTAIN_THRESHOLD, calibrate, is_non_diagnostic

STRONG = [{"work_order": "WO-1009", "match_score": 4}]   # same-machine, multi-term
WEAK = [{"work_order": "WO-1031", "match_score": 1}]     # one shared word
NONE: list[dict] = []


def test_strong_precedent_and_concrete_cause_keeps_confidence():
    c = calibrate(0.80, "bearing lubrication starvation on the drive end", STRONG)
    assert c.precedent_factor == 1.0 and c.specificity_factor == 1.0
    assert c.calibrated == 0.8 and not c.abstain


def test_confidence_is_never_asserted_as_certainty():
    c = calibrate(1.0, "worn mechanical seal leaking", STRONG)
    assert c.calibrated <= 0.95


def test_non_diagnostic_answer_is_discounted_and_abstains():
    # The exact failure shape from the real suction-restriction episodes.
    c = calibrate(0.65, "Test-loop operational transient during load cycling", STRONG)
    assert c.specificity_factor < 1.0
    assert c.abstain and c.calibrated < ABSTAIN_THRESHOLD


def test_confident_but_unprecedented_is_pulled_down():
    # High raw confidence with nothing to anchor it — exactly what over-confidence
    # on real data looks like. It should drop, even for a concrete-sounding cause.
    c = calibrate(0.85, "air ingress at the pump inlet causing cavitation", NONE)
    assert c.precedent_factor < 1.0 and c.calibrated < 0.85


def test_weak_precedent_lowers_but_does_not_zero():
    c = calibrate(0.60, "impeller erosion reducing head", WEAK)
    assert 0.0 < c.calibrated < 0.60


def test_abstention_phrases_detected():
    assert is_non_diagnostic("instrumentation malfunction or control system oscillation")
    assert is_non_diagnostic("no matching failure pattern — novel anomaly")
    assert not is_non_diagnostic("seized cooling fan motor bearing")
    assert not is_non_diagnostic("suction strainer partially blocked causing cavitation")


def test_classifier_agreement_adds_only_a_small_corroborating_bonus():
    base = calibrate(0.70, "imbalance mass on the rotor", STRONG)
    agreed = calibrate(0.70, "imbalance mass on the rotor", STRONG,
                       signature_agreement=True, signature_confidence=0.82)
    assert agreed.signature_factor == 1.05
    assert agreed.calibrated > base.calibrated
    assert agreed.calibrated - base.calibrated <= 0.04
    assert not agreed.abstain


def test_confident_classifier_disagreement_lowers_confidence_and_abstains():
    base = calibrate(0.80, "air ingress causing cavitation", STRONG)
    conflicted = calibrate(0.80, "air ingress causing cavitation", STRONG,
                           signature_agreement=False, signature_confidence=0.80)
    assert conflicted.signature_factor < 1.0
    assert conflicted.calibrated < base.calibrated
    assert conflicted.abstain
    assert "disagrees" in conflicted.reason


def test_abstaining_classifier_does_not_move_existing_calibration():
    base = calibrate(0.80, "air ingress causing cavitation", STRONG)
    no_verdict = calibrate(0.80, "air ingress causing cavitation", STRONG,
                           signature_agreement=None, signature_confidence=0.49)
    assert no_verdict.calibrated == base.calibrated
    assert no_verdict.signature_factor == 1.0
