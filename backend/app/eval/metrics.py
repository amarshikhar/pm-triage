"""Turn trial results into the numbers worth defending.

Accuracy is the headline, but calibration is the finding that changes the
product: if cases above some confidence are reliably right and cases below it
are coin flips, the human gate stops being a philosophical stance and becomes a
threshold derived from data.
"""

from collections import defaultdict

from .taxonomy import FAULT_CLASSES

# Wide buckets on purpose. Agents cluster their self-reported confidence into a
# few values (0.6/0.72/0.75), so ten narrow bins would mostly read n=0.
CONFIDENCE_BUCKETS = ((0.0, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 1.01))


def _pct(num: int, den: int) -> float | None:
    return round(100.0 * num / den, 1) if den else None


def summarize(results: list) -> dict:
    scored = [r for r in results if r.case_id is not None and not r.error]
    errored = [r for r in results if r.error]
    undetected = [r for r in results if not r.detected]

    report = {
        "n_trials": len(results),
        "n_scored": len(scored),
        "n_detector_missed": len(undetected),
        "n_agent_errors": len(errored),
        "llm_mode": scored[0].llm_mode if scored else "",
        "llm_model": scored[0].llm_model if scored else "",
        "detection_rate_pct": _pct(len([r for r in results if r.detected]), len(results)),
    }

    if not scored:
        report["errors"] = [r.error for r in errored][:5]
        return report

    correct_text = [r for r in scored if r.correct_text]
    correct_cite = [r for r in scored if r.correct_citation]

    report["accuracy"] = {
        "top1_text_pct": _pct(len(correct_text), len(scored)),
        "top1_citation_pct": _pct(len(correct_cite), len(scored)),
        # Credits an answer that named the true cause as a secondary hypothesis.
        # Separating this from top-1 keeps hedging visible instead of rewarding it.
        "hit_any_pct": _pct(len([r for r in scored if r.hit_any]), len(scored)),
        "hedged_pct": _pct(len([r for r in scored if r.hedged]), len(scored)),
        "unclassifiable_pct": _pct(
            len([r for r in scored if r.predicted_text is None]), len(scored)),
    }

    # The two scorers share no logic, so disagreement is a warning about the
    # instrument. High agreement means the accuracy number is not an artefact of
    # one brittle scorer.
    both = [r for r in scored if r.predicted_text and r.predicted_citation]
    report["scorer_agreement_pct"] = _pct(
        len([r for r in both if r.predicted_text == r.predicted_citation]), len(both))
    report["scorer_agreement_n"] = len(both)

    per_class = {}
    for cls in FAULT_CLASSES:
        rows = [r for r in scored if r.fault == cls]
        if rows:
            per_class[cls] = {
                "n": len(rows),
                "top1_text_pct": _pct(len([r for r in rows if r.correct_text]), len(rows)),
                "hit_any_pct": _pct(len([r for r in rows if r.hit_any]), len(rows)),
                "mean_confidence": round(sum(r.confidence for r in rows) / len(rows), 2),
                "mean_ticks_to_detect": round(
                    sum(r.ticks_to_detect for r in rows) / len(rows), 1),
            }
    report["per_class"] = per_class

    matrix = defaultdict(lambda: defaultdict(int))
    for r in scored:
        matrix[r.fault][r.predicted_text or "unclassified"] += 1
    report["confusion"] = {truth: dict(preds) for truth, preds in matrix.items()}

    report["calibration"] = _calibration(scored)
    report["ece"] = _ece(scored)

    latencies = sorted(r.latency_s for r in scored)
    report["latency_s"] = {
        "mean": round(sum(latencies) / len(latencies), 2),
        "p50": latencies[len(latencies) // 2],
        "max": latencies[-1],
    }
    if errored:
        report["errors"] = [r.error for r in errored][:5]
    return report


def _calibration(scored: list) -> list[dict]:
    """Stated confidence vs measured accuracy, per bucket.

    A well-calibrated agent's accuracy tracks its confidence. A gap in either
    direction is actionable: over-confidence means the gate cannot be relaxed;
    under-confidence means the agent is doing better than it admits.
    """
    out = []
    for lo, hi in CONFIDENCE_BUCKETS:
        rows = [r for r in scored if lo <= r.confidence < hi]
        if not rows:
            continue
        acc = _pct(len([r for r in rows if r.correct_text]), len(rows))
        mean_conf = round(100 * sum(r.confidence for r in rows) / len(rows), 1)
        out.append({
            "bucket": f"{lo:.2f}-{hi if hi <= 1 else 1.0:.2f}",
            "n": len(rows),
            "mean_confidence_pct": mean_conf,
            "accuracy_pct": acc,
            "gap_pct": round(acc - mean_conf, 1),  # +ve = under-confident
        })
    return out


def _ece(scored: list) -> float | None:
    """Expected calibration error: mean |confidence - accuracy| weighted by
    bucket size. One number for 'can I trust the confidence field?'"""
    if not scored:
        return None
    total = 0.0
    for lo, hi in CONFIDENCE_BUCKETS:
        rows = [r for r in scored if lo <= r.confidence < hi]
        if not rows:
            continue
        acc = len([r for r in rows if r.correct_text]) / len(rows)
        conf = sum(r.confidence for r in rows) / len(rows)
        total += (len(rows) / len(scored)) * abs(acc - conf)
    return round(total, 3)


def format_report(report: dict) -> str:
    """Console rendering. Kept plain so it pastes into a PR or a slide."""
    L = []
    a = report.get("accuracy")
    L.append(f"  mode              : {report['llm_mode']} ({report['llm_model'] or 'n/a'})")
    L.append(f"  trials            : {report['n_trials']}  scored={report['n_scored']}"
             f"  detector_missed={report['n_detector_missed']}"
             f"  agent_errors={report['n_agent_errors']}")
    L.append(f"  detection rate    : {report['detection_rate_pct']}%")
    if not a:
        L.append("  (nothing scored)")
        for e in report.get("errors", []):
            L.append(f"    error: {e}")
        return "\n".join(L)

    L.append("")
    L.append(f"  top-1 accuracy    : {a['top1_text_pct']}%   (free-text scorer)")
    L.append(f"  top-1 accuracy    : {a['top1_citation_pct']}%   (citation scorer, independent)")
    L.append(f"  scorer agreement  : {report['scorer_agreement_pct']}% (n={report['scorer_agreement_n']})")
    L.append(f"  hit@any           : {a['hit_any_pct']}%   (true cause named anywhere)")
    L.append(f"  hedged answers    : {a['hedged_pct']}%")
    L.append(f"  unclassifiable    : {a['unclassifiable_pct']}%")
    L.append(f"  ECE               : {report['ece']}  (0 = perfectly calibrated)")
    L.append(f"  latency           : mean {report['latency_s']['mean']}s"
             f"  p50 {report['latency_s']['p50']}s  max {report['latency_s']['max']}s")

    L.append("")
    L.append("  per fault class:")
    L.append(f"    {'class':<15}{'n':>4}{'top-1':>9}{'hit@any':>10}{'conf':>7}{'ticks':>7}")
    for cls, s in report["per_class"].items():
        L.append(f"    {cls:<15}{s['n']:>4}{str(s['top1_text_pct']) + '%':>9}"
                 f"{str(s['hit_any_pct']) + '%':>10}{s['mean_confidence']:>7}"
                 f"{s['mean_ticks_to_detect']:>7}")

    if report["calibration"]:
        L.append("")
        L.append("  calibration (stated confidence vs measured accuracy):")
        L.append(f"    {'bucket':<14}{'n':>4}{'stated':>9}{'actual':>9}{'gap':>8}")
        for c in report["calibration"]:
            L.append(f"    {c['bucket']:<14}{c['n']:>4}{str(c['mean_confidence_pct']) + '%':>9}"
                     f"{str(c['accuracy_pct']) + '%':>9}{str(c['gap_pct']) + '%':>8}")

    L.append("")
    L.append("  confusion (truth -> predicted):")
    for truth, preds in report["confusion"].items():
        row = ", ".join(f"{p}={n}" for p, n in sorted(preds.items(), key=lambda x: -x[1]))
        L.append(f"    {truth:<15} {row}")

    for e in report.get("errors", []):
        L.append(f"    error: {e}")
    return "\n".join(L)
