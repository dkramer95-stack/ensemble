# Directed Cross-Examination in Heterogeneous Multi-Model Agent Systems

## A Design-Science Case Study

**Derek Kramer**  
Independent researcher, Jakarta, Indonesia  
October 2026

**Abstract**

On 20 October 2026 I sent one question to four agent CLIs. Kimi, Gemini, DeepSeek, and Codex all said yes. Their answers ran between 232 and 329 characters, and each used the same three pieces of evidence: shared code, atomic commits, and one CI pipeline. A judge later called the four answers "near-identical in substance." Despite that agreement, the models relied on different assumptions about what a monorepo is, whether headcount should decide the question, and how much blast radius five people can tolerate.

I built a local system, `ensemble`, to make that disagreement visible. It runs the same prompt through four providers, stores every response and raw stream, and then supports either a directed cross-examination, where one model attacks one other model's answer, or an open debate, where every model sees every answer. The account covers the exchanges and the failures that followed. The directed challenge produced a target-specific critique in 32.1 seconds and 1,202 characters. The broadcast debate produced four rebuttals in 145.8 seconds and broad convergence. A state error exposed a gap in the evidence pipeline: the interface showed rebuttals that the report and judge could not see. The judge's complaint exposed it.

This design-science case study documents one deployment. The work contributes a design account, a protocol, a failure taxonomy, and five propositions. The expanded version specifies the protocol formally, with an artifact model, message schemas, a state machine, and numbered invariants; it organizes the failure evidence into a fourteen-class taxonomy, compares the system with adjacent kinds of multi-model system, states seven design principles with their evidence and their limits, gives a cost and latency model built from the observed timings, and sets out the controlled study the case cannot supply. It does not establish that debate improves decision quality. One prompt, one user, and no repeated trials cannot support that claim. The expansion adds structure and argument, not new evidence.

**Keywords:** multi-agent debate, large language models, agent orchestration, design science, case study, local-first software, human-AI decision support

## 1. Introduction

### 1.1 A run that agreed too well

I asked whether a five-person startup should use a monorepo, yes or no, with a justification under 50 words. I expected disagreement but received four similar recommendations. Kimi, Gemini, DeepSeek, and Codex all said yes. Their justifications repeated the same benefits. Their explanations differed in emphasis.

That kind of agreement is easy to mistake for confidence. A person comparing models might conclude that the answer is obvious. The run did not support that conclusion. The models used different definitions of a monorepo. DeepSeek treated a monorepo as one repository and one CI setup. Kimi treated it as a coupling decision that increases blast radius. Codex treated it as conditional on having several related services. Gemini treated it as a way to reduce multi-repository overhead.

Comparing independent answers still requires the reader to identify and test each justification. A synthesis pass can compress the pile into a paragraph, but compression hides the conflict. If the judge says "all four agree," it has not told the reader where the agreement is real and where it is a shared assumption.

The first version of the system did what most comparison tools do. It ran the models in parallel, displayed the answers side by side, and offered a synthesis. Readers could compare which answer was clearest, but testing the reasoning required a second phase in which models challenged one another.

### 1.2 Argument as a design problem

Multi-agent debate research has shown that interaction can improve reasoning and factual accuracy (Du et al., 2023; Liang et al., 2024). It has also shown that debate can help a non-expert judge identify a truthful answer (Irving et al., 2018; Khan et al., 2024). Most of that work uses controlled tasks, homogeneous model access, and centralized APIs. The models are usually instances of the same base model or models called through the same interface. The prompts are designed for the experiment, and the evaluation is designed around a benchmark.

A practitioner's setup looks different. The four models arrive as separate agents with separate logins, separate quotas, separate tool policies, and separate output formats. They may change underneath the system. One provider runs out of credit. Another loses an OAuth session. A third rejects a free tier that used to work. The comparison layer has to survive all of that before it can ask whether the models argue well.

The first debate design followed the research pattern. Every model received every answer and wrote a rebuttal. It was a broadcast. The format left the target of each rebuttal unspecified. Each model chose a convenient target. Several rebuttals made the same point. The reader had to reconstruct who was responding to whom. The exchange took two minutes and twenty-six seconds.

The correction came in one sentence: "take Kimi and have it argue against DeepSeek's answer." I changed the system to support one challenger addressing one target answer in a single response. That constraint made the argument easier to attribute and cheaper to run. The rest of the paper examines what the change bought and what it cost.

### 1.3 Research questions

I organized the inquiry around three questions.

**RQ1.** Which architectural and interaction choices make heterogeneous agent CLIs comparable, inspectable, and usable as a multi-model argument system?

**RQ2.** How does directed cross-examination differ from broadcast debate in cost, argument specificity, and auditability?

**RQ3.** Which failures dominate local-first multi-model orchestration, and what do they imply for design?

These questions concern design and practice. They do not ask whether debate makes a model more accurate. The record can show what the system did, what broke, and what the artifacts contain. It cannot establish a causal effect on decision quality.

### 1.4 Contributions

The main contribution is the architecture and the protocol that sits on top of it. `ensemble` wraps four CLIs behind a stable result interface, keeps the first round independent, stores canonical artifacts, and treats argument as a separate call. The directed protocol is short enough to describe in a page and specific enough to audit.

The second contribution is the failure analysis. Building the system exposed a state error that made the interface and the judge disagree about the same run. That error, along with the authentication and operating-system failures around it, says more about the design problem than a feature list would.

The research agenda is smaller: blind judging, structured claims, target responses, and a controlled evaluation. Those are pieces the current work cannot supply.

The expanded version adds a second layer of contribution that is analytical rather than empirical. It states the protocol as a specification: five artifact classes, four message schemas, a run state machine, and numbered invariants that the implementation either enforces or does not. It turns the failure table into a taxonomy with a layer, a trigger, a symptom, a detection method, and a mitigation for each class, and it records which classes the case exposed directly and which it did not. It compares the design with four adjacent kinds of multi-model system and states where the comparison cannot be settled without data. It gives seven design principles in full, each with the failure that produced it and the observation that would weaken it. It builds a cost and latency model from the measured calls and timings, with the assumptions written down and the missing quantities left missing. It specifies a controlled study that could test the propositions, and it lists what a third party would need to reproduce the case and what has already drifted beyond reproduction.

Those additions are derivations from the same material. They add no runs, no prompts, no timings, and no citations. Where a section needs a quantity that the case never measured, it says so and marks the gap instead of filling it.

### 1.5 Scope

The system ran on one macOS machine and used four provider accounts. The analysis focuses on one four-model prompt, two directed challenges, and supporting evidence from 38 run directories. The findings are analytically generalizable to the design problem, not statistically generalizable to other models, tasks, or users. I did not measure answer correctness, user trust, or decision quality.

The expanded version keeps that evidence base fixed. The formal specification, the taxonomy, the comparison, the principles, the cost model, the study design, the ethics analysis, and the replication package are all derived from the same run, the same code, and the same observed failures. None of them adds a trial. A reader who wants the shortest version can read Sections 1 through 6, the failure taxonomy in Section 7, and the discussion and conclusion in Sections 12 and 16. The later sections exist because a design-science account of a protocol has to say what the protocol is, where it breaks, and what would count as evidence against it.

## 2. Related Work

### 2.1 Debate for reasoning and factuality

Du et al. (2023) had multiple instances of a language model propose answers and reasoning, read one another's responses, and revise over several rounds. Across arithmetic and strategic reasoning tasks, the debate procedure improved performance over individual generation. The authors treated the models as black boxes and used the same procedure across tasks, which made the approach easy to transfer to proprietary systems. The result established a baseline: interaction among model instances can change the final answer.

Liang et al. (2024) found a failure mode they called degeneration of thought. Once a model commits to an answer, self-reflection may not produce a genuinely different alternative. Their multi-agent debate framework put agents into a "tit for tat" exchange and used a judge to manage it. They reported that adaptive termination and a moderate level of conflict were necessary for good performance. They also warned that a judge from a different model family might not be fair.

Wang et al. (2023) offered a non-interactive comparison. Self-consistency samples several reasoning paths and selects the most consistent answer. It improves chain-of-thought performance without any model seeing another model's output. Aggregation alone can help. Debate adds interaction, role asymmetry, and a textual record. The project cares about the record as much as the answer.

### 2.2 Debate for oversight

Irving et al. (2018) proposed debate as a scalable oversight mechanism. Two agents argue opposing positions, and a human or model judge decides which case is more convincing. The setting assumes that the judge cannot directly verify the answer and must evaluate the arguments. Khan et al. (2024) tested a version of that idea with stronger and weaker models. Two expert models debated; a weaker non-expert model or a human judged. Debate raised judge accuracy to 76% for non-expert models and 88% for humans, against naive baselines of 48% and 60%. Optimizing the debaters for persuasiveness improved the judge's ability to find the truth.

Those results support a design intuition: the judge and the roles matter as much as the models. They also carry a warning. A debate can persuade a judge without establishing truth. The work does not test truth. It asks whether a directed challenge produces a record a reader can audit.

### 2.3 Judges and evaluation

Zheng et al. (2023) evaluated strong language models as judges on open-ended questions. The judges agreed with human preferences more than 80% of the time in their setting, but the paper documented position bias, verbosity bias, self-enhancement bias, and limited reasoning. A judge can reward confidence or length for reasons unrelated to correctness. The judge here, DeepSeek, was also one of the four participants. That creates a self-preference risk I cannot rule out.

Chan et al. (2023) moved evaluation into a multi-agent debate. ChatEval uses a team of model referees that discuss and score generated responses. The work treats evaluation as an argument among evaluators rather than a single score. It also makes a design point that matters here: the evaluation protocol is part of the system, not an afterthought.

### 2.4 Orchestration frameworks

AutoGen (Wu et al., 2023) provides a general framework for composing conversable agents with tools, humans, and code. It supports flexible conversation patterns and demonstrates applications in mathematics, coding, question answering, and operations research. ChatEval similarly composes multiple model agents into an evaluation team. Both show that multi-agent patterns can be programmed and reused.

They do not solve the problems the system ran into. A framework assumes that agents are addressable through a common interface. These agents are vendor CLIs with different authentication flows, different tool policies, different quota systems, and different output formats. A framework also assumes that the state of a conversation is available to every component that needs it. The failure shows what happens when that assumption breaks: the interface, report, and judge can tell different stories about the same run.

### 2.5 The gap

The literature says a lot about whether debate improves benchmark performance. It says less about how to build a debate system around agents that were not designed to talk to one another. Four practical questions remain.

How should a system wrap heterogeneous CLIs without erasing their differences? How should argument be scoped when the goal is auditability rather than accuracy? How should state be represented so that every view of a run agrees? Which failures dominate when the system runs locally rather than as a hosted service?

The study addresses those questions through a design artifact and a failure analysis. It does not propose a new debate algorithm. It proposes a way to organize argument as an inspectable layer over heterogeneous execution.

## 3. Method

### 3.1 Design science and the case

I treated the system as a design artifact and studied it in use. Design science research treats an artifact as both a response to a practical problem and a source of design knowledge (Hevner et al., 2004). The artifact here is `ensemble`: its architecture, protocols, artifact model, and interface. The evaluation is formative. I asked whether the design behaved as intended, which failures appeared in practice, and which principles the evidence supported.

The case study follows the reporting guidance of Runeson and Höst (2009). The unit of analysis is the system in use, with two focal runs and supporting operational evidence. I treat it as an instrumental case: the point is to learn about the design problem, not to document every feature. Analytic generalization, not statistical generalization, is the goal.

I did not run a controlled experiment. I did not randomize prompts, repeat runs, blind judges, or collect human ratings. Those are limitations, and Section 13 treats them as such.

### 3.2 Context

The system was built and used by one researcher on a macOS workstation between 19 and 25 October 2026. The final provider set was Kimi, Gemini, DeepSeek, and Codex. Claude was in the first build and came out after its OAuth session expired. Gemini needed an AI Studio API key after Google rejected the free Code Assist tier for CLI clients. The accounts and model versions changed during development, which limits comparisons across dates.

The system is a Python command-line engine and a local HTTP server with a browser interface. It runs each provider as a subprocess, stores every response and raw stream in a run directory, and renders an HTML and Markdown report. A launchd agent keeps the server alive. A small application in `~/Applications` opens the interface from the Dock.

### 3.3 Data

At the time of analysis, the run directory held 38 run directories. I used four kinds of material.

The focal run, R1, is a four-model comparison on the monorepo prompt from 20 October 2026. It contains four initial answers, four open-debate rebuttals, a judge report, timing data, token counts where the provider reported them, and raw stdout and stderr. Two directed challenges were added to R1 on 25 October 2026. C1 is Kimi arguing against DeepSeek. C2 is Gemini arguing against Codex. C2 is a within-case replication of the format with a different pair.

The operational evidence includes CLI error messages, launchd logs, installation scripts, screenshots, and the source code. The remaining run directories are user-generated comparisons and earlier tests. I used them to check whether a failure was unique to the focal run, not as a balanced sample.

The focal prompt was chosen because all four models answered successfully and all four participated in the argument layer. That makes the run informative about the intended use. It also introduces selection bias: the run does not show what happens when several models fail or when the prompt has no clear answer.

### 3.4 Measures and analysis

I measured wall-clock time, per-provider latency, success and failure status, and output length. Those are descriptive and single-run. I did not treat them as benchmarks.

For the arguments, I checked whether a response named its target, quoted specific claims, offered counterarguments, conceded a point, and ended with a verdict. The directed prompt asks for those features, so the check is about protocol compliance, not argument quality. A response can satisfy the format and still be wrong.

The central consistency measure was simpler. Did the interface, the report, the judge input, and the saved artifacts agree about the run state? When they did not, I traced the disagreement to the code or the operating system.

The analysis proceeded in four passes. I extracted metadata and timings from the run directories. I read the initial answers, rebuttals, challenges, and judge reports against the protocol. I traced each inconsistency to its source. I compared the directed and broadcast formats on cost, target specificity, and auditability. The comparison is illustrative. There is one open-debate run, two directed challenges, and no repeated trials.

### 3.5 Position and ethics

I built the system and wrote this account, which creates an obvious risk of confirmation bias. I tried to reduce it by preserving raw artifacts that can contradict the narrative, by including failures that required code changes, and by quoting the judge when it disagreed with the system's presentation. I did not use an independent coder or a second analyst. The design conclusions are informed interpretation, not independent verification.

The study involved no human subjects. The prompts and outputs are model-generated and generic. API keys and credentials remain local and are not reproduced. The tool sent prompts and outputs to the model providers, as any use of those CLIs would. Model outputs can be wrong, and nothing in this paper should be read as factual advice.

### 3.6 Case boundaries and selection

Three things bound the case. The prompt was chosen because all four models answered it and because the initial answers exposed a disagreement about reasoning rather than a disagreement about the recommendation. That makes it a useful case for studying argument, but it is not a representative sample of tasks. A factual question with a verifiable answer, or a question where the models split on the recommendation, would produce a different case.

The provider set was whatever worked on this machine during the study window. Kimi, Gemini, DeepSeek, and Codex were available. Claude was removed after its OAuth session expired, and no attempt was made to replace it with a comparable model. The panel is a convenience sample, not a balanced benchmark panel. The paper describes the panel; it does not claim that the panel represents the model population.

The time window was 19 to 25 October 2026. Provider accounts, model aliases, and quotas were not held constant. A run on 20 October is not directly comparable to a run on 25 October even when the prompt is identical. I use the focal run for the case narrative and the later challenges to examine the argument format. I do not pool timings across dates.

I excluded runs that contained personal prompts, runs that failed before producing any answer, and runs from earlier versions of the argument protocol. The remaining 38 run directories provide context, but the analysis does not treat them as a corpus of independent trials. The unit of analysis is the system in use, with the run directory as the main evidence container and the argument artifact as the main object of inspection.

The selection creates an obvious bias. A prompt that produced four successful answers makes the system look more reliable than a prompt that produced three failures. A prompt that produced a clear disagreement makes the directed challenge look more useful than a prompt where all four answers are correct and similar. I chose the case for what it can reveal about design, not for what it can reveal about average performance.

## 4. System Design

### 4.1 Architecture

The system separates execution from argument. The orchestrator takes a prompt and a set of providers, launches each provider in parallel, applies a timeout, and records the result. The first round is independent: no provider sees another provider's answer. The outputs are normalized into a canonical run store. The argument layer reads that store, constructs one or more argument calls, and writes the results back. The judge, the report, and the interface are readers over the store.

Figure 1 shows the flow. The boundary between execution and argument matters. Execution produces evidence. Argument consumes evidence. The judge consumes both. Every layer reads or writes the same artifacts, which is why a mismatch between layers shows up as a contradiction.

The diagram is a logical view, not a deployment diagram. The orchestrator, HTTP server, and report writer share one Python process. The providers run as child processes. The run store is a directory, not a database, and the browser is an HTTP client with no persistent connection. That simplicity made the system easy to inspect. It also meant that a bug in one reader could look like a bug in the model.

The interface between layers is narrow. The orchestrator returns a list of results and a status. The argument layer takes a challenger result and a target result. The report takes the results, any argument records, and the judge. Only the adapter reads the provider's raw stream. That contract is what lets a directed challenge run against an old run without executing the four initial models again.

The cost of that design is that the run directory becomes an API. Once another tool reads `results.json` or `challenges.json`, the format has to stay compatible or be migrated. I kept the format additive during the case: new fields such as `debate` and challenge records appeared, but existing fields kept their meaning. An older run without a challenge still renders; a newer run with one can be read by an older reader as long as the reader ignores unknown fields. That is a small compatibility policy, not a formal schema, and a production system would need the formal version.

![System architecture](docs/case-architecture.png)

*Figure 1. Architecture of the heterogeneous multi-model debate system. Round 1 is independent and parallel. The directed challenge is the primary argument mode; open debate and the judge are optional. Canonical artifacts are the interface between execution, argument, and presentation.*

### 4.2 Provider adapters

I wrapped the vendor CLIs rather than calling four model APIs. That choice kept the agents' existing logins, tool policies, and quota arrangements, but it moved the integration burden into the adapter layer. Each provider has a different command, a different authentication state, and a different error vocabulary.

**Table 1. Provider integration matrix**

| Provider | Invocation | Authentication | Model used | Observed failure |
|---|---|---|---|---|
| Kimi | `kimi` CLI | Moonshot account | `kimi-code` | 429 errors for insufficient balance on the default account |
| Gemini | `gemini` CLI | Google OAuth or AI Studio API key | `default` | `IneligibleTierError` for the free Code Assist tier in CLI mode |
| DeepSeek | `dsh --profile headless` | Patched desktop account or API key | `deepseek-flash` | Authentication and patch fragility |
| Codex | `codex exec` | ChatGPT account | `default` | No blocking failure observed in the focal run |

Claude was part of the first build and was removed after its OAuth session expired. Its absence is part of the story, not a missing row in the final design. The four remaining providers were chosen because they worked, not because they formed a balanced panel.

The adapter does four things. It builds the provider-specific command, supplies the working directory and timeout, captures stdout and stderr, and normalizes the output into a `Result` object. That object carries key, label, model, status, text, elapsed time, token count when available, cost when available, error, and hint. The argument layer uses the same object for challenges and rebuttals.

### 4.3 The first round

Every model receives the same prompt and a separate working directory. The default context mode is an empty temporary directory. A copy mode gives each model a snapshot of a project. A current-directory mode runs in place when the task requires it. No model sees another model's output before the first round ends.

This has two costs. A model cannot build on another model's useful evidence, and the argument phase waits for every initial call. The benefit is comparability. A first answer is a response to the prompt, not to another model's framing. For a comparison tool, that independence is what makes the answers evidence about the prompt.

Providers run in parallel. A timeout or cancellation kills the process group. A provider failure becomes a failed result, not a failed run. Claude's expired session, Kimi's 429, and Gemini's tier error each produced one error while the other providers answered. The report kept the provider's own error text.

### 4.4 Run artifacts

Each run writes a directory with a prompt file, metadata, results, per-model markdown, raw stdout and stderr, optional debate and challenge files, a judge report, and an HTML and Markdown report. The redundancy is deliberate. Markdown is for reading, JSON is for programs, and raw streams are for debugging. The report is generated from the results, not from a separate copy of the conversation.

The canonical object is the `Result`. A run holds a list of results, and a debate or challenge attaches to the result it belongs to or lives in a separate challenge record. The report writer, judge builder, and interface read those objects. One representation should feed every view. Section 6.4 shows what happened when it did not.

The directory is also the unit of reproduction. A reader can inspect the prompt, the exact output, the timing, and the error without access to the original process. The report can be regenerated. A judge can be rerun. A challenge can be added to an old run without rerunning the four initial models.

### 4.5 The argument layer

The argument layer has two modes. The primary mode is directed cross-examination. One challenger receives the original prompt, the target model's initial answer, and its own initial answer. It is told to quote the two weakest claims in the target, explain why they fail, give counterarguments or missing evidence, state what a better answer would conclude, concede where the target may be right, and end with a verdict. One model, one target, one output.

The secondary mode is open debate. Every successful model receives every initial answer, with its own answer marked. It attacks the strongest claim it thinks is wrong, defends or corrects its own answer, and states its position. Open debate is opt-in. It is broader and more expensive.

Call count matters, but attribution matters more. A directed challenge creates attribution. The output has a named attacker and a named target. A reader can put the challenge next to the target answer and decide whether the attack landed. An open debate creates a group discussion. Each model may attack the easiest target, and the reader has to reconstruct the exchange.

![Kimi cross-examines DeepSeek's monorepo answer](docs/case-challenge-focus.png)

*Figure 2. A directed cross-examination in the web interface. Kimi attacks two claims in DeepSeek's answer, concedes one point, and ends with a verdict. The result is also saved as a Markdown artifact and included in the report.*

### 4.6 Judge and report

The judge is optional. It receives the initial answers, any open-debate rebuttals, and any cross-examinations. It compares positions, identifies strong and weak claims, notes who changed position, and says what to trust where. The judge is a reader with a different prompt, not a source of truth. Its output is stored as `judge.md` and shown in the interface.

The report is generated from the same results and artifacts. It has a summary table, per-model cards, optional rebuttal sections, cross-examination sections, and the judge. The web interface is a live reader over the run store, not a separate database. That kept the system inspectable, but it made the state model critical. If the interface and the report derived state differently, they could disagree.

### 4.7 Local deployment

The server binds to localhost. A launchd agent starts it at login, and a Dock application opens the browser interface. The runtime is copied to `~/.ensemble/app` because macOS privacy controls prevented the launchd agent from reading the source directory in Documents. The installer writes a LaunchAgent, a desktop shortcut, and a Dock entry.

The local-first choice has clear benefits. Prompts and responses stay on the machine, the user does not depend on a hosted account, and the CLIs can use existing subscriptions. It also has costs. The system has to handle macOS privacy permissions, application bundles, launchd state, and code signing. Those costs appear in the failure analysis because they took more time than the argument protocol.

### 4.8 Design principles in brief

Table 2 lists seven principles the work supports. They come from one deployment, not from a universal theory. Section 9 develops each principle in full, with the failure that produced it, the code that implements it, and the observation that would count against it; this subsection gives the compact form.

**Table 2. Design principles derived from the case**

| ID | Principle | Rationale | Evidence |
|---|---|---|---|
| DP1 | Wrap heterogeneous agents behind a stable result interface | Provider differences should not leak into the comparison layer | Four CLIs with different auth and output formats produced comparable results |
| DP2 | Keep the first round independent | Independence prevents anchoring and makes initial answers comparable | Four initial answers were generated before any argument call |
| DP3 | Make canonical artifacts the interface between layers | One representation prevents the UI, report, and judge from diverging | The split-state bug disappeared after the result object became canonical |
| DP4 | Treat argument as post-processing, not as part of generation | The initial answer should be complete before it is contested | Challenges can be added to an old run without rerunning the initial models |
| DP5 | Give every argument an explicit target and role | Attribution makes the attack auditable and reduces group-discussion drift | Directed challenge produced target-specific claims in 32.1 seconds |
| DP6 | Treat local-first deployment as an operating-system project | Privacy, launchd, app bundles, and Dock behavior are first-order costs | Multiple failures occurred outside the model layer |
| DP7 | Use the judge as a consistency check as well as an evaluator | A judge that reads the saved evidence can expose missing data | The judge reported that the rebuttal round was absent from the record |

### 4.9 Implementation notes

The implementation is deliberately small. The engine is a single Python file built on the standard library. The server uses `ThreadingHTTPServer`, and each run launches provider processes through `subprocess.Popen` with a new process group. A timeout or a cancellation kills the group rather than the immediate child, which matters when an agent CLI starts its own subprocesses. The report renderer, artifact writer, and provider adapters share the same `Result` type.

A run moves through a small state machine: starting, running, judging, finalizing, and a terminal state of done, partial, error, or cancelled. The open-debate variant adds a debating state. A directed challenge is handled separately because the initial run has already finished. The challenge manager appends the challenge record, writes the report, and exposes the record through the same run endpoint. The interface polls that endpoint rather than holding a WebSocket connection.

The small stack made the failures easier to trace. When the report and judge disagreed, I could inspect `results.json`, the raw streams, and the report writer without searching through a framework. The same choice imposed limits. There is no streaming, no queue, no concurrency cap beyond the provider count, and no background worker that survives a server restart. A challenge that is running when the server stops is lost. For a single-user local tool, those limits were acceptable. For a shared service, they would not be.

The provider adapters do more work than their size suggests. Each one builds a command, supplies environment and working directory, captures both output streams, detects timeouts, and parses the provider's final text. The parsers are heuristic because the CLIs do not share an output schema. The raw streams remain in the run directory so that a parsing mistake can be corrected later. The adapter boundary is where most of the integration risk lives, which is why the provider table is part of the design account rather than an appendix.

### 4.10 The system in operation

`ensemble` has two surfaces. From a terminal, it is a command that runs once and returns a report path. From a browser, it is a small local service over the same run model. Both use the same engine and artifact format. The difference is how much of the process the user wants to watch.

#### 4.10.1 Command surface

The default command takes a prompt and runs every authenticated provider. `--only` and `--skip` narrow the panel. `--model provider=model` overrides a model alias. `--timeout` sets the per-provider limit. `--context temp|copy|cwd` chooses the working-directory mode. `--judge` adds synthesis, `--debate` adds the open round, `--out` changes the run location, and `--open` opens the report. `--json` returns a machine-readable record for scripts. `--strict` turns a provider failure into a non-zero exit code. `--dry-run` prints the commands without running them.

The command surface grew around repeated use. `challenge` takes an existing run and two provider keys. `judge` re-synthesizes an existing run. `doctor --probe` checks authentication by sending a one-word prompt. `providers` lists the detected configuration. `web` starts the local server. `last` opens the newest run. These are small affordances, but they separate a one-shot comparison from a tool a person can use repeatedly.

The CLI and the web interface do not share identical defaults. The web composer enables synthesis by default; the CLI requires `--judge`. That inconsistency is a product decision, not a research finding. It reflects two different use cases: a browser user who wants a complete report, and a terminal user who may want only the raw answers.

#### 4.10.2 Run lifecycle

A run begins in `starting`. The orchestrator launches the provider processes and moves to `running` once the first call is in flight. If open debate is enabled and at least two initial answers succeeded, the run moves to `debating` after the first round. It then moves to `judging` if synthesis was requested, or to `finalizing` if not. The terminal states are `done`, `partial`, `error`, and `cancelled`.

The terminal state is not simply "the process exited." A run is `done` only when every initial result and every open-debate result is successful. A single provider failure produces `partial` if at least one answer succeeded, and `error` if none did. That distinction matters in the interface: a partial run still has a report, and a challenge can still target a successful answer.

Cancellation is allowed while the run is `starting`, `running`, or `debating`. The system marks the run as `cancelling`, kills the provider process groups, and settles into `cancelled`. A cancelled run keeps whatever results were already written, which is why the artifact directory is still useful after a stop.

A directed challenge is not a run state. It starts after the initial run has finished and is tracked as a separate challenge record. A run can be `done` while a challenge is running. The interface accounts for that by treating "run is busy" as either an active run state or a running challenge. The separation is deliberate: the initial evidence should not be rewritten every time someone adds an argument.

#### 4.10.3 Web interface

The browser interface has a history rail, a composer, a readiness list, a run view, a challenge bar, four panes, a challenge section, and a judge section. The composer carries the prompt, provider toggles, context mode, timeout, open-debate toggle, synthesis toggle, and judge provider. The readiness list shows which providers are authenticated but does not block a run.

The run view is a live reader. It polls the run endpoint roughly every 700 milliseconds. It does not use a WebSocket and does not maintain a second database. The panes show status, elapsed time, token counts where available, the cleaned answer, expand and copy controls, and any open-debate rebuttal. When a challenge is running, the challenge bar disables its button and the interface shows a skeleton in the challenge section.

The Cross-examine bar appears after the initial run is terminal and at least two providers have successful answers. If Kimi and DeepSeek are both available, it defaults to that pair. The selects are ordinary HTML selects, not a model browser. The button starts a challenge and then polls until the challenge record is available.

The interface is not a chat. It does not accept a follow-up prompt, a correction, or a free-form question to a single model. It is a control panel over a run directory. That restriction keeps the state model small and makes the evidence easier to compare.

#### 4.10.4 Storage and recovery

Runs live under `~/.ensemble/runs/<run-id>`. The newest run is linked at `~/.ensemble/latest`. Each run contains the prompt, metadata, normalized results, per-model markdown, raw streams, optional debate and challenge files, the judge output, and the report. A challenge writes a new record and regenerates the report without rerunning the initial models.

The run directory is durable in a way the process is not. A challenge can be added to a run created days earlier because the challenge builder needs only the prompt and the saved initial answers. A server restart loses any challenge that was in flight, but it does not lose the completed runs. The LaunchAgent restarts the server; the run store is already on disk.

The storage model is not transactional. Files are written directly, and a crash can leave a partial run. The directory remains inspectable, but there is no rollback. For a personal tool, that is an acceptable tradeoff: a partial artifact is often more useful than a missing one. For a production system, it would need atomic writes, a lock, and a migration policy.

#### 4.10.5 Limits

The implementation is single-process, single-user, and local. There is no authentication, no queue, no rate limiting, and no multi-tenant isolation. The HTTP server is bound to 127.0.0.1. The provider parsers are heuristic because the CLIs do not share an output schema. The interface polls instead of streaming. A provider that changes its output format can break the adapter until the parser is updated.

Those limits are consistent with the artifact's purpose. `ensemble` is a research instrument and a personal comparison tool, not a hosted service. The design keeps the state model simple enough to inspect, which is the property the case needed most.

## 5. Protocol

### 5.1 Initial round

The initial prompt is passed unchanged to each provider. The context mode determines what else the provider sees: an empty directory, a copy of a project, or the current directory. I did not add model-specific instructions in the first round. That keeps the answers comparable and makes provider differences visible.

### 5.2 Directed cross-examination

The directed prompt has four parts: the original prompt, the target answer, the challenger's own answer, and the instructions. The target answer is included because the challenge has to be grounded in what the target said. The challenger's own answer is included for consistency, not as the main content. The instructions are narrow:

```text
You are Kimi. The original prompt was:
[prompt]

--- DeepSeek's answer (the target) ---
[target answer]

--- Your own initial answer ---
[challenger answer]

Argue directly against DeepSeek's answer. Do not restate your own answer
as the main body and do not write a generic essay. Do exactly three things:
1. Quote the two weakest claims in DeepSeek's answer and explain precisely
   why they fail.
2. Give the strongest counterargument or missing evidence for each.
3. State what a better answer would conclude, and where you concede the
   target may be right.

Max 300 words. End with a line starting "Verdict:".
```

The constraints carry a theory of useful critique. Quoting forces the challenger to engage with the target's text. Two claims create a bounded comparison. The concession clause reduces one-sidedness. The verdict gives the reader a compact object to accept or reject. The word limit keeps the challenge from turning into a second essay.

### 5.3 Open debate

The open-debate prompt gives every successful model every initial answer, marks the model's own answer, and asks it to attack the strongest claim it thinks is wrong, defend or correct its own answer, and state its position. It is broader than the directed prompt and runs once per participating model. That makes it more expensive and less attributable.

### 5.4 Judge

The judge receives the initial answers and any argument artifacts. It is asked for a bottom line, areas of agreement and disagreement, a model-by-model assessment, and guidance on what to trust where. When rebuttals or cross-examinations exist, it is told to note who changed position. The judge is not blinded to model identity. Section 13 discusses what that means for the claims.

### 5.5 Stopping rule

The system uses one argument round. A second round would add cost, latency, and more chances for models to converge on a polite compromise. The first round tests whether the challenge changes the answer or the justification. If it does not, a second round is unlikely to change the conclusion. That is a design choice, not an empirical finding.

### 5.6 What the protocol leaves open

A protocol is also a set of omissions. The directed prompt says to quote the two weakest claims, but it does not define "weakest." The challenger decides whether a claim is weak because it is false, because it is unsupported, because it is irrelevant, or because it is stated too strongly. That ambiguity gives the model room to exercise judgment, and it also makes the output harder to score.

The prompt does not require external evidence. A challenger can produce a confident counterargument without checking a source. In the monorepo case, the disagreement was mostly about definitions and tradeoffs, so the absence of retrieval did not dominate. In a factual question, it would. The protocol is designed for reasoning disputes, not for verification.

The target never replies. A directed challenge is one-way by design, which keeps the cost low and the attribution clear. It also means the challenge is tested against the target's initial answer, not against the target's best defense. A two-call exchange would answer a different question: does the challenge survive a response? The current system cannot answer that.

The judge sees model identities. The challenger sees the target's identity. Both facts shape the rhetoric. A blind version would be a different experiment, and likely a better one for measuring argument quality. The current design keeps identities visible because the product is a comparison tool, where knowing which model said what is part of the point.

### 5.7 The artifact model

A protocol stated as prose is a description. A protocol stated as artifacts, messages, transitions, and invariants is a specification, because a reader can check an implementation against it. This section gives the specification for the protocol the case used. It is a reconstruction from the code and the saved runs, not a design document written in advance.

Five artifact classes carry the protocol. A **run** owns a set of results. A **result** owns at most one rebuttal. A **challenge** references exactly one challenger result and one target result. A **judge** is an optional synthesis over a run. A **report** is a projection of a run and its attached argument records. Every component in the system is a reader or a writer of those five classes, and the classes correspond to files on disk rather than to objects in a process.

That correspondence is the reason the case's central failure was fixable at all. When the interface showed rebuttals that the report could not see, the disagreement had a correct answer: the rebuttal belonged to the initial result, and the initial result was the thing serialized into `results.json`. Stating the protocol as ownership makes that question decidable before anyone writes a line of code. The split arose because two components each kept a local answer to the same ownership question.

**Table 3. Artifact classes and their representations**

| Class | Identity | Persisted as | Producer | Readers |
|---|---|---|---|---|
| Run | Directory name, which combines a local timestamp and a prompt slug | The run directory: `prompt.md`, `meta.json`, `results.json`, raw streams, report | Orchestrator and run manager | CLI, report writer, judge builder, web server, history rail |
| Result | Provider key within a run, for example `kimi` | Row in `results.json`; `<model>.md`; `<model>.stdout.txt`; `<model>.stderr.txt` | Provider adapter | Argument layer, judge builder, report writer, interface |
| Rebuttal | The initial result it argues from; at most one per result | `debate` field on the initial result; `<model>.debate.md` | Broadcast debate round | Judge builder, report writer, interface |
| Challenge | Generated id of the form timestamp, challenger, target, suffix | `challenges.json` list; `challenge-*.md`; challenge raw streams | Challenge manager | Judge builder, report writer, interface |
| Judge | The run it synthesizes | `judge.md`; judge metadata in `judge.json` and `meta.json` | Judge call | Report writer, interface |
| Report | The run it renders | `report.html`; `report.md` | Report renderer | Human readers |

Two properties of the table are load-bearing. First, no class is owned by two classes. A result has one provider key and one run; a challenge has one challenger and one target; a rebuttal has one owner. Second, the derived classes (report and judge output) have no state that cannot be regenerated from the canonical classes. A report can be deleted and rebuilt from `results.json`, the challenge records, and `judge.md`. That is what makes every view comparable.

The `Result` is the canonical object. Table 4 lists its fields as the implementation stores them.

**Table 4. Result and challenge record fields**

| Object field | Type | Meaning |
|---|---|---|
| `result.key` | string | Stable provider key: `kimi`, `gemini`, `deepseek`, `codex` |
| `result.label` | string | Display name |
| `result.accent` | string | Display color, not semantic |
| `result.model` | string | Model alias actually requested |
| `result.status` | enum | `ok`, `error`, `timeout`, or `empty` in a saved result; `queued` and `running` exist only in live views |
| `result.text` | string | Cleaned final answer, empty when the provider produced none |
| `result.error` | string | Provider or adapter error text, empty when the call succeeded |
| `result.hint` | string | Mapped remediation advice derived from the error text |
| `result.elapsed` | seconds | Wall-clock time for this call |
| `result.reported_ms` | number or null | Provider-reported duration when the CLI emits one |
| `result.tokens_in`, `tokens_out`, `tokens_total` | integer or null | Token counts when the provider reports them; null otherwise |
| `result.cost` | number or null | Reported cost when available; null otherwise |
| `result.exit_code` | integer or null | Process exit code |
| `result.argv` | list | The command line used, with the prompt replaced by `<prompt>` |
| `result.stdout`, `result.stderr` | text | Raw captured streams, ANSI stripped |
| `result.debate` | result or null | The rebuttal that owns this initial answer |
| `challenge.id` | string | Timestamp, challenger, target, random suffix |
| `challenge.from_key`, `from_label` | string | The one attacker |
| `challenge.to_key`, `to_label` | string | The one target |
| `challenge.status` | enum | `ok`, `error`, or `timeout` |
| `challenge.text`, `error`, `hint` | string | The argument text or the failure text |
| `challenge.elapsed`, `tokens_total` | number or null | Measurement, as on a result |
| `challenge.model` | string | Model alias used to produce the attack |
| `challenge.created_at` | timestamp | Local time the record was written |

The null columns are part of the model, not a defect. Providers report different amounts of telemetry, and the system records what it received rather than estimating the rest. The case's cost comparison rests on that rule: token counts were available for some providers and not others, so the paper compares calls and wall times and declines to compare money (Section 6.7).

Four ownership rules complete the model.

**R1.** Each expected provider has exactly one top-level result per run. Failure is represented as a result with a non-`ok` status, never as an absent row. A provider that cannot even be constructed produces an error result before any process starts.

**R2.** Each successful initial result may own at most one rebuttal, and a rebuttal cannot own a rebuttal. The argument layer is one level deep by specification, not by accident.

**R3.** A challenge is not owned by a result. It is a separate record that references two provider keys. It is appended to a list and never mutates the results or the run's terminal state.

**R4.** A judge is a property of a run, not of a result. It reads all successful results and all challenge records, and it names failed providers rather than omitting them.

R1 is what makes partial runs legible: a panel with three answers and one 429 is a run with four results, one of which failed. R2 is what makes attribution computable: the report can always pair a rebuttal with the answer it belongs to. R3 is what allows a challenge to be added to a five-day-old run. R4 is what stops the synthesis from silently scoring a smaller panel than the user requested.

The model has a compatibility policy and no schema version. The policy is additive: new fields such as `debate` and challenge records appeared during the case, existing fields kept their meaning, and an older reader that ignores unknown fields still renders a newer run. The version stored in `meta.json` is the engine version, not an artifact-schema version, so a reader cannot tell from a run directory which schema rules applied when it was written. Section 14 returns to that gap.

### 5.8 Message schemas

The protocol has four model-facing messages and one projection. Table 5 gives them. Each message is a one-shot prompt rendered from stored artifacts and configuration; none is a chat turn, none carries history, and none is sent twice with modified content.

**Table 5. Argument messages and their inputs**

| Message | Purpose | Inputs | Constraints | Output |
|---|---|---|---|---|
| M1 Initial query | Get an independent answer | User prompt; context mode (temp, copy, or cwd); provider configuration | No other provider's output; prompt passed unchanged; per-provider timeout | One result per provider |
| M2 Rebuttal request | Broadcast debate | Prompt; every successful answer, each labeled with its model and the model's own answer marked | Each answer capped at 8,000 characters; quote the attack in one sentence; defend or revise; end with "My position now:" in at most 80 words | One rebuttal per successful provider, attached to that provider's result |
| M3 Challenge request | Directed cross-examination | Prompt; target answer; challenger's own answer | Target and own answer capped at 8,000 characters each; quote the two weakest claims; give counterargument or missing evidence; concede where the target may be right; at most 300 words; end with a "Verdict:" line | One challenge record |
| M4 Judge request | Synthesis | Prompt; every answer (successful answers capped at 14,000 characters, failed providers named with their error); optional rebuttals and challenges (capped at 8,000 characters each) | Five required sections: bottom line, consensus, divergence, model by model, what to trust where; note who changed position; do not invent agreement | `judge.md` and judge metadata |
| P1 Report projection | Make the record readable | Results, rebuttals, challenges, judge | Deterministic rendering; no model call | `report.html`, `report.md` |

The important property is that M2, M3, and M4 are pure functions of stored artifacts. A challenge is computed from a prompt, a challenger result, and a target result, all of which are on disk. A re-judge reads the same material. That property is what made the two directed challenges cheap to add to a run created five days earlier, and it is what a replicator would rely on to re-interrogate an archived run without provider access.

The messages also contain no structure beyond text. There is no field for a claim identifier, a confidence value, a citation, or a token budget. The challenger is asked to quote claims, but the quote is prose inside a 300-word argument; the report cannot link a quote to a paragraph in the target answer. Section 6.4 relies on this absence being visible: the judge's most useful output was a complaint about the record, expressed in prose. A structured argument schema is future work (Section 15), not a property of the current protocol.

The prompts are visible to the models, and so are model identities. Every message names the target and the challenger; the judge prompt prints each answer under a heading that includes the model name and version. This is deliberate for a comparison tool, where knowing which model said what is the product, and it is a confound for measuring argument quality, which Section 13 treats.

### 5.9 The run state machine

A run passes through six protocol phases: dispatch (build each provider command and launch), collect (capture streams and produce results), normalize (parse each stream into a `Result`), challenge (the optional post-run argument pass), judge (the optional synthesis over the recorded evidence), and report (render the record). The first three happen inside the run state machine, challenge is outside it, and judge and report are its last two states plus a projection. A run moves through five active states, a cancellation state, and four terminal ones. Table 6 gives the transitions and their guards.

**Table 6. Run state transitions**

| From | To | Guard | Effect |
|---|---|---|---|
| `starting` | `running` | At least one provider specification was built | Provider processes launched; run directory exists |
| `starting` | `finalizing` | No provider specification was built | Per-provider error results written |
| `running` | `debating` | Open debate requested and at least two results are `ok` | Rebuttal calls start for successful providers |
| `running` | `judging` | No debate requested, judge requested, at least one result `ok` | Judge call starts |
| `running` | `finalizing` | No debate, no judge, or no successful result | Artifacts and report written |
| `debating` | `judging` | Judge requested and at least one result `ok` | Judge call starts after all rebuttals settle |
| `debating` | `finalizing` | Judge not requested, or no successful result | Report includes whatever rebuttals exist |
| `judging` | `finalizing` | Judge call returned or failed | Judge text or judge failure written |
| `finalizing` | terminal | Results classified | One of `done`, `partial`, `error` |
| `starting`, `running`, `debating` | `cancelling` | User cancels | Provider process groups killed |
| `cancelling` | `cancelled` | Processes settled | Partial results kept |

The terminal classification is a rule, not a side effect: `done` requires every expected result to be `ok`; `partial` requires at least one `ok` and at least one non-`ok`; `error` means no result succeeded. A cancelled run is `cancelled` regardless of how many results were already written.

Directed challenges are outside this machine. A challenge gets its own short sequence, `running` and then a terminal adapter status, and it does not change the parent run's state. A run can be `done` while a challenge on it is running. The interface has to treat "the run is busy" as either an active run state or an active challenge; that union is a small piece of state logic and a place where a second representation can creep in.

The machine also has a reconstruction rule. When the server reads an old run from disk, it does not trust the stored status if the stored status is not terminal. It derives the status from the results: all `ok` is `done`, some `ok` is `partial`, none is `error`, and an empty result list is `error`. An explicit terminal status wins over the derivation. This rule is what makes a run directory that was left mid-write readable, and it is the specific defense against the stale-run class in Section 7. The stored status can say `running` for a run whose process died days ago; the derived view says what the results support.

The reconstruction rule has a limit. It reconciles status with results, not results with arguments. A run whose initial answers are present but whose rebuttal round is missing will derive to `done` and still be missing a round. The judge quote in Section 6.4 is about exactly that: a run marked `running`, with results that looked complete, and a rebuttal round that existed in one representation and not the other. Derivation cannot recover evidence that was never written.

### 5.10 Invariants

The specification is worth little unless some properties are required to hold across every run. Table 7 states the invariants, where each is enforced, and how completely. "Enforced by construction" means the design makes the violation impossible without changing the code; "enforced by validation" means a check rejects the violating operation; "partially" means the property holds for the paths the case exercised; "convention" means nothing forces it.

**Table 7. Protocol invariants and their enforcement**

| ID | Invariant | Enforcement | Status |
|---|---|---|---|
| I1 | No first-round message contains another provider's output | Round-one spec builder takes only the user prompt and context; separate working directories | Enforced by construction |
| I2 | Every view of a run reads the same canonical files | Report and judge builders read `Result.debate`; server disk view loads `results.json`; no second store | Enforced by construction after the fix |
| I3 | Every expected provider has a terminal result, including failures | Adapter returns a result on every path; runner records build errors as results; artifacts serialize all results | Enforced by construction |
| I4 | A rebuttal is owned by one initial result and one only; arguments are one level deep | Single optional `debate` field; attach step assigns it per key | Enforced by construction |
| I5 | A challenge has exactly one challenger and one target, both successful and distinct | Validation rejects unknown keys, equal keys, and non-`ok` results | Enforced by validation on both CLI and HTTP paths |
| I6 | A challenge is append-only and does not alter the run's terminal state or initial results | Separate record list; report regenerated; initial results reloaded, not rewritten | Enforced by construction |
| I7 | Every view derives from the same files, and the live view is a projection, not a store | Server snapshot and disk snapshot both read results; report is a renderer | Partially enforced: two projections can still disagree in presentation |
| I8 | Terminal state is consistent with the results: `done` only when all succeeded | Classification rule; reconstruction rule for saved runs | Enforced by construction |
| I9 | Truncation is explicit whenever an argument or judge input is cut | Builders append a truncation marker; caps are fixed per message | Partially enforced: the reader is not shown that the argument saw a cut |
| I10 | Raw provider evidence is retained for every call, including arguments | Adapter writes stdout and stderr; challenge writes its own raw streams | Enforced by construction |
| I11 | Argument calls are pure functions of stored artifacts and can run without provider execution of the first round | Builders take prompt and results loaded from disk | Enforced by construction |
| I12 | The judge sees failures, not only successes | Judge prompt names each failed provider with status and error | Enforced by construction |
| I13 | Every argument record names its attacker and its target | Challenge record has from and to labels; challenge prompt addresses the target by name | Enforced by construction |
| I14 | The record identifies models; no view anonymises them | Labels and model aliases are written into results, judge input, and argument text | Enforced by construction, and deliberate |

I1, I5, and I7 are the three the case is actually about, and their evidence differs.

I1 is supported by the shape of the first round rather than by an experiment. All four initial answers were generated before any argument call, and the round-one spec builder has no argument input. The property is structural; the case did not test what happens when a provider's CLI reaches outside its working directory.

I5 is supported by validation in two places. The command-line path rejects an unknown challenger or target, a challenger with no initial answer, a target with no successful answer, and a challenge where the keys are equal; the HTTP path repeats the checks. The case's two challenges satisfy the rule.

I7 is supported by a bug and a fix. Before the fix, two representations of one run existed and the judge read the one without the rebuttal. After it, the initial result owns its rebuttal and every view reads that field. The invariant is only partially enforced at the presentation layer: the live snapshot and the disk snapshot are separate functions and can differ in what they show even when they agree about the status. The challenge-rendering bug is a failure of that space; rendering at the boundary makes the projections agree for that field.

I9 is the invariant that most wants a second look. The caps are fixed and the marker is appended, but a reader of the report never sees that the challenger was given a cut target. In the focal case this was invisible because every answer was under 330 characters and the longest challenge under 2,000. In a long-document task, an argument could be made against a truncated target without the record saying so.

I14 is the one invariant a research design might want to violate. It is listed because it is a deliberate product property, not because it is good for evaluation: the case kept identity visible for auditability, and a blind judge would break I14 and improve construct validity.

An invariant table is not a test suite. Three properties are covered by the 116-test suite, mostly through artifact round-trips and HTTP validation; the rest are structural properties the case observed but did not exercise adversarially. A production system would turn each row into a check. The current system does not, which is why the table states status as well as content.

## 6. Findings

### 6.1 Convergence in the first round

All four models recommended a monorepo. The answers were short, between 232 and 329 characters, and their evidence overlapped. The models did not disagree about the recommendation. They disagreed about the reasoning that made the recommendation conditional.

The judge read the same pattern. It called the first round "near-identical in substance: the same 'shared code + atomic commits + one CI beats theoretical modularity' argument, four times." That judgment is about the text, not about the models' inner reasoning. The text is what a reader has to work with.

### 6.2 What broadcast debate produced

The open debate produced four rebuttals and a real correction. The run took 145.8 seconds; per-model rebuttal times ranged from 11.6 to 70.8 seconds. After the persistence fix, the judge could read the rebuttals and concluded that all four models had converged on a shared correction: a monorepo does not eliminate overhead, it relocates it. No model flipped its recommendation. The debate exposed a shared assumption.

It also produced a group discussion. Each model selected a target from four answers. Three of the four rebuttals attacked Kimi's claims. Kimi had written that a monorepo "eliminates cross-repo tooling" and "removes version-mismatch headaches," which are absolute claims and easy to contest. DeepSeek attacked both. Gemini attacked the same sentence. Codex attacked it too, while keeping its own conditional yes. The concentration was not coordinated; it emerged from the text. That is what a broadcast does. It lets a shared target surface, but it does not assign one.

The exchange was broader than a directed challenge, but it was harder to attribute. If the question is "what does the room think," broadcast debate is useful. If the question is "does this answer survive an attack," it is indirect.

### 6.3 What a directed challenge produced

Kimi's challenge to DeepSeek took 32.1 seconds and produced 1,202 characters. It quoted two claims, attacked them, conceded that shared code is easier in a monorepo, and ended with a verdict:

> DeepSeek's "yes" is reasonable for homogeneous stacks, but its reasoning confuses uniformity with operational simplicity and ignores technology boundaries.

The challenge did not summarize DeepSeek. It named two claims and attacked each one. Atomicity, Kimi argued, increases blast radius: one bad commit can block every service. "One CI/tooling setup" confuses uniformity with simplicity, because a mobile app and a backend do not want the same pipeline. Then Kimi conceded the shared-code point. The result is a record a reader can check against the target answer.

A second challenge, Gemini against Codex, took 29.6 seconds and produced 1,994 characters. It attacked Codex's claim that a monorepo involves "dependency management with little organizational overhead," and it disputed Codex's condition that separate repositories are worthwhile only for genuinely independent access control. The output was longer and more enumerated than C1. That difference is a model difference, not a protocol difference. C2 is not an independent experimental replication, but it shows that the format is not tied to one pair.

Read side by side, the two challenges have the same skeleton. Both identify a target, quote claims, explain a failure, offer a counterargument, concede something, and end with a verdict. The prose around the skeleton varies. C1 is compact and argumentative. C2 is more taxonomic, with numbered claims and longer explanations. A reader can compare the two because the skeleton is stable. That stability is the point of specifying the protocol instead of asking for "a critique."

**Table 8. Observed costs in the focal case**

| Run | Mode | Wall time | Output | Notes |
|---|---|---:|---|---|
| R1 initial | Four independent answers | 5.5 to 21.5 s per model | 232 to 329 characters per answer | All four recommended a monorepo |
| R1 open debate | Four rebuttals | 145.8 s | Four rebuttals | Per-model rebuttal time 11.6 to 70.8 s |
| C1 | Kimi to DeepSeek | 32.1 s | 1,202 characters | Target-specific attack with a verdict |
| C2 | Gemini to Codex | 29.6 s | 1,994 characters | Same protocol, different pair |

The numbers are single-run observations on one machine. The structural point is more reliable: a four-model broadcast makes four argument calls, while a directed challenge makes one. The cost difference follows from the protocol, and the specificity difference follows from the role constraint.

Directed challenge has its own cost. It throws away the other models' perspectives. A reader who wants the full range of objections has to run several challenges or use open debate. The directed format is better for a focused question: does this answer survive an attack from this model? It is not a survey.

### 6.4 The judge and the missing rebuttals

The most useful failure was not a model error. The interface displayed four completed rebuttals. The saved results contained `debate: null` for all four. The report had no rebuttal sections. The judge, reading the saved results, wrote:

> the rebuttal round is not in the record... all four "debate": null, no `*.debate.md` files, and a status still marked "running."

The judge was right. The system had two representations of one run. The interface read a live object; the report and judge read the initial results. The rebuttal had been attached to the first, not the second. A screenshot would have shown a successful debate. The artifact directory showed a run with no debate. The judge exposed the difference.

The fix changed the state model. The rebuttal is attached to the initial result, persisted in `results.json`, and rendered from that result by the interface, the report, and the judge. A later variant of the same mistake appeared with directed challenges. The saved challenge text existed, but the API returned the raw record without rendered HTML. The interface interpreted missing HTML as a failed challenge. The fix was to render at the API boundary.

Both failures have the same shape: two representations of one state, with no invariant forcing them to agree. The judge was useful because it read the evidence rather than the presentation. It functioned as an integration test.

### 6.5 Failure modes beyond the model

Authentication was the first operational shock. Each provider failed in its own way. Claude's OAuth session expired and could not refresh. Kimi's default Moonshot account returned 429 errors for insufficient balance until I switched to `kimi-code`. Gemini's Google login succeeded, but Google rejected the free Code Assist tier for CLI clients with `IneligibleTierError`, so the headless path needed an AI Studio key. None of those were model failures. All of them looked like the tool was broken.

The second shock was the operating system. launchd could not read the source directory in Documents, so the runtime moved to `~/.ensemble/app`. The Desktop application sat behind iCloud and App Management permissions that the shell could not remove. The applet's resource fork overrode the custom Dock icon. The LaunchAgent ended up in a disabled state, and the installer ignored the bootstrap failure, so the app stopped opening after a restart. The debate code was not the hard part. The macOS lifecycle was.

**Table 9. Failure incidents observed in the case**

| ID | Failure | Manifestation | Root cause | Response | Design implication |
|---|---|---|---|---|---|
| F1 | Broadcast abstraction | Four rebuttals, repeated points, weak attribution | Every model was both target and source | Directed challenge became primary; open debate optional | A debate needs an explicit target |
| F2 | Split state representation | UI showed rebuttals; report and judge saw `null` | Rebuttal stored in a live object, not the canonical result | Attach argument to the result; persist; render from one source | Canonical state is a correctness requirement |
| F3 | Render-state mismatch | Saved challenge text existed; UI said "Challenge failed" | API returned raw text without rendered HTML | Add rendering at the API boundary | Every view needs a complete representation |
| F4 | Authentication heterogeneity | 429, expired OAuth, `IneligibleTierError` | Separate accounts, quotas, and entitlement rules | API key, model alias, provider-specific fallbacks | Auth is a first-order integration cost |
| F5 | Operating-system integration | Server would not start after restart; generic icon; protected app | launchd disabled state, TCC, iCloud, app bundle metadata | Enable agent, copy runtime, minimal app, dockutil | Local-first is an OS lifecycle project |
| F6 | Evaluation gap | No correctness or trust measure | Single-user case, no blind ratings, no repeated runs | Treat findings as design evidence; propose evaluation | Argument quality needs an external criterion |
| F7 | Test coverage gap | Early bugs were found by screenshots and judge complaints; a 116-test stdlib suite was added after the case | Tests arrived after the design work and cover parsers, config, sanitization, artifacts, and the HTTP API, not end-to-end providers or the UI | Regression suite added; end-to-end and UI tests remain future work | Tests improve confidence but do not replace evaluation |

The failure table is not a scorecard. F1 and F2 changed the design. F6 and F7 describe what this work cannot claim. The operational failures matter because they determine whether anyone can use the artifact at all.

### 6.6 Propositions

Five propositions follow from the work. "Supported" means consistent with the artifacts and the design experience. It does not mean statistically confirmed.

**Table 10. Propositions and evidence status**

| ID | Proposition | Status | Evidence |
|---|---|---|---|
| P1 | Explicit targets and roles increase argument specificity and attribution relative to broadcast debate | Illustratively supported | Directed challenge named two target claims and a verdict; broadcast debate produced broader, less attributable rebuttals |
| P2 | A canonical artifact representation is necessary for consistent interface, report, and judge behavior | Supported | The split-state bug disappeared when the result object became canonical |
| P3 | Provider authentication and entitlement heterogeneity is a first-order integration cost | Supported | Three providers failed for different authentication reasons |
| P4 | Local-first deployment shifts engineering effort toward operating-system lifecycle work | Supported | TCC, launchd, app bundle, and Dock failures consumed substantial time |
| P5 | A model judge can function as a consistency check on the evidence pipeline | Observed | The judge identified missing rebuttal data that the interface displayed as present |

### 6.7 Cost and latency

The cost of an argument round is easy to state in calls and harder to state in time. The independent round makes four calls. Open debate makes four more. A directed challenge makes one. For a four-model panel, that is a 4:1 difference in argument calls. The observed wall times were 145.8 seconds and 32.1 seconds, a ratio of 4.5. The ratio is not exactly four because the providers have different latencies and because the broadcast waits for the slowest rebuttal. Kimi took 70.8 seconds in the broadcast and 32.1 seconds as the challenger. The slowest participant sets the clock.

That detail matters for the interface. A user waits for the whole round, not for the average call. Streaming would make the wait more legible, but it would not reduce the total. A directed challenge is easier to justify because the user can name the question it answers: does this answer survive an attack from this model? Open debate asks a broader question and charges the user for four attempts.

The case does not support a monetary comparison. Token counts were reported for some providers and not others. The effective cost depends on subscription arrangements that changed during the week. The call-count comparison is the part that travels: broadcast scales with the number of participants, directed challenge does not.

### 6.8 What the test suite adds

The test suite arrived after the case narrative, not during the design work. It is a stdlib `unittest` suite of 116 tests. It covers the provider parsers with inline fixtures, configuration merging, Markdown and HTML sanitization, artifact round-trips, and the HTTP API. It also includes regression tests for three defects the suite found: a newline-obfuscated `javascript:` URL, non-object JSONL lines, and a `"defaults": null` configuration.

The suite changes the engineering claim from "manual verification only" to "partially verified." It does not execute a real provider CLI, does not exercise a live challenge, and does not drive the browser interface. A test can confirm that a result with a debate round serializes and renders. It cannot confirm that the model produced a good argument. That distinction is why the evaluation gap remains separate from the test gap.

The suite also illustrates the difference between regression coverage and research evidence. The three regressions are concrete and repeatable. The design claims in this paper are not. A reader should treat the tests as support for the implementation, not as support for the argument that directed challenge improves decisions.

## 7. Failure Taxonomy

### 7.1 What the taxonomy is for

Section 6.5 listed seven failures and asked what each one implied for design. This section turns that list into a taxonomy: a set of named classes, each with a layer, a trigger, a symptom, a detection method, a mitigation, and an account of whether the case exposed it. The purpose is not classification for its own sake. A failure class is useful when it tells a builder where to look, how to notice the failure, and what response is proportionate. A class that cannot be detected is a category, not a diagnosis.

The taxonomy has two axes. The first is the layer where the failure originates: provider execution, the adapter, the state and presentation path, the argument protocol, the evaluation layer, and the operating environment. The second is the stage at which it can be detected: before dispatch, while a call is in flight, at write time, or only by reading the artifacts afterwards. The two axes separate failures that look similar to a user. A Kimi 429 and a missing Kimi binary both present as "Kimi failed," but one is detected by a readiness probe and the other by the adapter at launch, and the mitigations differ.

### 7.2 The classes

Table 11 lists fourteen classes. The mapping to the seven incidents in Section 6.5 is not one to one: the earlier table grouped by incident, and this one separates by mechanism. State divergence and render-state mismatch map to F2 and F3; the broadcast abstraction maps to F11; the authentication and operating-system incidents map to F01, F02, and F14; the evaluation gap maps to F13. Stale runs, deployment skew, timeout, empty answer, truncation, parse failure, and judge bias did not have their own entries in the incident table.

**Table 11. Failure classes**

| ID | Class | Layer | Trigger | Symptom | Detection | Mitigation | Case exposure |
|---|---|---|---|---|---|---|---|
| F01 | Provider boot failure | Provider | CLI absent, unusable session, broken patch, command construction error | Provider never reaches a model; immediate error | Readiness probe; adapter exception; process start failure | Install or sign in; repair or bypass the launch path; record the error as a result | DeepSeek patch and authentication fragility; Claude removed after session expiry |
| F02 | API, quota, or entitlement failure | Provider | Balance exhausted, entitlement rejected, session expired, server error | Provider process runs and fails; error text from the remote service | Parsed error text; status is `error`; hint mapping | Switch plan or alias; supply an API key; retry later | Kimi 429 for insufficient balance; Gemini `IneligibleTierError` |
| F03 | Timeout | Adapter | Call exceeds the per-provider limit, 300 s by default | Process killed; partial output may survive | Timeout status; error text names the limit | Raise the limit; shorten the prompt; reduce context | Not observed in the focal run |
| F04 | Empty answer | Adapter | Process exits without usable text | `ok` exit with empty text | Empty status after parsing; "model returned an empty response" | Retry; inspect raw stream; change parser | Not observed in the focal run; parsers can yield no assistant message |
| F05 | Output truncation | Adapter and argument | Long answers exceed fixed input caps; provider output hits its own cap | Argument built from a cut target; judge reads a cut answer; provider output ends mid-sentence | Truncation marker in the prompt; length checks on text | Raise caps; summarize; argue over excerpts | Not observed: every focal answer was under 330 characters |
| F06 | Parse failure | Adapter | Provider changes stream format or emits a shape the parser does not expect | Empty or partial text despite a successful process; error file populated | Raw stdout inspection; parser tests; non-object lines seen | Update parser; fall back to plain text; keep raw stream | No focal-run failure; the heuristic parsers and the non-object JSONL regression are the evidence |
| F07 | State divergence between interface and report | State | Two representations of one fact, only one persisted | Interface shows an argument the report and judge cannot see | Compare interface, report, and judge input against `results.json` | Give the fact one owner in the canonical result; render from it | The rebuttal round: interface showed four, record had `debate: null` |
| F08 | Render-state mismatch | Presentation | Saved text exists but a projection drops or fails to render it | Interface reports failure while the artifact shows success | Compare `challenges.json` with the interface state | Render at the boundary; make the projection total | Challenge text present; interface said the challenge failed |
| F09 | Stale-run status | State | Process died or server restarted mid-run; directory keeps a non-terminal status | Run looks active or incomplete although its results are settled | Status derivation from results; history view; reading a run in order | Derive status when the stored status is not terminal; keep partial artifacts | The judge quote notes a status still marked "running" |
| F10 | Runtime deployment skew | Environment | Installed copy differs from the source tree; agent disabled after reboot | Fix present in source, absent in browser; server serves old code | Compare deployed files with source; check agent state | Copy runtime, restart agent, verify enabled state | Source had a fix the running server did not have; LaunchAgent disabled |
| F11 | Attribution ambiguity in broadcast debate | Argument | Every model receives every answer; no target assigned | Repeated attacks on one answer; reader reconstructs who answered whom | Count named targets; compare rebuttals with the target text | Directed challenge as primary mode; broadcast optional | Three of four rebuttals attacked Kimi's absolute claims |
| F12 | Judge identity and position bias | Evaluation | Judge sees model names and is one of the participants | Preference shaped by model identity, order, or verbosity | Compare judge output with blinded re-runs; vary order | Blind the judge; use several judges; report disagreement | Judge was DeepSeek, one of four participants; not measured |
| F13 | Evaluation gap | Evaluation | No ground truth, no repeated trials, no human ratings | Findings about structure, none about correctness | Ask what outcome was measured; check for an external criterion | Controlled study with a pre-registered rubric | No correctness or trust measure existed |
| F14 | Operating-system and permission failure | Environment | Privacy controls, launchd state, app bundle metadata, iCloud | Local service or app cannot start or update | Launch logs; `launchctl` state; shell diagnostics | Move runtime, enable agent, minimal app, verify after restart | launchd could not read Documents; app behind iCloud and App Management |

The table is deliberately unsorted by severity. Severity depends on the task: a parse failure on one provider in a four-model panel is nuisance; a state divergence in a tool used for decisions is disqualifying, because it undermines the property the tool exists to provide.

### 7.3 What the case exposed, and what it only predicted

Nine of the fourteen classes were exposed by the case directly or through artifacts around it: F01, F02, F07, F08, F09, F10, F11, F12, and F14. F13 is exposed as an absence: the case documents that no correctness measure existed. Four classes, F03, F04, F05, and F06, are implemented in the code but not documented in the focal run. The case predicts them rather than observing them. F03 and F05 become likelier as prompts and answers get longer, F06 as provider formats drift, and F04 as soon as a parser meets a stream it cannot read. That is where the next deployment would go.

The exposure pattern is the interesting result. No class in the table is a model-quality failure. Every observed failure sits in the wrapping, the state path, the evaluation layer, or the operating environment. That is partly a selection effect: the focal prompt was chosen because all four models answered it. It is also the design problem stated plainly. The models did not break the system. The machinery around them did.

The classes also cascade. Three chains appear in the record. The first: F02 leaves a partial panel; a partial panel constrains later argument because a challenge target must have a successful answer, so the failure that happened on day one decides which arguments are possible on day five. The second: F07 makes the interface and the report disagree; the judge reads the report's state, complains, and its complaint becomes the detection mechanism for a bug it did not cause. The third: F10 produces a fix that is present in source and absent from the running server, which turns one debugging session into two. Cascades matter for mitigation because the cheapest fix is usually at the root. Rendering at the boundary closes F08 and would have closed the second half of F07; a readiness probe closes most of F01 and F02 before a prompt is sent.

### 7.4 What the taxonomy implies

Three implications follow. Failures cluster at boundaries, not in models, so a system that treats the adapter and the artifact writer as plumbing will spend its debugging time there anyway. Detection is cheapest before dispatch: the readiness probe and the version check are small and catch most of the provider classes. And the state classes are the ones that need invariants rather than tests. A test can catch a parse regression; only an ownership rule can prevent two representations of one fact from diverging again.

The taxonomy is also a checklist for a replicator. A third party repeating the case should expect F01 and F02 as normal operating conditions, should check F05 and F09 when reading an archived run, and should not expect to observe F07, F08, or F11 in a fixed system. If they do observe them, the fix has regressed. That converts the failure analysis into something a team can act on, which is more than the incident list alone provides.

The remaining gap is prevalence. The case cannot say how often each class occurs, because it is one deployment with no incident log. The numbers in Section 10 are timings, not frequencies. A study that counted failures per hundred runs would be worth more than any extension of this table, and Section 11 explains how it would be designed.

## 8. Comparison with Adjacent Systems

### 8.1 The comparison classes

The system sits near four kinds of work. Each solves part of the same broad problem, and each assumes something the others do not.

**AutoGen-style orchestration.** A general framework for composing conversable agents with tools, humans, and code (Wu et al., 2023). Its strength is programmability: patterns are written once and reused. Its assumption is a common agent interface and a framework-owned state model. It can host heterogeneous models, but as framework agents, not as vendor CLIs with their own logins, quotas, and output formats.

**Self-consistency.** Non-interactive aggregation: sample several reasoning paths and select the most consistent answer (Wang et al., 2023). It needs no infrastructure beyond repeated calls and no record beyond the samples. It improves reasoning without any agent seeing another's output, but it produces agreement, not argument, and says nothing about the auditability of disagreement.

**ChatDev-style role pipelines.** A role-structured pattern in which fixed roles converse in ordered phases and hand artifacts to one another. The argument is a division of labour rather than a dispute between independent answers: each role contributes a different piece, not an attack on a peer's conclusion. The pattern needs a shared channel and task representation. The ChatDev paper is not in this paper's reference set; I describe the pattern at the level of role and phase structure, not as a cited result.

**Hosted side-by-side comparison interfaces.** The family behind Chatbot Arena and MT-Bench (Zheng et al., 2023). Many models, one prompt, a human preference, a maintained log. Its strength is scale and a stable preference instrument; its limitations are location and control. The operator holds the models, the prompts, and the record, the comparison is one-shot, and there is no argument layer. ChatEval (Chan et al., 2023) is a variant in which the evaluators are a team of model agents; the argument is among referees, not between an answer and its target.

### 8.2 Where the designs differ

Table 12 compares the five on five dimensions. "Heterogeneity" asks whether the system can run models that arrive through different vendor interfaces. "Local-first" asks whether execution and record live on the user's machine. "Auditability" asks whether a third party can reconstruct the exchange from the saved record. "Argument structure" asks whether the system specifies who argues against whom and what the argument must contain. "Failure visibility" asks whether a failed participant is recorded and shown, or silently dropped.

**Table 12. Comparison with adjacent systems**

| System class | Heterogeneity | Local-first | Auditability | Argument structure | Failure visibility |
|---|---|---|---|---|---|
| `ensemble` | Four vendor CLIs behind one result interface | Yes; prompts and record on the machine | Run directory is the record; every view derives from it | One attacker, one target, named; broadcast optional | Failures are results with status, error, and hint; judge is told |
| AutoGen-style orchestration | Framework agents; heterogeneous models possible | Depends on deployment; often API-hosted | Conversation log under framework control | User-defined patterns; no default target rule | Depends on what the user writes; framework-level |
| Self-consistency | Homogeneous by design: several samples | Yes, trivially | Samples, if retained | None; aggregation replaces argument | Sampling failure is invisible in the aggregate |
| ChatDev-style role pipeline | Agents in one framework | Usually local execution | Phase transcripts and shared artifacts | Roles, not targets; contribution, not attack | Role failure shows as a broken phase |
| Hosted side-by-side UI | Many models, one operator | No; operator-hosted | Operator-controlled log | None in the default pairwise flow | Model errors are an operator concern |

The table places `ensemble` in a narrow cell. It is the only row that combines vendor-CLI heterogeneity with a local record and a specified attacker-target relation. It is also the row with the least evidence about outcomes: no benchmark scores, no preference votes, no repeated trials. The comparison is not a ranking. AutoGen is more general, self-consistency is cheaper, hosted comparison is measured at a scale no local tool can reach, and a role pipeline produces deliverables rather than critiques. `ensemble` trades generality for auditability and scale for control.

One difference the table cannot show is the cost of heterogeneity. The adjacent designs assume a participant can be addressed through a stable programmatic interface. `ensemble` assumes the opposite and pays for it in adapters, authentication handling, and parser maintenance. Section 7 details what that price looks like.

### 8.3 What the comparison cannot establish

The comparison is architectural, not empirical. I did not run the same prompts through these systems and compare outputs, decisions, or costs, and the paper claims nothing about relative merit. The characterizations come from the cited papers and from the design constraints the case exposed. A controlled comparison would need the same model access in every condition, which is exactly what the local-CLI design cannot provide.

The comparison also cannot say whether the adjacent systems would have failed in the same ways. AutoGen would not have hit the launchd problem, because it would not have run on launchd; it would have had its own failure classes, and a fair test would compare taxonomies rather than incidents. The case gives the vocabulary for that study and the hypothesis that failures cluster at integration boundaries. It does not give the result.

## 9. Design Principles

### 9.1 How the principles were derived

Section 4.8 listed seven principles in one table. This section gives each the argument it needs: the failure that produced it, the mechanism that makes it work, the code that implements it, and the observation that would count against it. The evidence is uneven. Two principles are supported by failures, one by a bug and a fix, one by the shape of the first round, one by two argument records, one by an operating-system incident, and one by a judge's complaint. That unevenness is part of the result.

### 9.2 DP1: Wrap heterogeneous agents behind a stable result interface

The four agents share one interface where it matters: a `Result` with a status, text, timing, error, raw streams, and optional telemetry. Above it, the comparison layer does not know that Kimi reads a different stream format from Codex, that Gemini needs a key while Codex needs a login, or that DeepSeek needs a patch file. The failure that produced the principle was four different failures in four formats: a 429, a tier rejection, an expired session, and patch fragility. Normalising them into one result meant a failed provider became a row with an error string, which the report could render and the judge could read. The cost is the adapter layer, the largest source of integration risk (Section 7). The principle confines heterogeneity; it does not remove it.

### 9.3 DP2: Keep the first round independent

No provider sees another's output before the first round ends. The message schema enforces it: the round-one prompt is the user's prompt and the context mode, and no code path puts an answer into another provider's round-one call. The four answers are evidence about the prompt, not about the conversation. The failure without the principle is anchoring, and the case's first design showed the related consequence: once every model saw every answer, the room converged on a shared correction. Independence gives the argument layer something to compare. Its cost is that no model can build on another's evidence, which is the right trade for a comparison tool and the wrong one for a problem-solving tool.

### 9.4 DP3: Make canonical artifacts the interface between layers

One representation feeds every view. The initial result owns its rebuttal; the report, the judge, and the interface read that field, and the serialisation layer writes and restores it. The failure that produced the principle is the central one: the interface displayed four rebuttals, the saved results had `debate: null`, and the judge reported the round missing. Two representations of one fact, no invariant forcing them to agree. The principle names the property the fix established: every view is a reader, and no view is a second database. Its limit is that shared artifacts do not make two projections render a fact the same way; the challenge-rendering bug showed a projection that had the text and still displayed a failure.

### 9.5 DP4: Treat argument as post-processing, not as part of generation

The initial answer is complete before it is contested. An argument call consumes saved results and does not modify them: a challenge can run on a run directory created days earlier, and a re-judge can run on the same directory without provider execution of the first round. The two directed challenges are the evidence; they were added to a run from 20 October on 25 October, and the initial results were not regenerated. The cost is that the argument is always tested against the initial answer, never a revised one. That is the right unit for auditability and the wrong unit for measuring the strength of a position.

### 9.6 DP5: Give every argument an explicit target and role

One challenger, one target, one output. The prompt names the target, asks for the two weakest claims in it, and asks for a verdict; the record names both keys; validation rejects unknown, unsuccessful, or equal parties. The failure that produced the principle was the broadcast debate, where three of four rebuttals attacked Kimi's absolute claims because those claims were easiest, not because Kimi was assigned. The directed challenge made attribution structural. The principle's scope is narrower than "debate": it says that when the goal is auditability, the unit should be a pair. It does not claim a pair produces better arguments than a group; the evidence is protocol compliance, not quality.

### 9.7 DP6: Treat local-first deployment as an operating-system project

The system runs on the user's machine, so the operating system is part of the product. The principle names what a hosted service would hide: privacy permissions that block a launch agent from reading a source directory, app bundle install paths, iCloud and App Management restrictions, a Dock icon overridden by applet metadata, and a launch agent left disabled after an installer run. The evidence is a chain of failures that had nothing to do with models, cost more time than the argument protocol, and determined whether the artifact was usable. The limit is that this argues a position on a tradeoff, not a universal: a hosted service moves those failures to an operator but requires uploading prompts and outputs.

### 9.8 DP7: Use the judge as a consistency check as well as an evaluator

The judge is a reader with a different prompt. It compares answers and says what to trust, and when the record is incomplete it says so. The case's strongest example is a complaint: the judge reported that the rebuttal round was not in the record, and it was right. Because it reads the same files a human reader reads, a disagreement between its description and the files is evidence of a defect, a form of runtime verification that costs nothing extra because the judge call happens anyway. The principle does not make the judge's content judgements reliable; those are subject to the biases in Section 7 and Section 13.

### 9.9 The principles as a set

Table 13 summarizes the seven principles with their mechanism, evidence type, and the observation that would weaken them.

**Table 13. Principles, mechanisms, and evidence**

| ID | Principle | Mechanism | Evidence type | What would weaken it |
|---|---|---|---|---|
| DP1 | Stable result interface | Adapter normalization; one result type | Four different provider failures rendered coherently | A provider whose semantics cannot be normalized |
| DP2 | Independent first round | No cross-provider input path | Four answers generated before any argument | Evidence that round-one exchange improves the basis for argument |
| DP3 | Canonical artifacts | One owner per fact; views are readers | The split-state bug and its fix | A view that must hold state the canonical files cannot express |
| DP4 | Argument as post-processing | Builders read saved results | Challenges added to a five-day-old run | Evidence that replied argument changes the audit record's value |
| DP5 | Explicit target and role | Named challenger and target; validation | Two directed challenges with target-specific claims | Broadcast matching directed specificity under blind scoring |
| DP6 | Local-first as OS work | Runtime copy, installer, launch agent checks | Launchd, TCC, iCloud, app bundle failures | A use case where local control is worth less than the lifecycle cost |
| DP7 | Judge as consistency check | Judge reads the evidence, not the presentation | Judge reported missing rebuttals | A judge whose record descriptions are unreliable |

The table shows the unevenness directly. DP3 and DP6 are supported by failures that forced code and deployment changes; DP5 by two artifacts; DP2 by the shape of the first round; DP1 by the fact that a comparison happened at all; DP7 by one complaint. The set is design knowledge for a class of systems: local tools that wrap heterogeneous agents and produce an argument record. It is not a theory of multi-agent systems, and none of the principles is novel in isolation. The contribution is the combination and the evidence. A reader building a task-solving system rather than a comparison tool should keep DP1 and DP3 and treat DP2 and DP5 as optional.

## 10. Cost and Latency Model

### 10.1 What was measured

Section 6.7 made the structural point: a four-model broadcast makes four argument calls, a directed challenge makes one, and the slowest participant sets the clock. This section turns the observed timings into a small model. The inputs are measured, the arithmetic is derived, and the missing terms are named rather than guessed.

**Table 14. Measured timing quantities**

| Quantity | Observed value | Status |
|---|---|---|
| Initial round, per provider | 5.5 to 21.5 s | Measured, four providers |
| Initial round, wall time | 21.5 s maximum | Derived from the per-provider values |
| Open-debate rebuttal, per provider | 11.6 to 70.8 s | Measured, four providers |
| Open-debate configuration, end to end | 145.8 s | Measured whole run including judge; phase split not recorded |
| Directed challenge C1 | 32.1 s | Measured, one call |
| Directed challenge C2 | 29.6 s | Measured, one call |
| Initial answer length | 232 to 329 characters | Measured |
| Challenge output length | 1,202 and 1,994 characters | Measured |

The 145.8-second figure needs a note. It is the saved wall time for the broadcast run as a whole: initial round, open-debate round, judge, and finalisation. The code stores one wall time per run, not per phase, so the split among those phases is unknown. The per-call values are measured; the composition of the total is not.

### 10.2 The model

Write `n` for the number of providers and `k` for the number of directed challenges. Five assumptions define the model, and the case cannot verify them.

**A1.** Calls within a round run in parallel, so a round's wall time is its slowest call rather than its sum.

**A2.** A directed challenge is one call, run after the initial run has finished.

**A3.** Latency is a property of the provider, model, prompt, and load at the time of the call. The case measured each provider once on one prompt.

**A4.** There are no retries or queueing beyond the engine's existing concurrency; the system has no queue and no cap beyond the provider count.

**A5.** Multiple directed challenges are requested one at a time. The interface disables the challenge control while one is running, so `k` challenges cost the sum of their calls.

Under those assumptions the call counts are exact: `n` for the initial round, up to `n` for a broadcast round, and `k` for directed challenges. Wall times are `T_init(n) = max(latency_i)`; `T_bcast(n) = T_init(n) + max(rebuttal_i) + T_judge + T_overhead`, where the last two terms are unknown from the case; and `T_dir(k) = Σ latency_j`. A new run that includes challenges costs `T_init(n) + T_dir(k)`. The model predicts calls exactly and wall time only up to the unknown terms, and that asymmetry is the honest result: calls follow from the protocol, wall time follows from provider behavior, and the case has one observation per provider.

### 10.3 Worked examples

Table 15 applies the model to panels of two, three, and four providers. The latencies are the observed values for the four providers; a smaller panel is treated as the corresponding subset. That subsetting is assumption A3, not a measurement: the case never ran a two- or three-provider panel on this prompt.

**Table 15. Worked latency examples**

| Panel | Initial round, derived | Broadcast rebuttal max, derived | Broadcast end to end | One directed call, Kimi as challenger |
|---|---|---|---:|---:|
| Kimi and DeepSeek | 12.8 s (Kimi) | 70.8 s (Kimi) | Unknown | 32.1 s |
| Kimi, Gemini, DeepSeek | 12.8 s (Kimi) | 70.8 s (Kimi) | Unknown | 32.1 s |
| All four | 21.5 s (Codex) | 70.8 s (Kimi) | 145.8 s measured | 32.1 s |

Three things follow. Adding a provider raises the initial round only when the added provider is the slowest; Codex is why the four-provider initial round is 21.5 seconds rather than 12.8. The broadcast rebuttal round is dominated by its slowest participant in every panel containing Kimi; Kimi's 70.8-second rebuttal is more than twice its 32.1-second challenge. And the directed path is cheaper in calls and, for this prompt, in wall time, but the comparison is not like for like: the broadcast figure includes a judge and more calls. The end-to-end broadcast figure for the smaller panels is left unknown rather than computed, because computing it would assume judge and overhead values the case never measured.

For `k` challenges the cost is the sum of the calls. The two observed challenges would cost 61.7 seconds if run back to back, but they attack different pairs (Kimi to DeepSeek, Gemini to Codex), so the figure illustrates the arithmetic rather than a two-challenge experiment.

### 10.4 Coverage and the k-challenge tradeoff

Attribution costs calls. A directed challenge covers one ordered pair. A panel of `n` models contains `n(n-1)` ordered pairs; full pairwise coverage takes 2 calls at two providers, 6 at three, and 12 at four. That arithmetic is derived from the protocol, not measured. A broadcast round covers the same `n` answers in `n` calls, but not the same pairs: each rebuttal may attack any answer and usually attacks the easiest one, which is why three of four rebuttals converged on Kimi. Broadcast is cheaper per call and weaker per attribution.

**Table 16. Calls for argument coverage**

| Panel size | Directed calls for one pair | Directed calls for all ordered pairs | Broadcast calls | Attribution per call |
|---:|---:|---:|---:|---|
| 2 | 1 | 2 | 2 | Directed: exact; broadcast: unassigned |
| 3 | 1 | 6 | 3 | Directed: exact; broadcast: partial |
| 4 | 1 | 12 | 4 | Directed: exact; broadcast: partial |

The practical rule is the one Section 12.1 states for the protocol: use directed challenge when the question is whether one answer survives one attack, and broadcast when the question is what the room thinks. The cost model makes the rule quantitative. If the user cares about `j` specific pairs, directed costs `j` calls and broadcast costs `n` calls with no guarantee that those pairs are the ones attacked.

### 10.5 What the model does not capture

The model is a call-count and wall-time model. It says nothing about money. Token counts were reported for some providers and not others, the effective price per call depended on subscription arrangements that changed during the week, and the paper does not compare monetary cost (Section 6.7). A monetary model would need a price per provider, a token-count estimate, and an assumption about how much of each subscription is already paid for; none of those is in the case.

It also does not capture judge time, retry time, cancellation, queueing, provider load, or human reading time. Judge time is a fixed addition to any judged run; the judge model is one of the same providers, so its latency is probably in the observed range, but the case did not measure it. Retries and provider load are failure classes (Section 7), not latency terms. Reading time is the term most likely to dominate a real decision: a 145.8-second run producing four rebuttals and a judge report still requires a human to read several thousand words. The case measured generation, not consumption.

## 11. A Controlled Study Design

### 11.1 What the case cannot answer

The case supports claims about protocol compliance, attribution, and state consistency. It cannot answer whether directed challenge improves a decision. That needs four things the case lacks: a ground-truth criterion for some prompts, repeated runs to separate signal from variance, blinded scoring to remove model-identity effects, and a comparison condition that differs only in the variable of interest.

### 11.2 Design

The design is a mixed factorial. The first factor is the argument condition, varied within prompt: independent answers only, directed cross-examination, or broadcast debate. The second is panel size: two, three, or four providers. Each prompt is answered under every combination of the two, and condition order is randomized within each prompt, so prompt difficulty is not confounded with condition. Prompts come from the four categories the case already proposed: factual questions with a checkable answer, design questions with defensible alternatives, policy questions with value disagreement, and ambiguous questions with no clear answer.

**Table 17. Factorial structure**

| Factor | Levels | Role |
|---|---|---|
| Argument condition | Independent; directed; broadcast | Primary manipulation |
| Panel size | 2, 3, 4 providers | Secondary manipulation; cost scaling |
| Prompt category | Factual; design; policy; ambiguous | Blocking variable; tests generality |
| Repetition | 3 per cell | Estimates within-cell variance |
| Judge condition | Named judge; blinded judge | Controls identity bias |

The judge condition is a separate manipulation on the same runs, because judging can be repeated from saved artifacts without re-running the panel (invariant I11). That is one place where the artifact model simplifies the evaluation: the expensive part is generation, and saved results can be re-judged under multiple conditions.

The study needs a pre-registered analysis plan, a fixed prompt set, and version logging before any run. The case's run metadata records the engine version, the command, the provider set, the model aliases, and timestamps; it does not record provider CLI versions or account tiers. The study must add that logging, because otherwise a model update during the study is indistinguishable from an effect.

### 11.3 Measures

**Table 18. Outcome measures**

| Measure | Operationalisation | Analysis |
|---|---|---|
| Argument accuracy | Two blind raters score each answer and argument against a task-specific rubric; factual prompts also checked against the verifiable answer | Rater agreement; proportion of correct positions by condition |
| Decision change rate | Initial recommendation versus post-argument recommendation, with direction; justification change recorded separately | Paired proportions; directed versus broadcast |
| Time to decision | Wall time from submission to the reader's recorded choice, plus generation time | Distribution comparison by condition |
| Protocol compliance | Named target, two quoted claims, counterargument, concession, verdict | Automated check; descriptive |
| State consistency | Interface snapshot, report, and judge input compared against `results.json` | Disagreements per run; target is zero |
| Cost | Calls, wall time, tokens where reported | Descriptive; no monetary comparison unless prices are fixed |

The accuracy measure is the hardest and the most important. For factual prompts it can be exact. For design and policy prompts it must be a rubric agreed before data collection, with scored dimensions such as whether the answer names the load-bearing tradeoff, states a condition under which it would be wrong, and uses evidence that holds. Two raters should score independently and report agreement. The case did none of this, so the rubric cannot be borrowed from the record.

### 11.4 Power

The case provides no variance estimate. There is one run, one prompt, two challenges, and no repeated trials, so the within-cell standard deviation of any outcome is unknown, and the required sample size is unknown with it. The honest planning position is to run a pilot block, estimate variance from it, and size the main study from those estimates; a power calculation before the pilot would be an assumption with a decimal point.

The design is paired, so the relevant tests are paired comparisons (McNemar for a changed recommendation, paired or non-parametric tests for continuous outcomes). Because prompts are nested in categories and runs are nested in prompts, the analysis should use a mixed model with prompt as a random effect rather than pooling observations as independent.

### 11.5 Confounds the case cannot rule out

Six confounds are visible. Model versions and account states changed during the week; a study must pin and log them. The judge was one of the participants and saw identities; a study must blind it and use more than one. The prompt was selected because all four models answered it; a study must sample prompts before seeing model behavior. The author was user and coder; a study must separate those roles. The directed prompt is more directive than the broadcast prompt, so a difference could be a response to instruction rather than to target structure; a fair control is a broadcast instruction with equally specific constraints. And one observation per provider means latency comparisons are confounded with date and load.

Most of these are fixable in a real study: pin and log versions, blind the judge and use several, sample prompts before seeing model behavior, separate the author from the coder, add a directive-constrained broadcast control, and repeat runs. Three constraints are structural: one machine, one user, and a convenience panel. The study fixes what it can and reports the rest as boundary conditions.

### 11.6 What would count against the design claims

The propositions in Section 6.6 should be treated as falsifiable. P1 fails if blind raters score broadcast rebuttals as target-specific as directed challenges. P2 fails if a second implementation with a canonical model still produces view divergence, which would make the case's bug an implementation accident rather than a design lesson. P3 fails if, under a controlled setup with the same four providers, authentication is not the dominant pre-flight cost. P5 fails if the judge's record complaints turn out to be unreliable, or if an ordinary reader finds the same discrepancies as easily. None of those failures is likely on the current evidence, and "not likely" is not "tested."

## 12. Discussion

### 12.1 Argument needs a target

The first design treated debate as a group activity. Every model got every answer. The result was a discussion, not an argument. Each model chose a convenient target, and the reader had to reconstruct the exchange. The directed challenge changed the unit of analysis from the group to the pair. That made the output shorter, cheaper, and easier to audit.

The lesson is not that pairwise debate is always better. Broadcast debate is better for surveying the space of objections. Directed challenge is better for stress-testing a specific answer. The design should expose both and choose a default for the task. Here, the user's correction set the default.

What makes the directed version work is accountability. A named attacker and a named target create a record that can be checked. A group discussion creates a transcript that has to be interpreted. For decision support, the difference matters. The reader needs to know which claim was contested and what evidence was offered.

### 12.2 The artifact as the source of truth

The persistence bug is the strongest argument for the artifact-first design. A user could see four completed rebuttals in the interface. A reader of the report saw none. The judge saw `debate: null`. The system had two state representations and no invariant that forced them to agree. The judge's complaint made the inconsistency visible, but the problem was structural.

A canonical state model solves the immediate bug and enables a broader property: every view can be regenerated from the same evidence. A reader can compare the interface, the report, and the judge input and expect them to agree. When they do not, the system has a defect, not a difference of interpretation.

The failure also suggests a role for judges beyond scoring. A judge that reads the saved evidence can detect missing evidence. That is a form of runtime verification. It does not replace tests, but it is useful in a system whose outputs are heterogeneous and probabilistic.

### 12.3 The judge is a reader

The judge is both an evaluator and an instrument with known biases. Zheng et al. (2023) documented position, verbosity, and self-enhancement effects. The system adds a practical observation: a judge that sees model names and reads a partial record can produce a coherent narrative that is wrong about the record itself. The judge's complaint about the missing rebuttals was useful because it was grounded in the artifacts. Its content judgments are less trustworthy.

A stronger design would blind the judge to model identity, use several judges, and report disagreement. It would also separate the judge from the participants. The current judge, DeepSeek, is one of the four models. That creates a self-preference risk I cannot quantify.

### 12.4 Local-first means OS work

Local-first deployment is attractive for privacy, cost, and account ownership. It also makes the operating system part of the product. The system ran into privacy controls that blocked the launchd agent from reading the source directory, an iCloud and App Management restriction around a Desktop application, a generic Dock icon caused by applet metadata, and a launchd service that remained disabled after an installer run.

Those are not edge cases for a local tool. They are the conditions under which it is used. A hosted service would move them to an operator, but it would also require uploading prompts and outputs. The choice is a tradeoff between operational simplicity and data control, not a purely technical preference.

### 12.5 Implications for design

A few design priorities follow. Define the argument protocol before adding models; a clear target and role structure is worth more than another participant. Make the artifact model canonical before building multiple views, so the interface stays a reader rather than becoming a second database. Treat authentication and operating-system integration as product requirements. Instrument the pipeline so missing evidence is visible.

For researchers, benchmark accuracy is not the only dependent variable. Argument specificity, attribution, auditability, and state consistency are design outcomes that matter in decision support. They can be measured with human raters, blinded judges, and repeated runs. They can also be compared across argument formats on the same prompts with a pre-registered rubric.

### 12.6 Argument artifacts and decision support

The tool does not produce a decision. It produces a record that a person can use while making one. That distinction matters because the interface can make a contest look settled. A verdict at the end of a challenge reads like a conclusion, even when it is one model's attempt to discredit another. The report should keep the initial answer, the attack, the concession, and the verdict visibly connected, so the reader can see which claim was tested and what the challenger offered in its place.

Different readers need different things from that record. An engineer may want the specific defect: a missing condition, a false absolute, a tooling assumption that does not hold. A manager may want to know which answer is safe to act on and which caveat changes the decision. The same artifact can serve both, but only if the interface does not collapse the argument into a score. The current report shows the text and the route. A stronger version would let a reader click a challenged claim and see the paragraph that attacked it.

Argument quality and decision quality are separate. A challenge can be well structured and still persuade for the wrong reason. The judge can reward confidence. The challenger can attack a straw man. The target can be right for reasons the challenger ignores. The case cannot resolve those possibilities because it has no external criterion. What it can do is make them visible. A reader who sees the target text, the quoted claim, and the counterargument is in a better position than a reader who sees a single score.

That is also the limitation of using a model as the judge. The judge adds another interpretation to a record that already contains several. It is useful as a reader and as a consistency check. It should not be presented as an authority. The interface labels the judge as a synthesis, not a verdict, and the report keeps the judge's text separate from the challenges. That separation is a small design decision with a large effect on how the output is read.

## 13. Threats to Validity and Ethics

### 13.1 Construct validity

The construct measured here is protocol compliance, not argument quality. I checked whether a challenge named its target, quoted claims, offered counterarguments, conceded a point, and ended with a verdict. Those features are necessary for the intended argument, but a challenge can satisfy them and still be wrong. I did not measure correctness or usefulness to a decision maker.

Two further constructs sit underneath that one. "State consistency" is measured as agreement among the interface, the report, the judge input, and `results.json`; that is binary and traceable, which makes it the strongest construct in the study. "Failure" is measured as a class assignment made by me from the artifacts, which is why Section 7 states the mapping rather than asserting it. The judge's content claims are reported as the judge's reading, not as verified findings.

### 13.2 Internal validity

The internal comparison is weak. The open-debate and directed runs used different numbers of calls, different dates, and different model states. Timing differences cannot be attributed only to the protocol. Model versions, account quotas, and provider load changed during the week. The judge saw model identities and was one of the participants. The observed differences fit the design explanation, but they do not prove it.

The strongest rival explanation is that the directed and broadcast outputs differ because the prompts differ in how directive they are, not because of the target structure. The directed prompt says "argue directly against X's answer" and lists three tasks; the broadcast prompt says "attack the strongest claim you think is wrong." A model may produce a target-specific critique simply because it was asked for one. The case cannot separate compliance from quality, and a study needs a control condition in which a broadcast prompt is given equally specific constraints.

### 13.3 External validity

External validity is limited by the design. One user, one machine, four providers, one focal prompt, one week. The findings may not transfer to other model combinations, tasks, or organizations. The design principles are stated at a level that should travel, but their value elsewhere is an empirical question.

Two boundaries are worth naming. The provider set is a 2026 snapshot of four agent CLIs, each of which may change its interface, pricing, or model aliases without notice; a deployment on different providers would face the same design problem with different failure details. The task type is a reasoning question with a short answer; the protocol was not tested on long documents, code changes, or tasks where verification is possible. The evidence supports the scope only for comparison and argument, not for task-solving.

### 13.4 Reliability and researcher position

Reliability is limited by the lack of repetition. Language model outputs are stochastic. A second run could produce different arguments or timings. I performed the qualitative analysis myself, without an independent coder. Another analyst might classify the failures differently.

I preserved raw artifacts, quoted the judge when it contradicted the presentation, included a second directed challenge, and reported failures that required code changes. Those measures improve traceability. They do not eliminate bias. The appropriate conclusion is analytic, not statistical. The remaining bias is not only confirmation bias: a builder who spent the week on authentication and launchd is likely to overestimate how much of the design problem is operational. The taxonomy counts classes rather than incidents, but the same person built it.

### 13.5 Ethics

Five ethical issues follow from the design, and none was measured in the case.

**Prompt injection and sanitization.** The system renders model output into HTML and embeds model output verbatim into other models' prompts. The renderer sanitizes HTML and URLs before display, and the tests include a regression for an obfuscated `javascript:` URL, but the argument protocol has no defense against a model that writes "ignore the previous instructions." A model's initial answer is content inside the challenger's prompt; a sufficiently adversarial answer could redirect the challenger. The case neither observed nor tested this.

**Cost and quota externalities.** Every call consumes someone's quota. The system has no budget cap, no pre-flight cost estimate, and no per-run spending limit. The Kimi 429 is the visible instance of an account running out.

**Vendor dependency.** The tool depends on undocumented command-line interfaces, authentication flows, output formats, and model aliases, all controlled by four vendors and changeable without notice. The adapters are heuristic; a provider change can break the tool. Local-first design does not remove the dependency; it moves the failure point.

**Data retention.** Prompts, answers, raw streams, and provider error text persist in local run directories. The case documentation describes no automated retention or deletion policy. Error text can contain account-specific strings, which is why the artifacts are local, and anything shared publicly needs a review pass. What providers retain is unknown and governed by their terms.

**Human subjects and dual use.** The case involved no human subjects. A reader study would change that and would need review and consent. The dual-use concern is that a verdict at the end of each challenge reads like a conclusion: a reader who treats the record as advice may act on one model's attempt to discredit another. Separating synthesis from challenges is a mitigation, not a guarantee.

### 13.6 Residual risk

**Table 19. Validity threats and residual risk**

| Threat | What it affects | Response in this study | Residual risk |
|---|---|---|---|
| Construct | Argument quality is inferred from protocol compliance | Separate structure from quality; report exact text | A well-formed challenge can still be wrong |
| Internal | Timing and format differences are confounded | Compare call structure and artifacts, not only wall time | Model and account changes cannot be undone |
| External | One prompt, four providers, one user | State the boundary; use principles rather than population claims | Transfer to other tasks is unknown |
| Reliability | Single runs and one coder | Preserve artifacts; include a second challenge; quote the judge | Another run or coder may classify differently |
| Researcher | Builder interprets own system | Include failures that forced code changes; quote contradictory judge output | Confirmation bias remains possible |
| Ecological | Local macOS tool, not a team workflow | Describe the deployment and its OS constraints | Team use may expose different failures |
| Security | Model output enters other models' prompts unsanitized | Sanitised HTML and URL handling for display | Injection inside the argument is not defended |
| Cost | Argument calls consume user quota | Surface provider errors and hints | No budget cap or estimate |
| Data | Raw prompts and outputs persist locally | Documented local storage; selective sharing | No retention or deletion policy |

The table does not remove the threats. It makes them part of the argument. A reader can disagree with my interpretation and still inspect the artifacts that produced it.

## 14. Replication Package

### 14.1 What a replicator needs

The case is reproducible at the level of structure and protocol, and not at the level of outputs. The package is the project directory that produced the case: the engine, the server, the browser assets, the installer, the tests, the figures, and the written account.

**Table 20. Replication package contents**

| Component | What it provides | What it reproduces |
|---|---|---|
| `ensemble.py` | Engine: adapters, argument builders, artifact writers, report renderer, CLI | The execution and argument protocol |
| `serve.py`, `web/` | Local HTTP server and browser interface | The live view, challenge controls, polling |
| `desktop/` | Installer, LaunchAgent, Dock application | The local deployment path |
| `tests/` | 116-test stdlib suite for parsers, config, sanitization, artifacts, HTTP API | Implementation regressions |
| `docs/` | Architecture and interface figures | The visual record |
| `CASE_STUDY.md`, `references.bib` | The published account and its sources | The narrative and its citations |
| Build scripts | Report and manuscript builds | The rendered documents |

The run artifacts are not in the public package. They are local because they contain model output and account-specific error text, and the case says they can be shared selectively after review (Appendix C). A replicator will generate their own runs, which is the point.

### 14.2 Environment and commands

The environment is macOS as of October 2026, Python 3.9, standard library only, with four provider CLIs installed and authenticated. The sequence is the one in Appendix C and Appendix F: readiness probe, record provider versions and account states, run the focal prompt with a judge and no debate, inspect `results.json`, run the two directed challenges, compare the report and interface against the saved results, and check that the service survives a restart. The commands are short: `ensemble doctor --probe`, then `ensemble "..." --judge`, then `ensemble challenge ~/.ensemble/latest --from kimi --to deepseek` and the same with `--from gemini --to codex`.

### 14.3 What reproduces and what does not

Structural properties reproduce: the file layout, the artifact schema, the state transitions, the message templates, the report renderer, the sanitizer, and the failure-handling paths. A replicator should observe every invariant in Table 7 that is enforced by construction, and should be able to provoke the state failures only by reintroducing them.

Three things do not reproduce. Provider versions, model aliases, quotas, and entitlement rules have drifted since October 2026; the case does not pin them, and the exact versions in use are unknown from the record. Model outputs are stochastic and dated, so the answers and arguments are examples, not fixtures. Timings are single-run observations on one machine under unknown load, so Table 14 records what happened once, not expected values. Two smaller things are also lost: the 38-run corpus contains personal prompts and is excluded, and the qualitative coding of arguments is my reading.

### 14.4 What a third party should check

A replicator can validate the account without reproducing the outputs. Five checks are enough: the readiness probe reports the same four providers; every expected provider has either an answer or a failure; `report.html` regenerates from `results.json` without a provider call; a challenge added to a saved run reaches the report and the judge; and the interface, report, and judge agree about the run after a restart. If those pass, the protocol exists in the copy. If they fail, the copy has diverged from the design, and the difference is the finding.

The missing piece is version logging. The run metadata records the engine version, the command, the provider set, the model aliases, the context mode, and timestamps; it does not record provider CLI versions, entitlement tiers, or account state. A replication attempt should add those by hand, and a future system should write them into `meta.json` before the first call. Without them, a difference between two runs cannot be attributed to the protocol or to the world.

## 15. Future Work

The obvious next step is a controlled evaluation. A fixed prompt set, repeated runs, blinded human ratings, and a pre-registered rubric would let a study compare independent answers, self-consistency, directed challenge, open debate, and judge-only synthesis on the same questions. It could measure whether debate changes the answer, whether the change is justified, and whether a reader can verify the claims.

A feasible design would use prompts from four categories: factual questions with a checkable answer, design questions with defensible alternatives, policy questions with value disagreement, and ambiguous questions with no clear answer. Each prompt would run under five conditions: independent answers, self-consistency with several samples, directed challenge, open debate, and judge-only synthesis. Three repetitions would be enough to see variance without making the study unmanageable. Two raters, blind to condition, would score argument quality and decision confidence. A subset would be fact-checked against sources. The outcome would be a comparison of formats, not a leaderboard of models.

The protocol also needs structure. Free-form rebuttals are hard to compare. A JSON object with claims, evidence, confidence, target claim, counterargument, and concession would make the argument machine-readable. The report could render a claim graph and show which attacks landed. The prose would remain, but the structure would be inspectable.

Directed challenge is currently one-way. A two-call exchange, attack then response, would test whether the challenge survives a reply. The exchange should stop after one response. A long debate rewards stamina, not truth.

Judging needs more work. The judge should not see model names. Several judges should score the same run, and the system should report disagreement. That would reduce brand and self-preference effects and make uncertainty visible. Evidence checking would help too. A debate between models with no retrieval can amplify confident errors; requiring sources would change what the arguments look like.

The engineering work is less interesting but necessary. Streaming, per-challenge cancellation, token budgets, and caching would make the system usable for shorter interactions. A signed application, one runtime location, Keychain storage, an expanded end-to-end and UI test suite, and a health check that verifies the server would make it reliable enough for a broader study.

An engineering evaluation would ask different questions from a model evaluation. How often does the server survive a restart? How often does a provider change break the parser? How long does a new provider take to integrate? How many state mismatches appear per hundred runs? Those are measurable, and they matter more to a user than a small difference in argument quality. The case suggests that these questions deserve as much attention as the debate protocol.

## 16. Conclusion

The four model CLIs still agree that a five-person startup should probably use a monorepo. What changed is the visibility of the reasoning. The first round showed four versions of the same answer. Broadcast debate showed a shared assumption being corrected. Directed cross-examination showed one model attacking another model's specific claims. The interface and report showed the difference between a debate that happened and a debate the system claimed had happened.

The evidence supports explicit challenge targets and one canonical state. The saved artifacts document the observed exchanges and failures. Repeated trials are needed to assess whether the protocol improves decisions, and a blind judge would be a better test of the arguments themselves.

## References

Chan, C.-M., Chen, W., Su, Y., Yu, J., Xue, W., Zhang, S., Fu, J., & Liu, Z. (2023). *ChatEval: Towards better LLM-based evaluators through multi-agent debate.* arXiv:2308.07201. https://doi.org/10.48550/arXiv.2308.07201

Du, Y., Li, S., Torralba, A., Tenenbaum, J. B., & Mordatch, I. (2023). *Improving factuality and reasoning in language models through multiagent debate.* arXiv:2305.14325. https://doi.org/10.48550/arXiv.2305.14325

<span class='nowrap'>Hevner, A. R., March, S. T., Park, J., & Ram, S. (2004). Design science in information systems research. <em>MIS Quarterly, 28(1)</em>, 75-105.</span> https://doi.org/10.2307/25148625

Irving, G., Christiano, P., & Amodei, D. (2018). *AI safety via debate.* arXiv:1805.00899. https://doi.org/10.48550/arXiv.1805.00899

Khan, A., Hughes, J., Valentine, D., Ruis, L., Sachan, K., Radhakrishnan, A., Grefenstette, E., Bowman, S. R., Rocktäschel, T., & Perez, E. (2024). *Debating with more persuasive LLMs leads to more truthful answers.* arXiv:2402.06782. https://doi.org/10.48550/arXiv.2402.06782

Liang, T., He, Z., Jiao, W., Wang, X., Wang, Y., Wang, R., Yang, Y., Shi, S., & Tu, Z. (2024). *Encouraging divergent thinking in large language models through multi-agent debate.* In Proceedings of the 2024 Conference on Empirical Methods in Natural Language Processing. arXiv:2305.19118. https://doi.org/10.48550/arXiv.2305.19118

<span class='nowrap'>Runeson, P., & Höst, M. (2009). Guidelines for conducting and reporting case study research in software engineering. <em>Empirical Software Engineering, 14(2)</em>, 131-164.</span> https://doi.org/10.1007/s10664-008-9102-8

Wang, X., Wei, J., Schuurmans, D., Le, Q., Chi, E., Narang, S., Chowdhery, A., & Zhou, D. (2023). *Self-consistency improves chain of thought reasoning in language models.* In International Conference on Learning Representations. arXiv:2203.11171. https://doi.org/10.48550/arXiv.2203.11171

Wu, Q., Bansal, G., Zhang, J., Wu, Y., Li, B., Zhu, E., Jiang, L., Zhang, X., Zhang, S., Liu, J., Awadallah, A. H., White, R. W., Burger, D., & Wang, C. (2023). *AutoGen: Enabling next-gen LLM applications via multi-agent conversation.* arXiv:2308.08155. https://doi.org/10.48550/arXiv.2308.08155

Zheng, L., Chiang, W.-L., Sheng, Y., Zhuang, S., Wu, Z., Zhuang, Y., Lin, Z., Li, Z., Li, D., Xing, E. P., Zhang, H., Gonzalez, J. E., & Stoica, I. (2023). *Judging LLM-as-a-judge with MT-Bench and Chatbot Arena.* In Advances in Neural Information Processing Systems 36. arXiv:2306.05685. https://doi.org/10.48550/arXiv.2306.05685

## Appendix A. Prompt Templates

### A.1 Initial round

The provider receives the user prompt without additional model-specific instructions. The context mode determines the working directory and any project snapshot.

### A.2 Directed challenge

```text
You are {challenger}. The original prompt was:
{prompt}

--- {target}'s answer (the target) ---
{target_answer}

--- Your own initial answer ---
{challenger_answer}

Argue directly against {target}'s answer. Do not restate your own answer as
the main body and do not write a generic essay. Do exactly three things:
1. Quote the two weakest claims in {target}'s answer and explain precisely
   why they fail.
2. Give the strongest counterargument or missing evidence for each.
3. State what a better answer would conclude, and where you concede the
   target may be right.

Max 300 words. End with a line starting "Verdict:".
```

### A.3 Open debate

```text
The models answered the same prompt independently. Each model now receives
all initial answers, with its own answer marked.

--- Prompt ---
{prompt}

--- Initial answers ---
{answers}

--- Your own answer ---
{own_answer}

Attack the strongest claim you think is wrong. Defend or correct your own
answer. State your position now. Do not simply restate your first answer.
```

### A.4 Judge

```text
Compare the answers and the argument rounds for the following prompt.

--- Prompt ---
{prompt}

--- Initial answers ---
{answers}

--- Rebuttals and cross-examinations ---
{arguments}

Write: (1) a bottom line, (2) where the models agree and disagree, (3) which
arguments landed and which failed, (4) a model-by-model assessment, and
(5) what to trust where. Note who changed position. Do not invent agreement.
```

## Appendix B. Artifact Schema

Each run directory contains the following files:

| File | Contents |
|---|---|
| `prompt.md` | The prompt as submitted |
| `meta.json` | Version, prompt, models, debate flag, timings, status, results |
| `results.json` | Normalized results, including optional rebuttals |
| `<model>.md` | Cleaned initial answer |
| `<model>.stdout.txt` | Raw provider stdout |
| `<model>.stderr.txt` | Raw provider stderr |
| `<model>.debate.md` | Optional open-debate rebuttal |
| `challenge-*.md` | Directed cross-examination |
| `challenges.json` | Challenge metadata and text |
| `judge.md` | Optional synthesis |
| `report.html` | Rendered report |
| `report.md` | Markdown report |

The `Result` object contains `key`, `label`, `model`, `status`, `text`, `elapsed`, `tokens_total`, `cost`, `error`, `hint`, `stdout`, `stderr`, and an optional `debate` result. The challenge record contains `id`, `from_key`, `from_label`, `to_key`, `to_label`, `status`, `text`, `error`, `hint`, `elapsed`, `tokens_total`, `model`, and `created_at`.

## Appendix C. Focal Run Details and Reproduction

**Focal prompt.** "Should a 5-person startup use a monorepo? Answer yes or no, then justify in under 50 words."

**Focal run R1.** Four providers, open debate, judge. Initial answers: Kimi 247 characters in 12.8 s; Gemini 329 characters in 10.5 s; DeepSeek 232 characters in 5.5 s; Codex 303 characters in 21.5 s. Open-debate rebuttals: Kimi 70.8 s, Gemini 25.9 s, DeepSeek 11.6 s, Codex 19.1 s. Total wall time 145.8 s.

**Challenge C1.** Kimi to DeepSeek, 32.1 s, 1,202 characters, status ok. Challenge C2: Gemini to Codex, 29.6 s, 1,994 characters, status ok.

**Reproduction commands.**

```sh
ensemble "Should a 5-person startup use a monorepo? Answer yes or no, then justify in under 50 words."
ensemble challenge ~/.ensemble/latest --from kimi --to deepseek
ensemble challenge ~/.ensemble/latest --from gemini --to codex
ensemble --debate "Explain when a monorepo helps and when it hurts."
```

**Environment.** macOS, October 2026; Python 3.9; local HTTP server; providers as listed in Table 1; accounts and quotas varied during development.

**Availability.** The case study, architecture figure, and prompt templates are in the project directory. The run artifacts are local because they contain model output and account-specific error text. They can be shared selectively after review.

## Appendix D. Case Chronology

The chronology is deliberately coarse. Provider failures happened during development, and I did not keep a timestamped incident log for every authentication error. The table records the events that can be tied to artifacts.

**Table 21. Case chronology**

| Window | Event | Evidence |
|---|---|---|
| Build window, before 20 October | Claude removed after its OAuth session expired; Kimi default account returned 429s; Gemini CLI hit `IneligibleTierError` | CLI error output; provider notes |
| 19 to 20 October | CLI and local web interface built; four-provider round and report working | Source; run directories |
| 20 October | Focal run R1: four initial answers, four open-debate rebuttals, judge report | `meta.json`, `results.json`, `judge.md` |
| 25 October | Directed challenges C1 and C2 added to R1; challenge bar added to the web UI | `challenges.json`, screenshots |
| 25 October | Split-state and render-state bugs fixed; report regenerated | Code changes; judge output |
| 25 October | Case study drafted and revised | This document |

The chronology shows why the case is not a clean experiment. The protocol, the interface, and the provider accounts all changed during the same week. The focal run captures the system after the open-debate feature worked. The challenges capture it after the directed feature worked. The failures capture the transitions between those states.

## Appendix E. Glossary

**Agent CLI.** A vendor-supplied command-line program that runs a language model with its own authentication, tools, and output format. The four agents in this case are Kimi, Gemini, DeepSeek, and Codex.

**Canonical artifact.** A saved file that every view of a run reads from. In this system, `results.json` and the per-model markdown files are canonical; the interface and report are derived views.

**Challenge record.** The saved output of one directed cross-examination, including the challenger, the target, the status, the text, the timing, and the token count when available.

**Directed cross-examination.** An argument call in which one model receives one other model's answer as its target and is asked to attack specific claims, concede what is right, and state a verdict. It is the primary argument mode in the final system.

**Judge.** A model call that reads the initial answers and any argument artifacts and writes a comparison. It is optional and is not treated as ground truth.

**Open debate.** An argument call in which every successful model receives every initial answer and writes a rebuttal. It is broader and more expensive than a directed challenge, and it is off by default.

**Run.** One execution of a prompt across a set of providers, stored in a directory with metadata, results, raw streams, and a report.

**Run directory.** The filesystem container for a run. It holds the prompt, metadata, normalized results, raw streams, argument artifacts, judge output, and report.

**Provider adapter.** The code that builds a provider-specific command, supplies its working directory and timeout, captures its streams, and normalizes its output into a `Result`.

**Artifact-first design.** A design stance in which saved files, not a live session or a UI state, are the source of truth. Every view is generated from the artifacts.

**Argument round.** One pass in which models read prior answers and produce a rebuttal or challenge. The final system uses at most one such round per run.

**Broadcast debate.** The open-debate format in which every successful model receives every initial answer and writes a rebuttal. It is distinguished from a directed cross-examination, which has one challenger and one target.

**Split-state failure.** A failure in which two components represent the same run differently, so the interface, report, or judge can disagree about what happened. The term is used in this paper for the rebuttal-persistence and challenge-rendering bugs.


## Appendix F. Reproduction Checklist

A reader who wants to repeat the focal case can use the following checklist. It assumes the four CLIs are installed and authenticated. Section 14 states the full replication package and what cannot be reproduced.

1. Run `ensemble doctor --probe` and confirm which providers are authenticated. Do not assume that a provider that worked last week still works.
2. Record the provider versions and account states, because the model aliases and quotas change.
3. Run the focal prompt with `--judge` and no `--debate` to produce the independent round and the synthesis.
4. Inspect `results.json` and confirm that every expected provider has a result. A missing result is a finding, not a cleanup step.
5. Run `ensemble challenge ~/.ensemble/latest --from kimi --to deepseek` and inspect the challenge record.
6. Open `report.html` and compare the interface, the report, and the judge input. If they disagree, preserve the run directory before changing code.
7. Record the wall time, per-provider time, output length, and any provider error text.
8. If the system is running as a local service, check that the LaunchAgent is enabled and that the server survives a restart.

The checklist is intentionally short. The point is not to standardize every prompt. It is to make the evidence reproducible enough that another reader can see where a claim came from.

## Appendix G. Ensemble Command and API Reference

### G.1 Command surface

**Table 22. Command surface**

| Command | Purpose | Useful options |
|---|---|---|
| `ensemble "prompt"` | Run the four-provider comparison | `--only`, `--skip`, `--model`, `--context`, `--timeout`, `--judge`, `--debate`, `--out`, `--open` |
| `ensemble challenge <run>` | Make one model argue against another model's saved answer | `--from`, `--to`, `--model`, `--timeout`, `--json`, `--open` |
| `ensemble judge <run>` | Re-synthesize an existing run | `--provider`, `--model`, `--timeout`, `--open` |
| `ensemble web` | Start the local browser interface | `--port`, `--open`, `--no-open` |
| `ensemble doctor --probe` | Check provider readiness with a one-word prompt | `--only`, `--strict`, `--no-color` |
| `ensemble providers` | List detected providers and configuration | `--quiet` |
| `ensemble last` | Open the newest run | `--open` |

The run command also accepts `--prompt-file`, `--json`, `--quiet`, `--sequential`, `--keep-workdirs`, `--strict`, and `--dry-run`. The last two are useful for automation: `--strict` makes a provider failure visible to a shell script, and `--dry-run` prints commands without launching them.

### G.2 Run states

**Table 23. Run and challenge states**

| State | Meaning |
|---|---|
| `starting` | The run directory exists; provider processes are being prepared |
| `running` | Initial provider calls are in flight |
| `debating` | Open-debate rebuttals are in flight |
| `judging` | A judge call is in flight |
| `finalizing` | Artifacts and the report are being written |
| `done` | Every expected result succeeded |
| `partial` | At least one result succeeded; at least one did not |
| `error` | No result succeeded |
| `cancelled` | The run was stopped by the user |
| `cancelling` | Cancellation has been requested |

A directed challenge uses its own short state sequence: `running`, then `ok`, `error`, or `timeout`. It does not change the parent run's terminal state.

### G.3 HTTP interface

**Table 24. HTTP endpoints**

| Method and path | Purpose |
|---|---|
| `GET /api/health` | Server version and liveness |
| `GET /api/providers` | Provider readiness, defaults, and model labels |
| `GET /api/runs` | Recent run history |
| `GET /api/runs/<id>` | Live or saved run snapshot, including challenges |
| `POST /api/runs` | Start a run |
| `POST /api/runs/<id>/cancel` | Cancel an active run |
| `POST /api/runs/<id>/challenge` | Start a directed challenge on a finished run |
| `GET /runs/<id>/report.html` | Static report |
| `GET /runs/<id>/judge.md` | Judge text |

The server binds to 127.0.0.1 and has no authentication. That is appropriate for a single-user local tool. It would not be appropriate for a shared machine or a network service.

### G.4 Deployment layout

**Table 25. Deployment paths**

| Path | Role |
|---|---|
| `~/.ensemble/runs/` | Run directories and reports |
| `~/.ensemble/latest` | Link to the newest run |
| `~/.ensemble/app/` | Deployed runtime used by the LaunchAgent |
| `~/.ensemble/gemini.key` | Local Gemini API key, mode 600 |
| `~/Library/LaunchAgents/local.ensemble.web.plist` | LaunchAgent definition |
| `~/Applications/Ensemble.app` | Dock application |
| `~/Desktop/Ensemble.webloc` | Desktop shortcut |

The deployed runtime is a copy, not a symlink. Editing the source tree does not change the running application until the installer copies the files again and restarts the agent. That detail caused a confusing debugging session during the case: the source contained a fix, the browser did not, and the running server was still reading the deployed copy.

### G.5 Reading a run in order

When a report looks wrong, the run directory usually explains why. The order matters.

1. Read `meta.json` for the prompt, provider set, status, and wall time.
2. Read `results.json` for the normalized results and any attached debates.
3. Read `challenges.json` and the `challenge-*.md` files for directed arguments.
4. Read `judge.md` for the synthesis.
5. Read `report.html` last. The report is a view; it is not the evidence.

If the report and the interface disagree, compare both against `results.json`. If the judge describes a round that is not in the files, the judge is reading a different state, not hallucinating a debate.

## Appendix H. Source Map

The design principles are abstractions; the code is where they are enforced or violated. The two tables below trace the main responsibilities to concrete symbols. The point is not to document every function. It is to let a reader move from a claim in the paper to the code that would confirm or contradict it.

### H.1 Engine and artifact layer

**Table 26. Engine and artifact source map**

| File and symbols | Responsibility | Principle | What it makes visible |
|---|---|---|---|
| `ensemble.py`: `load_config`, `provider_settings`, `all_keys`, `gemini_api_key`, `deepseek_account_available` | Provider discovery, authentication state, model defaults | DP1, DP6 | Why a provider is present, skipped, or failing before a prompt is sent |
| `Spec`, `build_specs`, `select_keys`, `parse_models` | Build provider-specific commands and resolve the panel | DP1, DP2 | The exact command line used for each provider |
| `execute`, `kill_tree`, `parse_output`, `hint_for` | Run a subprocess, enforce timeout, capture streams, normalize text and errors | DP1 | Raw stdout and stderr, status, elapsed time, failure hint |
| `Result`, `run_specs`, `Progress`, `print_summary` | Parallel first round and CLI progress | DP2, DP7 | The normalized results that every later layer reads |
| `build_debate_prompts`, `debate_round`, `attach_debates` | Optional broadcast rebuttal round | DP4 | Open-debate text, status, and per-model timing |
| `build_challenge_prompt`, `run_challenge`, `result_to_challenge` | Directed cross-examination | DP4, DP5 | C1 and C2, including the target and the verdict |
| `load_challenges`, `save_challenge` | Persist challenge records | DP3 | `challenges.json` as an independent argument record |
| `result_to_dict`, `dict_to_result`, `write_artifacts`, `load_run` | Serialize and reload the canonical run | DP3 | Whether a debate survives a restart and reaches the judge |
| `render_markdown`, `write_report`, `card_html`, `debate_section_html`, `challenge_section_html` | Render the static report | DP3, DP7 | The report a reader sees, derived from the saved results |
| `build_judge_prompt`, `run_judge` | Construct the synthesis input and write the judge output | DP7 | Which rounds the judge actually received |
| `cmd_run`, `cmd_judge`, `cmd_challenge`, `cmd_doctor`, `cmd_web`, `cmd_last` | CLI entry points and option plumbing | DP1, DP6 | The user-facing commands described in Appendix G |

The split-state bug is visible in this map. `write_report` and `build_judge_prompt` read `Result.debate`. The live server's `snapshot` read `part["debate"]`. For a period, only the second path was populated. The report and judge were not wrong about the data they received; they received a result object with no debate attached.

### H.2 Service, interface, and deployment

**Table 27. Service and interface source map**

| File and symbols | Responsibility | Principle | What it makes visible |
|---|---|---|---|
| `serve.py`: `Run._build`, `Run._worker`, `Run._maybe_finish`, `Run._run_debate`, `Run._finalize`, `Run.cancel`, `Run.snapshot` | Server-side run lifecycle and live state | DP2, DP3, DP7 | Status transitions, cancellation, and the live pane view |
| `Run._debate_result` | Attach an open-debate result to the run and its initial result | DP3 | The exact point where the split-state bug was fixed |
| `ChallengeState`, `start_challenge`, `challenges_for` | Post-run challenge execution and snapshot merging | DP3, DP4, DP5 | A challenge that can run after the run is `done` |
| `derive_status`, `disk_snapshot`, `history`, `Handler` | Saved-run reconstruction, history, and HTTP routes | DP3, DP7 | How an old run is rendered without the original process |
| `web/app.js`: `startRun`, `loadRun`, `startPolling`, `renderPanes`, `updatePane` | Composer, polling, and four-pane rendering | DP3, DP7 | The live view that can diverge from the report |
| `renderChallengeBar`, `startChallenge`, `renderChallenges` | Cross-examine controls and challenge display | DP4, DP5 | How a user selects attacker and target |
| `renderJudge`, `renderHistory`, `showEmpty` | Judge display, history rail, empty states | DP3, DP7 | The parts of the interface that read completed artifacts |
| `desktop/install.sh`, `install-dock.sh`, `launch.sh` | Runtime copy, LaunchAgent, Dock application | DP6 | Why the installed app can lag the source tree |

### H.3 The state fix as a code path

The bug is easiest to explain as a path through the code.

Before the fix, `Run._debate_result` wrote the rebuttal into the live run's `part` dictionary. `Run.snapshot` read that dictionary, so the browser showed four completed rebuttals. `Run._finalize` built its result list from `part["result"]`. Those initial `Result` objects still had `debate = None`. `write_artifacts` serialized them, `write_report` rendered no rebuttal sections, and `build_judge_prompt` sent the judge a record without the round. Every component behaved correctly for the object it received; the objects were not the same.

After the fix, `Run._debate_result` sets `part["debate"]` for the live view and `initial.debate = result` for the canonical result. `result_to_dict` then serializes the debate with the initial answer, `load_run` restores it, and both the report and the judge read the same field. The split is closed by an invariant: the initial result owns its rebuttal, and every view derives from that result.

The challenge path needed a smaller version of the same treatment. `challenges_for` merged saved challenge records and active challenge snapshots, then rendered the text to HTML at the boundary. Before that, the browser received the text but not the HTML, and treated the missing HTML as a failure. The fix did not change the challenge prompt. It changed the representation the interface consumed.

### H.4 What the map does not cover

The map does not include the provider parsers, the report CSS, or every UI state. Those are implementation details that change more often than the design principles. A 116-test stdlib suite now covers the parsers, configuration, sanitization, artifacts, and the HTTP API, but it did not exist during the design work and does not cover end-to-end provider runs, the challenge lifecycle, or the UI. The map is a reading aid, not a verification claim. A reader who wants to verify a specific statement should start with the artifact named in the table, then compare it with the report and the judge.

The source map also shows where the case is weakest. The design principles are implemented across a small number of files, but only a few of them are directly tested by the case. DP1 and DP6 are supported by failures. DP3 is supported by a bug and a fix. DP4 and DP5 are supported by two challenges. DP2 is supported by the shape of the first round, not by an experiment. The uneven evidence is part of the result.
