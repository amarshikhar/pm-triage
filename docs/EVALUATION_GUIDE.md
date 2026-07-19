# Evaluation numbers in simple language

## Read the four numbers in this order

1. **Detection rate:** Did the system notice that something abnormal happened?
2. **Overall top-1 accuracy:** If every trial counts, how often was the first
   named class correct? Abstentions count as not correct.
3. **Coverage:** How often did the method feel it had enough evidence to name a
   class rather than abstain?
4. **Selective accuracy:** Among only the cases where it named a class, how
   often was it right?

Example from the current real replay suite:

- 8 recordings were tested across SKAB and CWRU.
- The hybrid rules + ML layer named a class on 7: coverage = 7/8 = 87.5%.
- All seven accepted answers were correct: selective accuracy = 7/7 = 100%.
- Across all eight recordings it was correct seven times: overall top-1 =
  7/8 = 87.5%; the abstention counts as not correct for overall top-1.

So “100% selective accuracy” is not the same as “the model is 100% accurate.”
It means “every accepted answer in this tiny run was correct.”

## Every reported metric

| Metric | Plain meaning | Good direction |
|---|---|---|
| `n_trials` | Number of attempted labelled trials. | Larger and more independent is better. |
| `n_scored` | Trials that produced a case and could be scored. | Should be close to trials. |
| `n_detector_missed` | Fault trials that never created an anomaly. | Lower. |
| `n_agent_errors` | Detection happened but triage failed. | Lower. |
| `detection_rate_pct` | Detected trials ÷ all trials. | Higher. |
| `top1_text_pct` | First fault class inferred from root-cause text was correct. | Higher. |
| `top1_citation_pct` | First class inferred independently from cited work orders was correct. | Higher. |
| `hit_any_pct` | True class appeared anywhere in the root-cause text, even secondarily. | Higher, but weaker than top-1. |
| `hedged_pct` | Answer listed multiple competing classes. | Context-dependent; top-1 still matters. |
| `unclassifiable_pct` | Text scorer could not map the answer to the known taxonomy. | Lower. |
| `abstained_pct` | Confidence/signature gate explicitly deferred classification to a human. | Not simply good/bad; on hard data it prevents false certainty. |
| `coverage_pct` | Non-abstained cases ÷ scored cases. | Higher only if selective accuracy stays high. |
| `selective_accuracy_pct` | Accuracy among non-abstained cases. | Higher. Always quote with coverage and n. |
| `scorer_agreement_pct` | Text scorer and citation scorer chose the same class when both produced one. | Higher. |
| `scorer_coverage_pct` | Fraction of scored cases where both scorers produced a class. | Higher; prevents agreement from hiding missing rows. |
| `mean_confidence` | Average calibrated confidence carried by cases in a class. | Meaningful only beside actual accuracy. |
| `ECE` | Weighted average gap between stated confidence and actual accuracy. 0 is perfect. | Lower. |
| `in_labelled_window_pct` | Replay anomaly fired inside the dataset authors' labelled abnormal region. | Higher. |
| `ticks_to_detect` | Feed steps from fault cue to anomaly. At a 3-second interval, multiply by 3 for demo seconds. | Lower, subject to noise/safety tradeoff. |

Other labels visible on the page:

| Label | Plain meaning |
|---|---|
| `synthetic` | Generated, repeatable sensor patterns; useful but easier than real equipment. |
| `real testbeds` | Five recorded SKAB pump episodes plus three recorded CWRU bearing episodes. |
| `mock` | Free scripted decision policy using the real tools and schemas; no external AI call. |
| `live` | Actual paid DeepSeek model calls through OpenRouter. |
| `delta` / `pp` | Live minus mock; `pp` means percentage points. |
| `provider requests` | Individual paid model API calls. One case normally needs several tool-loop turns. |
| `tokens` | Text units sent to and returned by the model. |
| `latency` | Mean wall-clock seconds to finish one case in that evaluation run. |
| `exact cost` | Cost returned by OpenRouter, not a guessed price calculation. |
| `seed` | Number that makes randomized trial order reproducible. |
| `generated` | UTC time when the saved report was produced. |

## Confusion matrix

Rows are the true class. Columns are what the method predicted.

- Diagonal cell: correct.
- Off-diagonal cell: a specific confusion, for example discharge restriction
  being called rotor imbalance.
- `abstained`: system refused to choose because evidence was not separable.
- `unclassified`: scorer could not understand the text; this is different from
  a deliberate abstention.

The evaluation page now shows **operational confusion**, which applies the
abstention gate. The raw draft confusion is retained in the JSON report.

## Calibration and ECE

Calibration asks: when the case says 80% confidence, is it correct about 80% of
the time?

The report groups cases into confidence bands. For each band:

- `states` is mean confidence.
- `actual` is measured top-1 accuracy.
- `gap = actual - stated`.
- Negative gap means overconfidence.
- Positive gap means underconfidence.

ECE combines the absolute gaps, weighted by how many cases are in each band.
ECE 0.239 means an average absolute confidence/accuracy mismatch of about 23.9
percentage points on that tiny run. It does not mean 76.1% accuracy.
The paid DeepSeek real run's ECE was 0.148: about a 14.8-point average mismatch,
still based on only eight cases.

## Current interpretation

### Synthetic, n=24

- Detection: 100%.
- Hybrid classifier: 75.0% overall, 79.2% coverage, 94.7% selective accuracy.
- Full mock system after abstention: 79.2% coverage and 89.5% selective accuracy.
- ECE: 0.207.

The classifier is useful on the clean simulated signatures. The paid DeepSeek
run on the same 24 cases produced 75.0% raw top-1, 75.0% coverage, 94.4%
selective accuracy, ECE 0.319, and no agent errors. Exact spend was not included
in that first report version; this gap caused paid-usage fields to be added.

### Real replay, n=8 across two testbeds

- Detection: 100%.
- Hybrid classifier: 87.5% overall, 87.5% coverage, 100% selective accuracy
  (7 correct accepted answers out of 7; one cavitation abstention).
- Full mock system: 87.5% raw top-1, 87.5% operational coverage, and 100%
  selective accuracy.
- ECE: 0.239.
- Live DeepSeek: 87.5% raw top-1 (7/8), 75.0% operational coverage (6/8),
  100% selective accuracy (6/6), 25.0% abstention, and ECE 0.148.
- Live execution: all 8 rows used `deepseek/deepseek-v4-flash`; 0 errors, 0
  mock fallbacks, 34 provider requests, 161,585 tokens, 32.17 seconds mean
  latency, and $0.014535 exact returned cost.

This shows that the narrow trained layer resolved the frozen restriction pair
without forcing an answer on the remaining cavitation ambiguity. It does not
solve cross-plant predictive maintenance.

## What not to quote

Do not quote historical Sonnet numbers as current, do not turn 6/6 selective
accuracy into “100% real-data accuracy,” and do not compare the LLM's 75%
operational coverage with the classifier's 87.5% without also stating that both
had 100% selective accuracy on a tiny n=8 suite.

## Honest evaluation limitations

- Eight episodes across two laboratory testbeds are too few for general claims.
- The trained restriction test itself is only three physical recordings.
- CWRU episodes concatenate real healthy and faulty steady-state recordings;
  they are not natural fault-onset trajectories.
- Repeating an identical replay measures agent variation, not new real evidence.
- Training, calibration, and test are grouped by physical SKAB experiment.
  Randomly splitting windows from one recording would leak operating-point
  fingerprints and is explicitly not used.
