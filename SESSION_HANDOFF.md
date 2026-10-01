# CORE Week 1 — ARE integration handoff

Updated 1 October 2026. Current branch: `siskos/core-are-integration`.

## Goal and current status

Siskos's Week 1 task is migration of the original CORE worlds to Meta ARE.
Manos's separate task is robust FarmAgent-derived native function calling and
scenario expansion. This work extends the original CORE paper, not CORE 2.0.

The executable ARE migration is implemented and live-validated. All 77 source
tasks are registered across 13 repository worlds; 71 execute, and six Web
Browsing tasks remain blocked by missing HTML fixtures. Farm and Arm source
implementations are absent. The original/default runner and historical scoring
policy remain available.

Read the [live validation report](docs/ARE_WEEK1_VALIDATION.md) and
[verified repairs](docs/ARE_REPAIRS.md). The authoritative paper is the user's
`2509.20998v1 (2).pdf`; its hash and evaluation conventions are recorded there.

## Verified results

- 89 offline tests pass. All 71 executable references match direct CORE
  execution in calls, results, and final state without tool exceptions.
- Fresh GPT-5 nano live validation saved 71 ARE episodes with zero world-tool
  or provider errors. Model replies: 56/71. Mean Path Correctness: 0.8497.
- A new native GPT-5 nano comparison covers the same 51 tasks as the saved
  Manos baseline. Both drivers use six model requests, no output-token cap,
  30-second provider timeouts, and no SDK retries.
- On these 51 tasks, mean Path Correctness is 0.8231 ARE versus 0.8765 native;
  model replies are 41/51 versus 39/51. Native has one rejected extra argument,
  with no provider failures. Prompts, state exposure, and tool interfaces
  differ, so this is not an interface-only causal comparison.
- All 122 stored revised scores were recomputed and matched. The revised
  policy is `core-paper-v1.1`; the ARE protocol is `core-are-json-v3`.
- Independent state validators passed for Computations 1 and CRUD 2.
  Generic scenarios have no independent task-success validator. Scores,
  runtime coverage, model replies, and automatic stops are distinct measures.

[Per-scenario results](docs/results/are_native_gpt5nano_2026-10-01.json) are
tracked for team review. Raw traces, source snapshots, and the source-hash
manifest remain local under ignored
`runs/are/validation/2026-10-01_schema_v3_gpt5nano/`.

The older Manos GPT-4.1 nano baseline remains at
`runs/batches/2026-09-18_230912_247245Z_live/summary.json`.
[Historical coverage](docs/PAPER_WORLD_COVERAGE.md) and the
[original comparison](docs/ARE_MANOS_COMPARISON.md) preserve that checkpoint.

## Commands and next work

Read the live validation report for reproduction commands. Live commands are
paid API experiments; imports, `--help`, offline tests, and saved-run scoring
make no model requests.

```sh
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python -m are_integration.sweep --mode offline --output /tmp/NEW_REFERENCE_REPORT.json
```

Next: supply reproducible Web Browsing fixtures and confirm Manos's Week 1
status. Week 2 adds models and related-work implementations; Week 3 collects
comparison metrics and aligns Farm-FOS. Do not equate a successful reply or
paper score with independent task success. Keep the original/default runner
unchanged unless explicitly requested.

## Branch and publishing

Use `siskos/core-are-integration` for this ARE work, not Manos's separate branch
or main. Publish code, tests, documentation, and compact results. Keep `.env`,
`.venv/`, raw ARE logs, local PDFs, and credentials out of Git.
