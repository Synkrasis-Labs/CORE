# Shared function-calling runner

This is an opt-in execution path. `run_experiments.py` and `baseline_agent.py`
remain unchanged. No default switch or branch merge has been performed.

Scope follows [CORE paper Table 2 and Appendix A](https://arxiv.org/html/2509.20998v1):
Automation, Communication, Computations, CRUD, Desktop Manager, Events Scheduler,
File Management, Legal Compliance, Navigation, Transactions, Validation,
Web Browsing, Writing. Configurations is excluded. Agentic Farm and Agentic Arm
are in the paper but their world implementations are absent from this checkout.

## Commands

From CORE, using the existing environment:

```powershell
..\.venv\Scripts\python.exe -m pip install -r requirements-experiments.txt
..\.venv\Scripts\python.exe -B -m function_calling.experiments
..\.venv\Scripts\python.exe -B -m function_calling.experiments --mode offline
..\.venv\Scripts\python.exe -B -m function_calling.experiments --mode live
```

Default mode only inventories tasks; `offline` executes the first supplied
reference sequence where it can be parsed. This checks execution, not reference
correctness or model capability. `live` makes paid requests using the saved
`CORE/.env` key and GPT-4.1 nano. Use repeated `--world` or `--task` options to
select a subset, and `--model` to change the model. Other models may need different
request options; only nano has been validated here.

Each task uses a fresh world and agent, up to 12 requests/tools, 512 output tokens
per request, a 30-second request timeout, a cooperative 120-second task timeout,
and no SDK retries. `--max-requests` accepts 1–20. Each batch stops on a fatal
runner/provider failure. Ordinary tool errors remain recorded and the agent may
recover. Setup-dependent tasks are deferred until scenario revamp.

## Outputs and interpretation

Task artifacts: `runs/<task>/<UTC-timestamp>_<model>/run.json`.
Batch inventory and incremental results: `runs/batches/<timestamp>_<mode>/summary.json`.
`--skip-completed-from <summary.json>` reuses completed entries from an earlier
batch in the same mode; inspect its model/configuration before using this option.

`completed` means the agent returned a final response. It does **not** mean the
task was accomplished. `task_success` and `evaluation` remain null. Tool errors,
domain responses such as False/not-found, state changes, and missed requested
actions need review. No paper metrics are computed by this runner.

The shared adapter preserves the legacy public-method tool surface, including
helpers. Navigation's `llm-tool` wrappers are unwrapped to their original Python
methods for binding/schema generation. A fixed homogeneous tuple input is encoded
as a length-constrained JSON array (Navigation unpacks its coordinate pair).
Earlier focused smoke scripts retain their smaller explicit tool allowlists.

## Existing scenario issues deferred to revamp

- Setup: the original runner reads `functions`, while tasks use `setup_functions`.
  Tasks with nonempty setup are explicitly deferred, as agreed.
- Transactions: source IDs use `transaction_*`, dataset IDs `transactions_*`.
  Both sides are listed; no heuristic join or scenario rewrite is performed.
- Web Browsing: required local HTML fixtures are absent. This filesystem-backed
  world is deferred rather than exposing arbitrary local files to the model.
- Navigation: `is_within_bounds` reads `world_state['grid_size']`, but construction
  stores it in `self.grid_size`. Movement raises KeyError; preserved for revamp.
- `computations_5`: its reference calls `powers`, but the method is `power`.
- `validation_2`: its reference has a positional argument after a keyword argument.
  These two reference probes cannot run; live requests can still use valid tools.

Paper-metric reproduction remains unfinished. The saved-trace legacy scoring
adapter is not a verified implementation of all five paper metrics.

Completed sweep: [paper-world coverage and reviewed findings](PAPER_WORLD_COVERAGE.md).

## Evaluate saved runs without API calls

```powershell
python -m function_calling.evaluation PATH_TO_RUN_JSON
python -m function_calling.evaluation PATH_TO_BATCH_SUMMARY_JSON --batch
```

Both write `evaluation.json` beside the input; use `--output` for another path.
Existing output is not overwritten. Batch mode includes reused runs. The adapter
accepts registered worlds with up to 12 tool calls; incompatible traces remain
unscored with reasons. Source run files retain their original null evaluation fields.
Raw runs are included under `runs/` for now; see the coverage report for the latest results.
