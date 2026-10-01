# Week 1 live migration validation

The live validation uses GPT-5 nano in both ARE and native FarmAgent-derived
function calling: six model requests per episode, no completion-token cap,
30-second request timeouts, and no SDK retries. Workers run in separate
processes, with three concurrent workers and a 260-second process timeout.
Native execution has a six-tool-call cap and a 210-second cooperative timeout.
The six-request budget includes the final reply in both implementations.

The full stage runs 71 executable ARE scenarios and exactly the 51 tasks from
Manos's saved September baseline through native function calling. It reuses the
four smoke episodes and the native Computations transport check rather than
paying to run those again. This is a matched-model, matched-request-budget
comparison. System prompts, state observations, argument normalization, and
tool interfaces still differ; it does not isolate ARE as a causal factor.

## Additional repair found by live smoke

The first Navigation smoke showed an ARE 1.2 adapter limitation: tuple and
container annotations become `any` in the model's tool description. GPT-5 nano
sent a coordinate object to `is_within_bounds`, which accepts a pair, before
successfully executing the four movement operations. That attempted call is
preserved in the original smoke evidence.

Catalog tools now include their source JSON argument schema in the visible
function description. This communicates the two-integer array contract without
changing source signatures or converting invalid objects. New runs record
`core-are-json-v3`; v2 runs remain available. A regression check exercises the
actual ARE text adapter and the bounds operation.

Native `OpenAILLM` accepts `max_output_tokens=None`, omitting the token-cap
parameter. The default remains unchanged. Tests check the outgoing request
rather than relying on client metadata alone.

## Reproduction

Choose a new output directory. The selected environment file supplies only
`OPENAI_API_KEY`; the driver does not copy it into artifacts.

```sh
.venv/bin/python -m are_integration.validation_batch --stage smoke \
  --output-dir runs/are/validation/NEW_BATCH --key-file /path/to/CORE/.env
.venv/bin/python -m are_integration.validation_batch --stage full \
  --output-dir runs/are/validation/NEW_BATCH --key-file /path/to/CORE/.env
.venv/bin/python -m are_integration.validation_report \
  runs/are/validation/NEW_BATCH/full_summary.json --output /tmp/validation-report.json
```

The full stage requires a reviewed smoke with no runner/provider/tool errors.
Completed run artifacts can be resumed; choose a new directory after changing
runtime code. Raw model outputs and ARE exports stay under ignored `runs/are/`.
This validation also saves a source snapshot and SHA256 manifest locally, so
its code can be reproduced even if the branch changes later.

## Interpretation

Report model-generated successful replies separately from automatic stop
messages. A metric score or accepting DFA path is not independent task-success
validation. Only the dedicated Computations 1 and CRUD 2 scenarios have state
validators. Keep all partial paths and failures in the reported scores.

The six Web Browsing scenarios remain blocked by missing reproducible HTML
fixtures. They are counted as blocked and incur no model requests. Farm and
Arm implementations are still absent from this checkout.

## Completed results: 1 October 2026

All **122 episodes** were saved: **71 ARE** and **51 native**. Every saved
paper score was independently recomputed and matched its stored result.
All episodes respected the six-request limit and uncapped output setting.
The runtime source snapshot hashes were checked. **89 offline tests pass.**

[Compact per-task results](results/are_native_gpt5nano_2026-10-01.json) include
both the full ARE results and the same-task comparison, without raw logs or
credential files. The configuration records the base Git revision and the
source hashes because the live validation includes the v3 repair made after
that revision.

| Metric on the same 51 tasks | ARE, GPT-5 nano | Native, GPT-5 nano |
|---|---:|---:|
| Mean Path Correctness | 0.8231 | 0.8765 |
| Mean PC–KTC | 0.8347 | 0.8892 |
| Mean Prefix Criticality | 0.8565 | 0.9234 |
| Mean Harmful-Call Rate, lower is better | 0.1471 | 0.0961 |
| Mean Efficiency, defined episodes only | 0.9444 (45/51) | 0.9215 (45/51) |
| Paths scoring 1.0 | 36/51 | 35/51 |
| Accepting DFA paths | 36/51 | 40/51 |
| Model final replies | 41/51 | 39/51 |
| Provider failures | 0 | 0 |
| World-tool errors/rejections | 0 | 1 |

The native rejection was an extra `app_name` argument to the zero-argument
`print_application_history` tool in Desktop Manager 6. Validation rejected it
before execution; the model attempt remains in its trace and score.

Across **all 71 ARE tasks**, mean Path Correctness was **0.8497**, with **51**
paths scoring 1.0, **56** model replies, **12** automatic stops, and **3** episodes
without either type of delivered reply. There were **213** world-tool attempts
and **306** provider requests, with **zero** world-tool and provider errors.
The Computations 1 and CRUD 2 state validators both passed.

The model still made 34 action-format errors and 3 JSON-execution errors,
including invalid reply arguments. These are error-log events, not episode
counts. Some tasks stopped after using their six requests on optional checks
or incomplete paths. For example, Navigation 4 spent requests on valid bounds
checks and completed only the first two movements. Do not discard these cases
or interpret a delivered final message as proof that the user goal was met.

Raw evidence is local under
`runs/are/validation/2026-10-01_schema_v3_gpt5nano/`. The earlier smoke that
exposed the tuple-description problem is preserved under
`runs/are/validation/2026-10-01_repaired_gpt5nano/`.

The executable CORE-to-ARE migration has passed its Week 1 validation. Remaining
scope is the six missing Web Browsing fixtures and independent confirmation of
Manos's Week 1 work. These results do not establish better model performance or
complete task success across every migrated scenario.
