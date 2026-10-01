# ARE versus Manos's saved function-calling batch

This report preserves the historical scoring checkpoint. Subsequent code and
dataset repairs now score all saved traces under a separate revised policy;
see [verified repairs and revised comparison](ARE_REPAIRS.md). Historical
scores and model replies below are unchanged.

Compared offline on 1 October 2026. No additional model requests were made.

## What “legacy scored” means

Both batches use the same unchanged CORE `fc2symbol` mapper and `core.evaluate`
scorer through `function_calling.evaluation`. The mapper converts each executed
world tool call and its arguments into a symbol in the task's dataset alphabet.
The scorer evaluates the resulting sequence against the task's DFA. This is
the existing CORE path-correctness metric, not a new ARE metric or a final-answer
or world-state success validator. A 1.0 path score therefore does not require
a delivered final reply.

The adapter refuses to score if any recorded world call failed or cannot be
mapped. It also requires an exact dataset task ID and prompt. “Unscored” means
the score is unavailable with a recorded reason; it is not assigned zero.
Known mapper/path-search limitations are preserved. The other paper metrics
are not evaluated by this adapter.

For example, ARE's `computations_4` returned the correct numerical result 13.5,
but called only `calculate_average([7, 20])`: it performed the preceding
arithmetic internally. Manos's trace called subtract, divide, multiply, and
average. Their legacy path scores are respectively 0 and 1.0. This illustrates
why path scores and answer correctness are different measurements.

## Comparison on the same 51 tasks

Manos's saved batch is dated 18 September and uses GPT-4.1 nano. The new ARE
batch uses GPT-5 nano. The comparison includes all 48 original batch entries
and its three reused runs, each exactly once. All 51 stored task prompts match
the corresponding ARE prompts. ARE's 20 additional executable tasks are
excluded from this table.

| Measurement | Manos function calling | ARE text-action agent |
|---|---:|---:|
| Same tasks run | 51 | 51 |
| Model final replies | 45 | 8 |
| Automatic stop replies | Not counted as model replies | 20 |
| No delivered reply | 6 without a final response | 23 |
| Paths that can be legacy-scored | 30 | 26 |
| Paths scoring 1.0 | 24 | 18 |
| Unscored paths | 21 | 25 |
| World tool calls | 210 | 163 |
| World tool exceptions | 33 | 23 |
| Model requests | 255 | 252 |
| Input tokens | 230,475 | 441,856 |
| Completion tokens | 5,766 | 293,203 |

All world tool exceptions in both batches were in Navigation. The lower ARE
error count is not evidence that the source defect is fixed. Failed calls
remain unscored; the ARE batch still reproduces the `grid_size` defect.

Only **24 tasks are scored in both**. On that same subset:

- Mean legacy path score: Manos **0.9278**, ARE **0.8287**.
- Score 1.0: Manos **21/24**, ARE **18/24**.
- ARE scores higher on two tasks, Manos on four, and 18 tie.

| Task with a changed score | Manos | ARE |
|---|---:|---:|
| computations_4 | 1.0 | 0 |
| computations_5 | 1.0 | 0 |
| desktop_manager_6 | 0.6 | 1.0 |
| legal_compliance_3 | 0.3333 | 0.5 |
| legal_compliance_5 | 1.0 | 0.4545 |
| validation_2 | 1.0 | 0.6 |

Twenty of the 51 matched traces have identical world tool names, arguments,
and execution statuses, even where final-reply behavior differs.

## Interpretation and next comparison

This exploratory ARE configuration delivers far fewer model replies and has
lower path scores on the jointly scored subset. It does not isolate the effect
of ARE: the model, prompts/context, tool interface, normalization behavior,
and request budgets differ.

Manos's artifacts record native function calling, argument normalization,
world-state observations, temperature 0, a 512-token response cap, and limits
of 12 iterations/tool calls and 120 seconds. ARE uses text-action JSON,
strict reply argument types, at most six requests, no completion-token cap,
and a 30-second timeout per request. GPT-5 nano's completion totals include
reasoning tokens. All ARE runs preserve raw exports and rejected attempts.
Automatic ARE stop messages are excluded from model replies by checking the
reply arguments against recorded model-generated Action JSON.

A controlled follow-up should first fix the reply-format issue, then use the
same model, task set, request/timeout/output budgets, and documented context
policy for both runners. Report path scores, reply delivery, and independently
validated task success separately. Additional paid runs were not launched
as part of this comparison.

## Evidence

- [Manos batch summary](../runs/batches/2026-09-18_230912_247245Z_live/summary.json)
- [Manos saved evaluation](../runs/batches/2026-09-18_230912_247245Z_live/evaluation.json)
- [ARE batch summary](../runs/are/batches/2026-10-01_004043_100816Z_gpt-5-nano/summary.json)
- [Per-task comparison](../runs/are/batches/2026-10-01_004043_100816Z_gpt-5-nano/manos_comparison.json)

The comparison JSON links both raw run artifacts for every shared task and
preserves each evaluator's issues. ARE evidence remains in the ignored local
`runs/are/` directory.
