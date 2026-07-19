"""CLI: python -m app.eval --trials 24 --mode mock

  --mode mock     deterministic policy, free, instant — the baseline
  --mode live     real model through OpenRouter (needs OPENROUTER_API_KEY)
  --mode both     run both and print the delta, i.e. what the LLM actually buys

Writes a JSON report with --out. Live runs are sequential and cost roughly
(trials x agent latency), so start small.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from .metrics import format_report, summarize  # noqa: E402
from .runner import run_replay_suite, run_suite  # noqa: E402
from ..llm_budget import process_budget_snapshot  # noqa: E402


def _run(mode: str, trials: int, seed: int, quiet: bool, data: str) -> dict:
    os.environ["LLM_MODE"] = mode
    if mode == "live":
        if not os.getenv("OPENROUTER_API_KEY"):
            sys.exit("live mode needs OPENROUTER_API_KEY (set it, or use --mode mock)")

    def progress(r):
        if quiet:
            return
        if r.error:
            mark = "!"
        elif r.correct_text:
            mark = "."
        else:
            mark = "x"
        print(mark, end="", flush=True)

    paid_before = process_budget_snapshot()
    if data == "replay":
        print(f"\n[{mode}] replaying {trials} real dataset episode(s) ",
              end="", flush=True)
        results = run_replay_suite(trials, on_result=progress)
    else:
        print(f"\n[{mode}] running {trials} trials ", end="", flush=True)
        results = run_suite(trials, seed, on_result=progress)
    print()

    report = summarize(results)
    if mode == "live":
        paid_after = process_budget_snapshot()
        report["paid_usage"] = {
            key: round(paid_after[key] - paid_before[key], 6)
            if "cost" in key else paid_after[key] - paid_before[key]
            for key in ("provider_requests", "returned_cost_usd", "prompt_tokens",
                        "completion_tokens", "total_tokens")
        }
        report["paid_usage"].update({
            "model": report.get("llm_model"),
            "cost_source": "OpenRouter response usage.cost",
            "request_cap": paid_after["request_cap"],
            "returned_cost_stop_usd": paid_after["returned_cost_stop_usd"],
        })
    report["trials_detail"] = [r.as_dict() for r in results]
    if data == "replay":
        detected = [r for r in results if r.detected]
        report["replay"] = {
            "detection_rate_pct": round(100 * len(detected) / len(results), 1) if results else 0,
            "in_labelled_window_pct": round(
                100 * sum(r.in_labelled_window for r in detected) / len(detected), 1)
            if detected else 0,
        }
    return report


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m app.eval")
    p.add_argument("--trials", type=int, default=16)
    p.add_argument("--mode", choices=("mock", "live", "both"), default="mock")
    p.add_argument("--seed", type=int, default=7, help="same seed = same fault plan")
    p.add_argument("--data", choices=("simulated", "replay"), default="simulated",
                   help="replay = score all configured real-data episodes")
    p.add_argument("--out", help="write the JSON report here")
    p.add_argument("--merge-existing", action="store_true",
                   help="preserve modes already present in --out and replace only modes run now")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    modes = ("mock", "live") if args.mode == "both" else (args.mode,)
    reports = {}
    for mode in modes:
        report = _run(mode, args.trials, args.seed, args.quiet, args.data)
        reports[mode] = report
        print(f"\n=== {mode.upper()} ===")
        print(format_report(report))

    if args.mode == "both":
        mock_acc = (reports["mock"].get("accuracy") or {}).get("top1_text_pct")
        live_acc = (reports["live"].get("accuracy") or {}).get("top1_text_pct")
        for report in reports.values():
            if report.get("comparison"):
                report["comparison"]["mock_top1_pct"] = mock_acc
        if mock_acc is not None and live_acc is not None:
            print("\n=== LIVE vs MOCK ===")
            print(f"  scripted baseline : {mock_acc}%")
            print(f"  live model        : {live_acc}%")
            print(f"  delta             : {round(live_acc - mock_acc, 1):+}pp"
                  "   <- what the LLM buys over a scripted policy")

    if args.out:
        merged_reports = {}
        if args.merge_existing and Path(args.out).exists():
            try:
                merged_reports = json.loads(Path(args.out).read_text()).get("reports", {})
            except (json.JSONDecodeError, OSError):
                merged_reports = {}
        merged_reports.update(reports)
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "pipeline_version": "2026-07-19-trained-ml-ood-v3",
            "seed": args.seed,
            "trials_requested": args.trials,
            "reports": merged_reports,
        }
        with open(args.out, "w") as fh:
            json.dump(payload, fh, indent=2)
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
