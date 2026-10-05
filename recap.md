# CORE Phase 1 progress and experiment update

Responsibilities: Manos - FarmAgent-derived native function calling. Siskos - CORE-to-ARE migration.

## Where we are

Two execution paths are implemented: FarmAgent-derived native function calling
and a migration to Meta ARE. The branch records **89 passing offline tests** and
live validation of the migration. Two GPT-5 nano experiments were run per
path on the same 51 tasks, plus two full ARE runs over 71 executable scenarios.
The original/default runner has **not** been switched.

## FarmAgent to CORE function-calling migration

FarmAgent's calling components were ported into CORE and connected to the
existing Python world methods. The model uses native API `tool_calls`. The
runtime validates arguments, bounds requests and tool calls, starts fresh
conversation and trace state per run, and records failed and skipped attempts.
Computations passed scripted and live nano checks. A shared runner and saved-action
evaluator are available as an opt-in path.

The original September checkpoint is preserved separately from later repairs:

| Measure | September result |
|---|---|
| Live coverage | 51 tasks across 11 paper worlds, GPT-4.1 nano |
| Runtime outcome | 45 final responses; 6 call-limit stops |
| Legacy evaluation | 30 scored; 24 scored 1.0; 21 unscored |
| Software and scope | 51 offline tests passed; 26 other source tasks deferred |

The 26 deferred tasks comprised eight setup issues, twelve Transactions ID
mismatches and six missing Web Browsing fixtures. The unscored traces had mapping
limitations or execution errors. Neither final replies nor legacy scores establish
independent task success. See the [original coverage report](docs/PAPER_WORLD_COVERAGE.md).

## CORE-to-ARE migration and repairs

Tool/state adapters expose CORE methods as ARE app tools, with
state save/load/reset and stable returned-value snapshots. CORE prompts, setup
operations and references become ARE scenarios. A bounded OpenAI connection and
trace conversion let CORE score ARE events and rejected world-tool attempts.
The bridge invokes CORE's Python functions; this ARE agent emits **JSON text
actions**, while native function calling remains a separate comparison path.

All **77 source tasks across 13 implemented paper worlds** are registered;
**71 execute**, and six Web Browsing tasks remain blocked by missing HTML fixtures.
Farm and Arm implementations are absent; Configurations is outside this paper scope.
ARE handles setup before the user request. The native shared runner still defers
setup-dependent tasks; the matched comparison covers the original 51 tasks.

Repairs cover Navigation's grid-size access, Computations/Validation reference
errors, CRUD reference target values, explicit Transactions ID aliases, and six
task DFAs. The separate **`core-paper-v1.1`** evaluator implements the five Section 3
metrics, retains failed/unmapped calls, and scores all 51 historical native traces.
Historical legacy scores remain available and must not be mixed with revised scores.

The six DFA corrections are applied to a copy for revised evaluation; the original
dataset file is unchanged. **Transactions 7 is a semantic benchmark correction**,
not just a typo. Runtime failures/rejections count as harmful without advancing the
DFA; unmatched calls receive distinct harmful tokens. These are explicit adapter
conventions. Section 4's HLR refinement is outside this implementation. See
[repairs and evaluation conventions](docs/ARE_REPAIRS.md).

## Code review map

| Review area | Files and what to inspect |
|---|---|
| Native calling path | [agent.py](function_calling/agent.py), [argument validation](function_calling/argument_normalizer.py), [shared runner](function_calling/experiments.py): native calls, execution limits, trace recording and fresh state |
| ARE worlds and setup | [catalog.py](are_integration/catalog.py), [registration.py](are_integration/registration.py): world wrappers, scenario registration, setup events, read/write annotations, JSON schemas in tool descriptions |
| ARE model loop and trace bridge | [live.py](are_integration/live.py), [trace.py](are_integration/trace.py), [reporting.py](are_integration/reporting.py): `core-are-json-v3`, bounded requests, failed attempts, model replies versus automatic stops |
| Revised scoring and benchmark changes | [paper_evaluation.py](function_calling/paper_evaluation.py), [dataset_repairs.py](function_calling/dataset_repairs.py), [dataset_identity.py](function_calling/dataset_identity.py), [policy selection](function_calling/evaluation.py) |
| Source-world repairs | [navigation.py](worlds/navigation.py), [computations.py](worlds/computations.py), [crud.py](worlds/crud.py), [validation.py](worlds/validation.py) |
| Matched experiment and results | [validation_batch.py](are_integration/validation_batch.py), [validation_report.py](are_integration/validation_report.py), [validation guide](docs/ARE_WEEK1_VALIDATION.md), [Run 1 JSON](docs/results/are_native_gpt5nano_2026-10-01.json) |
| Verification | [parity.py](are_integration/parity.py), [catalog tests](tests/test_are_catalog.py), [live adapter tests](tests/test_are_live.py), [metric tests](tests/test_paper_evaluation.py): reference execution parity, protocol checks, hand-calculated metric examples |

[Changes from main](https://github.com/Synkrasis-Labs/CORE/compare/main...siskos/core-are-integration): `baseline_agent.py`, `run_experiments.py`, `core.py`, and
`all_worlds_dataset.json` are unchanged. `evaluate.py` only loses an unused import; new scoring lives in the versioned module above.
ARE installation/discovery is in [pyproject.toml](pyproject.toml) and
[requirements-are.txt](requirements-are.txt), pinned to ARE 1.2.0.

## Two GPT-5 nano experiments

Both runs use six model requests per episode, uncapped completion
output, 30-second request timeouts and no SDK retries. The final reply consumes
the request budget; native execution also caps tool calls at six. Run 2 uses fresh
worlds/conversations and preserves Run 1.

[Run 1 per-task results](docs/results/are_native_gpt5nano_2026-10-01.json) are
tracked. Run 2 summary figures are included below; its supporting comparison JSON
still needs to be added to the branch.

| Same 51 tasks | ARE Run 1 | Native Run 1 | ARE Run 2 | Native Run 2 |
|---|---:|---:|---:|---:|
| Path Correctness | 0.8231 | 0.8765 | 0.8358 | 0.8658 |
| PC-KTC | 0.8347 | 0.8892 | 0.8460 | 0.8773 |
| Prefix Criticality | 0.8565 | 0.9234 | 0.8341 | 0.9184 |
| Harmful-Call Rate | 0.1471 | 0.0961 | 0.1732 | 0.1111 |
| Efficiency | 0.9444 | 0.9215 | 0.9630 | 0.9296 |
| Paths scoring 1.0 | 36/51 | 35/51 | 35/51 | 35/51 |
| Accepting DFA paths | 36/51 | 40/51 | 35/51 | 39/51 |
| Model final replies | 41/51 | 39/51 | 43/51 | 41/51 |
| Total tokens | 687,472 | 284,256 | 664,927 | 285,465 |

Higher is better for the five metrics except Harmful-Call Rate. Efficiency is
defined for 45/51 episodes in each column. PC-KTC includes ordering; Prefix
Criticality penalizes earlier harmful calls. Harm follows the task DFA and the
documented adapter rules. Token totals include model reasoning tokens where supplied.

### Comparison across repeats

Across 102 episodes per path, mean Path Correctness is **0.8295 ARE versus
0.8712 native**; mean Harmful-Call Rate is **0.1601 versus 0.1036**. These represent
two observations per task. Between runs, Path Correctness improved/declined on
5/5 ARE tasks and 4/5 native tasks; the others were unchanged.

Native has higher pooled Path Correctness, lower harm, and fewer tokens in both
runs; ARE has more final replies and higher path efficiency. Native is the
stronger default-path candidate on current evidence,
subject to review before any switch. ARE provides the scenario/state bridge.

### Full ARE coverage and robustness

| All 71 ARE tasks | Run 1 (tracked) | Run 2 (summary only) |
|---|---:|---:|
| Mean Path Correctness | 0.8497 | 0.8589 |
| Model final replies | 56 | 58 |
| Automatic stop messages | 12 | 10 |
| Provider error events | 0 | 1 |
| World-tool errors/rejections | 0 | 0 |
| Action-format error events | 34 | 23 |
| JSON-execution error events | 3 | 3 |

Run 1 had three episodes without either reply type. Native Run 1 had no provider
failures and one rejected extra `app_name` argument to `print_application_history`,
retained in scoring. Native Run 2 recorded no provider/tool errors; the
ARE Run 2 provider error was a timeout in Writing 5, retained without retry or
exclusion. Error events are not counts of failed episodes.

## What this establishes, and what remains

The model, tasks and request settings are matched, but prompts, state observations,
argument normalization and interfaces differ. Two repeats show variation; they
do not isolate the calling interface's causal effect or establish statistical
significance. Model replies, accepting DFA paths and scores are distinct from
independently verified task success. Only Computations 1 and CRUD 2 have dedicated
state validators; both passed Run 1. The branch records reference parity for all
71 executable tasks, which checks the bridge rather than arbitrary model success.

For review, start with this recap, the code map, and the tracked Run 1 JSON.
Raw ARE traces/source snapshots are ignored under `runs/are/`; they are not shipped
with the branch. September native runs and compact ARE results are tracked.

Next work, following the team's CoA:

1. Add the second-run comparison JSON for review; resolve the six missing Web
   Browsing fixtures and review readiness before changing the default runner.
2. Add more LLMs/API access, run broader experiments with team/edge-GPU support
   (including Thor), and continue scenario expansion.
3. Select one or two related-work papers and implement their methods from the
   available repositories.
4. Fix Farm-FOS and integrate FAIRY scenarios; align FOS with yield outcomes and
   compare against FAIRY, KTC, BFCL and related measures.
5. Consolidate ARE/native and related-work comparisons, then write the paper.

This remains an extension of the original CORE paper, not the CORE 2.0 redesign.
