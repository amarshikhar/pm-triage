"""The scorer is a measuring instrument, so it needs its own calibration.

Two checks matter here:
  1. It reproduces the labels on the seeded CMMS corpus (15 root causes whose
     signature we already committed to in WORK_ORDER_CLASS).
  2. It handles real strings captured from the deployed live agent, including
     the collisions that a naive keyword matcher gets wrong.
"""

import pytest

from app.eval.taxonomy import (
    FAULT_CLASSES,
    WORK_ORDER_CLASS,
    classify_citations,
    classify_text,
    mentions_class,
    score_text,
)
from app.seed import LOGS

# Real root_cause strings produced by claude-sonnet-4.5 on the deployed service.
LIVE_AGENT_OUTPUTS = [
    ("Likely coolant flow restriction (clogged filter or reduced flow to spindle)", "overheat"),
    ("Bearing lubrication issue or early bearing wear", "bearing_wear"),
    ("Likely drive chain wear or idler roller issue causing belt misalignment", "bearing_wear"),
    # Mock-mode output; 'bearing' collides with bearing_wear but 'cooling fan' must win.
    ("seized cooling fan motor bearing", "overheat"),
    ("suction strainer partially blocked causing cavitation", "cavitation"),
    ("worn discharge valve plates leaking back into cylinder", "pressure_loss"),
]


@pytest.mark.parametrize("text,expected", LIVE_AGENT_OUTPUTS)
def test_classifier_on_real_agent_output(text, expected):
    assert classify_text(text)[0] == expected


def test_seeded_corpus_is_labelled_correctly():
    """Every seeded work order's root_cause must classify to its curated label.

    Scored on root_cause ALONE, deliberately. The agent's `root_cause` field is
    the only string production ever hands the scorer — mock mode emits a work
    order's root_cause verbatim, and live mode writes its own one-liner. An
    earlier version of this test prepended `failure_mode`, which made the input
    easier than reality and hid a real miss on WO-1011.
    """
    misses = []
    for wo_id, _mid, _mtype, _date, _fm, _sym, root_cause, *_ in LOGS:
        expected = WORK_ORDER_CLASS[wo_id]
        if expected is None:
            continue
        got, _ = classify_text(root_cause)
        if got != expected:
            misses.append(f"{wo_id}: expected {expected}, got {got} ({root_cause!r})")
    assert not misses, "scorer disagrees with curated labels:\n" + "\n".join(misses)


def test_thermal_root_cause_is_not_read_as_a_pressure_fault():
    """WO-1011 is the gearbox *overheating* order, but its root cause talks
    about a leak at a seal. Caught in a real mock run by the two scorers
    disagreeing: the citation scorer said overheat, the text scorer said
    pressure_loss."""
    assert classify_text("low gearbox oil due to slow leak at output seal")[0] == "overheat"


def test_every_work_order_has_an_explicit_label():
    """A new seeded work order must be labelled deliberately, not defaulted."""
    assert {row[0] for row in LOGS} == set(WORK_ORDER_CLASS)


def test_labels_are_valid_classes():
    for wo, cls in WORK_ORDER_CLASS.items():
        assert cls is None or cls in FAULT_CLASSES, f"{wo} has bogus label {cls}"


def test_hedged_answer_is_flagged_but_still_scored():
    """The exact PMP-01 reply from production: two causes named, correct one
    first. It counts as top-1 correct, and is flagged as hedged."""
    text = "Early-stage bearing lubrication issue or suction strainer blockage beginning"
    cls, hedged = classify_text(text)
    assert cls == "bearing_wear"
    assert hedged is True
    assert mentions_class(text, "cavitation")  # the hedge is real, not imagined


def test_unhedged_answer_is_not_flagged():
    cls, hedged = classify_text("worn discharge valve plates leaking back into cylinder")
    assert cls == "pressure_loss"
    assert hedged is False


def test_explicit_discharge_restriction_is_not_stolen_by_generic_words():
    """Regression from the paid DeepSeek replay: this is one correct physical
    answer, not a three-way overheat/pressure/suction hedge. Generic "flow
    restriction" and "suction side" markers previously polluted its score."""
    text = (
        "Discharge-side flow restriction — most likely the outlet (discharge) "
        "valve has been throttled or is partially closed"
    )
    assert classify_text(text) == ("discharge_restriction", False)


def test_suction_restriction_is_not_called_a_cavitation_hedge():
    text = (
        "Suction line restriction — likely a partially closed inlet valve or "
        "debris blocking the suction side"
    )
    assert classify_text(text) == ("suction_restriction", False)


def test_machine_name_does_not_leak_a_verdict():
    """PMP-01 is literally named 'Coolant Pump 01'. Bare 'coolant' must not
    drag every pump verdict to overheat."""
    assert score_text("Coolant Pump 01 shows nothing unusual")["overheat"] == 0


def test_unrecognisable_text_returns_none():
    assert classify_text("something is wrong with the machine")[0] is None
    assert classify_text("")[0] is None


def test_citation_scorer_takes_first_known_work_order():
    assert classify_citations(["WO-1009", "WO-1007"]) == "bearing_wear"
    assert classify_citations(["WO-1002", "WO-1013"]) == "overheat"


def test_citation_scorer_skips_unmapped_and_unknown_ids():
    assert classify_citations(["WO-1003", "WO-1007"]) == "cavitation"  # 1003 has no signature
    assert classify_citations(["WO-9999", "WO-1005"]) == "overheat"
    assert classify_citations([]) is None
    assert classify_citations(["WO-1003"]) is None


def test_citation_scorer_is_case_and_space_tolerant():
    assert classify_citations([" wo-1009 "]) == "bearing_wear"
