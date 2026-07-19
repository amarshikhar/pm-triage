# Current status — 2026-07-19

## Simple answer

The trained classifier and genuine OOD gate are now implemented, but narrowly:
the ML model distinguishes SKAB suction-side versus discharge-side restriction.
Rules still own clear faults. The LLM does retrieval, explanation, and action
drafting; it does not get to overrule a concrete classifier verdict. A human
must approve every work order.

The expanded free real-data run has eight episodes across two laboratory
testbeds. The hybrid classifier is correct on 7/8 overall, covers 7/8, and is
7/7 correct when it speaks. It abstains on the remaining cavitation episode.
That is 87.5% overall, 87.5% coverage, and 100% selective accuracy—not universal
100% accuracy.

The intentionally paid DeepSeek replay also completed on all eight episodes:
7/8 raw top-1, 6/8 operational coverage after abstention, 6/6 selective
accuracy, ECE 0.148, zero errors/fallbacks, and $0.014535 returned provider cost.

Verification: **102 backend tests pass** and the Next.js production build
completes successfully.

## Done versus pending

| Work item | Status | Exact evidence |
|---|---|---|
| Evidence-grounded confidence and abstention | Done | Precedent, specificity, classifier agreement/OOD and a 0.45 gate control the operational path. |
| Scorer coverage fix | Done | Text and citation scorers report agreement and joint coverage. Generic restriction words no longer override explicit suction/discharge wording; paid-run regression strings are tested. |
| LLM job reframed | Done | Concrete classifier class owns `root_cause`; LLM owns precedent, explanation, actions, and drafting. A conflict guard retains the classifier and records the rejected LLM draft. |
| Trained hard-fault classifier | Done, narrow | Extra Trees, 510 windows from 17 training experiments, physical-episode grouping, 3/3 frozen restriction holdout. Artifact: `backend/data/models/skab_restriction.joblib`. |
| Genuine OOD detector/calibrator | Done for the narrow model | IsolationForest; threshold is the 10th percentile of leave-one-episode-out in-distribution scores. Same-roster non-restriction SKAB OOD test: AUROC 1.0 and 14/14 rejected. Unsupported sensor rosters abstain before inference. |
| More real datasets | Done for development evidence | Five SKAB episodes plus three CWRU bearing episodes are integrated. Raw CWRU checksums and provenance are documented. |
| Human-in-the-loop production flow | Done | Every case is `pending_review`; a named planner approves/rejects/edits; only approval creates a CMMS work order. |
| Cost-safe live mode | Done | Mock default, DeepSeek V4 Flash default, random production faults off, 12 provider requests/day, $0.25/day, 700 output tokens, persistent usage/cost ledger. |
| Fresh live DeepSeek evaluation | Done | GitHub run `29692423022`: 8/8 live rows, 0 errors/fallbacks, 34 calls, 161,585 tokens, $0.014535 returned cost. |
| Vercel frontend deployment | Done | PR #1 merged as `753b96f`; Vercel deployment `dpl_EgUjFP7JyrJLEuot1AzGoW2SQpmd` is READY/PROMOTED at `pm-triage.vercel.app`. |
| Render backend deployment | Not verified in this release | The frontend's committed reports are current even if Render is asleep or stale; backend SHA/health remains a separate release check. |

## Current mock-mode numbers

| Metric | Synthetic, n=24 | Real, n=8 across SKAB + CWRU |
|---|---:|---:|
| Detection | 100.0% | 100.0% |
| Hybrid classifier overall top-1 | 75.0% | 87.5% (7/8) |
| Hybrid classifier coverage | 79.2% | 87.5% (7/8) |
| Hybrid classifier selective accuracy | 94.7% | 100.0% (7/7) |
| Full mock system raw top-1 | 83.3% | 87.5% |
| Full-system operational coverage | 79.2% | 87.5% |
| Full-system selective accuracy | 89.5% | 100.0% (7/7) |
| Full-system abstention | 20.8% | 12.5% (1/8) |
| ECE | 0.207 | 0.239 |
| Scorer agreement / coverage | 100% / 79.2% | 100% / 100% |

## Current paid DeepSeek numbers

| Metric | Synthetic, n=24 | Real, n=8 across SKAB + CWRU |
|---|---:|---:|
| Detection | 100.0% | 100.0% |
| Raw text top-1 | 75.0% | 87.5% (7/8) |
| Operational coverage after confidence gate | 75.0% | 75.0% (6/8) |
| Selective accuracy | 94.4% | 100.0% (6/6) |
| Abstention | 25.0% | 25.0% (2/8) |
| ECE | 0.319 | 0.148 |
| Scorer agreement / joint coverage | 100% / 4.2% | 100% / 75.0% |
| Mean / maximum latency | 26.03 s / 62.88 s | 32.17 s / 56.25 s |
| Agent errors or mock fallbacks | 0 | 0 |
| Exact returned cost | Not captured by the first report version | $0.014535 |

The real paid report records 34 provider calls, 143,044 input tokens, 18,541
output tokens, and 161,585 total tokens. “Scorer joint coverage” is lower than
fault coverage because DeepSeek sometimes gave the right text class without a
mapped work-order citation; it is a measurement-quality warning, not another
accuracy denominator.

The real result includes:

- SKAB: rotor imbalance, cavitation, suction restriction, and two discharge
  restriction recordings;
- CWRU: inner-race, ball, and outer-race bearing recordings, mapped to the
  application's coarse `bearing_wear` family.

CWRU sequences concatenate real healthy steady-state feature frames with real
faulty steady-state frames. They test a second sensor roster and testbed, but are
not natural run-to-failure transitions. The official CWRU pages do not state an
explicit dataset license, so commercial/redistribution terms remain a release
constraint.

## Why the first ML attempt and the production model differ

The rejected experiment tried to classify four SKAB classes from one
first-trigger summary per episode. It scored 3/5 and made a wrong valve decision
at about 95% confidence.

The production replacement is intentionally smaller and safer:

1. rules retain easy classes;
2. ML only separates suction vs discharge restriction;
3. training uses many fault-window views but every split holds out the complete
   physical experiment;
4. probability and acceptance thresholds come from leave-one-experiment-out
   predictions, not the frozen test;
5. a learned novelty model rejects non-restriction SKAB contexts;
6. the untouched restriction test is `valve1/2`, `valve2/0`, `valve2/1`.

## Which works better?

- Numeric fault classification: use the hybrid rules + trained classifier. On
  this real suite it is 7/8 overall and 7/7 when it accepts.
- Explanation, precedent retrieval, recommended actions, and work-order prose:
  use the LLM. DeepSeek was 7/8 raw, 6/6 after its confidence gate, but averaged
  32.17 seconds and cost $0.014535 for the eight-case run. Keep the classifier
  class fixed.
- Detection, priority, spending controls, work-order authorization, and machine
  control: do not give these jobs to the LLM.

Production sentence: **rules detect; rules plus narrow ML classify; OOD can
abstain; the LLM explains and retrieves; a human authorizes every action.**
