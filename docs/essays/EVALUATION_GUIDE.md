# The evaluation numbers in simple language, in essay form

## Read the four headline numbers in this order

The first question is the detection rate: did the system notice that something
abnormal had happened at all? The second is overall top-one accuracy: counting
every trial, how often was the first named fault class correct, with abstentions
counted as not correct? The third is coverage: how often did the method feel it
had enough evidence to name a class instead of abstaining? And the fourth is
selective accuracy: among only those cases where it did name a class, how often
was it right?

Take the current real replay suite as a worked example. Eight recordings were
tested across the SKAB and CWRU datasets. The hybrid rules-plus-machine-learning
layer named a class on seven of them, so coverage was seven out of eight, or
87.5 percent. All seven of those accepted answers were correct, so selective
accuracy was seven out of seven, or 100 percent. And across all eight recordings
it was correct seven times, so overall top-one accuracy was seven out of eight,
or 87.5 percent — the abstention counts as not correct for that measure.

This is why "100 percent selective accuracy" is not the same claim as "the model
is 100 percent accurate". It means only that every accepted answer in this very
small run was correct.

## Every reported metric, explained

The metrics fall naturally into a few groups.

Start with the counting metrics. The number of trials is the number of labelled
trials attempted, and larger and more independent is better. The number scored
is the count of trials that actually produced a case and could therefore be
scored, and it should sit close to the number of trials. The number of detector
misses counts fault trials that never created an anomaly at all, and lower is
better. The number of agent errors counts trials where detection did happen but
triage subsequently failed, and again lower is better. The detection rate is
simply detected trials divided by all trials, and higher is better.

Then come the accuracy metrics. The text top-one percentage measures how often
the first fault class, as inferred from the root-cause text, was correct; higher
is better. The citation top-one percentage measures the same thing but with the
class inferred independently from the work orders the system cited, which is a
useful cross-check; higher is better. The hit-any percentage measures how often
the true class appeared anywhere in the root-cause text, even as a secondary
mention — higher is better, but it is a distinctly weaker claim than top-one.
The hedged percentage counts answers that listed several competing classes; this
is context-dependent rather than simply good or bad, and top-one still matters
more. The unclassifiable percentage counts cases where the text scorer could not
map the answer onto the known taxonomy, and lower is better.

Next, the abstention family, which is where most misreadings happen. The
abstained percentage is how often the confidence and signature gate explicitly
deferred classification to a human. That is not simply good or bad; on hard data
it is what prevents false certainty. Coverage is non-abstained cases divided by
scored cases, and higher is better only if selective accuracy stays high
alongside it. Selective accuracy is accuracy among the non-abstained cases, and
it should always be quoted together with coverage and with the sample size,
never alone.

Then there are the two metrics that keep the scorers honest. Scorer agreement is
how often the text scorer and the citation scorer picked the same class in cases
where both produced one; higher is better. Scorer coverage is the fraction of
scored cases where both scorers produced a class at all; higher is better, and
it exists specifically so that a high agreement number cannot hide a pile of
missing rows.

Finally, the calibration and timing metrics. Mean confidence is the average
calibrated confidence carried by the cases in a class, and it is meaningful only
when placed beside the actual accuracy. Expected calibration error, or ECE, is
the weighted average gap between stated confidence and actual accuracy, where
zero would be perfect and lower is better. The in-labelled-window percentage
measures how often the replay anomaly fired inside the region the dataset
authors themselves labelled abnormal; higher is better. And ticks-to-detect
counts feed steps from the fault cue to the anomaly — at a three-second interval,
multiply by three to get demonstration seconds. Lower is better, subject to the
trade-off against noise and safety.

## The other labels visible on the evaluation page

Several words on the page are mode or provenance labels rather than metrics.
"Synthetic" means generated, repeatable sensor patterns, which are useful but
easier than real equipment. "Real testbeds" means the five recorded SKAB pump
episodes plus the three recorded CWRU bearing episodes. "Mock" means the free
scripted decision policy, which uses the real tools and the real schemas but
makes no external AI call. "Live" means actual paid DeepSeek model calls through
OpenRouter.

"Delta" means live minus mock, and "pp" means percentage points. "Provider
requests" counts individual paid model API calls, and one case normally needs
several tool-loop turns. "Tokens" are the text units sent to and returned by the
model. "Latency" is the mean wall-clock seconds to finish one case in that
evaluation run. "Exact cost" is the cost returned by OpenRouter itself, not a
guessed price calculation. "Seed" is the number that makes the randomised trial
order reproducible. And "generated" is the UTC time at which the saved report
was produced.

## How to read the confusion matrix

Rows are the true class and columns are what the method predicted. A cell on the
diagonal is a correct answer. A cell off the diagonal is a specific confusion —
for example, discharge restriction being called rotor imbalance. The "abstained"
column means the system refused to choose because the evidence was not
separable. The "unclassified" column means the scorer could not understand the
text, which is a genuinely different thing from a deliberate abstention.

The evaluation page now shows the operational confusion matrix, which applies
the abstention gate. The raw draft confusion matrix is still retained in the
JSON report.

## Calibration and expected calibration error

Calibration asks one question: when a case says eighty percent confidence, is it
correct about eighty percent of the time?

The report groups cases into confidence bands. Within each band it reports the
stated value, which is the mean confidence; the actual value, which is the
measured top-one accuracy; and the gap, which is actual minus stated. A negative
gap means overconfidence, and a positive gap means underconfidence.

Expected calibration error combines the absolute gaps, weighted by how many
cases fall in each band. An ECE of 0.239 therefore means an average absolute
mismatch between confidence and accuracy of about 23.9 percentage points on that
very small run. It emphatically does not mean 76.1 percent accuracy. The paid
DeepSeek real run scored an ECE of 0.148, about a 14.8-point average mismatch,
and that too rests on only eight cases.

## What the current results say

On the synthetic suite of twenty-four trials, detection was 100 percent. The
hybrid classifier reached 75.0 percent overall accuracy at 79.2 percent
coverage, with 94.7 percent selective accuracy. The full mock system, after the
abstention gate, showed the same 79.2 percent coverage with 89.5 percent
selective accuracy. ECE was 0.207.

The reading is that the classifier is useful on clean simulated signatures. The
paid DeepSeek run over those same twenty-four cases produced 75.0 percent raw
top-one accuracy, 75.0 percent coverage, 94.4 percent selective accuracy, an ECE
of 0.319, and no agent errors. Exact spend was not included in that first version
of the report, and that gap is what prompted the paid-usage fields to be added.

On the real replay suite of eight episodes across two testbeds, detection was
again 100 percent. The hybrid classifier reached 87.5 percent overall at 87.5
percent coverage with 100 percent selective accuracy — seven correct accepted
answers out of seven, with a single cavitation abstention. The full mock system
matched that: 87.5 percent raw top-one, 87.5 percent operational coverage, 100
percent selective accuracy. ECE was 0.239.

Live DeepSeek on the same eight episodes reached 87.5 percent raw top-one, which
is seven out of eight, at 75.0 percent operational coverage, which is six out of
eight, with 100 percent selective accuracy across those six, a 25.0 percent
abstention rate, and an ECE of 0.148. On the execution side, all eight rows used
the `deepseek/deepseek-v4-flash` model, with zero errors and zero mock
fallbacks, across thirty-four provider requests and 161,585 tokens, at a mean
latency of 32.17 seconds and an exact returned cost of $0.014535.

What this shows is that the narrow trained layer resolved the frozen restriction
pair without forcing an answer on the remaining cavitation ambiguity. What it
does not show, and must not be stretched into, is a solution to cross-plant
predictive maintenance.

## What not to quote

Do not quote the historical Sonnet numbers as though they were current. Do not
turn a six-out-of-six selective accuracy into a claim of "100 percent real-data
accuracy". And do not compare the language model's 75 percent operational
coverage against the classifier's 87.5 percent without also saying that both had
100 percent selective accuracy on a tiny suite of eight.

## The honest limitations

Eight episodes across two laboratory testbeds are far too few to support general
claims. The trained restriction test rests on only three physical recordings.
The CWRU episodes are concatenations of real healthy and real faulty
steady-state recordings, which means they are not natural fault-onset
trajectories. Repeating an identical replay measures agent variation rather than
producing new real evidence. And training, calibration, and testing are all
grouped by physical SKAB experiment, because randomly splitting windows drawn
from a single recording would leak operating-point fingerprints — that approach
is explicitly not used here.
