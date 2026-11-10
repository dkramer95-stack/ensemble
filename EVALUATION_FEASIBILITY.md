# Is the Evaluation Feasible? A Decision Memo

**Derek Kramer**  
Independent researcher, Jakarta, Indonesia  
October 2026

## Decision

**Partially feasible.** The workshop paper and the 10-page writing sample are feasible now. A full two-phase evaluation is not feasible in the current setup without a pilot, a budget for provider calls, and human-subjects approval.

The binding constraints are not the code. They are provider quota, wall time, rater time, and access to participants.

## What is feasible now

- The six-page workshop paper, using the existing case and correcting the test claims.
- The ten-page writing sample, with a methods section and explicit limitations.
- A 116-test stdlib suite that already passes in under a second.
- An eight-prompt pilot comparing independent answers, judge-only synthesis, and directed challenge.

The pilot is useful because it measures variance, quota, and time before the full design is committed.

## What is not feasible now

A full model study of 40 prompts, five conditions, and three repetitions is 4,080 model calls if each condition is counted at the call level:

- Independent: 4 calls per repetition.
- Judge-only: 4 calls plus 1 judge.
- Directed: 4 calls plus 1 challenge.
- Broadcast: 4 calls plus 4 rebuttals.
- Self-consistency: 4 models × 3 samples.

At the observed latencies, with Kimi often the slowest provider, the full run is a multi-day job and likely exceeds current subscription quotas. The study design should not promise it until the pilot returns real numbers.

The human study is further away. Thirty participants at 60 to 75 minutes each is 30 to 38 session hours before recruitment, scheduling, compensation, transcription, and analysis. It requires IRB approval and a participant pool that this project does not currently have. It is a three-to-six month project, not an extension of the current week.

## What the pilot should measure

1. Completion rate per condition.
2. Wall time and provider failures.
3. Token use where the provider reports it.
4. Variance in target specificity between repetitions.
5. Whether two raters can score the directed and broadcast outputs without constant adjudication.

The pilot should use eight prompts from the four categories, three conditions, and two repetitions. That is small enough to finish, large enough to expose quota and coding problems.

## Stop and go criteria

Proceed to the full model study only if:

- At least 90% of provider calls complete.
- The pilot finishes within a defined wall-time and quota budget.
- The rubric produces acceptable agreement on the overlap sample.
- The directed and broadcast conditions produce distinguishable argument structures.

If those conditions fail, reduce the design to three conditions, 20 prompts, and two repetitions. A smaller study with a clean measure is better than a large study with missing cells.

Proceed to the human study only if IRB approval, recruitment, and compensation are in place. Do not run an informal convenience sample and call it a user study.

## Recommended path

1. Submit the workshop paper for feedback. It is honest about being a design case.
2. Use the ten-page paper as the PhD writing sample.
3. Run the eight-prompt pilot next, not the full 40-prompt study.
4. Decide on the full study from the pilot data.
5. Start the IRB and recruitment process only if the model-level results justify a human study.

## Bottom line

The project can support a workshop paper and a PhD writing sample today. It cannot support a full TOCHI-style empirical paper today. The difference is not length. It is whether the study has completed the comparison it claims to motivate.

The next honest artifact is the pilot protocol, not another expansion of the manuscript.
