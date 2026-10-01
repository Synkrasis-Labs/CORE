# Verified repairs and revised CORE evaluation

The subsequent [Week 1 live validation](ARE_WEEK1_VALIDATION.md) includes the
v3 argument-schema repair and fresh matched-model results. The saved-run
numbers below describe the earlier offline repair checkpoint.

1 October 2026. The authoritative paper specified by the user is
`2509.20998v1 (2).pdf` in Downloads (14 pages; SHA256
`e13731b15ed55b8fa6b7f48c9d21c1be83d5d04d856bd400368e01d11e8c6482`),
Sections 2–3 and equations 3–8. The corresponding public paper is
[CORE: Full-Path Evaluation of LLM Agents Beyond Final State](https://arxiv.org/html/2509.20998v1).

The initial repair pass inspected `CORE_LAW_NeurIPS_2025 _Final.pdf`, an
anonymous draft despite its filename. The specified arXiv PDF was subsequently
checked directly: its condensation rules and five metric definitions in
equations 3–8 agree with those used in the implementation, including the
0.5 Kendall convention for fewer than two matches and undefined efficiency
for traces shorter than every golden path. No calculation changes were needed
for this source-version correction. Use the specified arXiv PDF going forward.

## What changed

- Navigation uses its existing `self.grid_size` rather than an absent state key.
  Movement and out-of-bounds behavior are checked in the shared and ARE runners.
- Computations 5's reference calls `power`; Validation 2 names the
  `hashed_password` argument. CRUD 3's references use the requested
  `default@example.com` and update both John and Jane in all alternatives.
- Twelve Transactions source IDs resolve through an explicit alias table.
  The source and dataset prompts must match. Historical run IDs are preserved,
  and the resolved dataset ID appears in the revised score.
- A versioned evaluator, `core-paper-v1.1`, implements the five Section 3
  metrics. It maps empty argument lists and unconstrained parameter patterns,
  checks all argument constraints/exclusions, walks the DFA, condenses legal
  self-loops, and compares against every loop-free accepting path. This avoids
  the historical path-search bug for partial paths.
- Unmatched calls, failed execution, and rejected world-tool attempts remain
  in the revised evaluation. Empty traces receive a path score; efficiency
  stays undefined when the paper's length condition is not met. Scores are
  never made available by dropping the offending calls.
- ARE's system prompt now gives a concrete string-valued reply example and
  explains that schema descriptions are not argument values. It also instructs
  the agent to execute the requested intermediate operations through tools.
  Malformed replies still fail validation; they are not coerced into text.
- Reply reporting distinguishes model-generated successful replies from ARE's
  automatic stop messages. Blind replacement of `True`/`False` inside model
  output was removed, preserving literal strings such as passwords.

Future live results save both `evaluation` (historical policy) and
`paper_evaluation` (revised policy), plus `agent_protocol_version`. The legacy
scorer and original dataset stay available for reproduction; the default
experiment entry point has not switched. A revised metric is not task-success
validation, and these changes do not establish improved model behavior.

## Dataset corrections

Six task DFAs failed structural validation. `dataset_repairs.py` applies these
repairs to a copy only for revised evaluation, records the repairs in output,
and checks that their expected original structure still matches:

| Task | Repair supported by prompt/reference/neighboring states |
|---|---|
| CRUD 3 | In G3, repeating Jane's update loops; John's update progresses. Removed the conflicting B self-loop. |
| Desktop Manager 6 | Corrected a G2 outgoing edge whose source was mislabeled G1. |
| Event Scheduler 4 | Replaced undefined F-prime with declared F in the read self-loop. |
| File Management 5 | Split concatenated `KK'` into the two declared read symbols K and K-prime. |
| Transactions 3 | Removed duplicate G6 and corrected G5's reread loop so B456 confirmation progresses. |
| Transactions 7 | Replaced a copied close-account DFA with the prompt/reference sequence: create D001, deposit 1000, apply 0.1 interest, withdraw 300; fixed its deposit and withdrawal patterns. |

Transactions 7 is a semantic benchmark correction, not just a spelling fix.
Keep this dataset revision identified when reporting experiments.

## Explicit adapter conventions

The paper defines harm by missing DFA transitions. For integration traces,
the revised evaluator additionally treats runtime/rejected calls as harmful
without advancing the task DFA. Unmatched argument patterns become distinct
harmful tokens rather than disappearing. These are conservative adapter
policies, not additional paper definitions; they are included in every result.

The paper sets Kendall order similarity to 0.5 with fewer than two matches.
For repeated symbols, this implementation matches occurrences in order.
Empty condensed paths have Prefix Criticality 1, HarmRate 0, and undefined
efficiency; a nonempty golden task still receives Path Correctness 0. A clean
harm score therefore does not imply completion. Condensation follows task-DFA
self-loops, not a guess based solely on a tool's READ annotation.

The evaluator supports up to 10,000 golden paths and reports an explicit
unscored reason if that bound is exceeded. It implements the five Section 3
metrics; the additional Section 4 HLR refinement is outside this repair.

## Verification and saved-run results

**87 tests pass**, including hand-calculated metric cases, exclusions and
wildcards, empty/partial/reversed paths, harmful attempts, automatic-stop
classification, corrected references, and cross-world ARE execution.

All 71 executable references now run without tool exceptions and match direct
source execution in order, arguments, returned values, and final state. Six
Web Browsing tasks still require missing HTML fixtures. Farm and Arm remain
absent from the repository.

Offline revised evaluation scores **71/71 ARE traces** and **51/51 Manos
traces**. It exactly reproduces all stored historical evaluator outputs as
well. No raw run or historical result was overwritten, and no paid runs were
made for these repairs.

For the full ARE batch, revised Path Correctness averages 0.7811; 45 paths
score 1.0. Efficiency is defined for 63/71 episodes. This includes the old
Navigation failures as penalties; rescoring does not rerun or repair history.
Model final replies remain **10/71** in those saved traces.

On the **same 51 tasks**, using revised metrics for both:

| Metric | Manos: GPT-4.1 nano | ARE: GPT-5 nano |
|---|---:|---:|
| Path Correctness | 0.7629 | 0.7252 |
| PC–KTC | 0.8052 | 0.7557 |
| Prefix Criticality | 0.7768 | 0.7137 |
| Harmful-Call Rate (lower is better) | 0.2960 | 0.2941 |
| Efficiency, defined episodes only | 0.8573 (48/51) | 0.8439 (44/51) |
| Paths scoring 1.0 | 31/51 | 29/51 |

The different models, budgets, prompts/context, and tool interfaces still
prevent causal attribution to ARE. New live runs would be needed to measure
the updated reply protocol and Navigation behavior.

## Offline commands

Use a fresh output filename:

```sh
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python -m are_integration.sweep --mode offline --output /tmp/core-are-repaired.json
.venv/bin/python -m are_integration.rescore runs/are/batches/2026-10-01_004043_100816Z_gpt-5-nano/summary.json --output /tmp/are-revised.json
.venv/bin/python -m are_integration.rescore runs/batches/2026-09-18_230912_247245Z_live/summary.json --output /tmp/manos-revised.json
.venv/bin/python -m function_calling.evaluation PATH_TO_RUN_JSON --policy paper --output /tmp/task-revised.json
```

Saved revised results and the per-task comparison are alongside the ARE batch
under ignored `runs/are/batches/2026-10-01_004043_100816Z_gpt-5-nano/`, named
`paper_evaluation_v1_1.json`, `manos_paper_evaluation_v1_1.json`, and
`paper_comparison_v1_1.json`.

A [compact per-scenario snapshot](results/are_gpt5nano_2026-10-01.json) is included
in Git for team review. It contains outcome counts, token usage, both scoring
policies, and the matched comparison, without raw model logs or local paths.
