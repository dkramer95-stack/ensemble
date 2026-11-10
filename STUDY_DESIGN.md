# Evaluating Directed Cross-Examination: A Two-Phase Study Design

**Derek Kramer**  
Independent researcher, Jakarta, Indonesia  
October 2026

**Purpose.** This document specifies a study that can test the claims the workshop paper deliberately does not make. It separates a model-level evaluation from a human decision study. The first phase is feasible with the current system and accounts. The second phase requires human subjects review, recruitment, and a larger time budget.

## 1. Research questions and hypotheses

**RQ1.** Does directed cross-examination produce more specific and better-attributed arguments than broadcast debate?

**RQ2.** Does the format change the recommendation, the justification, or the reader's decision?

**RQ3.** What are the cost and latency penalties of each format?

**H1.** Directed challenges quote more target claims and produce fewer unattributed objections than broadcast debate.

**H2.** Readers exposed to a directed challenge are more likely to identify the strongest objection than readers exposed to a broadcast transcript.

**H3.** Directed challenge has lower wall time and fewer model calls than broadcast debate.

H1 and H3 are model-level hypotheses. H2 requires people and therefore belongs to Phase 2.

## 2. Phase 1: model-level study

### Design

The unit is a prompt-condition pair. Five conditions are compared:

1. Independent answers only.
2. Judge-only synthesis.
3. Directed challenge, one challenger against one target.
4. Broadcast debate.
5. Self-consistency, three samples with a majority answer.

The model panel is Kimi, Gemini, DeepSeek, and Codex, held constant within a replication. Each prompt runs three times per condition to estimate variance. A pilot of eight prompts estimates cost, variance, and quota limits before the full run.

### Prompt corpus

Forty prompts are drawn from four categories:

- Factual questions with a checkable answer.
- Design questions with defensible alternatives.
- Policy questions with value disagreement.
- Ambiguous questions with no clear answer.

Category is a blocking factor, not a claim about domain coverage. The prompts and model versions are frozen and archived before data collection.

### Measures

| Construct | Operationalization | Source |
|---|---|---|
| Target specificity | Number of target claims quoted, coded against the target answer | Two blind raters |
| Attribution | Whether each objection names the model and claim it addresses | Two blind raters |
| Argument quality | 5-point rubric: claim, evidence, counterargument, concession, verdict | Two blind raters |
| Correctness | Exact or rubric-scored correctness where ground truth exists | Researcher plus spot-check |
| Cost | Model calls, wall time, tokens where reported | Run artifacts |
| Consistency | Interface, report, and judge agree on the same result | Artifact audit |

Two raters score a 25% overlap sample. Report Cohen's kappa or ICC. Disagreements are resolved by discussion, and the unresolved rate is reported.

### Analysis

The primary model is a mixed-effects model with condition as a fixed effect, prompt category as a fixed effect, and prompt and model as random intercepts. Report estimated marginal means, 95% confidence intervals, and standardized effect sizes. The study is preregistered before the full run. The pilot is used to revise the rubric, not to test hypotheses.

## 3. Phase 2: human decision study

### Design

A within-subject study with 24 to 36 participants. Each participant sees four reports: independent answers, judge-only, directed challenge, and broadcast debate. Order is counterbalanced. Each report is paired with a decision task that has a defensible recommendation and one material caveat.

### Participants

Recruit practitioners who make technical or product decisions and have no stake in the model vendors. Screening excludes people who have worked on this project. Compensation follows local norms. Target 30 completed participants, with a stopping rule based on the preregistered sample-size calculation.

### Measures

- Decision accuracy against an expert-defined rubric.
- Time to decision.
- Confidence and trust calibration.
- Ability to identify the strongest objection.
- Perceived auditability and cognitive load.
- Preference and free-text rationale.

### Procedure

Each session lasts 60 to 75 minutes. Participants read four reports, answer comprehension checks, make a decision, and complete a short exit interview. Think-aloud is optional and analyzed separately. Sessions are recorded only with consent.

### Analysis

Mixed-effects models with condition, order, and task as fixed effects and participant as a random intercept. Report effect sizes and confidence intervals. Predefine the primary outcome as correct identification of the strongest objection. Secondary outcomes are exploratory and labeled as such.

## 4. Feasibility

A pilot for Phase 1 is feasible now. The full Phase 1 run is feasible only if the pilot confirms that provider quota and wall time are manageable. The system can run the conditions, the artifacts are already structured for coding, and the main constraint is provider quota and wall time. A rough full run is 40 prompts × 5 conditions × 3 repetitions, with some conditions making one call and others making four. That is a multi-day run and may exceed current subscription limits. The pilot is designed to measure that before committing.

Phase 2 is conditionally feasible. It requires IRB approval, recruitment, compensation, and a secure way to present reports without exposing model identities. That is a three-to-six month project, not a weekend extension. The current single-user setup has no participant pool.

All prompts, code, rubrics, and de-identified ratings will be released with the paper. The model phase involves no human subjects; the human phase requires informed consent and the right to withdraw.
