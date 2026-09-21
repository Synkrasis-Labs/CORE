# CORE Week 1 - session handoff

Updated 21 September 2026. Start here in a new session.

## Goal and scope

Manos: port CORE function calling using FarmAgent, then revamp scenarios.
Siskos: separate ARE migration. This supports the original CORE paper extension,
not CORE 2.0. Preserve metric definitions during the runtime port.

## Agreed steps

1. **Completed:** Preserve original CORE on a separate working branch.
2. **Completed:** Trace FarmAgent function calling and dependencies.
3. **Completed:** Identify CORE replacement points.
4. **Completed:** Port the runtime and test it offline.
5. **Completed:** Connect Computations and check scripted and live execution.
6. **Implemented with limitations:** Feed saved world traces to the existing
   evaluator. 30 of 51 live traces scored; 21 unscored with reasons.
7. **Coverage performed; gaps remain:** Live nano sweep of all 51 runnable tasks
   across 11 paper worlds. 26 source tasks deferred; existing failures documented.
   Offline checks cover execution errors, recovery, state snapshots, and resets.
8. **In progress:** Shared opt-in runner and usage documentation exist. The
   original/default runner remains unchanged pending review with Manos.

## Verified results

- 51 offline software tests passed at the last code checkpoint (19 September).
- Live GPT-4.1 nano: 51 tasks, 45 final responses, 6 call-limit stops.
  All 33 tool exceptions occurred in Navigation. No fatal provider failures.
- Legacy path evaluation: 30 scored (24 at 1.0, 6 lower); 21 unscored because of
  mapping limitations or execution errors. These are not task-success counts.
- The adapter preserves the original mapper and scorer. No new API calls were
  needed for scoring; source run files were preserved.
- No controlled comparison yet establishes improvement over original CORE.
  All five paper metrics have not been reproduced; that is separate work.

See [coverage and findings](docs/PAPER_WORLD_COVERAGE.md) for scope and limitations.
Run evidence is included under `runs/` for team review:

- Live: `runs/batches/2026-09-18_230912_247245Z_live/summary.json`
- Scores and reasons: `runs/batches/2026-09-18_230912_247245Z_live/evaluation.json`
- Offline references: `runs/batches/2026-09-18_231056_213804Z_offline/summary.json`

## Files and commands

- `function_calling/agent.py`: model/tool execution loop.
- `function_calling/experiments.py`: shared opt-in experiment runner.
- `function_calling/evaluation.py`: saved-trace adapter and batch scoring.
- `evaluate.py`: original action-to-symbol mapping; `core.py`: original path scorer.
- `tests/`: offline checks; [runner guide](docs/SHARED_RUNNER.md): usage.
- [Port guide](docs/FUNCTION_CALLING_PORT.md): implementation and milestone history.
- [FarmAgent trace](docs/FARMAGENT_FUNCTION_CALLING_TRACE.md) and
  [replacement points](docs/CORE_REPLACEMENT_POINTS.md): source analysis.

From CORE with the existing parent virtual environment:

```powershell
..\.venv\Scripts\python.exe -B -m unittest discover -s tests -p 'test_*.py' -q
..\.venv\Scripts\python.exe -B -m function_calling.experiments
..\.venv\Scripts\python.exe -B -m function_calling.evaluation runs/batches/2026-09-18_230912_247245Z_live/summary.json --batch --output runs/batches/2026-09-18_230912_247245Z_live/evaluation_review.json
```

These commands make no API calls. Scoring refuses to overwrite existing output.
A new checkout needs a Python environment and `requirements-experiments.txt`;
the saved artifacts under `runs/` allow this batch to be rescored without API calls.

## Next session

1. Read this handoff and the coverage report; inspect local Git changes.
2. Review outstanding execution/scoring limitations with Manos and propose the
   next change before implementing it. Do not assume the default switch is approved.
3. Keep existing scenario defects (setup, IDs, fixtures, Navigation) for the
   scenario-revamp stage. Evaluator fixes require a separate reviewed decision.

The evaluator accepts registered schema-v1 worlds and up to 12 tool calls.
Zero-argument calls can disappear in the original mapper; our adapter instead
leaves the entire trace unscored. Argument matching and incomplete-path scoring
also have known limitations. Do not reinterpret ordinary False/None tool results
as exceptions, or runtime completion as task success.

## Branch and publishing

Branch: https://github.com/Synkrasis-Labs/CORE/tree/manos/farmagent-function-calling

Publishing target is this feature branch. Main and the original runner remain
unchanged. `.env`, `.venv/`, and local
`PUSH_BRANCH_INSTRUCTIONS.txt` are ignored. Include new code, tests, requirements,
documentation, and `runs/` when committing. Runs are included for now; cleanup
is deferred. Do not add credentials.
