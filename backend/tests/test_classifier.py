"""Physics-signature classifier: strong cases and honest non-decisions."""

from app.classifier import classify_signature, signature_agrees


REAL_SIGNALS = [
    {"key": "vibration_g"}, {"key": "flow_lpm"}, {"key": "pressure_bar"},
    {"key": "current_a"}, {"key": "temp_motor_c"}, {"key": "temp_fluid_c"},
]


def _s(mean, drift, volatility, span, n=31):
    return {"mean": mean, "drift": drift, "volatility_pct": volatility,
            "range": span, "n": n}


def test_rotor_imbalance_is_separable_from_steady_process_signals():
    context = {
        "vibration_g": _s(0.31, 0.14, 48.0, 0.28),
        "flow_lpm": _s(126.0, 0.1, 0.8, 3.0),
        "pressure_bar": _s(0.2, 0.01, 12.0, 1.0),
        "current_a": _s(2.4, 0.0, 3.0, 0.3),
        "temp_motor_c": _s(88.0, 0.1, 0.2, 1.0),
    }
    result = classify_signature(context, REAL_SIGNALS, "pump", "replay")
    assert result["predicted"] == "rotor_imbalance"
    assert not result["abstain"]
    assert any("vibration" in line for line in result["evidence"])


def test_cavitation_flow_surge_and_pressure_drop_is_separable():
    context = {
        "vibration_g": _s(0.25, 0.03, 8.0, 0.12),
        "flow_lpm": _s(95.0, 36.0, 24.0, 70.0),
        "pressure_bar": _s(0.3, -0.18, 95.0, 0.55),
        "current_a": _s(2.4, 0.0, 8.0, 0.5),
        "temp_motor_c": _s(85.0, 0.0, 0.3, 1.0),
    }
    result = classify_signature(context, REAL_SIGNALS, "pump", "replay")
    assert result["predicted"] == "cavitation"
    assert not result["abstain"]
    assert any("flow rising" in line for line in result["evidence"])


def test_ambiguous_restriction_window_abstains_instead_of_guessing():
    # Flow/load ease slightly while the near-zero pressure channel is noisy and
    # directionally inconclusive: exactly the suction/discharge hard case.
    context = {
        "vibration_g": _s(0.028, 0.0, 1.2, 0.002),
        "flow_lpm": _s(31.7, -0.15, 1.6, 1.4),
        "pressure_bar": _s(0.01, 0.04, 450.0, 1.0),
        "current_a": _s(1.08, -0.14, 21.0, 0.9),
        "temp_motor_c": _s(70.0, -0.1, 0.4, 0.8),
    }
    result = classify_signature(context, REAL_SIGNALS, "pump", "replay")
    assert result["predicted"] is None
    assert result["abstain"]
    assert result["confidence"] < 0.56
    assert result["ranked"][0][0] in {
        "suction_restriction", "discharge_restriction",
    }


def test_unknown_signal_roster_abstains():
    result = classify_signature({"mystery": _s(1, 1, 1, 1)}, [{"key": "mystery"}],
                                "pump", "replay")
    assert result["predicted"] is None and result["abstain"]
    assert "No recognized" in result["evidence"][0]
    assert result["ml_analysis"]["ood"] is True
    assert "unsupported signal roster" in result["ml_analysis"]["ood_reason"]


def test_agreement_matches_physical_cause_language_not_only_class_labels():
    assert signature_agrees("clogged coolant filter reduced jacket flow", "overheat")
    assert signature_agrees("worn discharge valve plates leaking back", "pressure_loss")
    assert signature_agrees("inlet-side valve found partially closed", "suction_restriction")
    assert not signature_agrees("air entrainment causing cavitation", "rotor_imbalance")
